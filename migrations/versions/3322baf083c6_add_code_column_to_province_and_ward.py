"""add code column to province and ward

Revision ID: 3322baf083c6
Revises:
Create Date: 2026-11-19 09:39:00

Thêm cột code (mã hành chính quốc gia) vào bảng province và ward.
Cột này dùng làm khóa nhận diện khi đồng bộ dữ liệu hành chính từ file JSON,
tránh phụ thuộc vào tên tỉnh/xã có thể thay đổi theo đợt sáp nhập.

An toàn khi chạy nhiều lần — dùng try/except để bỏ qua nếu cột đã tồn tại.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError

revision = '3322baf083c6'
down_revision = None
branch_labels = None
depends_on = None


def _add_column_safe(table: str, column_name: str, column_def):
    """Thêm cột nếu chưa tồn tại (an toàn với SQLite và MySQL)."""
    try:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(column_def)
    except (OperationalError, Exception) as e:
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            pass  # Cột đã có, bỏ qua
        else:
            raise


def _create_index_safe(index_name: str, table: str, columns: list, unique: bool = False):
    """Tạo index nếu chưa tồn tại."""
    try:
        op.create_index(index_name, table, columns, unique=unique)
    except (OperationalError, Exception) as e:
        msg = str(e).lower()
        if "already exists" in msg:
            pass
        else:
            raise


def upgrade():
    # Province: thêm cột code (mã hành chính tỉnh/thành, ví dụ "01", "79")
    _add_column_safe(
        "province", "code",
        sa.Column("code", sa.String(length=10), nullable=True)
    )
    _create_index_safe("ix_province_code", "province", ["code"], unique=True)

    # Ward: thêm cột code (mã hành chính phường/xã, ví dụ "00004", "27184")
    _add_column_safe(
        "ward", "code",
        sa.Column("code", sa.String(length=10), nullable=True)
    )
    _create_index_safe("ix_ward_code", "ward", ["code"], unique=True)


def downgrade():
    # Xóa index và cột ward.code
    try:
        op.drop_index("ix_ward_code", table_name="ward")
    except Exception:
        pass
    try:
        with op.batch_alter_table("ward") as batch_op:
            batch_op.drop_column("code")
    except Exception:
        pass

    # Xóa index và cột province.code
    try:
        op.drop_index("ix_province_code", table_name="province")
    except Exception:
        pass
    try:
        with op.batch_alter_table("province") as batch_op:
            batch_op.drop_column("code")
    except Exception:
        pass
