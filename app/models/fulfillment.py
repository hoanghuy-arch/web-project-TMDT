"""Phân hệ D: vận chuyển và thanh toán (shipping_fee_rule, carrier, shipment, payment).
Cột khớp ERD Phân hệ D."""
from app.constants import PaymentMethod, PaymentStatus
from app.extensions import db
from app.models.base import Money, in_list, utcnow


class ShippingFeeRule(db.Model):
    """R14: quy tắc phí theo tỉnh. province_id NULL = mức mặc định (chỉ nên có đúng 1 dòng, xử lý ở service)."""
    __tablename__ = "shipping_fee_rule"

    id = db.Column(db.Integer, primary_key=True)
    province_id = db.Column(db.Integer, db.ForeignKey("province.id"), unique=True)
    fee = db.Column(Money, nullable=False)
    free_threshold = db.Column(Money)                                      # miễn phí khi tiền hàng đạt ngưỡng
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    province = db.relationship("Province", back_populates="shipping_fee_rule")

    __table_args__ = (
        db.CheckConstraint("fee >= 0", name="fee_non_negative"),
        db.CheckConstraint("free_threshold IS NULL OR free_threshold >= 0", name="threshold_non_negative"),
    )


class Carrier(db.Model):
    __tablename__ = "carrier"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    shipments = db.relationship("Shipment", back_populates="carrier")      # R22


class Shipment(db.Model):
    """R21: đúng 1-1 tùy chọn với đơn, khóa chính chính là sales_order_id."""
    __tablename__ = "shipment"

    sales_order_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"), primary_key=True)
    carrier_id = db.Column(db.Integer, db.ForeignKey("carrier.id"), nullable=False, index=True)
    tracking_code = db.Column(db.String(60), nullable=False)
    shipped_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    delivered_at = db.Column(db.DateTime)

    order = db.relationship("SalesOrder", back_populates="shipment")
    carrier = db.relationship("Carrier", back_populates="shipments")

    __table_args__ = (
        db.UniqueConstraint("carrier_id", "tracking_code", name="uq_shipment_carrier_tracking"),
    )


class Payment(db.Model):
    """R23: một đơn có thể có nhiều giao dịch (thanh toán online thử lại)."""
    __tablename__ = "payment"

    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"), nullable=False, index=True)
    method = db.Column(db.String(10), nullable=False)                      # COD / VNPAY
    status = db.Column(db.String(10), nullable=False, default=PaymentStatus.UNPAID)
    amount = db.Column(Money, nullable=False)                              # số tiền thực thu, dùng đối soát (BR13)
    gateway_txn_ref = db.Column(db.String(64), unique=True)                # mã tham chiếu giao dịch với cổng; NULL với COD
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    order = db.relationship("SalesOrder", back_populates="payments")

    __table_args__ = (
        db.CheckConstraint(in_list("method", PaymentMethod.ALL), name="method_valid"),
        db.CheckConstraint(in_list("status", PaymentStatus.ALL), name="status_valid"),
        db.CheckConstraint("amount >= 0", name="amount_non_negative"),
    )
