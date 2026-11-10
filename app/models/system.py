"""Phân hệ G: hệ thống (app_setting, audit_log). Cột khớp ERD Phân hệ G."""
from app.constants import SettingKey
from app.extensions import db
from app.models.base import make_append_only, utcnow


class AppSetting(db.Model):
    """Bảng cấu hình khóa-giá trị, độc lập có chủ đích (thời hạn đổi trả, thời gian giữ hàng...)."""
    __tablename__ = "app_setting"

    setting_key = db.Column(db.String(60), primary_key=True)
    setting_value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @classmethod
    def get_int(cls, key, default):
        row = db.session.get(cls, key)
        try:
            return int(row.setting_value) if row else default
        except (TypeError, ValueError):
            return default

    @classmethod
    def set_value(cls, key, value, description=None):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(setting_key=key, setting_value=str(value), description=description)
            db.session.add(row)
        else:
            row.setting_value = str(value)
        return row

    @classmethod
    def payment_timeout_minutes(cls, default=15):
        return cls.get_int(SettingKey.PAYMENT_TIMEOUT_MINUTES, default)


class AuditLog(db.Model):
    """Nhật ký thao tác nhạy cảm (đổi giá, đổi quyền, hủy đơn, điều chỉnh kho...), CHỈ THÊM.
    entity_id là tham chiếu mềm (không có khóa ngoại) vì trỏ tới nhiều loại thực thể."""
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), index=True)     # R36, NULL = hệ thống tự ghi
    action = db.Column(db.String(60), nullable=False, index=True)                   # ví dụ: order.cancel
    entity_name = db.Column(db.String(40), nullable=False)                          # tên bảng/thực thể bị tác động
    entity_id = db.Column(db.Integer, nullable=False)                               # tham chiếu mềm
    old_value = db.Column(db.JSON)
    new_value = db.Column(db.JSON)
    ip_address = db.Column(db.String(45), nullable=False)                           # thao tác của hệ thống ghi "system"
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    account = db.relationship("Account")

    __table_args__ = (
        db.Index("ix_audit_log_entity", "entity_name", "entity_id"),
    )


make_append_only(AuditLog)
