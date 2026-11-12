"""Kiểm tra render các template khu vực Quản trị viên (Task 9).
Chạy: python scripts/check_admin_templates.py"""
from datetime import datetime
from decimal import Decimal
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, "scripts")
from _render_env import Checker, Pag, make_app, set_user

from flask import render_template

from app.admin.forms import (CarrierForm, CategoryForm, ColorForm,
                             ProductForm, ProductImageForm, PromotionForm,
                             ShippingFeeRuleForm, SizeForm, SupplierForm,
                             UserCreateForm, UserEditForm, VariantForm)
from app.constants import OrderStatus

app = make_app()
ok = Checker()


class AdminUser:
    is_authenticated = True
    role_code = "ADMIN"
    full_name = "Quản trị viên"
    email = "admin@sportzone.local"

    def has_permission(self, code):
        return True


with app.test_request_context("/admin/"):
    set_user(app, AdminUser())

    # 1. Dashboard
    stats = {
        "orders_today": 5, "orders_month": 42, "revenue_total": Decimal(15000000),
        "status_counts": {"COMPLETED": 30, "PENDING_CONFIRM": 5},
        "user_counts": {"CUSTOMER": 100, "STAFF": 5, "ADMIN": 2},
        "low_stock": 3, "pending_returns": 1
    }
    html_dash = render_template("admin/dashboard.html", stats=stats, refunds=[],
                                best_sellers=[], labels=OrderStatus.LABELS, badges=OrderStatus.BADGES)
    ok("Bảng điều khiển Quản trị viên" in html_dash, "render dashboard.html thành công")

    # 2. Reports
    daily_rev = {"10/11": Decimal(2500000), "11/11": Decimal(4500000)}
    html_rep = render_template("admin/reports.html", days=30, daily_revenue=daily_rev,
                               best_sellers=[], total_rev=Decimal(7000000))
    ok("Báo cáo Doanh thu" in html_rep and "7.000.000 ₫" in html_rep, "render reports.html thành công")

    # 3. Categories & Form
    cat_mock = NS(id=1, name="Áo thể thao", slug="ao-the-thao", parent_category_id=None,
                  parent=None, is_active=True)
    html_cats = render_template("admin/categories.html", categories=[cat_mock])
    ok("Quản lý Danh mục" in html_cats and "ao-the-thao" in html_cats, "render categories.html thành công")

    cat_form = CategoryForm()
    cat_form.parent_category_id.choices = [(0, "-- Danh mục gốc --"), (1, "Áo")]
    html_catform = render_template("admin/category_form.html", form=cat_form, title="Thêm danh mục")
    ok("Thêm danh mục" in html_catform, "render category_form.html thành công")

    # 4. Attributes (Size & Color)
    size_mock = NS(id=1, name="L", sort_order=3)
    color_mock = NS(id=1, name="Xanh Navy", hex_code="#000080")
    html_attr = render_template("admin/attributes.html", sizes=[size_mock], colors=[color_mock],
                                size_form=SizeForm(), color_form=ColorForm())
    ok("Kích cỡ & Màu sắc" in html_attr and "#000080" in html_attr, "render attributes.html thành công")

    # 5. Products & Form & Detail
    prod_mock = NS(
        id=1, name="Áo khoác gió SportZone", slug="ao-khoac-gio", price=Decimal(350000),
        category=cat_mock, is_active=True, total_available=20,
        primary_image=NS(url="/static/img/test.jpg"),
        images=[NS(id=1, url="/static/img/test.jpg", is_primary=True)],
        variants=[NS(id=1, sku="AK-L-XANH", size=size_mock, color=color_mock,
                     stock_quantity=20, reserved_quantity=0, available_quantity=20, is_active=True)]
    )
    pag_prod = Pag([prod_mock], page=1, pages=1, total=1)
    html_prods = render_template("admin/products.html", pagination=pag_prod, products=[prod_mock],
                                 categories=[cat_mock], q="", cat_id=None, status="")
    ok("Quản lý Sản phẩm" in html_prods and "AK-L-XANH" not in html_prods, "render products.html thành công")

    prod_form = ProductForm()
    prod_form.category_id.choices = [(1, "Áo thể thao")]
    html_prodform = render_template("admin/product_form.html", form=prod_form, title="Thêm sản phẩm")
    ok("Thêm sản phẩm" in html_prodform, "render product_form.html thành công")

    v_form = VariantForm()
    v_form.size_id.choices = [(1, "L")]
    v_form.color_id.choices = [(1, "Xanh")]
    html_proddet = render_template("admin/product_detail.html", product=prod_mock,
                                   variant_form=v_form, image_form=ProductImageForm())
    ok("Áo khoác gió SportZone" in html_proddet and "AK-L-XANH" in html_proddet, "render product_detail.html thành công")

    # 6. Suppliers & Form & Carriers
    sup_mock = NS(id=1, name="Công ty May Mặc ABC", contact_name="Anh Nam", phone="0987654321",
                  email="nam@abc.vn", is_active=True)
    html_sups = render_template("admin/suppliers.html", suppliers=[sup_mock])
    ok("Công ty May Mặc ABC" in html_sups, "render suppliers.html thành công")

    html_supform = render_template("admin/supplier_form.html", form=SupplierForm(), title="Thêm nhà cung cấp")
    ok("Thêm nhà cung cấp" in html_supform, "render supplier_form.html thành công")

    car_mock = NS(id=1, name="Giao Hàng Tiết Kiệm", is_active=True)
    html_cars = render_template("admin/carriers.html", carriers=[car_mock], form=CarrierForm())
    ok("Giao Hàng Tiết Kiệm" in html_cars, "render carriers.html thành công")

    # 7. Promotions & Shipping Fees
    promo_mock = NS(
        id=1, code="SUMMER26", discount_type="PERCENT", discount_value=15,
        min_order_value=Decimal(200000), max_discount=Decimal(50000),
        start_at=datetime(2026, 6, 1), end_at=datetime(2026, 6, 30),
        orders=[], usage_limit=100, status="ACTIVE"
    )
    html_promos = render_template("admin/promotions.html", promotions=[promo_mock])
    ok("SUMMER26" in html_promos, "render promotions.html thành công")

    fee_mock = NS(id=1, province_id=None, province=None, fee=Decimal(30000),
                  free_threshold=Decimal(500000), is_active=True)
    fee_form = ShippingFeeRuleForm()
    fee_form.province_id.choices = [(0, "Mức mặc định")]
    html_fees = render_template("admin/shipping_fees.html", rules=[fee_mock], form=fee_form, provinces=[])
    ok("Mức mặc định toàn quốc" in html_fees, "render shipping_fees.html thành công")

    # 8. Users & Roles & Settings & Audit Logs
    role_mock = NS(id=2, name="STAFF", accounts=[], permissions=[])
    user_mock = NS(id=1, full_name="Trần Nhân Viên", email="staff@sportzone.local",
                   phone="0912345678", role=role_mock, is_active=True, locked_until=None, failed_login_count=0)
    pag_users = Pag([user_mock], page=1, pages=1, total=1)
    html_users = render_template("admin/users.html", pagination=pag_users, users=[user_mock],
                                 roles=[role_mock], q="", role_id=None)
    ok("Trần Nhân Viên" in html_users, "render users.html thành công")

    u_form = UserCreateForm()
    u_form.role_id.choices = [(1, "Admin"), (2, "Staff")]
    html_uform = render_template("admin/user_form.html", form=u_form, title="Tạo tài khoản")
    ok("Tạo tài khoản" in html_uform, "render user_form.html thành công")

    html_roles = render_template("admin/roles.html", roles=[role_mock],
                                 permissions=[NS(id=1, code="order.view")],
                                 perm_labels={"order.view": "Xem đơn hàng"})
    ok("Phân quyền Vai trò" in html_roles, "render roles.html thành công")

    html_set = render_template("admin/settings.html", settings={"payment_timeout_minutes": 15})
    ok("Tham số Cấu hình" in html_set, "render settings.html thành công")

    log_mock = NS(id=1, created_at=datetime(2026, 11, 12, 10, 0, 0),
                  account=user_mock, action="product.update", entity_name="product",
                  entity_id=1, ip_address="127.0.0.1", old_value=None, new_value=None)
    pag_logs = Pag([log_mock], page=1, pages=1, total=1)
    html_logs = render_template("admin/audit_logs.html", pagination=pag_logs, logs=[log_mock], action="", entity="")
    ok("product.update" in html_logs, "render audit_logs.html thành công")

print(f"OK: {ok.count} kiểm tra template admin đạt.")
