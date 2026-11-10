"""Phân hệ B: sản phẩm (category, product, product_image, product_variant, size, color).
Cột khớp ERD Phân hệ B."""
from app.constants import EntityStatus
from app.extensions import db
from app.models.base import Money, in_list, utcnow


class Category(db.Model):
    __tablename__ = "category"

    id = db.Column(db.Integer, primary_key=True)
    parent_category_id = db.Column(db.Integer, db.ForeignKey("category.id"), index=True)   # R07 đệ quy
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(120), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    parent = db.relationship("Category", remote_side=[id], back_populates="children")
    children = db.relationship("Category", back_populates="parent")
    products = db.relationship("Product", back_populates="category")                        # R08


class Size(db.Model):
    __tablename__ = "size"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, unique=True)          # S, M, L, XL...
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    variants = db.relationship("ProductVariant", back_populates="size")   # R11


class Color(db.Model):
    __tablename__ = "color"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    hex_code = db.Column(db.String(7), nullable=False)                    # #RRGGBB để hiển thị ô màu

    variants = db.relationship("ProductVariant", back_populates="color")  # R12


class Product(db.Model):
    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), nullable=False, unique=True)
    description = db.Column(db.Text)
    price = db.Column(Money, nullable=False)                              # VND
    status = db.Column(db.String(10), nullable=False, default=EntityStatus.ACTIVE)   # trạng thái kinh doanh
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    category = db.relationship("Category", back_populates="products")
    images = db.relationship("ProductImage", back_populates="product", cascade="all, delete-orphan",
                             order_by="ProductImage.sort_order")           # R09
    variants = db.relationship("ProductVariant", back_populates="product")  # R10

    __table_args__ = (
        db.CheckConstraint("price >= 0", name="price_non_negative"),
        db.CheckConstraint(in_list("status", EntityStatus.ALL), name="status_valid"),
    )

    @property
    def is_active(self):
        return self.status == EntityStatus.ACTIVE

    @property
    def primary_image(self):
        for img in self.images:
            if img.is_primary:
                return img
        return self.images[0] if self.images else None

    @property
    def total_available(self):
        return sum(v.available_quantity for v in self.variants if v.is_active)

    @property
    def in_stock(self):
        return self.total_available > 0

    @property
    def available_colors(self):
        """Các màu còn hàng (hiển thị chấm màu trên thẻ sản phẩm)."""
        seen = {}
        for v in self.variants:
            if v.is_active and v.available_quantity > 0:
                seen.setdefault(v.color_id, v.color)
        return sorted(seen.values(), key=lambda c: c.name)


class ProductImage(db.Model):
    __tablename__ = "product_image"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True)
    url = db.Column(db.String(500), nullable=False)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    product = db.relationship("Product", back_populates="images")


class ProductVariant(db.Model):
    """Biến thể = sản phẩm + kích cỡ + màu. Tồn kho quản lý ở cấp biến thể."""
    __tablename__ = "product_variant"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)   # R10
    size_id = db.Column(db.Integer, db.ForeignKey("size.id"), nullable=False)                     # R11
    color_id = db.Column(db.Integer, db.ForeignKey("color.id"), nullable=False)                   # R12
    sku = db.Column(db.String(50), nullable=False, unique=True)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)      # số dư kho, lưu có chủ đích
    reserved_quantity = db.Column(db.Integer, nullable=False, default=0)   # số đang giữ, lưu có chủ đích
    status = db.Column(db.String(10), nullable=False, default=EntityStatus.ACTIVE)

    product = db.relationship("Product", back_populates="variants")
    size = db.relationship("Size", back_populates="variants")
    color = db.relationship("Color", back_populates="variants")

    __table_args__ = (
        db.UniqueConstraint("product_id", "size_id", "color_id", name="uq_variant_product_size_color"),
        # Không để tồn kho âm; lượng giữ không vượt tồn kho (ràng buộc cuối cùng ở tầng DB)
        db.CheckConstraint("stock_quantity >= 0", name="stock_non_negative"),
        db.CheckConstraint("reserved_quantity >= 0", name="reserved_non_negative"),
        db.CheckConstraint("reserved_quantity <= stock_quantity", name="reserved_within_stock"),
        db.CheckConstraint(in_list("status", EntityStatus.ALL), name="status_valid"),
    )

    @property
    def is_active(self):
        return self.status == EntityStatus.ACTIVE

    @property
    def available_quantity(self):
        """Số lượng khả dụng = stock_quantity - reserved_quantity (suy diễn, không lưu)."""
        return (self.stock_quantity or 0) - (self.reserved_quantity or 0)

    @property
    def display_name(self):
        return f"{self.product.name} - {self.size.name} - {self.color.name}"
