"""drop uq_ward_province_name constraint

Revision ID: 753f5f73ef9b
Revises: 3322baf083c6
Create Date: 2026-11-19 09:54:57.273057

Bỏ UniqueConstraint uq_ward_province_name trên bảng ward.
Lý do: Trong cùng 1 tỉnh có thể có các xã/phường tên gần giống nhau nhưng dấu khác nhau
(ví dụ: 'Văn Lang' vs 'Văn Lăng' ở Thái Nguyên, 'Tân Thành' vs 'Tân Thạnh' ở Long An).
Trên MySQL với collation accent-insensitive (utf8mb4_0900_ai_ci / utf8mb4_general_ci),
các tên này bị coi là trùng lặp và gây lỗi IntegrityError 1062.
Khóa nhận diện chính xác hiện tại là Ward.code (mã hành chính quốc gia).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '753f5f73ef9b'
down_revision = '3322baf083c6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        # MySQL: dùng raw SQL để drop index (batch_alter_table không hoạt động trên MySQL)
        try:
            op.execute(sa.text("ALTER TABLE ward DROP INDEX uq_ward_province_name"))
        except Exception:
            pass  # Index không tồn tại → bỏ qua
        try:
            op.execute(sa.text(
                "ALTER TABLE ward ADD INDEX ix_ward_province_id (province_id)"
            ))
        except Exception:
            pass  # Index đã tồn tại → bỏ qua
    else:
        # SQLite và các DB khác: dùng batch mode
        try:
            with op.batch_alter_table('ward', schema=None) as batch_op:
                batch_op.drop_constraint('uq_ward_province_name', type_='unique')
        except Exception:
            pass
        try:
            with op.batch_alter_table('ward', schema=None) as batch_op:
                batch_op.create_index('ix_ward_province_id', ['province_id'], unique=False)
        except Exception:
            pass


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        try:
            op.execute(sa.text("ALTER TABLE ward DROP INDEX ix_ward_province_id"))
        except Exception:
            pass
        try:
            op.execute(sa.text(
                "ALTER TABLE ward ADD UNIQUE INDEX uq_ward_province_name (province_id, name)"
            ))
        except Exception:
            pass
    else:
        try:
            with op.batch_alter_table('ward', schema=None) as batch_op:
                batch_op.drop_index('ix_ward_province_id')
        except Exception:
            pass
        try:
            with op.batch_alter_table('ward', schema=None) as batch_op:
                batch_op.create_unique_constraint('uq_ward_province_name', ['province_id', 'name'])
        except Exception:
            pass
