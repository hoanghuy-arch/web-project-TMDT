"""Form khu vực tài khoản (Flask-WTF: có sẵn CSRF token)."""
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError

from app.utils.form_validators import password_validator, phone_validator, strip_filter


class ChoiceField(SelectField):
    """SelectField với thông báo lỗi tiếng Việt. Giá trị gửi lên phải nằm trong danh sách lựa chọn do server gán."""

    def process_formdata(self, valuelist):
        if not valuelist:
            return
        try:
            self.data = self.coerce(valuelist[0])
        except ValueError:
            self.data = None
            raise ValueError("Lựa chọn không hợp lệ.")

    def pre_validate(self, form):
        if self.data is None:                       # để DataRequired báo "vui lòng chọn"
            return
        if self.data not in {value for value, *_ in (self.choices or [])}:
            raise ValidationError("Lựa chọn không hợp lệ.")


class ProfileForm(FlaskForm):
    full_name = StringField("Họ và tên", filters=[strip_filter], validators=[
        DataRequired("Vui lòng nhập họ tên."), Length(min=2, max=100, message="Họ tên từ 2 đến 100 ký tự.")])
    phone = StringField("Số điện thoại", validators=[DataRequired("Vui lòng nhập số điện thoại."), phone_validator])


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Mật khẩu hiện tại", validators=[DataRequired("Vui lòng nhập mật khẩu hiện tại.")])
    new_password = PasswordField("Mật khẩu mới", validators=[DataRequired("Vui lòng nhập mật khẩu mới."), password_validator])
    confirm_password = PasswordField("Nhập lại mật khẩu mới", validators=[
        DataRequired("Vui lòng nhập lại mật khẩu mới."), EqualTo("new_password", "Mật khẩu nhập lại không khớp.")])


class AddressForm(FlaskForm):
    recipient_name = StringField("Họ tên người nhận", filters=[strip_filter], validators=[
        DataRequired("Vui lòng nhập họ tên người nhận."), Length(min=2, max=100, message="Họ tên từ 2 đến 100 ký tự.")])
    phone = StringField("Số điện thoại người nhận", validators=[
        DataRequired("Vui lòng nhập số điện thoại."), phone_validator])
    # Danh sách lựa chọn được gán trong route (tỉnh từ DB, phường theo tỉnh đã chọn). 0 = chưa chọn.
    province_id = ChoiceField("Tỉnh/Thành phố", coerce=int, validators=[DataRequired("Vui lòng chọn tỉnh/thành phố.")])
    ward_id = ChoiceField("Phường/Xã", coerce=int, validators=[DataRequired("Vui lòng chọn phường/xã.")])
    street_detail = StringField("Số nhà, tên đường", filters=[strip_filter], validators=[
        DataRequired("Vui lòng nhập số nhà, tên đường."), Length(min=3, max=255, message="Địa chỉ từ 3 đến 255 ký tự.")])
    is_default = BooleanField("Đặt làm địa chỉ mặc định")
