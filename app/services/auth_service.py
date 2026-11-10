"""Nghiệp vụ xác thực: đăng ký, đăng nhập (khóa tạm), đặt lại mật khẩu (FR-KH01, 02, 03)."""
import math
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app, url_for
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.constants import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_STAFF
from app.extensions import db
from app.models import Account, PasswordResetToken, Role
from app.models.base import utcnow
from app.services.email_service import send_password_reset_email
from app.utils.security import generate_token, hash_token
from app.utils.validators import normalize_email, normalize_phone

# Dùng khi email không tồn tại: vẫn băm một mật khẩu giả để thời gian phản hồi gần như không đổi,
# tránh để kẻ xấu dò xem email nào đã đăng ký.
_DUMMY_HASH = generate_password_hash("mat-khau-gia-de-can-bang-thoi-gian")


class AuthStatus:
    OK = "OK"
    INVALID = "INVALID"        # sai email hoặc mật khẩu (thông báo chung, không nói sai cái nào)
    LOCKED = "LOCKED"          # đang bị khóa tạm
    INACTIVE = "INACTIVE"      # tài khoản bị vô hiệu hóa


@dataclass
class AuthResult:
    status: str
    account: Account = None
    minutes_left: int = 0


class EmailAlreadyUsedError(Exception):
    pass


# ---------------------------------------------------------------- vai trò
def get_or_create_role(name):
    """Dự phòng khi chưa chạy seed: đảm bảo vai trò tồn tại (seed đầy đủ ở scripts/seed.py)."""
    assert name in (ROLE_CUSTOMER, ROLE_STAFF, ROLE_ADMIN)
    role = db.session.execute(db.select(Role).filter_by(name=name)).scalar_one_or_none()
    if role is None:
        role = Role(name=name)
        db.session.add(role)
        db.session.flush()
    return role


def find_account_by_email(email):
    return db.session.execute(db.select(Account).filter_by(email=normalize_email(email))).scalar_one_or_none()


# ---------------------------------------------------------------- đăng ký
def register_customer(full_name, email, phone, password):
    """Tạo tài khoản KHÁCH HÀNG. Nhân viên/quản trị viên chỉ do quản trị viên tạo (Task 9)."""
    account = Account(
        full_name=full_name.strip(),
        email=normalize_email(email),
        phone=normalize_phone(phone),
        role=get_or_create_role(ROLE_CUSTOMER),
        is_active=True,
    )
    account.set_password(password)
    db.session.add(account)
    try:
        db.session.commit()
    except IntegrityError:           # hai yêu cầu cùng email gần như đồng thời
        db.session.rollback()
        raise EmailAlreadyUsedError()
    return account


# ---------------------------------------------------------------- đăng nhập
def authenticate(email, password):
    cfg = current_app.config
    account = find_account_by_email(email)

    if account is None:
        check_password_hash(_DUMMY_HASH, password or "")
        return AuthResult(AuthStatus.INVALID)

    if account.is_locked:
        return AuthResult(AuthStatus.LOCKED, minutes_left=_minutes_left(account))

    if not account.check_password(password or ""):
        account.register_failed_login(cfg["MAX_FAILED_LOGINS"], cfg["LOCKOUT_MINUTES"])
        db.session.commit()                       # phải lưu ngay dù request này báo lỗi
        if account.is_locked:
            current_app.logger.warning("Khóa tạm tài khoản id=%s do đăng nhập sai liên tiếp", account.id)
            return AuthResult(AuthStatus.LOCKED, minutes_left=_minutes_left(account))
        return AuthResult(AuthStatus.INVALID)

    if not account.is_active:                     # chỉ báo khi mật khẩu đúng, tránh lộ thông tin
        return AuthResult(AuthStatus.INACTIVE)

    account.register_successful_login()
    db.session.commit()
    return AuthResult(AuthStatus.OK, account=account)


def _minutes_left(account):
    seconds = (account.locked_until - utcnow()).total_seconds()
    return max(1, math.ceil(seconds / 60))


# ---------------------------------------------------------------- đặt lại mật khẩu
def request_password_reset(email):
    """Luôn trả về như nhau dù email có tồn tại hay không (chống dò tài khoản)."""
    cfg = current_app.config
    account = find_account_by_email(email)
    if account is None or not account.is_active:
        return

    now = utcnow()
    recent = db.session.execute(
        db.select(PasswordResetToken)
        .filter(PasswordResetToken.account_id == account.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.created_at > now - timedelta(seconds=cfg["PASSWORD_RESET_COOLDOWN_SECONDS"]))
    ).first()
    if recent:                                     # vừa gửi xong, không gửi dồn dập
        return

    # Mỗi tài khoản chỉ giữ một liên kết còn hiệu lực: xóa các token chưa dùng cũ
    db.session.execute(
        db.delete(PasswordResetToken).where(PasswordResetToken.account_id == account.id,
                                            PasswordResetToken.used_at.is_(None)))

    raw_token = generate_token()
    db.session.add(PasswordResetToken(
        account_id=account.id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(minutes=cfg["PASSWORD_RESET_TTL_MINUTES"]),
    ))
    db.session.commit()                            # token phải tồn tại trước khi người dùng bấm liên kết

    send_password_reset_email(account, url_for("auth.reset_password", token=raw_token, _external=True))


def get_valid_reset_token(raw_token):
    record = db.session.execute(
        db.select(PasswordResetToken).filter_by(token_hash=hash_token(raw_token))).scalar_one_or_none()
    if record is None or not record.is_valid or not record.account.is_active:
        return None
    return record


def complete_password_reset(raw_token, new_password):
    """Đổi mật khẩu bằng token. Token chỉ dùng được một lần. Đồng thời mở khóa tài khoản."""
    record = get_valid_reset_token(raw_token)
    if record is None:
        return False
    account = record.account
    account.set_password(new_password)
    account.failed_login_count = 0
    account.locked_until = None
    record.used_at = utcnow()
    db.session.flush()
    # Hủy mọi liên kết đặt lại khác còn hiệu lực của tài khoản
    db.session.execute(
        db.delete(PasswordResetToken).where(PasswordResetToken.account_id == account.id,
                                            PasswordResetToken.used_at.is_(None)))
    db.session.commit()
    return True
