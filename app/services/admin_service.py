"""Dịch vụ nghiệp vụ cho khu vực Quản trị viên (Task 9: FR-QT01..09)."""
from datetime import datetime, timedelta
from decimal import Decimal
import re
import unicodedata

from flask import current_app
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import selectinload
from werkzeug.security import generate_password_hash

from app.constants import (DiscountType, EntityStatus, OrderStatus,
                           PaymentStatus, Perm, ReturnStatus)
from app.extensions import db
from app.models import (Account, AppSetting, AuditLog, Carrier, Category,
                        Color, Permission, Product, ProductImage,
                        ProductVariant, Promotion, Province, ReturnRequest,
                        Role, SalesOrder, SalesOrderItem, ShippingFeeRule,
                        Size, Supplier)
from app.models.base import utcnow
from app.services import audit_service


# ------------------------------------------------------------------ Xử lý Slug Tiếng Việt
_VI_MAP = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
    'đ': 'd',
    'À': 'a', 'Á': 'a', 'Ả': 'a', 'Ã': 'a', 'Ạ': 'a',
    'Ă': 'a', 'Ằ': 'a', 'Ắ': 'a', 'Ẳ': 'a', 'Ẵ': 'a', 'Ặ': 'a',
    'Â': 'a', 'Ầ': 'a', 'Ấ': 'a', 'Ẩ': 'a', 'Ẫ': 'a', 'Ậ': 'a',
    'È': 'e', 'É': 'e', 'Ẻ': 'e', 'Ẽ': 'e', 'Ẹ': 'e',
    'Ê': 'e', 'Ề': 'e', 'Ế': 'e', 'Ể': 'e', 'Ễ': 'e', 'Ệ': 'e',
    'Ì': 'i', 'Í': 'i', 'Ỉ': 'i', 'Ĩ': 'i', 'Ị': 'i',
    'Ò': 'o', 'Ó': 'o', 'Ỏ': 'o', 'Õ': 'o', 'Ọ': 'o',
    'Ô': 'o', 'Ồ': 'o', 'Ố': 'o', 'Ổ': 'o', 'Ỗ': 'o', 'Ộ': 'o',
    'Ơ': 'o', 'Ờ': 'o', 'Ớ': 'o', 'Ở': 'o', 'Ỡ': 'o', 'Ợ': 'o',
    'Ù': 'u', 'Ú': 'u', 'Ủ': 'u', 'Ũ': 'u', 'Ụ': 'u',
    'Ư': 'u', 'Ừ': 'u', 'Ứ': 'u', 'Ử': 'u', 'Ữ': 'u', 'Ự': 'u',
    'Ỳ': 'y', 'Ý': 'y', 'Ỷ': 'y', 'Ỹ': 'y', 'Ỵ': 'y',
    'Đ': 'd',
}


def slugify(text):
    text = text or ""
    for k, v in _VI_MAP.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '-', text)


def unique_slug(model_cls, name, current_id=None):
    base = slugify(name) or "item"
    candidate = base
    i = 2
    while True:
        stmt = select(model_cls.id).where(model_cls.slug == candidate)
        if current_id:
            stmt = stmt.where(model_cls.id != current_id)
        if db.session.scalar(stmt) is None:
            return candidate
        candidate = f"{base}-{i}"
        i += 1


