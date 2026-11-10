"""Bộ lọc Jinja2 hiển thị tiền tệ, ngày giờ, trạng thái."""
from datetime import timedelta

from flask import url_for

from app.constants import ROLE_LABELS, OrderStatus, PaymentStatus

VN_OFFSET = timedelta(hours=7)  # DB lưu UTC, hiển thị giờ Việt Nam


def vnd(value):
    """1500000 -> '1.500.000 ₫'."""
    if value is None:
        return "0 ₫"
    return f"{int(value):,}".replace(",", ".") + " ₫"


def dt(value, fmt="%d/%m/%Y %H:%M"):
    return (value + VN_OFFSET).strftime(fmt) if value else ""


def order_status_label(code):
    return OrderStatus.LABELS.get(code, code)


def order_status_badge(code):
    return OrderStatus.BADGES.get(code, "secondary")


def payment_status_label(code):
    return PaymentStatus.LABELS.get(code, code)


def payment_status_badge(code):
    return PaymentStatus.BADGES.get(code, "secondary")


def role_label(code):
    return ROLE_LABELS.get(code, code)


def image_url(path):
    """Đường dẫn ảnh: URL tuyệt đối giữ nguyên, đường dẫn tương đối lấy trong static, rỗng dùng ảnh mặc định."""
    if not path:
        return url_for("static", filename="img/placeholder.svg")
    if path.startswith(("http://", "https://", "/")):
        return path
    return url_for("static", filename=path)


def mask_name(full_name):
    """'Nguyễn Văn An' -> 'N. V. An' (che bớt họ tên khi hiển thị đánh giá công khai)."""
    parts = (full_name or "").split()
    if not parts:
        return "Khách hàng"
    if len(parts) == 1:
        return parts[0]
    return " ".join(p[0].upper() + "." for p in parts[:-1]) + " " + parts[-1]


def register_filters(app):
    app.jinja_env.filters.update(
        vnd=vnd, dt=dt, role_label=role_label, image_url=image_url, mask_name=mask_name,
        order_status_label=order_status_label, order_status_badge=order_status_badge,
        payment_status_label=payment_status_label, payment_status_badge=payment_status_badge,
    )
