"""Đánh giá sản phẩm đã mua (FR-KH14, R27): mỗi dòng đơn hàng được đánh giá tối đa một lần."""
from sqlalchemy.exc import IntegrityError

from app.constants import OrderStatus
from app.extensions import db
from app.models import Review
from app.services.errors import ReviewError

# Đơn đã được giao tới khách (kể cả khi sau đó có đổi trả)
REVIEWABLE_STATUSES = (OrderStatus.COMPLETED, OrderStatus.RETURNING, OrderStatus.RETURNED)


def review_blocker(order, item):
    if order.status not in REVIEWABLE_STATUSES:
        return "Bạn chỉ có thể đánh giá sau khi đã nhận hàng."
    if item.review is not None:
        return "Bạn đã đánh giá sản phẩm này rồi."
    return None


def create_review(account, order, item, rating, comment):
    if order.account_id != account.id or item.sales_order_id != order.id:
        raise ReviewError("Bạn không có quyền đánh giá sản phẩm này.")
    blocker = review_blocker(order, item)
    if blocker:
        raise ReviewError(blocker)
    if rating is None or not 1 <= rating <= 5:
        raise ReviewError("Vui lòng chọn số sao từ 1 đến 5.")
    comment = (comment or "").strip()
    if len(comment) > 1000:
        raise ReviewError("Nhận xét tối đa 1000 ký tự.")
    review = Review(sales_order_item_id=item.id, rating=rating, comment=comment or None)
    db.session.add(review)
    try:
        db.session.commit()
    except IntegrityError:               # hai lần gửi gần như đồng thời: ràng buộc UNIQUE chặn bản thứ hai
        db.session.rollback()
        raise ReviewError("Bạn đã đánh giá sản phẩm này rồi.")
    return review
