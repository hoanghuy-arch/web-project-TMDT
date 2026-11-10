"""Thành phần dùng chung cho các model."""
from datetime import datetime, timezone

from sqlalchemy import event

from app.extensions import db


# Các cột "decimal" trong ERD: tiền VND không có phần lẻ
Money = db.Numeric(12, 0)


def utcnow():
    """Thời điểm hiện tại theo UTC, không kèm tzinfo (MySQL DATETIME không lưu múi giờ).
    Khi hiển thị, bộ lọc `dt` đổi sang giờ Việt Nam (UTC+7)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


def in_list(column, values):
    """Sinh biểu thức CHECK: column IN ('A','B',...)."""
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class ImmutableRecordError(Exception):
    """Ném ra khi cố sửa/xóa bản ghi chỉ-thêm (lịch sử trạng thái, nhật ký, giao dịch kho)."""


def make_append_only(model):
    """Chặn UPDATE/DELETE qua ORM. Kết hợp với phân quyền DB (chỉ cấp INSERT/SELECT) khi triển khai thật."""
    def _forbid(_mapper, _connection, target):
        raise ImmutableRecordError(
            f"{target.__class__.__name__} chỉ được thêm mới, không được sửa hoặc xóa.")

    event.listen(model, "before_update", _forbid)
    event.listen(model, "before_delete", _forbid)
