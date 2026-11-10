"""Phân hệ F: kho và nhà cung cấp (supplier, stock_receipt, stock_receipt_item, stock_transaction).
Cột khớp ERD Phân hệ F."""
from app.constants import EntityStatus, ReceiptStatus, StockTxType
from app.extensions import db
from app.models.base import Money, in_list, make_append_only, utcnow


class Supplier(db.Model):
    __tablename__ = "supplier"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    contact_name = db.Column(db.String(100))
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(255))
    address_detail = db.Column(db.String(255))
    status = db.Column(db.String(10), nullable=False, default=EntityStatus.ACTIVE)

    receipts = db.relationship("StockReceipt", back_populates="supplier")   # R28

    __table_args__ = (
        db.CheckConstraint(in_list("status", EntityStatus.ALL), name="status_valid"),
    )

    @property
    def is_active(self):
        return self.status == EntityStatus.ACTIVE


class StockReceipt(db.Model):
    __tablename__ = "stock_receipt"

    id = db.Column(db.Integer, primary_key=True)
    receipt_code = db.Column(db.String(30), nullable=False, unique=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=False, index=True)             # R28
    created_by_account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False, index=True)   # R29
    status = db.Column(db.String(10), nullable=False, default=ReceiptStatus.DRAFT)
    note = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    confirmed_at = db.Column(db.DateTime)

    supplier = db.relationship("Supplier", back_populates="receipts")
    created_by = db.relationship("Account")
    items = db.relationship("StockReceiptItem", back_populates="receipt", cascade="all, delete-orphan")  # R30

    __table_args__ = (
        db.CheckConstraint(in_list("status", ReceiptStatus.ALL), name="status_valid"),
    )

    @property
    def total_cost(self):
        return sum(i.received_quantity * i.unit_cost for i in self.items)


class StockReceiptItem(db.Model):
    """Chỉ received_quantity (số lượng thực nhận) mới được cộng vào tồn kho."""
    __tablename__ = "stock_receipt_item"

    id = db.Column(db.Integer, primary_key=True)
    stock_receipt_id = db.Column(db.Integer, db.ForeignKey("stock_receipt.id", ondelete="CASCADE"),
                                 nullable=False, index=True)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=False, index=True)
    ordered_quantity = db.Column(db.Integer, nullable=False)
    received_quantity = db.Column(db.Integer, nullable=False, default=0)
    unit_cost = db.Column(Money, nullable=False, default=0)

    receipt = db.relationship("StockReceipt", back_populates="items")
    variant = db.relationship("ProductVariant")

    __table_args__ = (
        db.UniqueConstraint("stock_receipt_id", "product_variant_id", name="uq_receipt_item_receipt_variant"),
        db.CheckConstraint("ordered_quantity > 0", name="ordered_positive"),
        db.CheckConstraint("received_quantity >= 0", name="received_non_negative"),
        db.CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
    )


class StockTransaction(db.Model):
    """Sổ cái biến động kho, CHỈ THÊM. Số dư hiện tại (stock_quantity, reserved_quantity) của biến thể
    phải khớp tổng stock_delta, reserved_delta của các giao dịch."""
    __tablename__ = "stock_transaction"

    id = db.Column(db.Integer, primary_key=True)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=False, index=True)  # R31
    # Nguồn phát sinh: tối đa MỘT trong ba (CHECK bên dưới)
    sales_order_id = db.Column(db.Integer, db.ForeignKey("sales_order.id"), index=True)                  # R32
    stock_receipt_item_id = db.Column(db.Integer, db.ForeignKey("stock_receipt_item.id"), index=True)    # R33
    return_item_id = db.Column(db.Integer, db.ForeignKey("return_item.id"), index=True)                  # R34
    created_by_account_id = db.Column(db.Integer, db.ForeignKey("account.id"))                           # R35, NULL = hệ thống
    transaction_type = db.Column(db.String(10), nullable=False)
    stock_delta = db.Column(db.Integer, nullable=False, default=0)
    reserved_delta = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.String(500))                                       # bắt buộc lý do với ADJUST (kiểm ở service)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    variant = db.relationship("ProductVariant")
    created_by = db.relationship("Account")

    __table_args__ = (
        db.CheckConstraint(in_list("transaction_type", StockTxType.ALL), name="type_valid"),
        db.CheckConstraint(
            "(CASE WHEN sales_order_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN stock_receipt_item_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN return_item_id IS NOT NULL THEN 1 ELSE 0 END) <= 1",
            name="single_source"),
    )


make_append_only(StockTransaction)
