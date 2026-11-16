"""Xử lý đơn của nhân viên: xác nhận, đóng gói, bàn giao vận chuyển, giao thành công, ghi sự cố (FR-NV02..04, FR-HT03).
Mỗi thao tác là MỘT transaction: chuyển trạng thái (nguyên tử, có kiểm tra theo sơ đồ), cập nhật dữ liệu liên quan
(vận đơn, kho, thanh toán) và ghi lịch sử cùng nhau; lỗi ở bước nào thì hoàn tác tất cả."""
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.constants import OrderStatus, PaymentMethod, PaymentStatus
from app.extensions import db
from app.models import Carrier, Shipment
from app.models.base import utcnow
from app.services import audit_service, inventory_service, order_service
from app.services.errors import FulfillmentError

_TRACKING_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_.]{2,59}$")


def _transition(order, to_status, actor, reason, extra=None):
    """Chuyển trạng thái rồi chạy bước phụ (extra) trong cùng transaction."""
    try:
        order_service.change_status(order, to_status, actor, reason)
        if extra:
            extra()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return order


def confirm_order(order, actor):
    """Chờ xác nhận -> Đã xác nhận."""
    return _transition(order, OrderStatus.CONFIRMED, actor, "Nhân viên xác nhận đơn")


def start_packing(order, actor):
    """Đã xác nhận -> Đang đóng gói."""
    return _transition(order, OrderStatus.PACKING, actor, "Bắt đầu đóng gói")


def active_carriers():
    return db.session.scalars(select(Carrier).where(Carrier.is_active.is_(True)).order_by(Carrier.name)).all()


def ship_order(order, actor, carrier_id, tracking_code):
    """Đang đóng gói -> Đang giao: ghi đơn vị vận chuyển + mã vận đơn và xuất kho."""
    tracking = (tracking_code or "").strip()
    if not _TRACKING_RE.match(tracking):
        raise FulfillmentError("Mã vận đơn gồm 3-60 ký tự chữ, số, dấu gạch ngang, gạch dưới hoặc dấu chấm.")
    carrier = db.session.get(Carrier, carrier_id) if carrier_id else None
    if carrier is None or not carrier.is_active:
        raise FulfillmentError("Vui lòng chọn đơn vị vận chuyển hợp lệ.")

    def hand_over():
        db.session.add(Shipment(sales_order_id=order.id, carrier_id=carrier.id, tracking_code=tracking,
                                shipped_at=utcnow()))
        db.session.flush()                                   # phát hiện trùng mã vận đơn ngay tại đây
        inventory_service.issue_for_order(order, actor)

    try:
        _transition(order, OrderStatus.SHIPPING, actor, f"Bàn giao cho {carrier.name}, mã vận đơn {tracking}", hand_over)
    except IntegrityError:
        raise FulfillmentError(f"Mã vận đơn {tracking} đã tồn tại với đơn vị vận chuyển {carrier.name}.")
    return order.shipment


def ship_order_ghn(order, actor, service_code="GHN_STANDARD", required_note="CHOXEMHANGKHONGTHU", note=None):
    """Bàn giao tự động qua GHN Open API: tự sinh mã vận đơn, tạo shipment và xuất kho."""
    from app.services import ghn_service
    carrier = ghn_service.get_active_ghn_carrier()

    def hand_over():
        ghn_service.create_shipping_order(order, service_code=service_code, note=note, required_note=required_note)
        inventory_service.issue_for_order(order, actor)

    try:
        _transition(order, OrderStatus.SHIPPING, actor, f"Bàn giao tự động cho {carrier.name} qua API", hand_over)
    except Exception as e:
        raise FulfillmentError(f"Lỗi tạo đơn vận chuyển với GHN: {e}")
    return order.shipment


def mark_delivered(order, actor):
    """Đang giao -> Hoàn thành. Đơn COD: ghi nhận đã thu tiền khi giao thành công."""
    def finish():
        shipment = db.session.get(Shipment, order.id)
        if shipment is None:
            raise FulfillmentError("Đơn chưa có thông tin vận chuyển.")
        shipment.delivered_at = utcnow()
        payment = order.latest_payment
        if payment and payment.method == PaymentMethod.COD and payment.status == PaymentStatus.UNPAID:
            payment.status = PaymentStatus.PAID
            payment.paid_at = utcnow()

    return _transition(order, OrderStatus.COMPLETED, actor, "Giao hàng thành công", finish)


def report_incident(order, actor, note):
    """Giao hàng gặp sự cố: chỉ ghi nhận (đơn vẫn Đang giao); quản trị viên quyết định tiếp tục giao hay hủy/hoàn
    theo quy trình thủ công của phiên bản đầu."""
    note = (note or "").strip()
    if len(note) < 5:
        raise FulfillmentError("Vui lòng mô tả sự cố giao hàng (ít nhất 5 ký tự).")
    db.session.refresh(order)
    if order.status != OrderStatus.SHIPPING:
        raise FulfillmentError("Chỉ ghi nhận sự cố cho đơn đang giao.")
    shipment = order.shipment
    audit_service.record("shipment.incident", "sales_order", order.id, None,
                         {"note": note[:500], "tracking_code": shipment.tracking_code if shipment else None}, actor)
    db.session.commit()
