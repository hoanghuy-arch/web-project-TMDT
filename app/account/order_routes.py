"""Đặt hàng và đơn của tôi (FR-KH08..12): checkout, danh sách đơn, chi tiết, hủy đơn."""
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.account import bp
from app.account.routes import _form_int
from app.constants import OrderStatus, PaymentMethod
from app.services import address_service, order_service, payment_service, return_service, review_service
from app.services.errors import CheckoutError, OrderStateError
from app.utils.decorators import customer_required


def online_payment_enabled():
    """Thanh toán online khả dụng khi có cổng VNPay đã cấu hình hoặc cổng giả lập (chỉ phát triển)."""
    return payment_service.is_online_enabled()


# ------------------------------------------------------------------ checkout
@bp.route("/checkout", methods=["GET", "POST"])
@customer_required
def checkout():
    posting = request.method == "POST"
    address_id = _form_int("address_id") if posting else None
    promo_code = request.form.get("promo_code", "") if posting else ""
    method = request.form.get("payment_method", PaymentMethod.COD) if posting else PaymentMethod.COD
    note = request.form.get("note", "")[:500] if posting else ""
    shipping_service_code = request.form.get("shipping_service_code", "GHN_STANDARD") if posting else "GHN_STANDARD"

    if posting and request.form.get("action") == "place":
        if method == PaymentMethod.VNPAY and not online_payment_enabled():
            flash("Thanh toán online hiện chưa khả dụng. Vui lòng chọn thanh toán khi nhận hàng.", "danger")
        else:
            try:
                order = order_service.place_order(current_user, address_id, promo_code, method, note,
                                                  shipping_service_code=shipping_service_code)
            except CheckoutError as e:
                flash(str(e), "danger")
            else:
                if method == PaymentMethod.VNPAY:
                    return redirect(url_for("payment.start", order_code=order.order_code))
                flash(f"Đặt hàng thành công! Mã đơn của bạn là {order.order_code}.", "success")
                return redirect(url_for("account.order_detail", order_code=order.order_code))

    summary = order_service.build_checkout(current_user, address_id, promo_code,
                                          shipping_service_code=shipping_service_code)
    if not summary.cart.lines:
        flash("Giỏ hàng của bạn đang trống.", "info")
        return redirect(url_for("account.cart"))
    return render_template(
        "account/checkout.html", summary=summary, addresses=address_service.list_active_addresses(current_user),
        method=method, note=note, online_enabled=online_payment_enabled(), payment_methods=PaymentMethod.LABELS)


# ------------------------------------------------------------------ đơn của tôi
@bp.route("/orders")
@customer_required
def orders():
    status = request.args.get("status", "")
    status = status if status in OrderStatus.ALL else None
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = order_service.list_orders(current_user, status, page)
    if pagination.total and not pagination.items:
        return redirect(url_for("account.orders", status=status, page=pagination.pages if pagination.pages > 1 else None))
    return render_template(
        "account/orders.html", pagination=pagination, orders=pagination.items, status=status,
        counts=order_service.status_counts(current_user), order_status_labels=OrderStatus.LABELS,
        list_url=lambda p: url_for("account.orders", status=status, page=p if p > 1 else None))


@bp.route("/orders/<order_code>")
@customer_required
def order_detail(order_code):
    order = order_service.get_owned_order(current_user, order_code)
    from app.services import ghn_service
    tracking = ghn_service.get_tracking_timeline(order)
    return render_template("account/order_detail.html", order=order, can_cancel=order_service.can_customer_cancel(order),
                           deadline=order_service.payment_deadline(order), online_enabled=online_payment_enabled(),
                           return_blocker=return_service.request_blocker(order),
                           return_deadline=return_service.return_deadline(order) if order.status == OrderStatus.COMPLETED else None,
                           can_review=order.status in review_service.REVIEWABLE_STATUSES,
                           tracking=tracking)


@bp.route("/orders/<order_code>/shipping-label")
def order_shipping_label(order_code):
    """Xem và in phiếu giao hàng A5 chính thức (chuẩn Barcode GHN)."""
    from app.models import SalesOrder
    order = SalesOrder.query.filter_by(order_code=order_code).first_or_404()
    from app.services import ghn_service
    tracking = ghn_service.get_tracking_timeline(order)
    return render_template("account/shipping_label.html", order=order, tracking=tracking)


@bp.route("/orders/<order_code>/cancel", methods=["POST"])
@customer_required
def order_cancel(order_code):
    order = order_service.get_owned_order(current_user, order_code)
    try:
        order_service.cancel_order(order, current_user, request.form.get("reason", ""))
        flash(f"Đã hủy đơn hàng {order.order_code}.", "info")
    except OrderStateError as e:
        flash(str(e), "danger")
    return redirect(url_for("account.order_detail", order_code=order_code))
