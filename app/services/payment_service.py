"""Thanh toán online qua VNPay (FR-KH10, FR-HT01, R23) và cổng giả lập khi chưa có tài khoản sandbox.

Nguyên tắc an toàn:
- Chỉ ghi nhận thanh toán khi CHỮ KÝ hợp lệ và SỐ TIỀN khớp với số tiền hệ thống đã tạo cho giao dịch đó.
- Kết quả tới từ hai đường (IPN từ máy chủ VNPay và Return từ trình duyệt khách) có thể trùng nhau hoặc chạy đồng
  thời: việc chuyển Đang chờ/Thất bại -> Đã thanh toán là một câu UPDATE có điều kiện nên chỉ một đường thành công.
- Không lưu thông tin thẻ; hệ thống không bao giờ nhìn thấy số thẻ."""
import hashlib
from dataclasses import dataclass
from decimal import Decimal

from flask import current_app, url_for
from sqlalchemy import select, update

from app.constants import OrderStatus, PaymentMethod, PaymentStatus
from app.extensions import db
from app.models import Payment
from app.models.base import utcnow
from app.services import audit_service, order_service, vnpay
from app.utils.codes import generate_txn_ref

MOCK_TMN_CODE = "MOCKTMN1"


class PaymentStartError(Exception):
    """Không thể bắt đầu thanh toán (thông báo tiếng Việt hiển thị cho khách)."""


@dataclass
class Outcome:
    code: str                    # mã trả cho VNPay (IPN): 00, 01, 02, 04, 97
    message: str
    kind: str                    # paid | already_paid | failed | late | duplicate | invalid | not_found | amount_mismatch
    order: object = None
    payment: object = None
    detail: str = ""             # mô tả lý do khi giao dịch thất bại


# ------------------------------------------------------------------ cấu hình cổng
def gateway_mode():
    """'vnpay' khi đã cấu hình khóa thật; 'mock' khi cho phép cổng giả lập; None nếu không có thanh toán online."""
    cfg = current_app.config
    if cfg.get("VNPAY_TMN_CODE") and cfg.get("VNPAY_HASH_SECRET"):
        return "vnpay"
    if cfg.get("PAYMENT_MOCK_ENABLED"):
        return "mock"
    return None


def is_online_enabled():
    return gateway_mode() is not None


def secret():
    cfg = current_app.config
    if gateway_mode() == "vnpay":
        return cfg["VNPAY_HASH_SECRET"]
    # Khóa của cổng giả lập: suy ra từ SECRET_KEY của ứng dụng, không bao giờ trùng khóa thật
    return hashlib.sha256(f"mock-vnpay:{cfg['SECRET_KEY']}".encode("utf-8")).hexdigest()


def tmn_code():
    return current_app.config["VNPAY_TMN_CODE"] if gateway_mode() == "vnpay" else MOCK_TMN_CODE


def _gateway_url():
    if gateway_mode() == "vnpay":
        return current_app.config["VNPAY_URL"]
    return url_for("payment.mock_pay", _external=True)


def _return_url():
    configured = current_app.config.get("VNPAY_RETURN_URL")
    if gateway_mode() == "vnpay" and configured:
        return configured
    return url_for("payment.vnpay_return", _external=True)


# ------------------------------------------------------------------ bắt đầu thanh toán
def start_payment(order, ip_addr):
    """Trả về URL cổng thanh toán để chuyển khách sang.
    Lần thanh toán trước đã thất bại -> tạo lần thử mới (mã tham chiếu mới); còn đang chờ -> dùng lại."""
    if gateway_mode() is None:
        raise PaymentStartError("Thanh toán online hiện chưa khả dụng.")
    db.session.refresh(order)
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise PaymentStartError("Đơn hàng này không ở trạng thái chờ thanh toán.")
    deadline = order_service.payment_deadline(order)
    if deadline <= utcnow():
        raise PaymentStartError("Đơn hàng đã quá hạn thanh toán và sẽ được hủy tự động.")
    payment = order.latest_payment
    if payment is None or payment.method != PaymentMethod.VNPAY:
        raise PaymentStartError("Đơn hàng này không dùng thanh toán online.")

    if payment.status == PaymentStatus.FAILED:
        payment = Payment(sales_order_id=order.id, method=PaymentMethod.VNPAY, status=PaymentStatus.PENDING,
                          amount=order.total_amount, gateway_txn_ref=generate_txn_ref(order.order_code))
        db.session.add(payment)
        db.session.commit()
    elif payment.status != PaymentStatus.PENDING:
        raise PaymentStartError("Đơn hàng này không thể thanh toán lúc này.")

    return vnpay.build_payment_url(
        _gateway_url(), secret(), tmn_code=tmn_code(), txn_ref=payment.gateway_txn_ref, amount=payment.amount,
        order_info=vnpay.ascii_text(f"Thanh toan don hang {order.order_code}"), return_url=_return_url(),
        ip_addr=ip_addr or "127.0.0.1", create_date=vnpay.vn_timestamp(utcnow()),
        expire_date=vnpay.vn_timestamp(deadline))


