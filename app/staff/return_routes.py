"""Nhân viên tiếp nhận và xử lý yêu cầu đổi trả (FR-NV05)."""
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.constants import Perm, ReturnStatus
from app.services import return_service
from app.services.errors import InventoryError, OrderStateError, ReturnError
from app.staff import bp
from app.utils.decorators import permission_required


@bp.route("/returns")
@permission_required(Perm.RETURN_HANDLE)
def returns():
    status = request.args.get("status", "")
    status = status if status in ReturnStatus.ALL else None
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = return_service.list_returns(status, page)
    if pagination.total and not pagination.items:
        return redirect(url_for("staff.returns", status=status, page=pagination.pages if pagination.pages > 1 else None))
    return render_template("staff/returns.html", pagination=pagination, requests=pagination.items, status=status,
                           counts=return_service.status_counts(), labels=ReturnStatus.LABELS,
                           list_url=lambda p: url_for("staff.returns", status=status, page=p if p > 1 else None))


@bp.route("/returns/<int:return_id>")
@permission_required(Perm.RETURN_HANDLE)
def return_detail(return_id):
    req = return_service.get_return(return_id)
    return render_template("staff/return_detail.html", req=req, suggested=return_service.suggested_refund(req),
                           window_days=return_service.return_window_days())


def _handle(return_id, action, success, *args):
    req = return_service.get_return(return_id)
    try:
        action(req, current_user, *args)
    except (ReturnError, OrderStateError) as e:
        flash(str(e), "danger")
    except InventoryError:
        current_app.logger.exception("Lỗi kho khi xử lý đổi trả #%s", return_id)
        flash("Không cập nhật được tồn kho. Vui lòng báo quản trị viên kiểm tra số liệu kho.", "danger")
    else:
        flash(success, "success")
    return redirect(url_for("staff.return_detail", return_id=return_id))


@bp.route("/returns/<int:return_id>/approve", methods=["POST"])
@permission_required(Perm.RETURN_HANDLE)
def return_approve(return_id):
    return _handle(return_id, return_service.approve_return,
                   "Đã chấp nhận yêu cầu. Đơn chuyển sang Đang đổi trả, chờ nhận hàng trả về.", request.form.get("note", ""))


@bp.route("/returns/<int:return_id>/reject", methods=["POST"])
@permission_required(Perm.RETURN_HANDLE)
def return_reject(return_id):
    return _handle(return_id, return_service.reject_return, "Đã từ chối yêu cầu đổi trả.", request.form.get("reason", ""))


@bp.route("/returns/<int:return_id>/complete", methods=["POST"])
@permission_required(Perm.RETURN_HANDLE)
def return_complete(return_id):
    req = return_service.get_return(return_id)
    accepted = {}
    for ri in req.items:
        raw = request.form.get(f"accepted_{ri.id}", "").strip()
        accepted[ri.id] = int(raw) if raw.isdigit() else None
    return _handle(return_id, return_service.complete_return,
                   "Đã hoàn tất đổi trả: hàng đạt đã được nhập lại kho, đơn chuyển sang Đã đổi trả.",
                   accepted, request.form.get("refund_amount", ""), request.form.get("note", ""))
