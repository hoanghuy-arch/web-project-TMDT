"""Giao thức VNPay (phiên bản 2.1.0): dựng URL thanh toán, ký và xác thực chữ ký HMAC-SHA512, đọc kết quả.
Thuần Python (không truy cập DB/Flask) nên kiểm thử được độc lập.

Cách ký (theo tài liệu và mã mẫu của VNPay): lấy các tham số vnp_* (trừ vnp_SecureHash, vnp_SecureHashType),
sắp xếp theo tên, nối thành `khóa=giá_trị_đã_mã_hóa_URL` bằng '&', rồi HMAC-SHA512 với khóa bí mật."""
import hashlib
import hmac
import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote_plus

VERSION = "2.1.0"
_VN_OFFSET = timedelta(hours=7)
_IGNORED = ("vnp_SecureHash", "vnp_SecureHashType")

RESPONSE_MESSAGES = {
    "00": "Giao dịch thành công",
    "07": "Giao dịch bị nghi ngờ gian lận",
    "09": "Thẻ/tài khoản chưa đăng ký dịch vụ Internet Banking",
    "10": "Xác thực thông tin thẻ/tài khoản không đúng quá 3 lần",
    "11": "Đã hết thời gian chờ thanh toán",
    "12": "Thẻ/tài khoản bị khóa",
    "13": "Nhập sai mật khẩu xác thực giao dịch (OTP)",
    "24": "Khách hàng đã hủy giao dịch",
    "51": "Tài khoản không đủ số dư",
    "65": "Tài khoản vượt hạn mức giao dịch trong ngày",
    "75": "Ngân hàng đang bảo trì",
    "79": "Nhập sai mật khẩu thanh toán quá số lần quy định",
    "99": "Lỗi khác",
}


def describe_response(code):
    return RESPONSE_MESSAGES.get(code, f"Giao dịch không thành công (mã {code})")


def _hash_data(params):
    items = sorted((k, v) for k, v in params.items() if k.startswith("vnp_") and k not in _IGNORED)
    return "&".join(f"{k}={quote_plus(str(v))}" for k, v in items)


def sign(params, secret):
    return hmac.new(secret.encode("utf-8"), _hash_data(params).encode("utf-8"), hashlib.sha512).hexdigest()


def verify(params, secret):
    """Đúng khi có chữ ký và chữ ký khớp. So sánh thời gian hằng số để chống tấn công dò thời gian."""
    received = params.get("vnp_SecureHash") or ""
    if not received or not secret:
        return False
    return hmac.compare_digest(received.lower(), sign(params, secret).lower())


def vn_timestamp(dt_utc):
    """Thời điểm UTC -> chuỗi yyyyMMddHHmmss theo giờ Việt Nam (định dạng VNPay yêu cầu)."""
    return (dt_utc + _VN_OFFSET).strftime("%Y%m%d%H%M%S")


def ascii_text(text, limit=255):
    """VNPay khuyến nghị nội dung đơn hàng không dấu và không ký tự đặc biệt."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9 _.\-]", "", text)[:limit].strip()


def build_payment_url(base_url, secret, *, tmn_code, txn_ref, amount, order_info, return_url, ip_addr,
                      create_date, expire_date=None, locale="vn", order_type="other"):
    """URL chuyển khách sang cổng thanh toán. amount: số tiền VND (VNPay yêu cầu nhân 100)."""
    params = {
        "vnp_Version": VERSION, "vnp_Command": "pay", "vnp_TmnCode": tmn_code,
        "vnp_Amount": str(int(amount) * 100), "vnp_CurrCode": "VND", "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": order_info, "vnp_OrderType": order_type, "vnp_Locale": locale,
        "vnp_ReturnUrl": return_url, "vnp_IpAddr": ip_addr, "vnp_CreateDate": create_date,
    }
    if expire_date:
        params["vnp_ExpireDate"] = expire_date
    return f"{base_url}?{_hash_data(params)}&vnp_SecureHash={sign(params, secret)}"


@dataclass
class VNPayResult:
    txn_ref: str
    amount: int                  # VND; None nếu vnp_Amount không hợp lệ
    response_code: str
    transaction_status: str
    transaction_no: str
    bank_code: str
    pay_date: str

    @property
    def success(self):
        """Thành công khi mã phản hồi là 00 và (nếu cổng có gửi) trạng thái giao dịch cũng là 00."""
        return self.response_code == "00" and self.transaction_status in ("00", "")


def parse_result(params):
    try:
        raw = int(params.get("vnp_Amount", ""))
    except (TypeError, ValueError):
        raw = None
    amount = raw // 100 if raw is not None and raw >= 0 and raw % 100 == 0 else None
    return VNPayResult(
        txn_ref=params.get("vnp_TxnRef", ""), amount=amount,
        response_code=params.get("vnp_ResponseCode", ""), transaction_status=params.get("vnp_TransactionStatus", ""),
        transaction_no=params.get("vnp_TransactionNo", ""), bank_code=params.get("vnp_BankCode", ""),
        pay_date=params.get("vnp_PayDate", ""))


def build_result_params(secret, *, tmn_code, txn_ref, amount, response_code, pay_date, order_info=""):
    """Tạo bộ tham số kết quả đã ký giống cổng thật (dùng cho cổng giả lập và kiểm thử)."""
    ok = response_code == "00"
    params = {
        "vnp_Amount": str(int(amount) * 100), "vnp_BankCode": "NCB",
        "vnp_BankTranNo": f"VNP{random.randint(10**7, 10**8 - 1)}" if ok else "",
        "vnp_CardType": "ATM", "vnp_OrderInfo": order_info, "vnp_PayDate": pay_date,
        "vnp_ResponseCode": response_code, "vnp_TmnCode": tmn_code,
        "vnp_TransactionNo": str(random.randint(10**7, 10**8 - 1)) if ok else "0",
        "vnp_TransactionStatus": "00" if ok else "02", "vnp_TxnRef": txn_ref,
    }
    params["vnp_SecureHash"] = sign(params, secret)
    return params