# ------------------------------------------------------------------ 1. Báo cáo & Thống kê (FR-QT08)
def dashboard_stats():
    """Số liệu tổng quan cho trang chủ quản trị."""
    now = utcnow()
    start_of_day = datetime(now.year, now.month, now.day)
    start_of_month = datetime(now.year, now.month, 1)

    # Đơn hàng hôm nay & trong tháng
    orders_today = db.session.scalar(select(func.count(SalesOrder.id)).where(SalesOrder.created_at >= start_of_day)) or 0
    orders_month = db.session.scalar(select(func.count(SalesOrder.id)).where(SalesOrder.created_at >= start_of_month)) or 0

    # Doanh thu ước tính (đơn hoàn thành)
    completed_orders = db.session.scalars(
        select(SalesOrder).where(SalesOrder.status == OrderStatus.COMPLETED)
    ).all()
    revenue_total = sum((o.total_amount for o in completed_orders), Decimal(0))

    # Đếm đơn theo trạng thái
    status_counts = dict(
        db.session.execute(
            select(SalesOrder.status, func.count(SalesOrder.id)).group_by(SalesOrder.status)
        ).all()
    )

    # Khách hàng & Nhân viên
    user_counts = dict(
        db.session.execute(
            select(Role.name, func.count(Account.id))
            .join(Account, Account.role_id == Role.id)
            .group_by(Role.name)
        ).all()
    )

    # Biến thể sắp hết hàng
    low_thresh = AppSetting.get_int("low_stock_threshold", 5)
    low_stock = db.session.scalar(
        select(func.count(ProductVariant.id)).where(
            ProductVariant.status == EntityStatus.ACTIVE,
            ProductVariant.stock_quantity - ProductVariant.reserved_quantity <= low_thresh
        )
    ) or 0

    # Đổi trả chờ xử lý
    pending_returns = db.session.scalar(
        select(func.count(ReturnRequest.id)).where(ReturnRequest.status == ReturnStatus.PENDING)
    ) or 0

    return {
        "orders_today": orders_today,
        "orders_month": orders_month,
        "revenue_total": revenue_total,
        "status_counts": status_counts,
        "user_counts": user_counts,
        "low_stock": low_stock,
        "pending_returns": pending_returns,
    }


def revenue_report(days=30):
    """Báo cáo doanh thu theo ngày trong N ngày gần nhất."""
    now = utcnow()
    start_date = now - timedelta(days=days)

    orders = db.session.scalars(
        select(SalesOrder)
        .where(SalesOrder.status == OrderStatus.COMPLETED, SalesOrder.created_at >= start_date)
        .order_by(SalesOrder.created_at.asc())
    ).all()

    daily = {}
    for o in orders:
        d_str = o.created_at.strftime("%d/%m")
        daily[d_str] = daily.get(d_str, Decimal(0)) + o.total_amount

    return daily


def best_selling_products(limit=10):
    """Top sản phẩm bán chạy nhất."""
    rows = db.session.execute(
        select(Product, func.sum(SalesOrderItem.quantity).label("total_sold"))
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .join(SalesOrderItem, SalesOrderItem.product_variant_id == ProductVariant.id)
        .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
        .where(SalesOrder.status.not_in([OrderStatus.CANCELLED, OrderStatus.PENDING_PAYMENT]))
        .group_by(Product.id)
        .order_by(desc("total_sold"))
        .limit(limit)
    ).all()
    return [(row[0], row[1]) for row in rows]


def pending_refunds():
    """Các đơn hàng đổi trả / đã hủy cần đối soát hoàn tiền."""
    orders = db.session.scalars(
        select(SalesOrder)
        .where(SalesOrder.status.in_([OrderStatus.RETURNING, OrderStatus.RETURNED, OrderStatus.CANCELLED]))
        .order_by(SalesOrder.updated_at.desc())
        .limit(20)
    ).all()
    return orders


# ------------------------------------------------------------------ 2. Quản lý Danh mục (FR-QT02)
def get_categories():
    return db.session.scalars(select(Category).order_by(Category.name.asc())).all()


def get_category(cat_id):
    return db.session.get(Category, cat_id)


def save_category(name, parent_id, is_active, cat_id=None, actor=None):
    slug = unique_slug(Category, name, current_id=cat_id)
    if cat_id:
        cat = db.session.get(Category, cat_id)
        old_val = {"name": cat.name, "parent_id": cat.parent_category_id, "is_active": cat.is_active}
        cat.name = name
        cat.slug = slug
        cat.parent_category_id = parent_id if parent_id and parent_id != cat_id else None
        cat.is_active = is_active
        action = "category.update"
    else:
        cat = Category(name=name, slug=slug, parent_category_id=parent_id or None, is_active=is_active)
        db.session.add(cat)
        db.session.flush()
        old_val = None
        action = "category.create"

    audit_service.record(action, "category", cat.id, old_val, {"name": name, "is_active": is_active}, actor)
    db.session.commit()
    return cat


def toggle_category(cat_id, actor=None):
    cat = db.session.get(Category, cat_id)
    if cat:
        old_val = {"is_active": cat.is_active}
        cat.is_active = not cat.is_active
        audit_service.record("category.toggle", "category", cat.id, old_val, {"is_active": cat.is_active}, actor)
        db.session.commit()
    return cat


