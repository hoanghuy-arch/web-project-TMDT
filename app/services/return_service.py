"""Đổi trả (FR-KH13, FR-NV05). Quy trình theo Hình 2.6:
  khách gửi yêu cầu (đơn Hoàn thành, trong thời hạn) -> nhân viên CHẤP NHẬN (đơn: Đang đổi trả)
  -> nhận hàng về và kiểm tra, nhập số lượng đạt -> HOÀN TẤT (đơn: Đã đổi trả).
  Hoặc nhân viên TỪ CHỐI (đơn giữ nguyên Hoàn thành). Hoàn tiền là thủ công và luôn được ghi lịch sử, nhật ký.
Chỉ số lượng kiểm tra đủ điều kiện bán lại mới được cộng lại tồn kho."""
from datetime import timedelta
from decimal import Decimal

from flask import abort, current_app
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.constants import OrderStatus, PaymentStatus, ReturnStatus, SettingKey
from app.extensions import db
from app.models import (AppSetting, ReturnItem, ReturnRequest, SalesOrder, SalesOrderItem)
from app.models.base import utcnow
from app.services import audit_service, inventory_service, order_service
from app.services.errors import ConcurrentUpdateError, ReturnError


# ================================================================== phía khách hàng
def return_window_days():
    return AppSetting.get_int(SettingKey.RETURN_WINDOW_DAYS, current_app.config["DEFAULT_RETURN_WINDOW_DAYS"])


def received_at(order):
    """Thời điểm khách nhận hàng: lúc giao thành công (nếu thiếu thì lấy thời điểm đơn hoàn thành)."""
    shipment = order.shipment
    return shipment.delivered_at if shipment and shipment.delivered_at else order.updated_at


def return_deadline(order):
    return received_at(order) + timedelta(days=return_window_days())


def request_blocker(order):
    """Lý do chưa thể gửi yêu cầu đổi trả (None nếu được phép)."""
    if order.status != OrderStatus.COMPLETED:
        return "Chỉ đơn hàng đã hoàn thành mới có thể yêu cầu đổi trả."
    if utcnow() > return_deadline(order):
        return f"Đã quá thời hạn đổi trả ({return_window_days()} ngày kể từ khi nhận hàng)."
    if any(r.status == ReturnStatus.PENDING for r in order.return_requests):
        return "Đơn hàng đang có yêu cầu đổi trả chờ xử lý."
    return None


def create_return_request(account, order, quantities, reason):
    """quantities: {sales_order_item_id: số lượng muốn trả}. Mỗi dòng không vượt số lượng đã mua."""
    reason = (reason or "").strip()
    if order.account_id != account.id:
        raise ReturnError("Bạn không có quyền yêu cầu đổi trả cho đơn hàng này.")
    if len(reason) < 5:
        raise ReturnError("Vui lòng nêu lý do đổi trả (ít nhất 5 ký tự).")

    chosen = []
    for item in order.items:
        qty = quantities.get(item.id, 0)
        if qty is None or qty < 0 or qty > item.quantity:
            raise ReturnError(f"Số lượng trả của \"{item.variant.product.name}\" phải từ 0 đến {item.quantity}.")
        if qty > 0:
            chosen.append((item, qty))
    if not chosen:
        raise ReturnError("Vui lòng chọn ít nhất một sản phẩm cần trả.")

    try:
        # Khóa dòng đơn rồi kiểm tra lại: hai yêu cầu gửi cùng lúc không thể cùng vượt qua điều kiện
        locked = db.session.scalar(select(SalesOrder).where(SalesOrder.id == order.id).with_for_update())
        db.session.refresh(locked)
        blocker = request_blocker(locked)
        if blocker:
            raise ReturnError(blocker)
        request = ReturnRequest(sales_order_id=order.id, reason=reason[:500], status=ReturnStatus.PENDING)
        for item, qty in chosen:
            request.items.append(ReturnItem(sales_order_item_id=item.id, quantity=qty))
        db.session.add(request)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return request


# ================================================================== phía nhân viên: truy vấn
def pending_count():
    return db.session.scalar(select(func.count(ReturnRequest.id)).where(ReturnRequest.status == ReturnStatus.PENDING)) or 0


def status_counts():
    rows = db.session.execute(select(ReturnRequest.status, func.count(ReturnRequest.id)).group_by(ReturnRequest.status)).all()
    return {s: n for s, n in rows}


def list_returns(status=None, page=1):
    stmt = (select(ReturnRequest)
            .options(selectinload(ReturnRequest.order).selectinload(SalesOrder.account), selectinload(ReturnRequest.items))
            .order_by(ReturnRequest.created_at.desc(), ReturnRequest.id.desc()))
    if status in ReturnStatus.ALL:
        stmt = stmt.where(ReturnRequest.status == status)
    return db.paginate(stmt, page=page, per_page=current_app.config["ADMIN_ITEMS_PER_PAGE"], error_out=False)


def get_return(return_id):
    request = db.session.scalar(
        select(ReturnRequest).where(ReturnRequest.id == return_id)
        .options(selectinload(ReturnRequest.order).selectinload(SalesOrder.account),
                 selectinload(ReturnRequest.order).selectinload(SalesOrder.payments),
                 selectinload(ReturnRequest.items).selectinload(ReturnItem.order_item).selectinload(SalesOrderItem.variant),
                 selectinload(ReturnRequest.handled_by)))
    if request is None:
        abort(404)
    return request


