"""Phân hệ A: tài khoản, phân quyền, địa chỉ (role, permission, role_permission, account,
province, ward, address, password_reset_token). Cột khớp ERD Phân hệ A."""
from datetime import timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.constants import ROLE_ADMIN
from app.extensions import db, login_manager
from app.models.base import utcnow

# R02: role N-N permission, bảng trung gian chỉ có khóa kép
role_permission = db.Table(
    "role_permission",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
)


class Role(db.Model):
    __tablename__ = "role"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)   # lưu mã vai trò: CUSTOMER / STAFF / ADMIN

    permissions = db.relationship("Permission", secondary=role_permission, back_populates="roles")
    accounts = db.relationship("Account", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"


class Permission(db.Model):
    __tablename__ = "permission"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True)   # ví dụ: stock.receipt
    description = db.Column(db.String(255))

    roles = db.relationship("Role", secondary=role_permission, back_populates="permissions")


class Account(UserMixin, db.Model):
    __tablename__ = "account"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"), nullable=False, index=True)   # R01
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)      # chỉ lưu bản băm
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)                          # khóa tạm sau 5 lần sai
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    role = db.relationship("Role", back_populates="accounts")
    addresses = db.relationship("Address", back_populates="account")
    orders = db.relationship("SalesOrder", back_populates="account", foreign_keys="SalesOrder.account_id")
    cart_items = db.relationship("CartItem", back_populates="account", cascade="all, delete-orphan")

    __table_args__ = (
        db.CheckConstraint("failed_login_count >= 0", name="failed_login_non_negative"),
    )

    # --- mật khẩu ---
    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    # --- vai trò, quyền ---
    @property
    def role_code(self):
        return self.role.name if self.role else None

    def has_permission(self, code):
        """Quản trị viên có toàn bộ quyền nghiệp vụ; vai trò khác kiểm tra theo bảng role_permission."""
        if self.role_code == ROLE_ADMIN:
            return True
        return any(p.code == code for p in self.role.permissions)

    # --- khóa tài khoản khi đăng nhập sai ---
    @property
    def is_locked(self):
        return self.locked_until is not None and self.locked_until > utcnow()

    def register_failed_login(self, max_attempts, lock_minutes):
        self.failed_login_count = (self.failed_login_count or 0) + 1
        if self.failed_login_count >= max_attempts:
            self.locked_until = utcnow() + timedelta(minutes=lock_minutes)
            self.failed_login_count = 0

    def register_successful_login(self):
        self.failed_login_count = 0
        self.locked_until = None

    def __repr__(self):
        return f"<Account {self.email}>"


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(Account, int(user_id))
    # Tài khoản bị vô hiệu hóa sẽ bị đăng xuất ở request kế tiếp
    return user if user and user.is_active else None


class PasswordResetToken(db.Model):
    """R06: mã đặt lại mật khẩu. Chỉ lưu bản băm của token, token gốc chỉ gửi qua email."""
    __tablename__ = "password_reset_token"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)   # SHA-256 hex
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)

    account = db.relationship("Account")

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > utcnow()


class Province(db.Model):
    __tablename__ = "province"

    id   = db.Column(db.Integer, primary_key=True)
    # Mã hành chính quốc gia (ví dụ: "01" = Hà Nội, "79" = TP.HCM).
    # Dùng làm khóa nhận diện khi đồng bộ dữ liệu, tránh phụ thuộc vào tên có thể thay đổi.
    code = db.Column(db.String(10), nullable=True, unique=True, index=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    wards = db.relationship("Ward", back_populates="province")            # R04
    shipping_fee_rule = db.relationship("ShippingFeeRule", back_populates="province", uselist=False)  # R14


class Ward(db.Model):
    __tablename__ = "ward"

    id          = db.Column(db.Integer, primary_key=True)
    # Mã hành chính quốc gia (ví dụ: "00004" = Ba Đình – Hà Nội).
    code        = db.Column(db.String(10), nullable=True, unique=True, index=True)
    province_id = db.Column(db.Integer, db.ForeignKey("province.id"), nullable=False)
    name        = db.Column(db.String(100), nullable=False)

    province = db.relationship("Province", back_populates="wards")

    __table_args__ = (
        db.UniqueConstraint("province_id", "name", name="uq_ward_province_name"),
    )


class Address(db.Model):
    """Địa chỉ nhận hàng. Không sửa đè địa chỉ đã gắn đơn: sửa = tạo mới, bản cũ is_active=False."""
    __tablename__ = "address"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False, index=True)  # R03
    ward_id = db.Column(db.Integer, db.ForeignKey("ward.id"), nullable=False)                    # R05
    recipient_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    street_detail = db.Column(db.String(255), nullable=False)             # số nhà, tên đường
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    account = db.relationship("Account", back_populates="addresses")
    ward = db.relationship("Ward")

    __table_args__ = (
        # Cần để sales_order tham chiếu khóa kép (address_id, account_id): địa chỉ giao phải thuộc đúng người đặt
        db.UniqueConstraint("id", "account_id", name="uq_address_id_account"),
    )

    @property
    def province(self):
        return self.ward.province

    @property
    def full_address(self):
        return f"{self.street_detail}, {self.ward.name}, {self.ward.province.name}"
