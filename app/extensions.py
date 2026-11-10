"""Khai báo extension dùng chung (khởi tạo ở đây, gắn vào app trong create_app)."""
import sqlite3

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine

# Đặt tên ràng buộc ổn định để migration (Alembic) sửa/xóa được ràng buộc.
# Ràng buộc đã tự đặt tên rõ ràng (UNIQUE kép, FK kép) giữ nguyên tên đó.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
migrate = Migrate()
csrf = CSRFProtect()
mail = Mail()
limiter = Limiter(key_func=get_remote_address)
scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Vui lòng đăng nhập để tiếp tục."
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record):
    """SQLite mặc định KHÔNG kiểm tra khóa ngoại; bật lên để dev/test hành xử giống MySQL InnoDB."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
