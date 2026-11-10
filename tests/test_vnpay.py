"""Kiểm thử giao thức VNPay (thuần Python): ký, xác thực, dựng URL, đọc kết quả."""
import hashlib
import hmac
import urllib.parse
from datetime import datetime

import pytest

from app.services import vnpay

SECRET = "SECRETKEY123"
PARAMS = {"vnp_Amount": "28000000", "vnp_TxnRef": "SZ261107ABCDEF1A2B3C", "vnp_OrderInfo": "Thanh toan don hang SZ261107ABCDEF",
          "vnp_TmnCode": "TMN001", "vnp_ReturnUrl": "http://127.0.0.1:5000/payment/vnpay/return?x=1&y=a b",
          "vnp_ResponseCode": "00"}


def reference_sign(data, secret):
    """Cài đặt độc lập theo đúng mã mẫu của VNPay để đối chiếu."""
    s, seq = "", 0
    for key, val in sorted(data.items()):
        if str(key).startswith("vnp_"):
            if seq == 1:
                s += "&" + str(key) + "=" + urllib.parse.quote_plus(str(val))
            else:
                seq = 1
                s = str(key) + "=" + urllib.parse.quote_plus(str(val))
    return hmac.new(secret.encode(), s.encode(), hashlib.sha512).hexdigest()


def test_sign_matches_reference_implementation():
    assert vnpay.sign(PARAMS, SECRET) == reference_sign(PARAMS, SECRET)
    assert len(vnpay.sign(PARAMS, SECRET)) == 128


def test_verify_accepts_valid_signature():
    signed = dict(PARAMS, vnp_SecureHash=vnpay.sign(PARAMS, SECRET))
    assert vnpay.verify(signed, SECRET)
    assert vnpay.verify(dict(signed, vnp_SecureHash=signed["vnp_SecureHash"].upper()), SECRET)
    assert vnpay.verify(dict(signed, vnp_SecureHashType="HmacSHA512"), SECRET)
    assert vnpay.verify(dict(signed, khong_phai_vnp="bỏ qua"), SECRET)


@pytest.mark.parametrize("tamper", [dict(vnp_Amount="100"), dict(vnp_ResponseCode="24"), dict(vnp_TxnRef="X"),
                                    dict(vnp_SecureHash="")])
def test_verify_rejects_tampering(tamper):
    signed = dict(PARAMS, vnp_SecureHash=vnpay.sign(PARAMS, SECRET))
    assert not vnpay.verify(dict(signed, **tamper), SECRET)


def test_verify_rejects_wrong_or_missing_key_and_signature():
    signed = dict(PARAMS, vnp_SecureHash=vnpay.sign(PARAMS, SECRET))
    assert not vnpay.verify(signed, "SAIKHOA") and not vnpay.verify(signed, "")
    assert not vnpay.verify(PARAMS, SECRET) and not vnpay.verify({}, SECRET)


def test_build_payment_url():
    url = vnpay.build_payment_url(
        "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html", SECRET, tmn_code="TMN001", txn_ref="REF1", amount=280000,
        order_info=vnpay.ascii_text("Thanh toán đơn hàng SZ261107ABCDEF"), return_url="http://x/return",
        ip_addr="127.0.0.1", create_date="20261107120000", expire_date="20261107121500")
    base, _, query = url.partition("?")
    q = dict(urllib.parse.parse_qsl(query))
    assert base.endswith("vpcpay.html") and q["vnp_Amount"] == "28000000" and q["vnp_CurrCode"] == "VND"
    assert q["vnp_Version"] == "2.1.0" and q["vnp_Command"] == "pay" and q["vnp_ExpireDate"] == "20261107121500"
    assert q["vnp_OrderInfo"] == "Thanh toan don hang SZ261107ABCDEF"
    assert vnpay.verify(q, SECRET)


def test_expire_date_is_optional():
    url = vnpay.build_payment_url("u", SECRET, tmn_code="T", txn_ref="R", amount=1, order_info="a", return_url="r",
                                  ip_addr="i", create_date="d")
    assert "vnp_ExpireDate" not in dict(urllib.parse.parse_qsl(url.partition("?")[2]))


def test_helpers():
    assert vnpay.vn_timestamp(datetime(2026, 11, 6, 20, 30, 5)) == "20261107033005"          # UTC -> giờ Việt Nam
    assert vnpay.ascii_text("Thanh toán đơn hàng Đỗ Văn Ấn #1 <script>") == "Thanh toan don hang Do Van An 1 script"
    assert len(vnpay.ascii_text("a" * 500)) == 255 and vnpay.ascii_text(None) == ""
    assert "hủy" in vnpay.describe_response("24") and "mã 88" in vnpay.describe_response("88")


def test_parse_result_success_and_failure():
    ok = vnpay.parse_result({"vnp_Amount": "28000000", "vnp_ResponseCode": "00", "vnp_TransactionStatus": "00",
                             "vnp_TxnRef": "R", "vnp_TransactionNo": "123"})
    assert ok.success and ok.amount == 280000 and ok.txn_ref == "R" and ok.transaction_no == "123"
    assert not vnpay.parse_result({"vnp_Amount": "1", "vnp_ResponseCode": "00", "vnp_TransactionStatus": "02"}).success
    assert vnpay.parse_result({"vnp_Amount": "100", "vnp_ResponseCode": "00"}).success
    assert not vnpay.parse_result({"vnp_Amount": "100", "vnp_ResponseCode": "24", "vnp_TransactionStatus": "02"}).success


@pytest.mark.parametrize("bad", ["", "abc", "-100", "28000050", None])
def test_parse_result_invalid_amount(bad):
    assert vnpay.parse_result({"vnp_Amount": bad}).amount is None


def test_build_result_params_roundtrip():
    ok = vnpay.build_result_params(SECRET, tmn_code="T", txn_ref="REF", amount=1000, response_code="00", pay_date="20261107")
    bad = vnpay.build_result_params(SECRET, tmn_code="T", txn_ref="REF", amount=1000, response_code="24", pay_date="20261107")
    assert vnpay.verify(ok, SECRET) and vnpay.verify(bad, SECRET)
    assert vnpay.parse_result(ok).success and not vnpay.parse_result(bad).success
    assert vnpay.parse_result(ok).amount == 1000 and ok["vnp_TransactionStatus"] == "00" and bad["vnp_TransactionStatus"] == "02"