# ------------------------------------------------------------------ 3. Quản lý Thuộc tính: Size & Color
def get_sizes():
    return db.session.scalars(select(Size).order_by(Size.sort_order.asc(), Size.name.asc())).all()


def save_size(name, sort_order, size_id=None, actor=None):
    if size_id:
        s = db.session.get(Size, size_id)
        s.name = name
        s.sort_order = sort_order
        action = "size.update"
    else:
        s = Size(name=name, sort_order=sort_order)
        db.session.add(s)
        db.session.flush()
        action = "size.create"
    audit_service.record(action, "size", s.id, None, {"name": name, "sort_order": sort_order}, actor)
    db.session.commit()
    return s


def get_colors():
    return db.session.scalars(select(Color).order_by(Color.name.asc())).all()


def save_color(name, hex_code, color_id=None, actor=None):
    if color_id:
        c = db.session.get(Color, color_id)
        c.name = name
        c.hex_code = hex_code
        action = "color.update"
    else:
        c = Color(name=name, hex_code=hex_code)
        db.session.add(c)
        db.session.flush()
        action = "color.create"
    audit_service.record(action, "color", c.id, None, {"name": name, "hex_code": hex_code}, actor)
    db.session.commit()
    return c


# ------------------------------------------------------------------ 4. Quản lý Sản phẩm, Biến thể, Ảnh (FR-QT01)
def search_products(q=None, cat_id=None, status=None, page=1, per_page=20):
    stmt = select(Product).options(
        selectinload(Product.category),
        selectinload(Product.images),
        selectinload(Product.variants)
    )
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    if cat_id:
        stmt = stmt.where(Product.category_id == cat_id)
    if status in EntityStatus.ALL:
        stmt = stmt.where(Product.status == status)

    stmt = stmt.order_by(Product.created_at.desc())
    return db.paginate(stmt, page=page, per_page=per_page, error_out=False)


def get_product(product_id):
    return db.session.get(Product, product_id)


def save_product(name, category_id, price, description, status, product_id=None, actor=None):
    slug = unique_slug(Product, name, current_id=product_id)
    if product_id:
        p = db.session.get(Product, product_id)
        old_val = {"name": p.name, "price": str(p.price), "status": p.status}
        p.name = name
        p.slug = slug
        p.category_id = category_id
        p.price = price
        p.description = description
        p.status = status
        action = "product.update"
    else:
        p = Product(name=name, slug=slug, category_id=category_id, price=price,
                    description=description, status=status)
        db.session.add(p)
        db.session.flush()
        old_val = None
        action = "product.create"

    audit_service.record(action, "product", p.id, old_val,
                         {"name": name, "price": str(price), "status": status}, actor)
    db.session.commit()
    return p


def toggle_product_status(product_id, actor=None):
    p = db.session.get(Product, product_id)
    if p:
        new_status = EntityStatus.INACTIVE if p.status == EntityStatus.ACTIVE else EntityStatus.ACTIVE
        old_val = {"status": p.status}
        p.status = new_status
        audit_service.record("product.toggle_status", "product", p.id, old_val, {"status": new_status}, actor)
        db.session.commit()
    return p


def add_product_variant(product_id, size_id, color_id, sku, initial_stock=0, status=EntityStatus.ACTIVE, actor=None):
    existing = db.session.scalar(
        select(ProductVariant).where(ProductVariant.product_id == product_id,
                                     ProductVariant.size_id == size_id,
                                     ProductVariant.color_id == color_id)
    )
    if existing:
        raise ValueError("Biến thể với kích cỡ và màu sắc này đã tồn tại.")

    sku_check = db.session.scalar(select(ProductVariant).where(ProductVariant.sku == sku))
    if sku_check:
        raise ValueError("Mã SKU này đã tồn tại trên hệ thống.")

    v = ProductVariant(product_id=product_id, size_id=size_id, color_id=color_id, sku=sku,
                       stock_quantity=max(initial_stock, 0), reserved_quantity=0, status=status)
    db.session.add(v)
    db.session.flush()
    audit_service.record("variant.create", "product_variant", v.id, None,
                         {"sku": sku, "stock": initial_stock, "status": status}, actor)
    db.session.commit()
    return v


