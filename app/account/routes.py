"""Khu vực tài khoản: hồ sơ, đổi mật khẩu, sổ địa chỉ (FR-KH04), giỏ hàng (FR-KH07).
Hồ sơ và đổi mật khẩu dùng được cho mọi người đã đăng nhập; sổ địa chỉ và giỏ hàng chỉ dành cho khách hàng."""
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.account import bp
from app.account.forms import AddressForm, ChangePasswordForm, ProfileForm
from app.constants import ROLE_CUSTOMER
from app.extensions import limiter
from app.services import account_service, address_service, cart_service
from app.services.account_service import PasswordChangeError
from app.services.address_service import AddressLimitError
from app.services.cart_service import CartError
from app.utils.decorators import customer_required
from app.utils.security import redirect_back


# ------------------------------------------------------------------ số lượng giỏ hàng trên menu
@bp.app_context_processor
def inject_cart_count():
    count = 0
    try:
        if current_user.is_authenticated and current_user.role_code == ROLE_CUSTOMER:
            count = cart_service.cart_count(current_user)
    except Exception:            # lỗi DB không được làm hỏng cả trang lỗi đang hiển thị
        current_app.logger.exception("Không đọc được số lượng giỏ hàng")
    return {"cart_count": count}


# ------------------------------------------------------------------ hồ sơ
@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user) if request.method == "GET" else ProfileForm()
    if form.validate_on_submit():
        account_service.update_profile(current_user, form.full_name.data, form.phone.data)
        flash("Đã cập nhật thông tin cá nhân.", "success")
        return redirect(url_for("account.profile"))
    return render_template("account/profile.html", form=form)


@bp.route("/password", methods=["GET", "POST"])
@login_required
@limiter.limit(lambda: current_app.config["RATELIMIT_RESET_PASSWORD"], methods=["POST"])
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            account_service.change_password(current_user, form.current_password.data, form.new_password.data)
        except PasswordChangeError as e:
            form.current_password.errors = list(form.current_password.errors) + [str(e)]
        else:
            flash("Đổi mật khẩu thành công.", "success")
            return redirect(url_for("account.profile"))
    return render_template("account/change_password.html", form=form)


# ------------------------------------------------------------------ sổ địa chỉ
def _prepare_address_form(form, province_id):
    """Gán danh sách tỉnh, phường (theo tỉnh đang chọn). Phường chỉ hợp lệ khi thuộc đúng tỉnh."""
    provinces = address_service.list_provinces()
    form.province_id.choices = [(0, "-- Chọn tỉnh/thành phố --")] + [(p.id, p.name) for p in provinces]
    wards = address_service.list_wards(province_id) if province_id else []
    form.ward_id.choices = [(0, "-- Chọn phường/xã --")] + [(w.id, w.name) for w in wards]


@bp.route("/addresses")
@customer_required
def addresses():
    return render_template("account/addresses.html", addresses=address_service.list_active_addresses(current_user),
                           max_addresses=current_app.config["MAX_ADDRESSES_PER_ACCOUNT"])


@bp.route("/addresses/new", methods=["GET", "POST"])
@customer_required
def address_new():
    form = AddressForm()
    _prepare_address_form(form, form.province_id.data if request.method == "POST" else None)
    if form.validate_on_submit():
        try:
            address_service.create_address(current_user, form.recipient_name.data, form.phone.data,
                                           form.ward_id.data, form.street_detail.data, form.is_default.data)
        except AddressLimitError as e:
            flash(str(e), "danger")
        else:
            flash("Đã thêm địa chỉ nhận hàng.", "success")
            return redirect(url_for("account.addresses"))
    return render_template("account/address_form.html", form=form, address=None)


@bp.route("/addresses/<int:address_id>/edit", methods=["GET", "POST"])
@customer_required
def address_edit(address_id):
    address = address_service.get_owned_address(current_user, address_id)
    if request.method == "GET":
        form = AddressForm(obj=address)
        form.province_id.data = address.ward.province_id
        _prepare_address_form(form, address.ward.province_id)
        form.ward_id.data = address.ward_id
    else:
        form = AddressForm()
        _prepare_address_form(form, form.province_id.data)
    if form.validate_on_submit():
        address_service.update_address(current_user, address, form.recipient_name.data, form.phone.data,
                                       form.ward_id.data, form.street_detail.data, form.is_default.data)
        flash("Đã cập nhật địa chỉ.", "success")
        return redirect(url_for("account.addresses"))
    return render_template("account/address_form.html", form=form, address=address)


@bp.route("/addresses/<int:address_id>/default", methods=["POST"])
@customer_required
def address_default(address_id):
    address_service.set_default(current_user, address_service.get_owned_address(current_user, address_id))
    flash("Đã đặt làm địa chỉ mặc định.", "success")
    return redirect(url_for("account.addresses"))


@bp.route("/addresses/<int:address_id>/delete", methods=["POST"])
@customer_required
def address_delete(address_id):
    address_service.delete_address(current_user, address_service.get_owned_address(current_user, address_id))
    flash("Đã xóa địa chỉ.", "info")
    return redirect(url_for("account.addresses"))


@bp.route("/api/wards")
@customer_required
def wards_api():
    """Danh sách phường/xã theo tỉnh, dùng cho ô chọn phụ thuộc trong form địa chỉ."""
    province_id = request.args.get("province_id", type=int)
    if not province_id:
        abort(400)
    return jsonify([{"id": w.id, "name": w.name} for w in address_service.list_wards(province_id)])


# ------------------------------------------------------------------ giỏ hàng
def _form_int(name, default=None):
    """Số nguyên từ form. Thiếu trường -> default; có trường nhưng rỗng/sai định dạng -> None (để báo lỗi,
    không âm thầm đổi thành giá trị mặc định)."""
    raw = request.form.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return None


@bp.route("/cart")
@customer_required
def cart():
    return render_template("account/cart.html", cart=cart_service.get_cart(current_user),
                           max_per_item=current_app.config["CART_MAX_QUANTITY_PER_ITEM"])


@bp.route("/cart/add", methods=["POST"])
@customer_required
def cart_add():
    try:
        message, level = cart_service.add_to_cart(
            current_user, _form_int("variant_id"), _form_int("quantity", default=1))
    except CartError as e:
        flash(str(e), "danger")
        return redirect_back("account.cart")
    flash(message, level)
    return redirect(url_for("account.cart"))


@bp.route("/cart/update", methods=["POST"])
@customer_required
def cart_update():
    try:
        message, level = cart_service.update_quantity(
            current_user, _form_int("variant_id"), _form_int("quantity"))
        flash(message, level)
    except CartError as e:
        flash(str(e), "danger")
    return redirect(url_for("account.cart"))


@bp.route("/cart/remove", methods=["POST"])
@customer_required
def cart_remove():
    try:
        cart_service.remove_item(current_user, _form_int("variant_id"))
        flash("Đã xóa sản phẩm khỏi giỏ hàng.", "info")
    except CartError as e:
        flash(str(e), "danger")
    return redirect(url_for("account.cart"))


@bp.route("/cart/clean", methods=["POST"])
@customer_required
def cart_clean():
    removed = cart_service.remove_unavailable(current_user)
    flash(f"Đã xóa {removed} sản phẩm không còn bán." if removed else "Không có sản phẩm nào cần xóa.", "info")
    return redirect(url_for("account.cart"))
