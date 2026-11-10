"""Phân hệ E: đổi trả và đánh giá (return_request, return_item, review). Cột khớp ERD Phân hệ E."""
from app.constants import ReturnStatus
from app.extensions import db
from app.models.base import in_list, utcnow


class ReturnRequest(db.Model):
    __tablename__ = "return_request"

    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"), nullable=False, index=True)   # R24
    handled_by_account_id = db.Column(db.Integer, db.ForeignKey("account.id"), index=True)               # R25
    reason = db.Column(db.String(500), nullable=False)                     # lý do khách nêu
    status = db.Column(db.String(10), nullable=False, default=ReturnStatus.PENDING)
    resolution = db.Column(db.String(500))                                 # kết quả xử lý / lý do từ chối của nhân viên
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    resolved_at = db.Column(db.DateTime)

    order = db.relationship("SalesOrder", back_populates="return_requests")
    handled_by = db.relationship("Account")
    items = db.relationship("ReturnItem", back_populates="request", cascade="all, delete-orphan")  # R26

    __table_args__ = (
        db.CheckConstraint(in_list("status", ReturnStatus.ALL), name="status_valid"),
    )

    @property
    def customer(self):
        """Người đặt suy ra từ đơn hàng (không lưu)."""
        return self.order.account


class ReturnItem(db.Model):
    __tablename__ = "return_item"

    id = db.Column(db.Integer, primary_key=True)
    return_request_id = db.Column(db.Integer, db.ForeignKey("return_request.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    sales_order_item_id = db.Column(db.Integer, db.ForeignKey("sales_order_item.id"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)                       # số lượng khách muốn trả
    accepted_quantity = db.Column(db.Integer)                              # số lượng nhân viên chấp nhận sau kiểm tra

    request = db.relationship("ReturnRequest", back_populates="items")
    order_item = db.relationship("SalesOrderItem")

    __table_args__ = (
        db.UniqueConstraint("return_request_id", "sales_order_item_id", name="uq_return_item_request_order_item"),
        db.CheckConstraint("quantity > 0", name="quantity_positive"),
        db.CheckConstraint("accepted_quantity IS NULL OR (accepted_quantity >= 0 AND accepted_quantity <= quantity)",
                           name="accepted_within_quantity"),
    )


class Review(db.Model):
    """R27: mỗi dòng đơn hàng có tối đa 1 đánh giá. Người đánh giá và sản phẩm được suy ra từ dòng đơn."""
    __tablename__ = "review"

    id = db.Column(db.Integer, primary_key=True)
    sales_order_item_id = db.Column(db.Integer, db.ForeignKey("sales_order_item.id"), nullable=False, unique=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(1000))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    order_item = db.relationship("SalesOrderItem", back_populates="review")

    __table_args__ = (
        db.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
    )

    @property
    def account(self):
        return self.order_item.order.account

    @property
    def product(self):
        return self.order_item.variant.product
