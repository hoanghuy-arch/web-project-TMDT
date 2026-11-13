"""Gửi email (FR-HT02). Gửi ở luồng riêng để không làm chậm phản hồi và không lộ thời gian xử lý."""
import threading

from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail


def _deliver(app, msg):
    with app.app_context():
        try:
            if app.config.get("MAIL_SUPPRESS_SEND") and not app.testing:
                # Chưa cấu hình SMTP: ghi nội dung email ra log để dev lấy liên kết khi chạy thử
                app.logger.info("[EMAIL chưa cấu hình SMTP - chỉ ghi log] To=%s | Subject=%s\n%s",
                                msg.recipients, msg.subject, msg.body)
            mail.send(msg)
        except Exception:  # không để lỗi SMTP làm hỏng nghiệp vụ chính
            app.logger.exception("Gửi email thất bại tới %s", msg.recipients)


def send_email(to, subject, text_body, html_body=None):
    msg = Message(subject=subject, recipients=[to], body=text_body, html=html_body)
    app = current_app._get_current_object()
    if app.testing:
        _deliver(app, msg)             # đồng bộ để test đọc được hộp thư giả lập
    else:
        threading.Thread(target=_deliver, args=(app, msg), daemon=True).start()


def send_password_reset_email(account, reset_url):
    ttl = current_app.config["PASSWORD_RESET_TTL_MINUTES"]
    ctx = dict(full_name=account.full_name, reset_url=reset_url, ttl_minutes=ttl)
    send_email(
        to=account.email,
        subject="SportZone - Đặt lại mật khẩu",
        text_body=render_template("emails/reset_password.txt", **ctx),
        html_body=render_template("emails/reset_password.html", **ctx),
    )


def send_order_confirmation_email(order):
    """Email xác nhận đơn hàng (FR-HT02)."""
    account = order.account
    ctx = dict(order=order, full_name=account.full_name, address=order.address)
    send_email(
        to=account.email,
        subject=f"SportZone - Xác nhận đơn hàng {order.order_code}",
        text_body=render_template("emails/order_confirmation.txt", **ctx),
        html_body=render_template("emails/order_confirmation.html", **ctx),
    )


def send_order_status_changed_email(order, new_status_label, reason=None):
    """Email thông báo thay đổi trạng thái đơn hàng (FR-HT02).

    Gửi cho khách khi nhân viên/hệ thống cập nhật trạng thái.
    Chỉ gửi cho các trạng thái đáng thông báo; bỏ qua PENDING_PAYMENT và PENDING_CONFIRM
    vì khách đã nhận email xác nhận riêng khi đặt hàng.
    """
    from flask import url_for
    account = order.account
    # Tránh spam cho trạng thái nội bộ
    _SKIP_NOTIFY = {"PENDING_PAYMENT", "PENDING_CONFIRM", "CONFIRMED", "PACKING"}
    if order.status in _SKIP_NOTIFY:
        return
    try:
        order_url = url_for("account.order_detail", order_code=order.order_code, _external=True)
    except Exception:
        order_url = ""
    ctx = dict(
        full_name=account.full_name,
        order=order,
        new_status_label=new_status_label,
        reason=reason,
        order_url=order_url,
    )
    send_email(
        to=account.email,
        subject=f"SportZone - Đơn hàng {order.order_code}: {new_status_label}",
        text_body=render_template("emails/order_status_changed.txt", **ctx),
        html_body=render_template("emails/order_status_changed.html", **ctx),
    )
