"""Khu vực Quản trị viên (Task 9: FR-QT01..09)."""
from datetime import datetime
from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.admin import bp
from app.admin.forms import (CarrierForm, CategoryForm, ColorForm,
                             ProductForm, ProductImageForm, PromotionForm,
                             ShippingFeeRuleForm, SizeForm, SupplierForm,
                             UserCreateForm, UserEditForm, VariantForm)
from app.constants import EntityStatus, OrderStatus, Perm, SettingKey
from app.services import admin_service
from app.utils.decorators import admin_required, permission_required


# ------------------------------------------------------------------ 1. Bảng điều khiển & Báo cáo (FR-QT08)
@bp.route("/")
@admin_required
def dashboard():
    stats = admin_service.dashboard_stats()
    refunds = admin_service.pending_refunds()
    best_sellers = admin_service.best_selling_products(limit=5)
    return render_template("admin/dashboard.html", stats=stats, refunds=refunds,
                           best_sellers=best_sellers, labels=OrderStatus.LABELS,
                           badges=OrderStatus.BADGES)


@bp.route("/reports")
@permission_required(Perm.REPORT_VIEW)
def reports():
    days = request.args.get("days", 30, type=int)
    daily_revenue = admin_service.revenue_report(days=days)
    best_sellers = admin_service.best_selling_products(limit=10)
    total_rev = sum(daily_revenue.values(), Decimal(0))
    return render_template("admin/reports.html", days=days, daily_revenue=daily_revenue,
                           best_sellers=best_sellers, total_rev=total_rev)


# ------------------------------------------------------------------ 2. Quản lý Danh mục (FR-QT02)
@bp.route("/categories")
@permission_required(Perm.CATALOG_MANAGE)
def categories():
    cats = admin_service.get_categories()
    return render_template("admin/categories.html", categories=cats)


@bp.route("/categories/new", methods=["GET", "POST"])
@permission_required(Perm.CATALOG_MANAGE)
def category_create():
    form = CategoryForm()
    cats = admin_service.get_categories()
    form.parent_category_id.choices = [(0, "-- Danh mục gốc (không có cha) --")] + [
        (c.id, c.name) for c in cats
    ]
    if form.validate_on_submit():
        admin_service.save_category(
            name=form.name.data,
            parent_id=form.parent_category_id.data if form.parent_category_id.data > 0 else None,
            is_active=form.is_active.data,
            actor=current_user
        )
        flash("Đã thêm danh mục mới thành công.", "success")
        return redirect(url_for("admin.categories"))
    return render_template("admin/category_form.html", form=form, title="Thêm danh mục mới")


