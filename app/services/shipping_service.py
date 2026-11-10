"""Phí vận chuyển theo bảng phí cấu hình (FR-KH08, R14)."""
from dataclasses import dataclass
from decimal import Decimal

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import ShippingFeeRule
from app.services.pricing import compute_shipping_fee


@dataclass
class ShippingQuote:
    fee: Decimal
    free: bool          # được miễn phí nhờ đạt ngưỡng


def _active_rule(province_id):
    return db.session.scalar(select(ShippingFeeRule).where(
        ShippingFeeRule.province_id == province_id, ShippingFeeRule.is_active.is_(True)))


def quote(province_id, subtotal):
    """Ưu tiên quy tắc riêng của tỉnh, nếu không có dùng mức mặc định (province_id NULL).
    Chưa cấu hình quy tắc nào thì phí = 0 và ghi cảnh báo để quản trị viên bổ sung."""
    rule = _active_rule(province_id) or db.session.scalar(select(ShippingFeeRule).where(
        ShippingFeeRule.province_id.is_(None), ShippingFeeRule.is_active.is_(True)))
    if rule is None:
        current_app.logger.warning("Chưa cấu hình bảng phí vận chuyển (kể cả mức mặc định)")
        return ShippingQuote(Decimal(0), False)
    fee, free = compute_shipping_fee(subtotal, rule.fee, rule.free_threshold)
    return ShippingQuote(fee, free)