def suggested_refund(request, accepted=None):
    """Gợi ý số tiền hoàn = Σ số lượng đạt × đơn giá (không gồm phí vận chuyển). Nhân viên quyết định số cuối cùng."""
    total = Decimal(0)
    for ri in request.items:
        qty = (accepted or {}).get(ri.id, ri.accepted_quantity if ri.accepted_quantity is not None else ri.quantity)
        total += Decimal(qty) * ri.order_item.unit_price
    return total


# ================================================================== phía nhân viên: xử lý
def _claim(request, from_status, to_status, actor, resolved=False):
    """Chuyển trạng thái yêu cầu một cách nguyên tử (chống hai nhân viên cùng xử lý)."""
    values = {"status": to_status, "handled_by_account_id": actor.id}
    if resolved:
        values["resolved_at"] = utcnow()
    result = db.session.execute(
        update(ReturnRequest).where(ReturnRequest.id == request.id, ReturnRequest.status == from_status)
        .values(**values).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ConcurrentUpdateError("Yêu cầu đổi trả vừa được xử lý bởi người khác hoặc không còn ở trạng thái phù hợp.")
    db.session.expire(request)


def _run(request, fn):
    try:
        fn()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return request


def approve_return(request, actor, note=None):
    """Chờ xử lý -> Đã chấp nhận; đơn Hoàn thành -> Đang đổi trả."""
    note = (note or "").strip()[:400]

    def work():
        _claim(request, ReturnStatus.PENDING, ReturnStatus.APPROVED, actor)
        order_service.change_status(request.order, OrderStatus.RETURNING, actor, f"Chấp nhận yêu cầu đổi trả #{request.id}")
        request.resolution = note or "Đã chấp nhận, chờ nhận hàng trả về."
        audit_service.record("return.approve", "return_request", request.id, {"status": ReturnStatus.PENDING},
                             {"status": ReturnStatus.APPROVED, "order": request.order.order_code}, actor)
    return _run(request, work)


def reject_return(request, actor, reason):
    """Chờ xử lý -> Từ chối (bắt buộc lý do). Đơn giữ nguyên trạng thái Hoàn thành."""
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ReturnError("Vui lòng nhập lý do từ chối (ít nhất 5 ký tự).")

    def work():
        _claim(request, ReturnStatus.PENDING, ReturnStatus.REJECTED, actor, resolved=True)
        request.resolution = reason[:500]
        audit_service.record("return.reject", "return_request", request.id, {"status": ReturnStatus.PENDING},
                             {"status": ReturnStatus.REJECTED, "reason": reason[:500]}, actor)
    return _run(request, work)


def _parse_money(value):
    """'250.000' hoặc '250000' -> Decimal; chỉ nhận chữ số (dấu '.' ngăn cách hàng nghìn)."""
    cleaned = str(value).strip().replace(".", "")
    if not cleaned.isdigit():
        raise ReturnError("Số tiền hoàn không hợp lệ.")
    return Decimal(cleaned)


def complete_return(request, actor, accepted, refund_amount=None, note=None):
    """Đã chấp nhận -> Hoàn tất. accepted: {return_item_id: số lượng đạt}. Cộng lại tồn kho phần đạt, đơn -> Đã đổi trả.
    refund_amount (tùy chọn): ghi nhận đã hoàn tiền thủ công cho khách (đơn phải đã thu tiền)."""
    if request.status != ReturnStatus.APPROVED:
        raise ReturnError("Chỉ hoàn tất được yêu cầu đã chấp nhận.")
    plan = {}
    for ri in request.items:
        qty = accepted.get(ri.id)
        if qty is None or qty < 0 or qty > ri.quantity:
            raise ReturnError(f"Số lượng đạt của \"{ri.order_item.variant.product.name}\" phải từ 0 đến {ri.quantity}.")
        plan[ri.id] = qty

    refund = None
    if refund_amount not in (None, "", "0"):
        refund = _parse_money(refund_amount)
        if refund > 0:
            payment = request.order.latest_payment
            if payment is None or payment.status != PaymentStatus.PAID:
                raise ReturnError("Đơn hàng chưa thu tiền nên không thể ghi nhận hoàn tiền.")
            if refund > payment.amount:
                raise ReturnError("Số tiền hoàn không được lớn hơn số tiền khách đã thanh toán.")
        else:
            refund = None

    note = (note or "").strip()[:300]

    def work():
        _claim(request, ReturnStatus.APPROVED, ReturnStatus.COMPLETED, actor, resolved=True)
        for ri in request.items:
            ri.accepted_quantity = plan[ri.id]
            if plan[ri.id] > 0:
                inventory_service.receive_return_item(ri, plan[ri.id], actor)
        order_service.change_status(request.order, OrderStatus.RETURNED, actor, f"Hoàn tất đổi trả #{request.id}")
        parts = [note] if note else []
        parts.append("Số lượng đạt: " + ", ".join(f"{ri.order_item.variant.product.name} {plan[ri.id]}/{ri.quantity}" for ri in request.items))
        if refund:
            payment = request.order.latest_payment
            payment.status = PaymentStatus.REFUNDED
            parts.append(f"Đã hoàn tiền {int(refund):,}".replace(",", ".") + " ₫")
            audit_service.record("return.refund", "payment", payment.id, {"status": PaymentStatus.PAID},
                                 {"status": PaymentStatus.REFUNDED, "refund_amount": int(refund),
                                  "return_request": request.id}, actor)
        request.resolution = "; ".join(parts)[:500]
        audit_service.record("return.complete", "return_request", request.id, {"status": ReturnStatus.APPROVED},
                             {"status": ReturnStatus.COMPLETED, "accepted": {str(k): v for k, v in plan.items()},
                              "refund": int(refund) if refund else 0}, actor)
    return _run(request, work)
