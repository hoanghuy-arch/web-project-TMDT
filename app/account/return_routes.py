"""Khách hàng gửi yêu cầu đổi trả (FR-KH13) và đánh giá sản phẩm đã mua (FR-KH14)."""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.account import bp
from app.services import order_service, return_service, review_service
from app.services.errors import ReturnError, ReviewError
from app.utils.decorators import customer_required


@bp.route("/orders/<order_code>/return", methods=["GET", "POST"])
@customer_required
def return_new(order_code):
    order = order_service.get_owned_order(current_user, order_code)
    blocker = return_service.request_blocker(order)
    if blocker:
        flash(blocker, "danger")
        return redirect(url_for("account.order_detail", order_code=order_code))

    form = {"reason": "", "quantities": {}}
    if request.method == "POST":
        form["reason"] = request.form.get("reason", "")
        for item in order.items:
            raw = request.form.get(f"qty_{item.id}", "0").strip() or "0"
            form["quantities"][item.id] = int(raw) if raw.lstrip("-").isdigit() else None
        try:
            return_service.create_return_request(current_user, order, form["quantities"], form["reason"])
        except ReturnError as e:
            flash(str(e), "danger")
        else:
            flash("Đã gửi yêu cầu đổi trả. Cửa hàng sẽ xem xét và phản hồi cho bạn.", "success")
            return redirect(url_for("account.order_detail", order_code=order_code))
    return render_template("account/return_form.html", order=order, form=form,
                           deadline=return_service.return_deadline(order))


@bp.route("/orders/<order_code>/review/<int:item_id>", methods=["GET", "POST"])
@customer_required
def review_new(order_code, item_id):
    order = order_service.get_owned_order(current_user, order_code)
    item = next((i for i in order.items if i.id == item_id), None)
    if item is None:
        abort(404)
    blocker = review_service.review_blocker(order, item)
    if blocker:
        flash(blocker, "danger")
        return redirect(url_for("account.order_detail", order_code=order_code))

    form = {"rating": request.form.get("rating", type=int) if request.method == "POST" else None,
            "comment": request.form.get("comment", "") if request.method == "POST" else ""}
    if request.method == "POST":
        try:
            review_service.create_review(current_user, order, item, form["rating"], form["comment"])
        except ReviewError as e:
            flash(str(e), "danger")
        else:
            flash("Cảm ơn bạn đã đánh giá sản phẩm!", "success")
            return redirect(url_for("account.order_detail", order_code=order_code))
    return render_template("account/review_form.html", order=order, item=item, form=form)