# ------------------------------------------------------------------ xử lý kết quả
def process_gateway_result(params):
    """Xử lý kết quả thanh toán từ IPN hoặc Return. An toàn khi gọi lặp hoặc đồng thời."""
    if not vnpay.verify(params, secret()):
        current_app.logger.warning("Kết quả thanh toán sai chữ ký (txn_ref=%s)", params.get("vnp_TxnRef"))
        return Outcome("97", "Invalid signature", "invalid")

    result = vnpay.parse_result(params)
    payment = db.session.scalar(select(Payment).where(Payment.gateway_txn_ref == result.txn_ref)) if result.txn_ref else None
    if payment is None:
        return Outcome("01", "Order not found", "not_found")
    order = payment.order

    if result.amount is None or Decimal(result.amount) != Decimal(payment.amount):
        audit_service.record("payment.amount_mismatch", "payment", payment.id,
                             {"expected_amount": int(payment.amount)},
                             {"received_vnp_amount": params.get("vnp_Amount"), "response_code": result.response_code,
                              "transaction_no": result.transaction_no})
        db.session.commit()
        current_app.logger.error("Số tiền thanh toán không khớp: payment=%s mong đợi=%s nhận=%s",
                                 payment.id, payment.amount, params.get("vnp_Amount"))
        return Outcome("04", "Invalid amount", "amount_mismatch", order, payment)

    if payment.status == PaymentStatus.PAID:
        return Outcome("02", "Order already confirmed", "already_paid", order, payment)

    try:
        if result.success:
            return _record_success(payment, order, result)
        return _record_failure(payment, order, result)
    except Exception:
        db.session.rollback()
        raise


def _record_failure(payment, order, result):
    """Lần thanh toán này thất bại. Đơn vẫn chờ thanh toán để khách thử lại cho đến hết hạn (R23)."""
    db.session.execute(
        update(Payment).where(Payment.id == payment.id, Payment.status == PaymentStatus.PENDING)
        .values(status=PaymentStatus.FAILED).execution_options(synchronize_session=False))
    db.session.commit()
    return Outcome("00", "Confirm Success", "failed", order, payment, detail=vnpay.describe_response(result.response_code))


def _record_success(payment, order, result):
    previous = payment.status
    won = db.session.execute(
        update(Payment).where(Payment.id == payment.id, Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.FAILED]))
        .values(status=PaymentStatus.PAID, paid_at=utcnow(), amount=result.amount)
        .execution_options(synchronize_session=False))
    if won.rowcount != 1:                                  # luồng khác (IPN/Return) vừa ghi nhận xong
        db.session.rollback()
        return Outcome("02", "Order already confirmed", "already_paid", order, payment)
    db.session.expire(payment)

    audit_service.record("payment.paid", "payment", payment.id, {"status": previous},
                         {"status": PaymentStatus.PAID, "amount": result.amount, "transaction_no": result.transaction_no,
                          "bank": result.bank_code, "pay_date": result.pay_date})

    db.session.refresh(order)
    if order.status == OrderStatus.PENDING_PAYMENT:
        order_service.change_status(order, OrderStatus.PENDING_CONFIRM, None, "Thanh toán online thành công")
        kind = "paid"
    elif order.status == OrderStatus.CANCELLED:
        # Tiền về sau khi đơn đã bị hủy (quá hạn). Hàng đã được nhả nên không khôi phục đơn: cần hoàn tiền thủ công.
        audit_service.record("payment.late_after_cancel", "sales_order", order.id, {"status": order.status},
                             {"payment_id": payment.id, "amount": result.amount, "action": "cần hoàn tiền cho khách"})
        kind = "late"
    else:
        # Đơn đã được thanh toán bằng giao dịch khác: khoản này là thu trùng
        audit_service.record("payment.duplicate", "sales_order", order.id, {"status": order.status},
                             {"payment_id": payment.id, "amount": result.amount, "action": "cần hoàn tiền khoản thu trùng"})
        kind = "duplicate"
    db.session.commit()

    if kind == "paid":
        order_service.notify_order_placed(order)    # gửi email xác nhận đơn sau khi đã thanh toán
    return Outcome("00", "Confirm Success", kind, order, payment)
