"""Form nhập liệu khu vực quản trị viên (Flask-WTF)."""
from flask_wtf import FlaskForm
from wtforms import (BooleanField, DecimalField, IntegerField, PasswordField,
                     SelectField, StringField, TextAreaField)
from wtforms.validators import (DataRequired, Email, EqualTo, Length,
                                NumberRange, Optional, ValidationError)

from app.constants import DiscountType, EntityStatus
from app.extensions import db
from app.models import Account, Carrier, Category, Color, Promotion, Size, Supplier
from app.utils.form_validators import email_filter as _email_filter
from app.utils.form_validators import password_validator as _password_validator
from app.utils.form_validators import phone_validator as _phone_validator
from app.utils.form_validators import strip_filter as _strip


# ------------------------------------------------------------------ Danh mục & Thuộc tính
class CategoryForm(FlaskForm):
    name = StringField("Tên danh mục", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập tên danh mục."), Length(max=100)])
    parent_category_id = SelectField("Danh mục cha", coerce=int, validators=[Optional()])
    is_active = BooleanField("Đang hoạt động", default=True)


class SizeForm(FlaskForm):
    name = StringField("Tên kích cỡ", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập kích cỡ (ví dụ S, M, L, XL)."), Length(max=20)])
    sort_order = IntegerField("Thứ tự sắp xếp", default=0, validators=[
        DataRequired("Vui lòng nhập thứ tự sắp xếp.")])


class ColorForm(FlaskForm):
    name = StringField("Tên màu", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập tên màu (ví dụ Đen, Trắng)."), Length(max=50)])
    hex_code = StringField("Mã màu Hex", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập mã màu (ví dụ #000000)."), Length(min=4, max=7)])

    def validate_hex_code(self, field):
        val = (field.data or "").strip()
        if not val.startswith("#") or len(val) not in (4, 7):
            raise ValidationError("Mã màu phải bắt đầu bằng dấu # (ví dụ #000000 hoặc #FFF).")


# ------------------------------------------------------------------ Sản phẩm, Biến thể, Ảnh
class ProductForm(FlaskForm):
    category_id = SelectField("Danh mục", coerce=int, validators=[DataRequired("Vui lòng chọn danh mục.")])
    name = StringField("Tên sản phẩm", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập tên sản phẩm."), Length(max=200)])
    price = DecimalField("Giá bán (VND)", places=0, validators=[
        DataRequired("Vui lòng nhập giá bán."), NumberRange(min=0, message="Giá không được âm.")])
    description = TextAreaField("Mô tả sản phẩm", filters=[_strip])
    status = SelectField("Trạng thái", choices=[
        (EntityStatus.ACTIVE, "Đang kinh doanh"),
        (EntityStatus.INACTIVE, "Ngừng kinh doanh")
    ], default=EntityStatus.ACTIVE)


class VariantForm(FlaskForm):
    size_id = SelectField("Kích cỡ", coerce=int, validators=[DataRequired("Vui lòng chọn kích cỡ.")])
    color_id = SelectField("Màu sắc", coerce=int, validators=[DataRequired("Vui lòng chọn màu sắc.")])
    sku = StringField("Mã SKU", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập SKU."), Length(max=50)])
    stock_quantity = IntegerField("Số lượng tồn kho ban đầu", default=0, validators=[
        NumberRange(min=0, message="Tồn kho không được âm.")])
    status = SelectField("Trạng thái", choices=[
        (EntityStatus.ACTIVE, "Đang kinh doanh"),
        (EntityStatus.INACTIVE, "Ngừng kinh doanh")
    ], default=EntityStatus.ACTIVE)


class ProductImageForm(FlaskForm):
    url = StringField("Đường dẫn ảnh (URL hoặc đường dẫn tĩnh)", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập URL ảnh."), Length(max=500)])
    is_primary = BooleanField("Ảnh đại diện chính", default=False)
    sort_order = IntegerField("Thứ tự sắp xếp", default=0)


# ------------------------------------------------------------------ Đối tác: Nhà cung cấp & Vận chuyển
class SupplierForm(FlaskForm):
    name = StringField("Tên nhà cung cấp", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập tên nhà cung cấp."), Length(max=150)])
    contact_name = StringField("Người liên hệ", filters=[_strip], validators=[Length(max=100)])
    phone = StringField("Số điện thoại", validators=[DataRequired("Vui lòng nhập số điện thoại."), _phone_validator])
    email = StringField("Email", filters=[_email_filter], validators=[
        Optional(), Email("Email không hợp lệ."), Length(max=255)])
    address_detail = StringField("Địa chỉ", filters=[_strip], validators=[Length(max=255)])
    status = SelectField("Trạng thái", choices=[
        (EntityStatus.ACTIVE, "Đang hợp tác"),
        (EntityStatus.INACTIVE, "Ngừng hợp tác")
    ], default=EntityStatus.ACTIVE)


class CarrierForm(FlaskForm):
    name = StringField("Tên đơn vị vận chuyển", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập tên đơn vị vận chuyển."), Length(max=100)])
    is_active = BooleanField("Đang hoạt động", default=True)


# ------------------------------------------------------------------ Khuyến mãi & Phí ship
class PromotionForm(FlaskForm):
    code = StringField("Mã khuyến mãi", filters=[lambda v: v.strip().upper() if v else v], validators=[
        DataRequired("Vui lòng nhập mã khuyến mãi."), Length(min=3, max=30)])
    discount_type = SelectField("Loại giảm giá", choices=[
        (DiscountType.PERCENT, "Giảm theo phần trăm (%)"),
        (DiscountType.FIXED, "Giảm số tiền cố định (VND)")
    ], default=DiscountType.PERCENT)
    discount_value = DecimalField("Giá trị giảm", places=0, validators=[
        DataRequired("Vui lòng nhập giá trị giảm."), NumberRange(min=1, message="Giá trị giảm phải lớn hơn 0.")])
    min_order_value = DecimalField("Giá trị đơn hàng tối thiểu (VND)", places=0, default=0, validators=[
        NumberRange(min=0, message="Đơn tối thiểu không được âm.")])
    max_discount = DecimalField("Mức giảm tối đa (VND, chỉ áp dụng cho %)", places=0, validators=[
        Optional(), NumberRange(min=0, message="Mức giảm tối đa không được âm.")])
    start_at = StringField("Thời gian bắt đầu (YYYY-MM-DD HH:MM)", filters=[_strip], validators=[
        DataRequired("Vui lòng chọn thời gian bắt đầu.")])
    end_at = StringField("Thời gian kết thúc (YYYY-MM-DD HH:MM)", filters=[_strip], validators=[
        DataRequired("Vui lòng chọn thời gian kết thúc.")])
    usage_limit = IntegerField("Giới hạn số lượt dùng (để trống nếu không giới hạn)", validators=[
        Optional(), NumberRange(min=1, message="Số lượt dùng phải lớn hơn 0.")])
    status = SelectField("Trạng thái", choices=[
        (EntityStatus.ACTIVE, "Đang áp dụng"),
        (EntityStatus.INACTIVE, "Tạm ngưng")
    ], default=EntityStatus.ACTIVE)


class ShippingFeeRuleForm(FlaskForm):
    province_id = SelectField("Tỉnh / Thành phố", coerce=int, validators=[Optional()])
    fee = DecimalField("Phí vận chuyển (VND)", places=0, validators=[
        DataRequired("Vui lòng nhập phí vận chuyển."), NumberRange(min=0, message="Phí không được âm.")])
    free_threshold = DecimalField("Ngưỡng miễn phí ship (VND, để trống nếu không miễn phí)", places=0, validators=[
        Optional(), NumberRange(min=0, message="Ngưỡng không được âm.")])
    is_active = BooleanField("Đang áp dụng", default=True)


# ------------------------------------------------------------------ Người dùng & Phân quyền
class UserCreateForm(FlaskForm):
    full_name = StringField("Họ và tên", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập họ tên."), Length(min=2, max=100)])
    email = StringField("Email", filters=[_email_filter], validators=[
        DataRequired("Vui lòng nhập email."), Email("Email không hợp lệ."), Length(max=255)])
    phone = StringField("Số điện thoại", validators=[DataRequired("Vui lòng nhập số điện thoại."), _phone_validator])
    password = PasswordField("Mật khẩu khởi tạo", validators=[
        DataRequired("Vui lòng nhập mật khẩu."), _password_validator])
    confirm_password = PasswordField("Nhập lại mật khẩu", validators=[
        DataRequired("Vui lòng nhập lại mật khẩu."), EqualTo("password", "Mật khẩu không khớp.")])
    role_id = SelectField("Vai trò", coerce=int, validators=[DataRequired("Vui lòng chọn vai trò.")])

    def validate_email(self, field):
        if db.session.scalar(db.select(Account.id).filter_by(email=field.data)):
            raise ValidationError("Email này đã được sử dụng.")


class UserEditForm(FlaskForm):
    full_name = StringField("Họ và tên", filters=[_strip], validators=[
        DataRequired("Vui lòng nhập họ tên."), Length(min=2, max=100)])
    phone = StringField("Số điện thoại", validators=[DataRequired("Vui lòng nhập số điện thoại."), _phone_validator])
    role_id = SelectField("Vai trò", coerce=int, validators=[DataRequired("Vui lòng chọn vai trò.")])
    is_active = BooleanField("Tài khoản đang hoạt động")
    is_locked = BooleanField("Khóa tài khoản")
    reset_failed_logins = BooleanField("Đặt lại số lần đăng nhập sai về 0")