def add_product_image(product_id, url, is_primary=False, sort_order=0, actor=None):
    if is_primary:
        # Nếu đặt ảnh chính, bỏ ảnh chính của các ảnh khác
        for img in db.session.scalars(select(ProductImage).where(ProductImage.product_id == product_id)).all():
            img.is_primary = False

    img = ProductImage(product_id=product_id, url=url, is_primary=is_primary, sort_order=sort_order)
    db.session.add(img)
    db.session.flush()
    audit_service.record("product_image.add", "product_image", img.id, None, {"url": url}, actor)
    db.session.commit()
    return img


def delete_product_image(image_id, actor=None):
    img = db.session.get(ProductImage, image_id)
    if img:
        audit_service.record("product_image.delete", "product_image", img.id, {"url": img.url}, None, actor)
        db.session.delete(img)
        db.session.commit()


# ------------------------------------------------------------------ 5. Quản lý Nhà cung cấp (FR-QT04) & Vận chuyển
def get_suppliers():
    return db.session.scalars(select(Supplier).order_by(Supplier.name.asc())).all()


def get_supplier(supplier_id):
    return db.session.get(Supplier, supplier_id)


def save_supplier(name, contact_name, phone, email, address_detail, status=EntityStatus.ACTIVE,
                  supplier_id=None, actor=None):
    if supplier_id:
        s = db.session.get(Supplier, supplier_id)
        old_val = {"name": s.name, "phone": s.phone, "status": s.status}
        s.name = name
        s.contact_name = contact_name
        s.phone = phone
        s.email = email
        s.address_detail = address_detail
        s.status = status
        action = "supplier.update"
    else:
        s = Supplier(name=name, contact_name=contact_name, phone=phone, email=email,
                     address_detail=address_detail, status=status)
        db.session.add(s)
        db.session.flush()
        old_val = None
        action = "supplier.create"

    audit_service.record(action, "supplier", s.id, old_val, {"name": name, "status": status}, actor)
    db.session.commit()
    return s


def get_carriers():
    return db.session.scalars(select(Carrier).order_by(Carrier.name.asc())).all()


def save_carrier(name, is_active=True, carrier_id=None, actor=None):
    if carrier_id:
        c = db.session.get(Carrier, carrier_id)
        c.name = name
        c.is_active = is_active
        action = "carrier.update"
    else:
        c = Carrier(name=name, is_active=is_active)
        db.session.add(c)
        db.session.flush()
        action = "carrier.create"
    audit_service.record(action, "carrier", c.id, None, {"name": name, "is_active": is_active}, actor)
    db.session.commit()
    return c


# ------------------------------------------------------------------ 6. Quản lý Khuyến mãi (FR-QT06) & Phí ship (FR-QT07)
def get_promotions():
    return db.session.scalars(select(Promotion).order_by(Promotion.start_at.desc())).all()


def get_promotion(promo_id):
    return db.session.get(Promotion, promo_id)


def save_promotion(code, discount_type, discount_value, min_order_value, max_discount,
                   start_at, end_at, usage_limit, status=EntityStatus.ACTIVE, promo_id=None, actor=None):
    code = (code or "").strip().upper()
    if promo_id:
        p = db.session.get(Promotion, promo_id)
        old_val = {"code": p.code, "value": str(p.discount_value)}
        p.code = code
        p.discount_type = discount_type
        p.discount_value = discount_value
        p.min_order_value = min_order_value
        p.max_discount = max_discount
        p.start_at = start_at
        p.end_at = end_at
        p.usage_limit = usage_limit
        p.status = status
        action = "promotion.update"
    else:
        p = Promotion(code=code, discount_type=discount_type, discount_value=discount_value,
                      min_order_value=min_order_value, max_discount=max_discount,
                      start_at=start_at, end_at=end_at, usage_limit=usage_limit, status=status)
        db.session.add(p)
        db.session.flush()
        old_val = None
        action = "promotion.create"

    audit_service.record(action, "promotion", p.id, old_val, {"code": code, "status": status}, actor)
    db.session.commit()
    return p


def get_shipping_rules():
    return db.session.scalars(
        select(ShippingFeeRule).options(selectinload(ShippingFeeRule.province))
        .order_by(ShippingFeeRule.province_id.nulls_first())
    ).all()


def get_provinces():
    return db.session.scalars(select(Province).order_by(Province.name.asc())).all()


