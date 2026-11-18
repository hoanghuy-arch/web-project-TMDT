"""Truy vấn sản phẩm cho khu vực cửa hàng (FR-KH05, FR-KH06). Chỉ đọc dữ liệu."""
import re
import unicodedata

from flask import abort, current_app
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.constants import EntityStatus, OrderStatus, SettingKey
from app.extensions import db
from app.models import (AppSetting, Category, Color, Product, ProductVariant, Review, SalesOrder,
                        SalesOrderItem, Size)


def _remove_accents(text: str) -> str:
    """Chuyển chuỗi tiếng Việt có dấu thành không dấu để hỗ trợ tìm kiếm linh hoạt."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    stripped = re.sub(r"[\u0300-\u036f]", "", normalized)
    return stripped.replace("đ", "d").replace("Đ", "D").lower()


# ------------------------------------------------------------------ điều kiện hiển thị
def _variant_exists(filters=None):
    """Sản phẩm có ít nhất một biến thể đang kinh doanh thỏa MỌI điều kiện (cùng một biến thể)."""
    conds = [ProductVariant.product_id == Product.id, ProductVariant.status == EntityStatus.ACTIVE]
    if filters is not None:
        if filters.sizes:
            conds.append(ProductVariant.size_id.in_(filters.sizes))
        if filters.colors:
            conds.append(ProductVariant.color_id.in_(filters.colors))
        if filters.in_stock:
            conds.append(ProductVariant.stock_quantity - ProductVariant.reserved_quantity > 0)
    return exists().where(*conds)


def _visible_conditions():
    """Khách chỉ thấy sản phẩm đang kinh doanh, thuộc danh mục đang hoạt động và có biến thể để mua."""
    return [
        Product.status == EntityStatus.ACTIVE,
        Product.category_id.in_(select(Category.id).where(Category.is_active.is_(True))),
        _variant_exists(),
    ]


def _card_loaders():
    # Tránh N+1: nạp trước ảnh và biến thể (kèm màu) cho thẻ sản phẩm
    return (selectinload(Product.images),
            selectinload(Product.variants).selectinload(ProductVariant.color))


def _sold_subquery():
    """Tổng số lượng đã bán theo sản phẩm (không tính đơn đã hủy và đơn chưa thanh toán)."""
    return (
        select(ProductVariant.product_id.label("product_id"),
               func.sum(SalesOrderItem.quantity).label("sold"))
        .select_from(SalesOrderItem)
        .join(ProductVariant, ProductVariant.id == SalesOrderItem.product_variant_id)
        .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
        .where(SalesOrder.status.not_in([OrderStatus.CANCELLED, OrderStatus.PENDING_PAYMENT]))
        .group_by(ProductVariant.product_id)
        .subquery()
    )


# ------------------------------------------------------------------ danh mục
def root_categories():
    return db.session.scalars(
        select(Category)
        .where(Category.parent_category_id.is_(None), Category.is_active.is_(True))
        .order_by(Category.name)
        .options(selectinload(Category.children))
    ).all()


def get_active_category(slug):
    return db.session.scalar(select(Category).where(Category.slug == slug, Category.is_active.is_(True)))


def category_ids_with_descendants(category):
    """Lọc theo danh mục cha thì gồm cả sản phẩm của danh mục con đang hoạt động."""
    ids, stack = [], [category]
    while stack:
        current = stack.pop()
        ids.append(current.id)
        stack.extend(c for c in current.children if c.is_active)
    return ids


def category_breadcrumb(category):
    chain = []
    while category is not None:
        chain.append(category)
        category = category.parent
    return list(reversed(chain))


# ------------------------------------------------------------------ danh sách
def search_products(filters, category_ids=None):
    """Trả về đối tượng phân trang (.items, .total, .pages...)."""
    stmt = select(Product).where(*_visible_conditions()).options(*_card_loaders())

    if category_ids:
        stmt = stmt.where(Product.category_id.in_(category_ids))

    for term in filters.terms:
        term_clean = term.strip()
        if not term_clean:
            continue
        term_lower = term_clean.lower()
        slug_term = _remove_accents(term_lower)

        # Hỗ trợ tìm kiếm thông minh: tiếng Việt có dấu, mô tả, và từ khóa không dấu trong slug
        conds = [
            func.lower(Product.name).contains(term_lower, autoescape=True),
            func.lower(Product.description).contains(term_lower, autoescape=True),
        ]
        # Nếu có từ khóa không dấu hợp lệ (không chứa ký tự wildcard % _)
        if slug_term and not any(c in "%_\\ " for c in slug_term):
            conds.extend([
                Product.slug == slug_term,
                Product.slug.like(f"{slug_term}-%"),
                Product.slug.like(f"%-{slug_term}-%"),
                Product.slug.like(f"%-{slug_term}"),
            ])
        stmt = stmt.where(or_(*conds))

    if filters.sizes or filters.colors or filters.in_stock:
        stmt = stmt.where(_variant_exists(filters))

    if filters.min_price is not None:
        stmt = stmt.where(Product.price >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(Product.price <= filters.max_price)

    if filters.sort == "price_asc":
        stmt = stmt.order_by(Product.price.asc(), Product.id.desc())
    elif filters.sort == "price_desc":
        stmt = stmt.order_by(Product.price.desc(), Product.id.desc())
    elif filters.sort == "name_asc":
        stmt = stmt.order_by(Product.name.asc(), Product.id.desc())
    elif filters.sort == "bestselling":
        sold = _sold_subquery()
        stmt = (stmt.outerjoin(sold, sold.c.product_id == Product.id)
                .order_by(func.coalesce(sold.c.sold, 0).desc(), Product.id.desc()))
    else:
        stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())

    return db.paginate(stmt, page=filters.page, per_page=current_app.config["PRODUCTS_PER_PAGE"],
                       error_out=False)


def new_products(limit=8):
    stmt = (select(Product).where(*_visible_conditions()).options(*_card_loaders())
            .order_by(Product.created_at.desc(), Product.id.desc()).limit(limit))
    return db.session.scalars(stmt).all()


def best_selling_products(limit=8):
    """Chỉ gồm sản phẩm đã có lượt bán; chưa có đơn nào thì trả danh sách rỗng."""
    sold = _sold_subquery()
    stmt = (select(Product).join(sold, sold.c.product_id == Product.id)
            .where(*_visible_conditions()).options(*_card_loaders())
            .order_by(sold.c.sold.desc(), Product.id.desc()).limit(limit))
    return db.session.scalars(stmt).all()


def filter_options():
    """Danh sách kích cỡ, màu thực sự đang có ở biến thể kinh doanh (để bộ lọc không hiện mục vô nghĩa)."""
    active = ProductVariant.status == EntityStatus.ACTIVE
    sizes = db.session.scalars(
        select(Size).where(Size.id.in_(select(ProductVariant.size_id).where(active)))
        .order_by(Size.sort_order, Size.name)).all()
    colors = db.session.scalars(
        select(Color).where(Color.id.in_(select(ProductVariant.color_id).where(active)))
        .order_by(Color.name)).all()
    return sizes, colors


# ------------------------------------------------------------------ chi tiết
def get_product_or_404(slug):
    product = db.session.scalar(
        select(Product).where(Product.slug == slug, *_visible_conditions())
        .options(selectinload(Product.images),
                 selectinload(Product.variants).selectinload(ProductVariant.size),
                 selectinload(Product.variants).selectinload(ProductVariant.color),
                 joinedload(Product.category)))
    if product is None:
        abort(404)
    return product


def variant_options(product):
    """Kích cỡ, màu và dữ liệu biến thể (cho JavaScript chọn biến thể)."""
    active = [v for v in product.variants if v.is_active]
    sizes = sorted({v.size for v in active}, key=lambda s: (s.sort_order, s.name))
    colors = sorted({v.color for v in active}, key=lambda c: c.name)
    data = [{"id": v.id, "size_id": v.size_id, "color_id": v.color_id,
             "available": v.available_quantity, "sku": v.sku} for v in active]
    return sizes, colors, data


def low_stock_threshold():
    return AppSetting.get_int(SettingKey.LOW_STOCK_THRESHOLD, current_app.config["DEFAULT_LOW_STOCK_THRESHOLD"])


def related_products(product, limit=4):
    stmt = (select(Product).where(*_visible_conditions(), Product.category_id == product.category_id,
                                  Product.id != product.id)
            .options(*_card_loaders()).order_by(Product.created_at.desc(), Product.id.desc()).limit(limit))
    return db.session.scalars(stmt).all()


def review_summary(product, limit=10):
    """Điểm trung bình, số đánh giá và các đánh giá mới nhất (người đánh giá suy ra từ dòng đơn hàng)."""
    base = (select(Review).join(SalesOrderItem, SalesOrderItem.id == Review.sales_order_item_id)
            .join(ProductVariant, ProductVariant.id == SalesOrderItem.product_variant_id)
            .where(ProductVariant.product_id == product.id))
    avg, count = db.session.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .select_from(Review)
        .join(SalesOrderItem, SalesOrderItem.id == Review.sales_order_item_id)
        .join(ProductVariant, ProductVariant.id == SalesOrderItem.product_variant_id)
        .where(ProductVariant.product_id == product.id)).one()
    items = db.session.scalars(
        base.order_by(Review.created_at.desc(), Review.id.desc()).limit(limit)
        .options(selectinload(Review.order_item).selectinload(SalesOrderItem.order)
                 .selectinload(SalesOrder.account))).all()
    return {"average": round(float(avg), 1) if avg is not None else None, "count": count, "items": items}