@bp.route("/categories/<int:cat_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.CATALOG_MANAGE)
def category_edit(cat_id):
    cat = admin_service.get_category(cat_id)
    if not cat:
        abort(404)
    form = CategoryForm(obj=cat)
    cats = admin_service.get_categories()
    form.parent_category_id.choices = [(0, "-- Danh mục gốc (không có cha) --")] + [
        (c.id, c.name) for c in cats if c.id != cat_id
    ]
    if request.method == "GET":
        form.parent_category_id.data = cat.parent_category_id or 0

    if form.validate_on_submit():
        admin_service.save_category(
            name=form.name.data,
            parent_id=form.parent_category_id.data if form.parent_category_id.data > 0 else None,
            is_active=form.is_active.data,
            cat_id=cat_id,
            actor=current_user
        )
        flash("Đã cập nhật danh mục thành công.", "success")
        return redirect(url_for("admin.categories"))
    return render_template("admin/category_form.html", form=form, title="Chỉnh sửa danh mục", cat=cat)


@bp.route("/categories/<int:cat_id>/toggle", methods=["POST"])
@permission_required(Perm.CATALOG_MANAGE)
def category_toggle(cat_id):
    admin_service.toggle_category(cat_id, actor=current_user)
    flash("Đã thay đổi trạng thái danh mục.", "success")
    return redirect(url_for("admin.categories"))


# ------------------------------------------------------------------ 3. Thuộc tính: Kích cỡ & Màu sắc (FR-QT02)
@bp.route("/attributes")
@permission_required(Perm.CATALOG_MANAGE)
def attributes():
    sizes = admin_service.get_sizes()
    colors = admin_service.get_colors()
    size_form = SizeForm()
    color_form = ColorForm()
    return render_template("admin/attributes.html", sizes=sizes, colors=colors,
                           size_form=size_form, color_form=color_form)


@bp.route("/sizes/new", methods=["POST"])
@permission_required(Perm.CATALOG_MANAGE)
def size_create():
    form = SizeForm()
    if form.validate_on_submit():
        admin_service.save_size(name=form.name.data, sort_order=form.sort_order.data, actor=current_user)
        flash("Đã thêm kích cỡ mới.", "success")
    else:
        for err in form.name.errors:
            flash(err, "danger")
    return redirect(url_for("admin.attributes"))


@bp.route("/colors/new", methods=["POST"])
@permission_required(Perm.CATALOG_MANAGE)
def color_create():
    form = ColorForm()
    if form.validate_on_submit():
        admin_service.save_color(name=form.name.data, hex_code=form.hex_code.data, actor=current_user)
        flash("Đã thêm màu sắc mới.", "success")
    else:
        for err in form.hex_code.errors + form.name.errors:
            flash(err, "danger")
    return redirect(url_for("admin.attributes"))


# ------------------------------------------------------------------ 4. Quản lý Sản phẩm, Biến thể, Ảnh (FR-QT01)
@bp.route("/products")
@permission_required(Perm.PRODUCT_MANAGE)
def products():
    q = request.args.get("q", "").strip()
    cat_id = request.args.get("cat_id", type=int)
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    pagination = admin_service.search_products(q=q, cat_id=cat_id, status=status, page=page)
    categories = admin_service.get_categories()
    return render_template("admin/products.html", pagination=pagination, products=pagination.items,
                           categories=categories, q=q, cat_id=cat_id, status=status)


@bp.route("/products/new", methods=["GET", "POST"])
@permission_required(Perm.PRODUCT_MANAGE)
def product_create():
    form = ProductForm()
    cats = admin_service.get_categories()
    form.category_id.choices = [(c.id, c.name) for c in cats]
    if form.validate_on_submit():
        p = admin_service.save_product(
            name=form.name.data,
            category_id=form.category_id.data,
            price=form.price.data,
            description=form.description.data,
            status=form.status.data,
            actor=current_user
        )
        flash(f"Đã tạo sản phẩm '{p.name}'. Vui lòng thêm biến thể và ảnh bên dưới.", "success")
        return redirect(url_for("admin.product_detail", product_id=p.id))
    return render_template("admin/product_form.html", form=form, title="Thêm sản phẩm mới")


@bp.route("/products/<int:product_id>")
@permission_required(Perm.PRODUCT_MANAGE)
def product_detail(product_id):
    p = admin_service.get_product(product_id)
    if not p:
        abort(404)
    variant_form = VariantForm()
    variant_form.size_id.choices = [(s.id, s.name) for s in admin_service.get_sizes()]
    variant_form.color_id.choices = [(c.id, c.name) for c in admin_service.get_colors()]
    image_form = ProductImageForm()
    return render_template("admin/product_detail.html", product=p,
                           variant_form=variant_form, image_form=image_form)


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.PRODUCT_MANAGE)
def product_edit(product_id):
    p = admin_service.get_product(product_id)
    if not p:
        abort(404)
    form = ProductForm(obj=p)
    cats = admin_service.get_categories()
    form.category_id.choices = [(c.id, c.name) for c in cats]
    if form.validate_on_submit():
        admin_service.save_product(
            name=form.name.data,
            category_id=form.category_id.data,
            price=form.price.data,
            description=form.description.data,
            status=form.status.data,
            product_id=product_id,
            actor=current_user
        )
        flash("Đã cập nhật sản phẩm thành công.", "success")
        return redirect(url_for("admin.product_detail", product_id=product_id))
    return render_template("admin/product_form.html", form=form, title="Chỉnh sửa sản phẩm", product=p)


@bp.route("/products/<int:product_id>/toggle", methods=["POST"])
@permission_required(Perm.PRODUCT_MANAGE)
def product_toggle(product_id):
    admin_service.toggle_product_status(product_id, actor=current_user)
    flash("Đã đổi trạng thái kinh doanh của sản phẩm.", "success")
    return redirect(url_for("admin.products"))


