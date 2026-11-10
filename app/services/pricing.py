"""Quy tắc tính tiền: giảm giá và phí vận chuyển (thuần Python, không truy cập DB nên dễ kiểm thử).
Tiền là VND không có phần lẻ; mọi phép tính làm tròn xuống đồng."""
from decimal import ROUND_DOWN, Decimal

from app.constants import DiscountType
from app.utils.formatters import vnd

_ONE = Decimal(1)


def _dong(value):
    return Decimal(value).quantize(_ONE, rounding=ROUND_DOWN)


def promotion_problem(promo, subtotal, now, used_count):
    """Trả về thông báo lỗi nếu mã không áp dụng được, ngược lại trả None.
    promo cần có: is_active, start_at, end_at, min_order_value, usage_limit."""
    if not promo.is_active:
        return "Mã khuyến mãi đã ngừng áp dụng."
    if now < promo.start_at:
        return "Mã khuyến mãi chưa đến thời gian áp dụng."
    if now > promo.end_at:
        return "Mã khuyến mãi đã hết hạn."
    if Decimal(subtotal) < Decimal(promo.min_order_value):
        return f"Đơn hàng tối thiểu {vnd(promo.min_order_value)} để dùng mã này."
    if promo.usage_limit is not None and used_count >= promo.usage_limit:
        return "Mã khuyến mãi đã hết lượt sử dụng."
    return None


def compute_discount(promo, subtotal):
    """Số tiền giảm: theo % (có trần max_discount) hoặc số tiền cố định; không bao giờ vượt tiền hàng."""
    subtotal = Decimal(subtotal)
    if promo.discount_type == DiscountType.PERCENT:
        amount = _dong(subtotal * Decimal(promo.discount_value) / Decimal(100))
        if promo.max_discount is not None:
            amount = min(amount, Decimal(promo.max_discount))
    else:
        amount = Decimal(promo.discount_value)
    return max(Decimal(0), min(_dong(amount), subtotal))


def compute_shipping_fee(subtotal, fee, free_threshold):
    """Trả về (phí phải trả, được miễn phí không). Miễn phí khi tiền hàng (trước giảm giá) đạt ngưỡng."""
    fee = Decimal(fee)
    if free_threshold is not None and Decimal(subtotal) >= Decimal(free_threshold) and fee > 0:
        return Decimal(0), True
    return fee, False
