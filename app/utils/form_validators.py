"""Validator WTForms dùng chung cho nhiều form (bọc các hàm thuần trong utils/validators.py)."""
from wtforms.validators import ValidationError

from app.utils.validators import is_valid_phone, normalize_email, password_problem


def email_filter(value):
    return normalize_email(value) if value else value


def strip_filter(value):
    return value.strip() if isinstance(value, str) else value


def phone_validator(_form, field):
    if not is_valid_phone(field.data):
        raise ValidationError("Số điện thoại không hợp lệ (ví dụ: 0912345678).")


def password_validator(_form, field):
    problem = password_problem(field.data)
    if problem:
        raise ValidationError(problem)
