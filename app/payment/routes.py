"""Thanh toán online: chuyển sang cổng, nhận kết quả (Return + IPN), cổng giả lập cho phát triển/demo (FR-KH10)."""
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models.base import utcnow
from app.payment import bp
from app.services import order_service, payment_service, vnpay
from app.services.payment_service import PaymentStartError
from app.utils.decorators import customer_required
from app.utils.formatters import dt


# ------------------------------------------------------------------ bắt đầu thanh toán
@bp.route("/start/<order_code>")
@customer_required
def start(order_code):
    order = order_service.get_owned_order(current_user, order_code)
    try:
        gateway_url = payment_service.start_payment(order, request.remote_addr)
    except PaymentStartError as e:
        flash(str(e), "danger")
        return redirect(url_for("account.order_detail", order_code=order_code))
    return redirect(gateway_url)


# ------------------------------------------------------------------ kết quả từ cổng
def _describe(outcome):
    """(loại thông báo, nội dung, mã HTTP) cho khách hàng."""
    code = outcome.order.order_code if outcome.order else ""
    if outcome.kind == "invalid":
        return "danger", "Không xác thực được kết quả thanh toán. Giao dịch không được ghi nhận.", 400
    if outcome.kind == "not_found":
        return "danger", "Không tìm thấy giao dịch tương ứng.", 404
    if outcome.kind == "amount_mismatch":
        return "danger", ("Số tiền thanh toán không khớp với đơn hàng nên giao dịch không được ghi nhận. "
                          "Vui lòng liên hệ cửa hàng để được hỗ trợ."), 400
    if outcome.kind in ("paid", "already_paid"):
        return "success", f"Thanh toán thành công! Đơn hàng {code} đang chờ cửa hàng xác nhận.", 200
    if outcome.kind == "late":
        return "warning", (f"Đơn hàng {code} đã bị hủy do quá hạn thanh toán trước khi giao dịch hoàn tất. "
                           "Cửa hàng sẽ liên hệ để hoàn tiền cho bạn."), 200
    if outcome.kind == "duplicate":
        return "warning", f"Đơn hàng {code} đã được thanh toán trước đó. Khoản thu trùng sẽ được hoàn lại cho bạn.", 200
    deadline = order_service.payment_deadline(outcome.order) if outcome.order else None
    retry = f" Bạn có thể thử thanh toán lại trước {dt(deadline)}." if deadline else ""
    return "danger", f"Thanh toán không thành công: {outcome.detail}.{retry}", 200


@bp.route("/vnpay/return")
def vnpay_return():
    """Trình duyệt khách quay về từ cổng. Kết quả được xác thực chữ ký và số tiền giống hệt đường IPN."""
    try:
        outcome = payment_service.process_gateway_result(request.args.to_dict())
    except Exception:
        current_app.logger.exception("Lỗi xử lý kết quả thanh toán (return)")
        return render_template("payment/result.html", ok=False, order=None, status_code=500,
                               message="Hệ thống đang xử lý kết quả thanh toán. Vui lòng kiểm tra lại đơn hàng sau ít phút."), 500

    category, message, status = _describe(outcome)
    owner = (current_user.is_authenticated and outcome.order is not None
             and outcome.order.account_id == current_user.id)
    if owner and status == 200:
        flash(message, category)
        return redirect(url_for("account.order_detail", order_code=outcome.order.order_code))
    return render_template("payment/result.html", ok=category == "success", order=outcome.order,
                           message=message, status_code=status), status


@bp.route("/vnpay/ipn")
def vnpay_ipn():
    """VNPay gọi máy chủ-tới-máy chủ (cần URL công khai khi dùng cổng thật). Luôn trả JSON theo đặc tả."""
    try:
        outcome = payment_service.process_gateway_result(request.args.to_dict())
    except Exception:
        current_app.logger.exception("Lỗi xử lý IPN thanh toán")
        return jsonify(RspCode="99", Message="Unknown error")
    current_app.logger.info("IPN thanh toán: kind=%s code=%s", outcome.kind, outcome.code)
    return jsonify(RspCode=outcome.code, Message=outcome.message)


# ------------------------------------------------------------------ cổng giả lập (chỉ phát triển/demo)
def _require_mock():
    if payment_service.gateway_mode() != "mock":
        abort(404)


@bp.route("/mock/pay")
def mock_pay():
    _require_mock()
    params = request.args.to_dict()
    if not vnpay.verify(params, payment_service.secret()):
        abort(400)
    result = vnpay.parse_result(params)
    return render_template("payment/mock_gateway.html", txn_ref=result.txn_ref, amount=result.amount,
                           order_info=params.get("vnp_OrderInfo", ""))


@bp.route("/mock/complete", methods=["POST"])
def mock_complete():
    _require_mock()
    outcome = request.form.get("outcome", "")
    txn_ref = request.form.get("txn_ref", "")
    amount = request.form.get("amount", type=int)
    if amount is None or amount < 0 or not txn_ref:
        abort(400)
    codes = {"success": "00", "fail": "51", "cancel": "24", "tamper": "00"}
    if outcome not in codes:
        abort(400)
    if outcome == "tamper":                       # giả lập kết quả có số tiền sai để kiểm chứng cơ chế chống giả mạo
        amount += 1000
    params = vnpay.build_result_params(
        payment_service.secret(), tmn_code=payment_service.tmn_code(), txn_ref=txn_ref, amount=amount,
        response_code=codes[outcome], pay_date=vnpay.vn_timestamp(utcnow()),
        order_info=request.form.get("order_info", ""))
    return redirect(url_for("payment.vnpay_return", **params))
