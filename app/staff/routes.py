"""Khu vực nhân viên: bảng điều khiển, xử lý đơn, giao hàng (FR-NV01..04). Nhân viên và quản trị viên.
Quyền được kiểm tra ở backend theo từng thao tác (bảng role_permission); quản trị viên luôn có đủ quyền."""
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.constants import OrderStatus, Perm
from app.services import fulfillment_service, order_service, staff_service
from app.services.errors import FulfillmentError, InventoryError, OrderStateError
from app.staff import bp
from app.utils.decorators import permission_required, staff_required


@bp.route("/")
@staff_required
def dashboard():
    return render_template("staff/dashboard.html", stats=staff_service.dashboard_stats(),
                           labels=OrderStatus.LABELS, badges=OrderStatus.BADGES)


# ------------------------------------------------------------------ danh sách và chi tiết đơn
@bp.route("/orders")
@permission_required(Perm.ORDER_VIEW)
def orders():
    status = request.args.get("status", "")
    status = status if status in OrderStatus.ALL else None
    q = " ".join(request.args.get("q", "").split())[:100]
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = staff_service.search_orders(status, q, page)
    if pagination.total and not pagination.items:
        return redirect(url_for("staff.orders", status=status, q=q or None, page=pagination.pages if pagination.pages > 1 else None))
    return render_template(
        "staff/orders.html", pagination=pagination, orders=pagination.items, status=status, q=q,
        counts=staff_service.status_counts(), labels=OrderStatus.LABELS,
        list_url=lambda p: url_for("staff.orders", status=status, q=q or None, page=p if p > 1 else None))


@bp.route("/orders/<order_code>")
@permission_required(Perm.ORDER_VIEW)
def order_detail(order_code):
    order = staff_service.get_order(order_code)
    return render_template("staff/order_detail.html", order=order, carriers=fulfillment_service.active_carriers(),
                           incidents=staff_service.incidents(order),
                           deadline=order_service.payment_deadline(order))


# ------------------------------------------------------------------ thao tác xử lý đơn
def _perform(order_code, action, success, *args):
    """Chạy một thao tác nghiệp vụ, báo kết quả bằng flash rồi quay lại trang chi tiết đơn."""
    order = staff_service.get_order(order_code)
    try:
        result = action(order, current_user, *args)
    except (OrderStateError, FulfillmentError) as e:
        flash(str(e), "danger")
    except InventoryError:
        current_app.logger.exception("Số liệu kho không nhất quán khi xử lý đơn %s", order_code)
        flash("Số liệu kho không nhất quán nên chưa thể thực hiện. Vui lòng báo quản trị viên kiểm tra tồn kho.", "danger")
    else:
        flash(success(result) if callable(success) else success, "success")
    return redirect(url_for("staff.order_detail", order_code=order_code))


@bp.route("/orders/<order_code>/confirm", methods=["POST"])
@permission_required(Perm.ORDER_PROCESS)
def order_confirm(order_code):
    return _perform(order_code, fulfillment_service.confirm_order, "Đã xác nhận đơn hàng.")


@bp.route("/orders/<order_code>/pack", methods=["POST"])
@permission_required(Perm.ORDER_PROCESS)
def order_pack(order_code):
    return _perform(order_code, fulfillment_service.start_packing, "Đã chuyển đơn sang đóng gói.")


@bp.route("/orders/<order_code>/cancel", methods=["POST"])
@permission_required(Perm.ORDER_PROCESS)
def order_cancel(order_code):
    return _perform(order_code, order_service.cancel_order, "Đã hủy đơn hàng và nhả hàng đang giữ.",
                    request.form.get("reason", ""))


@bp.route("/orders/<order_code>/ship", methods=["POST"])
@permission_required(Perm.SHIPMENT_UPDATE)
def order_ship(order_code):
    carrier_id = request.form.get("carrier_id", type=int)
    return _perform(order_code, fulfillment_service.ship_order,
                    lambda s: f"Đã bàn giao cho {s.carrier.name}, mã vận đơn {s.tracking_code}. Hàng đã được xuất kho.",
                    carrier_id, request.form.get("tracking_code", ""))


@bp.route("/orders/<order_code>/deliver", methods=["POST"])
@permission_required(Perm.SHIPMENT_UPDATE)
def order_deliver(order_code):
    return _perform(order_code, fulfillment_service.mark_delivered, "Đã ghi nhận giao hàng thành công.")


@bp.route("/orders/<order_code>/incident", methods=["POST"])
@permission_required(Perm.SHIPMENT_UPDATE)
def order_incident(order_code):
    return _perform(order_code, fulfillment_service.report_incident, "Đã ghi nhận sự cố giao hàng.",
                    request.form.get("note", ""))
