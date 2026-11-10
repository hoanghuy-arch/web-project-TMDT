"""Giỏ hàng (FR-KH07, R13). Giỏ hàng KHÔNG giữ tồn kho; việc giữ hàng chỉ xảy ra khi tạo đơn (Task 6).
Giá luôn lấy theo giá hiện tại của sản phẩm; giá chốt vào đơn khi đặt hàng (BR05)."""
from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import CartItem, Product, ProductVariant
from app.services.cart_view import CartLine, CartView, line_issue


class CartError(Exception):
    """Lỗi nghiệp vụ hiển thị cho khách (thông báo tiếng Việt)."""


def is_purchasable(variant):
    """Biến thể đang kinh doanh, sản phẩm đang kinh doanh và thuộc danh mục đang hoạt động."""
    product = variant.product
    return bool(variant.is_active and product.is_active and product.category.is_active)


def _cfg(name):
    return current_app.config[name]


# ------------------------------------------------------------------ đọc giỏ
def get_cart(account):
    items = db.session.scalars(
        select(CartItem).where(CartItem.account_id == account.id)
        .options(selectinload(CartItem.variant).selectinload(ProductVariant.product)
                 .selectinload(Product.images),
                 selectinload(CartItem.variant).selectinload(ProductVariant.product)
                 .selectinload(Product.category),
                 selectinload(CartItem.variant).selectinload(ProductVariant.size),
                 selectinload(CartItem.variant).selectinload(ProductVariant.color))
        .order_by(CartItem.product_variant_id)
    ).all()
    lines = []
    for item in items:
        v = item.variant
        purchasable = is_purchasable(v)
        available = v.available_quantity if purchasable else 0
        lines.append(CartLine(item=item, variant=v, product=v.product, quantity=item.quantity,
                              unit_price=v.product.price, available=available, purchasable=purchasable,
                              issue=line_issue(purchasable, available, item.quantity)))
    return CartView(lines)


def cart_count(account):
    """Tổng số lượng trong giỏ (hiển thị trên thanh menu)."""
    return db.session.scalar(
        select(func.coalesce(func.sum(CartItem.quantity), 0)).where(CartItem.account_id == account.id)) or 0


# ------------------------------------------------------------------ ghi giỏ
def _validate_quantity(quantity):
    maximum = _cfg("CART_MAX_QUANTITY_PER_ITEM")
    if quantity is None or quantity < 1 or quantity > maximum:
        raise CartError(f"Số lượng phải từ 1 đến {maximum}.")
    return quantity


def add_to_cart(account, variant_id, quantity):
    """Trả về (thông báo, mức độ). Cộng dồn nếu biến thể đã có trong giỏ; không vượt tồn khả dụng và giới hạn mỗi dòng."""
    quantity = _validate_quantity(quantity)
    variant = db.session.get(ProductVariant, variant_id) if variant_id else None
    if variant is None or not is_purchasable(variant):
        raise CartError("Sản phẩm này không còn được bán.")
    available = variant.available_quantity
    if available <= 0:
        raise CartError("Phiên bản này đã hết hàng.")

    cap = min(_cfg("CART_MAX_QUANTITY_PER_ITEM"), available)
    item = db.session.get(CartItem, (account.id, variant.id))
    if item is None:
        lines = db.session.scalar(select(func.count()).select_from(CartItem).where(CartItem.account_id == account.id))
        if lines >= _cfg("CART_MAX_LINES"):
            raise CartError(f"Giỏ hàng tối đa {_cfg('CART_MAX_LINES')} sản phẩm khác nhau.")

    current = item.quantity if item else 0
    wanted = current + quantity
    new_quantity = min(wanted, cap)
    if new_quantity == current:                       # đã ở mức tối đa, không thêm được nữa
        raise CartError(f"Bạn đã có {current} sản phẩm này trong giỏ, đây là số lượng tối đa có thể mua.")

    _upsert(account, variant.id, new_quantity)
    name = variant.display_name
    if new_quantity < wanted:
        return f"Đã thêm {name}. Số lượng được giới hạn ở mức {new_quantity} (tồn kho hoặc giới hạn mỗi sản phẩm).", "warning"
    return f"Đã thêm {name} vào giỏ hàng.", "success"


def _upsert(account, variant_id, quantity):
    item = db.session.get(CartItem, (account.id, variant_id))
    if item is None:
        db.session.add(CartItem(account_id=account.id, product_variant_id=variant_id, quantity=quantity))
    else:
        item.quantity = quantity
    try:
        db.session.commit()
    except IntegrityError:        # hai yêu cầu thêm cùng biến thể gần như đồng thời: chuyển sang cập nhật
        db.session.rollback()
        item = db.session.get(CartItem, (account.id, variant_id))
        if item is None:
            raise
        item.quantity = quantity
        db.session.commit()


def _get_item(account, variant_id):
    item = db.session.get(CartItem, (account.id, variant_id)) if variant_id else None
    if item is None:
        raise CartError("Sản phẩm không có trong giỏ hàng.")
    return item


def update_quantity(account, variant_id, quantity):
    """Đặt số lượng cho một dòng. Vượt tồn khả dụng thì hạ xuống bằng tồn khả dụng và báo cho khách."""
    item = _get_item(account, variant_id)
    quantity = _validate_quantity(quantity)
    variant = item.variant
    if not is_purchasable(variant):
        raise CartError("Sản phẩm này đã ngừng kinh doanh. Vui lòng xóa khỏi giỏ hàng.")
    available = variant.available_quantity
    if available <= 0:
        raise CartError("Phiên bản này đã hết hàng. Vui lòng xóa khỏi giỏ hàng.")
    if quantity > available:
        item.quantity = available
        db.session.commit()
        return f"Chỉ còn {available} sản phẩm trong kho, đã điều chỉnh số lượng.", "warning"
    item.quantity = quantity
    db.session.commit()
    return "Đã cập nhật số lượng.", "success"


def remove_item(account, variant_id):
    item = _get_item(account, variant_id)
    db.session.delete(item)
    db.session.commit()


def remove_unavailable(account):
    """Xóa các dòng đã ngừng kinh doanh hoặc hết hàng. Trả về số dòng đã xóa."""
    removed = 0
    for line in get_cart(account).lines:
        if not line.purchasable or line.available <= 0:
            db.session.delete(line.item)
            removed += 1
    db.session.commit()
    return removed


def clear_cart(account):
    """Dùng sau khi đặt hàng thành công (Task 6)."""
    db.session.execute(db.delete(CartItem).where(CartItem.account_id == account.id))
