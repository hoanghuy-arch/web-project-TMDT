"""Kiểm thử toàn diện khu vực Quản trị viên (Task 9: FR-QT01..09)."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.constants import (DiscountType, EntityStatus, OrderStatus,
                           PaymentStatus, Perm, ROLE_ADMIN, ROLE_CUSTOMER,
                           ROLE_STAFF, SettingKey)
from app.extensions import db
from app.models import (Account, AppSetting, AuditLog, Carrier, Category,
                        Color, Permission, Product, ProductImage,
                        ProductVariant, Promotion, Role, ShippingFeeRule,
                        Size, Supplier)
from app.services import admin_service


# ------------------------------------------------------------------ 1. Phân quyền truy cập
def test_admin_access_controls(client, make_account, login):
    # Chưa đăng nhập -> chuyển hướng login
    assert client.get("/admin/").status_code == 302

    # Khách hàng -> 403 Forbidden
    make_account(email="customer@test.com", role=ROLE_CUSTOMER)
    login("customer@test.com")
    assert client.get("/admin/").status_code == 403
    client.post("/auth/logout")

    # Nhân viên chưa được cấp quyền riêng -> 403
    make_account(email="staff@test.com", role=ROLE_STAFF)
    login("staff@test.com")
    assert client.get("/admin/").status_code == 403
    assert client.get("/admin/categories").status_code == 403
    client.post("/auth/logout")

    # Quản trị viên -> 200 OK vào toàn bộ
    make_account(email="admin@test.com", role=ROLE_ADMIN)
    login("admin@test.com")
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/categories").status_code == 200
    assert client.get("/admin/products").status_code == 200
    assert client.get("/admin/suppliers").status_code == 200
    assert client.get("/admin/promotions").status_code == 200
    assert client.get("/admin/users").status_code == 200


# ------------------------------------------------------------------ 2. Quản lý Danh mục (FR-QT02)
def test_admin_category_management(client, make_account, login):
    admin = make_account(email="admin_cat@test.com", role=ROLE_ADMIN)
    login("admin_cat@test.com")

    # Tạo danh mục cha
    resp = client.post("/admin/categories/new", data={
        "name": "Thời Trang Nam",
        "parent_category_id": 0,
        "is_active": "y"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Thời Trang Nam" in resp.get_data(as_text=True)

    parent = db.session.scalar(db.select(Category).where(Category.name == "Thời Trang Nam"))
    assert parent is not None
    assert parent.slug == "thoi-trang-nam"

    # Tạo danh mục con
    client.post("/admin/categories/new", data={
        "name": "Áo Thun Nam",
        "parent_category_id": parent.id,
        "is_active": "y"
    }, follow_redirects=True)
    child = db.session.scalar(db.select(Category).where(Category.name == "Áo Thun Nam"))
    assert child is not None
    assert child.parent_category_id == parent.id

    # Toggle trạng thái
    client.post(f"/admin/categories/{parent.id}/toggle", follow_redirects=True)
    db.session.refresh(parent)
    assert parent.is_active is False

    # Kiểm tra có ghi audit log
    logs = db.session.scalars(db.select(AuditLog).where(AuditLog.entity_name == "category")).all()
    assert len(logs) >= 2


# ------------------------------------------------------------------ 3. Kích cỡ & Màu sắc
def test_admin_attributes_management(client, make_account, login):
    make_account(email="admin_attr@test.com", role=ROLE_ADMIN)
    login("admin_attr@test.com")

    # Thêm Size
    resp_size = client.post("/admin/sizes/new", data={"name": "XXL", "sort_order": 5}, follow_redirects=True)
    assert resp_size.status_code == 200
    assert db.session.scalar(db.select(Size).where(Size.name == "XXL")) is not None

    # Thêm Color
    resp_color = client.post("/admin/colors/new", data={"name": "Xanh Rêu", "hex_code": "#2E8B57"}, follow_redirects=True)
    assert resp_color.status_code == 200
    c = db.session.scalar(db.select(Color).where(Color.name == "Xanh Rêu"))
    assert c is not None and c.hex_code == "#2E8B57"


# ------------------------------------------------------------------ 4. Quản lý Sản phẩm, Biến thể, Ảnh (FR-QT01)
def test_admin_product_variant_image_management(client, make_account, login):
    make_account(email="admin_prod@test.com", role=ROLE_ADMIN)
    login("admin_prod@test.com")

    cat = Category(name="Đồ Tập", slug="do-tap", is_active=True)
    size = Size(name="L", sort_order=2)
    color = Color(name="Đen", hex_code="#000000")
    db.session.add_all([cat, size, color])
    db.session.commit()

    # Tạo sản phẩm mới
    resp = client.post("/admin/products/new", data={
        "name": "Quần Jogger Thể Thao Nam",
        "category_id": cat.id,
        "price": "350000",
        "description": "Quần co giãn tốt",
        "status": EntityStatus.ACTIVE
    }, follow_redirects=True)
    assert resp.status_code == 200

    prod = db.session.scalar(db.select(Product).where(Product.name == "Quần Jogger Thể Thao Nam"))
    assert prod is not None
    assert prod.slug == "quan-jogger-the-thao-nam"
    assert prod.price == Decimal(350000)

    # Thêm biến thể cho sản phẩm
    resp_var = client.post(f"/admin/products/{prod.id}/variants/new", data={
        "size_id": size.id,
        "color_id": color.id,
        "sku": "JOGGER-L-DEN",
        "stock_quantity": 50,
        "status": EntityStatus.ACTIVE
    }, follow_redirects=True)
    assert resp_var.status_code == 200
    db.session.refresh(prod)
    assert len(prod.variants) == 1
    assert prod.variants[0].sku == "JOGGER-L-DEN"
    assert prod.total_available == 50

    # Thêm ảnh sản phẩm
    client.post(f"/admin/products/{prod.id}/images/new", data={
        "url": "/static/img/jogger.jpg",
        "is_primary": "y",
        "sort_order": 0
    }, follow_redirects=True)
    db.session.refresh(prod)
    assert len(prod.images) == 1
    assert prod.primary_image.url == "/static/img/jogger.jpg"

    # Toggle trạng thái sản phẩm
    client.post(f"/admin/products/{prod.id}/toggle", follow_redirects=True)
    db.session.refresh(prod)
    assert prod.status == EntityStatus.INACTIVE


# ------------------------------------------------------------------ 5. Quản lý Nhà cung cấp (FR-QT04) & Vận chuyển
def test_admin_suppliers_and_carriers(client, make_account, login):
    make_account(email="admin_sup@test.com", role=ROLE_ADMIN)
    login("admin_sup@test.com")

    # Tạo nhà cung cấp
    resp = client.post("/admin/suppliers/new", data={
        "name": "Xưởng Dệt Kim Đông Xuân",
        "contact_name": "Nguyễn Văn Quản",
        "phone": "0912345678",
        "email": "dongxuan@detkim.vn",
        "address_detail": "Hà Nội",
        "status": EntityStatus.ACTIVE
    }, follow_redirects=True)
    assert resp.status_code == 200
    sup = db.session.scalar(db.select(Supplier).where(Supplier.name == "Xưởng Dệt Kim Đông Xuân"))
    assert sup is not None
    assert sup.is_active is True

    # Sửa nhà cung cấp
    client.post(f"/admin/suppliers/{sup.id}/edit", data={
        "name": "Xưởng Dệt Kim Đông Xuân (Chi Nhánh 2)",
        "contact_name": "Nguyễn Văn Quản",
        "phone": "0912345678",
        "email": "dongxuan2@detkim.vn",
        "address_detail": "Hà Nội",
        "status": EntityStatus.INACTIVE
    }, follow_redirects=True)
    db.session.refresh(sup)
    assert sup.status == EntityStatus.INACTIVE

    # Tạo đơn vị vận chuyển
    client.post("/admin/carriers/new", data={"name": "J&T Express", "is_active": "y"}, follow_redirects=True)
    car = db.session.scalar(db.select(Carrier).where(Carrier.name == "J&T Express"))
    assert car is not None and car.is_active is True


# ------------------------------------------------------------------ 6. Quản lý Khuyến mãi & Phí vận chuyển
def test_admin_promotions_and_shipping(client, make_account, login):
    make_account(email="admin_promo@test.com", role=ROLE_ADMIN)
    login("admin_promo@test.com")

    # Tạo mã khuyến mãi
    resp = client.post("/admin/promotions/new", data={
        "code": "SPORTZONE20",
        "discount_type": DiscountType.PERCENT,
        "discount_value": 20,
        "min_order_value": 300000,
        "max_discount": 100000,
        "start_at": "2026-01-01 00:00",
        "end_at": "2026-12-31 23:59",
        "usage_limit": 50,
        "status": EntityStatus.ACTIVE
    }, follow_redirects=True)
    assert resp.status_code == 200
    promo = db.session.scalar(db.select(Promotion).where(Promotion.code == "SPORTZONE20"))
    assert promo is not None
    assert promo.discount_value == Decimal(20)

    # Tạo quy tắc phí vận chuyển mặc định
    client.post("/admin/shipping-fees/new", data={
        "province_id": 0,
        "fee": 35000,
        "free_threshold": 600000,
        "is_active": "y"
    }, follow_redirects=True)
    rule = db.session.scalar(db.select(ShippingFeeRule).where(ShippingFeeRule.province_id.is_(None)))
    assert rule is not None
    assert rule.fee == Decimal(35000)
    assert rule.free_threshold == Decimal(600000)


# ------------------------------------------------------------------ 7. Quản lý Tài khoản & Phân quyền RBAC (FR-QT03)
def test_admin_user_rbac_and_lock(client, roles, make_account, login):
    make_account(email="admin_rbac@test.com", role=ROLE_ADMIN)
    login("admin_rbac@test.com")

    # Tạo tài khoản nhân viên mới
    resp = client.post("/admin/users/new", data={
        "full_name": "Lê Nhân Viên",
        "email": "lenhanvien@test.com",
        "phone": "0988776655",
        "password": "Password123",
        "confirm_password": "Password123",
        "role_id": roles[ROLE_STAFF].id
    }, follow_redirects=True)
    assert resp.status_code == 200

    new_staff = db.session.scalar(db.select(Account).where(Account.email == "lenhanvien@test.com"))
    assert new_staff is not None
    assert new_staff.role.name == ROLE_STAFF

    # Khóa tài khoản
    client.post(f"/admin/users/{new_staff.id}/edit", data={
        "full_name": "Lê Nhân Viên (Khóa)",
        "phone": "0988776655",
        "role_id": roles[ROLE_STAFF].id,
        "is_active": "y",
        "is_locked": "y",
        "reset_failed_logins": "y"
    }, follow_redirects=True)
    db.session.refresh(new_staff)
    assert new_staff.locked_until is not None

    # Phân quyền cho vai trò STAFF
    perm = Permission(code=Perm.ORDER_VIEW, description="Xem đơn")
    db.session.add(perm)
    db.session.commit()

    client.post("/admin/roles", data={
        "role_id": roles[ROLE_STAFF].id,
        "permissions": [Perm.ORDER_VIEW]
    }, follow_redirects=True)
    db.session.refresh(roles[ROLE_STAFF])
    staff_codes = [p.code for p in roles[ROLE_STAFF].permissions]
    assert Perm.ORDER_VIEW in staff_codes


# ------------------------------------------------------------------ 8. Cấu hình Tham số (FR-QT07) & Nhật ký (FR-QT09)
def test_admin_settings_and_audit_logs(client, make_account, login):
    make_account(email="admin_sys@test.com", role=ROLE_ADMIN)
    login("admin_sys@test.com")

    # Cập nhật cài đặt
    resp = client.post("/admin/settings", data={
        "payment_timeout_minutes": 20,
        "return_window_days": 10,
        "low_stock_threshold": 8
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert AppSetting.payment_timeout_minutes() == 20
    assert AppSetting.get_int(SettingKey.RETURN_WINDOW_DAYS, 7) == 10
    assert AppSetting.get_int(SettingKey.LOW_STOCK_THRESHOLD, 5) == 8

    # Xem nhật ký hoạt động
    resp_logs = client.get("/admin/audit-logs")
    assert resp_logs.status_code == 200
    assert "Nhật ký Hoạt động" in resp_logs.get_data(as_text=True)
