"""Form xác thực (Flask-WTF: có sẵn CSRF token)."""
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.extensions import db
from app.models import Account
from app.utils.form_validators import email_filter as _email_filter
from app.utils.form_validators import password_validator as _password_validator
from app.utils.form_validators import phone_validator as _phone_validator


class RegisterForm(FlaskForm):
    full_name = StringField("Họ và tên", filters=[lambda v: v.strip() if v else v], validators=[
        DataRequired("Vui lòng nhập họ tên."), Length(min=2, max=100, message="Họ tên từ 2 đến 100 ký tự.")])
    email = StringField("Email", filters=[_email_filter], validators=[
        DataRequired("Vui lòng nhập email."), Email("Email không hợp lệ."), Length(max=255)])
    phone = StringField("Số điện thoại", validators=[DataRequired("Vui lòng nhập số điện thoại."), _phone_validator])
    password = PasswordField("Mật khẩu", validators=[DataRequired("Vui lòng nhập mật khẩu."), _password_validator])
    confirm_password = PasswordField("Nhập lại mật khẩu", validators=[
        DataRequired("Vui lòng nhập lại mật khẩu."), EqualTo("password", "Mật khẩu nhập lại không khớp.")])

    def validate_email(self, field):
        if db.session.execute(db.select(Account.id).filter_by(email=field.data)).first():
            raise ValidationError("Email này đã được đăng ký.")


class LoginForm(FlaskForm):
    email = StringField("Email", filters=[_email_filter], validators=[DataRequired("Vui lòng nhập email.")])
    password = PasswordField("Mật khẩu", validators=[DataRequired("Vui lòng nhập mật khẩu.")])
    remember = BooleanField("Ghi nhớ đăng nhập")


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", filters=[_email_filter], validators=[
        DataRequired("Vui lòng nhập email."), Email("Email không hợp lệ.")])


class ResetPasswordForm(FlaskForm):
    password = PasswordField("Mật khẩu mới", validators=[DataRequired("Vui lòng nhập mật khẩu."), _password_validator])
    confirm_password = PasswordField("Nhập lại mật khẩu mới", validators=[
        DataRequired("Vui lòng nhập lại mật khẩu."), EqualTo("password", "Mật khẩu nhập lại không khớp.")])
