"""Mã khuyến mãi (FR-KH08)."""
from sqlalchemy import func, select

from app.constants import OrderStatus
from app.extensions import db
from app.models import Promotion, SalesOrder
from app.models.base import utcnow
from app.services.errors import PromotionError
from app.services.pricing import compute_discount, promotion_problem


def normalize_code(code):
    return (code or "").strip().upper()[:30]


def used_count(promotion):
    """Số lượt đã dùng = số đơn có mã này (suy diễn); đơn đã hủy không tính."""
    return db.session.scalar(
        select(func.count(SalesOrder.id)).where(SalesOrder.promotion_id == promotion.id,
                                                SalesOrder.status != OrderStatus.CANCELLED)) or 0


def evaluate(code, subtotal, lock=False):
    """Kiểm tra mã với tiền hàng. Trả về (promotion, số tiền giảm) hoặc ném PromotionError.
    lock=True khóa dòng mã (SELECT ... FOR UPDATE) để hai đơn đồng thời không cùng vượt giới hạn lượt dùng."""
    stmt = select(Promotion).where(Promotion.code == normalize_code(code))
    if lock:
        stmt = stmt.with_for_update()
    promotion = db.session.scalar(stmt)
    if promotion is None:
        raise PromotionError("Mã khuyến mãi không tồn tại.")
    problem = promotion_problem(promotion, subtotal, utcnow(), used_count(promotion))
    if problem:
        raise PromotionError(problem)
    return promotion, compute_discount(promotion, subtotal)
