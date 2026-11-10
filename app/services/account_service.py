"""Hồ sơ cá nhân và đổi mật khẩu (FR-KH04)."""
from app.extensions import db
from app.utils.validators import normalize_phone


class PasswordChangeError(Exception):
    pass


def update_profile(account, full_name, phone):
    """Email là định danh đăng nhập nên không cho đổi ở đây."""
    account.full_name = full_name.strip()
    account.phone = normalize_phone(phone)
    db.session.commit()
    return account


def change_password(account, current_password, new_password):
    if not account.check_password(current_password or ""):
        raise PasswordChangeError("Mật khẩu hiện tại không đúng.")
    if account.check_password(new_password):
        raise PasswordChangeError("Mật khẩu mới phải khác mật khẩu hiện tại.")
    account.set_password(new_password)
    db.session.commit()