@bp.route("/products/<int:product_id>/variants/new", methods=["POST"])
@permission_required(Perm.PRODUCT_MANAGE)
def variant_create(product_id):
    p = admin_service.get_product(product_id)
    if not p:
        abort(404)
    form = VariantForm()
    form.size_id.choices = [(s.id, s.name) for s in admin_service.get_sizes()]
    form.color_id.choices = [(c.id, c.name) for c in admin_service.get_colors()]
    if form.validate_on_submit():
        try:
            admin_service.add_product_variant(
                product_id=product_id,
                size_id=form.size_id.data,
                color_id=form.color_id.data,
                sku=form.sku.data,
                initial_stock=form.stock_quantity.data,
                status=form.status.data,
                actor=current_user
            )
            flash("Đã thêm biến thể thành công.", "success")
        except ValueError as e:
            flash(str(e), "danger")
    else:
        for err in form.sku.errors:
            flash(err, "danger")
    return redirect(url_for("admin.product_detail", product_id=product_id))


@bp.route("/products/<int:product_id>/images/new", methods=["POST"])
@permission_required(Perm.PRODUCT_MANAGE)
def image_create(product_id):
    form = ProductImageForm()
    if form.validate_on_submit():
        admin_service.add_product_image(
            product_id=product_id,
            url=form.url.data,
            is_primary=form.is_primary.data,
            sort_order=form.sort_order.data,
            actor=current_user
        )
        flash("Đã thêm ảnh sản phẩm thành công.", "success")
    else:
        for err in form.url.errors:
            flash(err, "danger")
    return redirect(url_for("admin.product_detail", product_id=product_id))


@bp.route("/images/<int:image_id>/delete", methods=["POST"])
@permission_required(Perm.PRODUCT_MANAGE)
def image_delete(image_id):
    product_id = request.form.get("product_id", type=int)
    admin_service.delete_product_image(image_id, actor=current_user)
    flash("Đã xóa ảnh sản phẩm.", "success")
    return redirect(url_for("admin.product_detail", product_id=product_id))


# ------------------------------------------------------------------ 5. Nhà cung cấp (FR-QT04) & Vận chuyển
@bp.route("/suppliers")
@permission_required(Perm.SUPPLIER_MANAGE)
def suppliers():
    sups = admin_service.get_suppliers()
    return render_template("admin/suppliers.html", suppliers=sups)


@bp.route("/suppliers/new", methods=["GET", "POST"])
@permission_required(Perm.SUPPLIER_MANAGE)
def supplier_create():
    form = SupplierForm()
    if form.validate_on_submit():
        s = admin_service.save_supplier(
            name=form.name.data,
            contact_name=form.contact_name.data,
            phone=form.phone.data,
            email=form.email.data,
            address_detail=form.address_detail.data,
            status=form.status.data,
            actor=current_user
        )
        flash(f"Đã thêm nhà cung cấp '{s.name}'.", "success")
        return redirect(url_for("admin.suppliers"))
    return render_template("admin/supplier_form.html", form=form, title="Thêm nhà cung cấp mới")


@bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.SUPPLIER_MANAGE)
def supplier_edit(supplier_id):
    s = admin_service.get_supplier(supplier_id)
    if not s:
        abort(404)
    form = SupplierForm(obj=s)
    if form.validate_on_submit():
        admin_service.save_supplier(
            name=form.name.data,
            contact_name=form.contact_name.data,
            phone=form.phone.data,
            email=form.email.data,
            address_detail=form.address_detail.data,
            status=form.status.data,
            supplier_id=supplier_id,
            actor=current_user
        )
        flash("Đã cập nhật thông tin nhà cung cấp.", "success")
        return redirect(url_for("admin.suppliers"))
    return render_template("admin/supplier_form.html", form=form, title="Chỉnh sửa nhà cung cấp", supplier=s)


@bp.route("/carriers")
@permission_required(Perm.CATALOG_MANAGE)
def carriers():
    cars = admin_service.get_carriers()
    form = CarrierForm()
    return render_template("admin/carriers.html", carriers=cars, form=form)


@bp.route("/carriers/new", methods=["POST"])
@permission_required(Perm.CATALOG_MANAGE)
def carrier_create():
    form = CarrierForm()
    if form.validate_on_submit():
        admin_service.save_carrier(name=form.name.data, is_active=form.is_active.data, actor=current_user)
        flash("Đã thêm đơn vị vận chuyển mới.", "success")
    return redirect(url_for("admin.carriers"))


# ------------------------------------------------------------------ 6. Khuyến mãi (FR-QT06) & Phí ship (FR-QT07)
@bp.route("/promotions")
@permission_required(Perm.PROMOTION_MANAGE)
def promotions():
    promos = admin_service.get_promotions()
    return render_template("admin/promotions.html", promotions=promos)