def save_shipping_rule(province_id, fee, free_threshold=None, is_active=True, rule_id=None, actor=None):
    prov_id = province_id if province_id and province_id > 0 else None
    if rule_id:
        r = db.session.get(ShippingFeeRule, rule_id)
        r.province_id = prov_id
        r.fee = fee
        r.free_threshold = free_threshold
        r.is_active = is_active
        action = "shipping_rule.update"
    else:
        r = ShippingFeeRule(province_id=prov_id, fee=fee, free_threshold=free_threshold, is_active=is_active)
        db.session.add(r)
        db.session.flush()
        action = "shipping_rule.create"

    audit_service.record(action, "shipping_fee_rule", r.id, None,
                         {"province_id": prov_id, "fee": str(fee)}, actor)
    db.session.commit()
    return r


# ------------------------------------------------------------------ 7. Quản lý Người dùng & Phân quyền (FR-QT03)
def search_users(q=None, role_id=None, page=1, per_page=20):
    stmt = select(Account).options(selectinload(Account.role))
    if q:
        stmt = stmt.where(or_(Account.full_name.ilike(f"%{q}%"),
                              Account.email.ilike(f"%{q}%"),
                              Account.phone.ilike(f"%{q}%")))
    if role_id:
        stmt = stmt.where(Account.role_id == role_id)

    stmt = stmt.order_by(Account.created_at.desc())
    return db.paginate(stmt, page=page, per_page=per_page, error_out=False)


def get_roles():
    return db.session.scalars(select(Role).options(selectinload(Role.permissions)).order_by(Role.id.asc())).all()


def get_permissions():
    return db.session.scalars(select(Permission).order_by(Permission.code.asc())).all()


def create_user(full_name, email, phone, password, role_id, actor=None):
    acc = Account(
        full_name=full_name,
        email=email.strip().lower(),
        phone=phone.strip(),
        password_hash=generate_password_hash(password),
        role_id=role_id,
        is_active=True
    )
    db.session.add(acc)
    db.session.flush()
    audit_service.record("user.create", "account", acc.id, None,
                         {"email": acc.email, "role_id": role_id}, actor)
    db.session.commit()
    return acc


def update_user(user_id, full_name, phone, role_id, is_active, is_locked=False,
                reset_failed=False, actor=None):
    acc = db.session.get(Account, user_id)
    if not acc:
        return None

    old_val = {
        "full_name": acc.full_name,
        "phone": acc.phone,
        "role_id": acc.role_id,
        "is_active": acc.is_active,
        "locked": bool(acc.locked_until and acc.locked_until > utcnow()),
    }

    acc.full_name = full_name
    acc.phone = phone
    acc.role_id = role_id
    acc.is_active = is_active
    if is_locked:
        acc.locked_until = utcnow() + timedelta(days=365)  # Khóa tạm 1 năm
    else:
        acc.locked_until = None

    if reset_failed:
        acc.failed_login_count = 0

    audit_service.record("user.update", "account", acc.id, old_val,
                         {"full_name": full_name, "is_active": is_active, "role_id": role_id}, actor)
    db.session.commit()
    return acc


def update_role_permissions(role_id, permission_codes, actor=None):
    role = db.session.get(Role, role_id)
    if not role:
        return None

    all_perms = db.session.scalars(select(Permission).where(Permission.code.in_(permission_codes))).all()
    old_codes = [p.code for p in role.permissions]
    role.permissions = all_perms

    audit_service.record("role.permissions_update", "role", role.id,
                         {"permissions": old_codes}, {"permissions": permission_codes}, actor)
    db.session.commit()
    return role


# ------------------------------------------------------------------ 8. Cấu hình & Nhật ký (FR-QT07, FR-QT09)
def get_all_settings():
    return db.session.scalars(select(AppSetting).order_by(AppSetting.setting_key.asc())).all()


def save_setting(key, value, description=None, actor=None):
    old_val = AppSetting.get_int(key, None)
    setting = AppSetting.set_value(key, value, description=description)
    audit_service.record("setting.update", "app_setting", 0,
                         {"key": key, "old_value": old_val}, {"key": key, "new_value": value}, actor)
    db.session.commit()
    return setting


def search_audit_logs(action=None, entity_name=None, page=1, per_page=30):
    stmt = select(AuditLog).options(selectinload(AuditLog.account))
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if entity_name:
        stmt = stmt.where(AuditLog.entity_name == entity_name)

    stmt = stmt.order_by(AuditLog.created_at.desc())
    return db.paginate(stmt, page=page, per_page=per_page, error_out=False)
