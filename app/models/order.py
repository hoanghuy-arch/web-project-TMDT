"""Phân hệ C: giỏ hàng, khuyến mãi, đơn hàng
(cart_item, promotion, sales_order, sales_order_item, sales_order_status_history).
Cột khớp ERD Phân hệ C."""
from app.constants import DiscountType, EntityStatus, OrderStatus, PaymentMethod, can_transition
from app.extensions import db
from app.models.base import Money, TimestampMixin, in_list, make_append_only, utcnow


class CartItem(db.Model):
    """R13: giỏ hàng = quan hệ N-N account - product_variant, khóa chính kép."""
    __tablename__ = "cart_item"

    account_id = db.Column(db.Integer, db.ForeignKey("account.id", ondelete="CASCADE"), primary_key=True)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variant.id", ondelete="CASCADE"),
                                   primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    account = db.relationship("Account", back_populates="cart_items")
    variant = db.relationship("ProductVariant")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="quantity_positive"),
    )


class Promotion(db.Model):
    __tablename__ = "promotion"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), nullable=False, unique=True)
    discount_type = db.Column(db.String(10), nullable=False)               # PERCENT / FIXED
    discount_value = db.Column(Money, nullable=False)                      # % hoặc VND
    min_order_value = db.Column(Money, nullable=False, default=0)
    max_discount = db.Column(Money)                                        # trần giảm khi giảm theo %
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    usage_limit = db.Column(db.Integer)                                    # NULL = không giới hạn
    status = db.Column(db.String(10), nullable=False, default=EntityStatus.ACTIVE)

    orders = db.relationship("SalesOrder", back_populates="promotion")     # R17

    __table_args__ = (
        db.CheckConstraint(in_list("discount_type", DiscountType.ALL), name="type_valid"),
        db.CheckConstraint(in_list("status", EntityStatus.ALL), name="status_valid"),
        db.CheckConstraint("discount_value > 0", name="value_positive"),
        db.CheckConstraint("min_order_value >= 0", name="min_order_non_negative"),
        db.CheckConstraint("max_discount IS NULL OR max_discount >= 0", name="max_discount_non_negative"),
        db.CheckConstraint("usage_limit IS NULL OR usage_limit >= 0", name="usage_limit_non_negative"),
        db.CheckConstraint("end_at > start_at", name="period_valid"),
    )

    @property
    def is_active(self):
        return self.status == EntityStatus.ACTIVE

    @property
    def used_count(self):
        """Số lượt đã dùng = số đơn có promotion_id này (suy diễn). Không tính đơn đã hủy."""
        return sum(1 for o in self.orders if o.status != OrderStatus.CANCELLED)


class SalesOrder(TimestampMixin, db.Model):
    __tablename__ = "sales_order"

    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(30), nullable=False, unique=True)     # mã hiển thị cho khách
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False, index=True)   # R15
    address_id = db.Column(db.Integer, nullable=False, index=True)                                  # R16
    promotion_id = db.Column(db.Integer, db.ForeignKey("promotion.id"), index=True)                 # R17
    status = db.Column(db.String(20), nullable=False, default=OrderStatus.PENDING_CONFIRM, index=True)
    discount_amount = db.Column(Money, nullable=False, default=0)          # lưu tại thời điểm đặt (BR16)
    shipping_fee = db.Column(Money, nullable=False, default=0)             # lưu tại thời điểm đặt (BR17)
    note = db.Column(db.String(500))

    account = db.relationship("Account", back_populates="orders", foreign_keys=[account_id])
    # Chỉ nối theo address.id; việc "địa chỉ thuộc đúng tài khoản" do khóa ngoại kép bên dưới bảo đảm ở DB
    address = db.relationship("Address", primaryjoin="SalesOrder.address_id == Address.id",
                              foreign_keys=[address_id])
    promotion = db.relationship("Promotion", back_populates="orders")
    items = db.relationship("SalesOrderItem", back_populates="order", cascade="all, delete-orphan")   # R18
    status_history = db.relationship("SalesOrderStatusHistory", back_populates="order",
                                     order_by="SalesOrderStatusHistory.id")                           # R19
    payments = db.relationship("Payment", back_populates="order", order_by="Payment.id")              # R23
    shipment = db.relationship("Shipment", back_populates="order", uselist=False)                     # R21
    return_requests = db.relationship("ReturnRequest", back_populates="order")                        # R24

    __table_args__ = (
        # Địa chỉ giao phải thuộc đúng tài khoản đặt hàng
        db.ForeignKeyConstraint(["address_id", "account_id"], ["address.id", "address.account_id"],
                                name="fk_sales_order_address_account"),
        db.CheckConstraint(in_list("status", OrderStatus.ALL), name="status_valid"),
        db.CheckConstraint("discount_amount >= 0", name="discount_non_negative"),
        db.CheckConstraint("shipping_fee >= 0", name="shipping_fee_non_negative"),
    )

    # --- giá trị suy diễn (không lưu) ---
    @property
    def subtotal(self):
        return sum(i.line_total for i in self.items)

    @property
    def total_amount(self):
        """Tổng tiền = tổng thành tiền các dòng - discount_amount + shipping_fee."""
        return self.subtotal - (self.discount_amount or 0) + (self.shipping_fee or 0)

    @property
    def latest_payment(self):
        return self.payments[-1] if self.payments else None

    @property
    def payment_status(self):
        p = self.latest_payment
        return p.status if p else None

    @property
    def payment_method(self):
        p = self.latest_payment
        return p.method if p else None

    @property
    def is_cod(self):
        return self.payment_method == PaymentMethod.COD

    @property
    def total_quantity(self):
        return sum(i.quantity for i in self.items)

    def can_transition_to(self, new_status):
        return can_transition(self.status, new_status)


class SalesOrderItem(db.Model):
    __tablename__ = "sales_order_item"

    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"), nullable=False, index=True)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(Money, nullable=False)                          # giá tại thời điểm đặt (BR05)

    order = db.relationship("SalesOrder", back_populates="items")
    variant = db.relationship("ProductVariant")
    review = db.relationship("Review", back_populates="order_item", uselist=False)   # R27

    __table_args__ = (
        db.UniqueConstraint("sales_order_id", "product_variant_id", name="uq_order_item_order_variant"),
        db.CheckConstraint("quantity > 0", name="quantity_positive"),
        db.CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
    )

    @property
    def line_total(self):
        return (self.quantity or 0) * (self.unit_price or 0)


class SalesOrderStatusHistory(db.Model):
    """R19, R20: lịch sử chuyển trạng thái, CHỈ THÊM. Trạng thái cũ = to_status của dòng liền trước."""
    __tablename__ = "sales_order_status_history"

    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"), nullable=False, index=True)
    changed_by_account_id = db.Column(db.Integer, db.ForeignKey("account.id"))   # NULL khi hệ thống tự chuyển
    to_status = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(500))                                           # bắt buộc khi hủy (kiểm ở service)
    changed_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    order = db.relationship("SalesOrder", back_populates="status_history")
    changed_by = db.relationship("Account")

    __table_args__ = (
        db.CheckConstraint(in_list("to_status", OrderStatus.ALL), name="to_status_valid"),
    )


make_append_only(SalesOrderStatusHistory)