@bp.route("/promotions/new", methods=["GET", "POST"])
@permission_required(Perm.PROMOTION_MANAGE)
def promotion_create():
    form = PromotionForm()
    if form.validate_on_submit():
        try:
            start_dt = datetime.strptime(form.start_at.data.strip(), "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(form.end_at.data.strip(), "%Y-%m-%d %H:%M")
            if end_dt <= start_dt:
                flash("Thời gian kết thúc phải sau thời gian bắt đầu.", "danger")
                return render_template("admin/promotion_form.html", form=form, title="Tạo mã khuyến mãi")

            admin_service.save_promotion(
                code=form.code.data,
                discount_type=form.discount_type.data,
                discount_value=form.discount_value.data,
                min_order_value=form.min_order_value.data or Decimal(0),
                max_discount=form.max_discount.data,
                start_at=start_dt,
                end_at=end_dt,
                usage_limit=form.usage_limit.data,
                status=form.status.data,
                actor=current_user
            )
            flash("Đã tạo chương trình khuyến mãi mới.", "success")
            return redirect(url_for("admin.promotions"))
        except ValueError:
            flash("Định dạng ngày giờ không hợp lệ (định dạng YYYY-MM-DD HH:MM).", "danger")
    return render_template("admin/promotion_form.html", form=form, title="Tạo mã khuyến mãi mới")


@bp.route("/promotions/<int:promo_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.PROMOTION_MANAGE)
def promotion_edit(promo_id):
    p = admin_service.get_promotion(promo_id)
    if not p:
        abort(404)
    form = PromotionForm(obj=p)
    if request.method == "GET":
        form.start_at.data = p.start_at.strftime("%Y-%m-%d %H:%M")
        form.end_at.data = p.end_at.strftime("%Y-%m-%d %H:%M")

    if form.validate_on_submit():
        try:
            start_dt = datetime.strptime(form.start_at.data.strip(), "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(form.end_at.data.strip(), "%Y-%m-%d %H:%M")
            admin_service.save_promotion(
                code=form.code.data,
                discount_type=form.discount_type.data,
                discount_value=form.discount_value.data,
                min_order_value=form.min_order_value.data or Decimal(0),
                max_discount=form.max_discount.data,
                start_at=start_dt,
                end_at=end_dt,
                usage_limit=form.usage_limit.data,
                status=form.status.data,
                promo_id=promo_id,
                actor=current_user
            )
            flash("Đã cập nhật khuyến mãi thành công.", "success")
            return redirect(url_for("admin.promotions"))
        except ValueError:
            flash("Định dạng ngày giờ không hợp lệ.", "danger")
    return render_template("admin/promotion_form.html", form=form, title="Chỉnh sửa khuyến mãi", promo=p)


@bp.route("/shipping-fees")
@permission_required(Perm.SHIPPING_FEE_MANAGE)
def shipping_fees():
    rules = admin_service.get_shipping_rules()
    provinces = admin_service.get_provinces()
    form = ShippingFeeRuleForm()
    form.province_id.choices = [(0, "-- Mức mặc định toàn quốc --")] + [(pr.id, pr.name) for pr in provinces]
    return render_template("admin/shipping_fees.html", rules=rules, form=form, provinces=provinces)


@bp.route("/shipping-fees/new", methods=["POST"])
@permission_required(Perm.SHIPPING_FEE_MANAGE)
def shipping_fee_create():
    form = ShippingFeeRuleForm()
    provinces = admin_service.get_provinces()
    form.province_id.choices = [(0, "-- Mức mặc định toàn quốc --")] + [(pr.id, pr.name) for pr in provinces]
    if form.validate_on_submit():
        admin_service.save_shipping_rule(
            province_id=form.province_id.data,
            fee=form.fee.data,
            free_threshold=form.free_threshold.data,
            is_active=form.is_active.data,
            actor=current_user
        )
        flash("Đã lưu quy tắc phí vận chuyển.", "success")
    return redirect(url_for("admin.shipping_fees"))


@bp.route("/shipping-fees/<int:rule_id>/delete", methods=["POST"])
@permission_required(Perm.SHIPPING_FEE_MANAGE)
def shipping_fee_delete(rule_id):
    if admin_service.delete_shipping_rule(rule_id, actor=current_user):
        flash("Đã xóa quy tắc phí vận chuyển thành công.", "success")
    else:
        flash("Không tìm thấy quy tắc phí cần xóa.", "danger")
    return redirect(url_for("admin.shipping_fees"))


# ------------------------------------------------------------------ 7. Người dùng & Phân quyền (FR-QT03)
@bp.route("/users")
@permission_required(Perm.USER_MANAGE)
def users():
    q = request.args.get("q", "").strip()
    role_id = request.args.get("role_id", type=int)
    page = request.args.get("page", 1, type=int)

    pagination = admin_service.search_users(q=q, role_id=role_id, page=page)
    roles = admin_service.get_roles()
    return render_template("admin/users.html", pagination=pagination, users=pagination.items,
                           roles=roles, q=q, role_id=role_id)


@bp.route("/users/new", methods=["GET", "POST"])
@permission_required(Perm.USER_MANAGE)
def user_create():
    form = UserCreateForm()
    roles = admin_service.get_roles()
    form.role_id.choices = [(r.id, r.name) for r in roles]
    if form.validate_on_submit():
        admin_service.create_user(
            full_name=form.full_name.data,
            email=form.email.data,
            phone=form.phone.data,
            password=form.password.data,
            role_id=form.role_id.data,
            actor=current_user
        )
        flash(f"Đã tạo tài khoản cho {form.full_name.data}.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, title="Tạo tài khoản mới")


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.USER_MANAGE)
def user_edit(user_id):
    user = admin_service.db.session.get(admin_service.Account, user_id)
    if not user:
        abort(404)
    form = UserEditForm(obj=user)
    roles = admin_service.get_roles()
    form.role_id.choices = [(r.id, r.name) for r in roles]

    if request.method == "GET":
        form.is_locked.data = user.is_locked

    if form.validate_on_submit():
        admin_service.update_user(
            user_id=user_id,
            full_name=form.full_name.data,
            phone=form.phone.data,
            role_id=form.role_id.data,
            is_active=form.is_active.data,
            is_locked=form.is_locked.data,
            reset_failed=form.reset_failed_logins.data,
            actor=current_user
        )
        flash("Đã cập nhật thông tin người dùng.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_edit.html", form=form, user=user)


@bp.route("/roles", methods=["GET", "POST"])
@permission_required(Perm.USER_MANAGE)
def roles():
    roles = admin_service.get_roles()
    permissions = admin_service.get_permissions()

    if request.method == "POST":
        role_id = request.form.get("role_id", type=int)
        selected_perms = request.form.getlist("permissions")
        admin_service.update_role_permissions(role_id, selected_perms, actor=current_user)
        flash("Đã cập nhật bảng phân quyền thành công.", "success")
        return redirect(url_for("admin.roles"))

    return render_template("admin/roles.html", roles=roles, permissions=permissions,
                           perm_labels=Perm.LABELS)


# ------------------------------------------------------------------ 8. Cấu hình & Nhật ký (FR-QT07, FR-QT09)
@bp.route("/settings", methods=["GET", "POST"])
@permission_required(Perm.SETTING_MANAGE)
def settings():
    if request.method == "POST":
        timeout = request.form.get("payment_timeout_minutes", type=int)
        ret_days = request.form.get("return_window_days", type=int)
        stock_thresh = request.form.get("low_stock_threshold", type=int)

        if timeout:
            admin_service.save_setting(SettingKey.PAYMENT_TIMEOUT_MINUTES, timeout,
                                       "Thời gian giữ hàng đơn online (phút)", actor=current_user)
        if ret_days:
            admin_service.save_setting(SettingKey.RETURN_WINDOW_DAYS, ret_days,
                                       "Thời hạn đổi trả sau khi nhận hàng (ngày)", actor=current_user)
        if stock_thresh:
            admin_service.save_setting(SettingKey.LOW_STOCK_THRESHOLD, stock_thresh,
                                       "Ngưỡng cảnh báo tồn kho sắp hết", actor=current_user)

        flash("Đã lưu các tham số cấu hình hệ thống.", "success")
        return redirect(url_for("admin.settings"))

    current_settings = {s.setting_key: s.setting_value for s in admin_service.get_all_settings()}
    return render_template("admin/settings.html", settings=current_settings)


@bp.route("/audit-logs")
@permission_required(Perm.AUDIT_VIEW)
def audit_logs():
    action = request.args.get("action", "").strip()
    entity = request.args.get("entity", "").strip()
    page = request.args.get("page", 1, type=int)

    pagination = admin_service.search_audit_logs(action=action, entity_name=entity, page=page)
    return render_template("admin/audit_logs.html", pagination=pagination, logs=pagination.items,
                           action=action, entity=entity)
