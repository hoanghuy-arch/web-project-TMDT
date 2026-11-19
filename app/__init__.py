"""Application factory của SportZone."""
import sqlite3
from flask import Flask, jsonify, render_template, request
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import get_config
from app.extensions import csrf, db, limiter, login_manager, mail, migrate
from app.logging_config import configure_logging
from app.utils.formatters import register_filters


# Cấu hình SQLite hỗ trợ hàm lower() cho chuỗi Unicode tiếng Việt có dấu
@event.listens_for(Engine, "connect")
def _setup_sqlite_connection(dbapi_conn, connection_record):
    if isinstance(dbapi_conn, sqlite3.Connection):
        dbapi_conn.create_function("lower", 1, lambda s: s.lower() if s else s)


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    configure_logging(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_hooks(app)
    register_filters(app)
    _init_scheduler(app)

    @app.route("/health")
    def health():
        """Endpoint cho UptimeRobot / Docker healthcheck."""
        return jsonify(status="ok")

    @app.route("/favicon.ico")
    def favicon():
        """Phục vụ favicon trực tiếp cho trình duyệt truy vấn /favicon.ico."""
        return app.send_static_file("img/favicon.png")

    return app


def _init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)

    # Import models để SQLAlchemy/Flask-Migrate nhận biết các bảng (Task 2)
    from app import models  # noqa: F401


def _register_blueprints(app):
    from app.auth import bp as auth_bp
    from app.shop import bp as shop_bp
    from app.account import bp as account_bp
    from app.payment import bp as payment_bp
    from app.staff import bp as staff_bp
    from app.admin import bp as admin_bp

    app.register_blueprint(shop_bp)                              # công khai, đường dẫn gốc
    app.register_blueprint(auth_bp, url_prefix="/auth")          # công khai
    app.register_blueprint(account_bp, url_prefix="/account")    # khách hàng
    app.register_blueprint(payment_bp, url_prefix="/payment")    # khách hàng + cổng thanh toán
    app.register_blueprint(staff_bp, url_prefix="/staff")        # nhân viên, quản trị viên
    app.register_blueprint(admin_bp, url_prefix="/admin")        # quản trị viên


def _register_error_handlers(app):
    def _render(code, title, message):
        if request.path.startswith(("/payment/vnpay/ipn", "/health")):
            return jsonify(error=title), code
        return render_template("errors/error.html", code=code, title=title, message=message), code

    @app.errorhandler(403)
    def forbidden(_e):
        return _render(403, "Không có quyền truy cập", "Bạn không có quyền thực hiện thao tác này.")

    @app.errorhandler(404)
    def not_found(_e):
        return _render(404, "Không tìm thấy trang", "Trang bạn tìm không tồn tại hoặc đã bị xóa.")

    @app.errorhandler(429)
    def too_many(_e):
        return _render(429, "Thao tác quá nhanh", "Bạn gửi yêu cầu quá nhiều lần. Vui lòng thử lại sau ít phút.")

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        app.logger.exception("Lỗi 500:", exc_info=e)
        return _render(500, "Lỗi hệ thống", "Đã có lỗi xảy ra. Vui lòng thử lại sau.")


def _register_hooks(app):
    _schema_migrated = False

    @app.before_request
    def check_schema_updates():
        nonlocal _schema_migrated
        if _schema_migrated or app.config.get("TESTING"):
            return
        _schema_migrated = True
        try:
            with db.engine.connect() as conn:
                for col_name, col_type in [
                    ("service_name", "VARCHAR(100)"),
                    ("expected_delivery_at", "DATETIME"),
                    ("label_url", "VARCHAR(255)")
                ]:
                    try:
                        conn.execute(db.text(f"ALTER TABLE shipment ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        app.logger.info(f"Đã bổ sung cột {col_name} vào bảng shipment.")
                    except Exception:
                        pass
        except Exception as e:
            app.logger.warning(f"Lỗi kiểm tra schema tự động: {e}")

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp


def _init_scheduler(app):
    """Khởi động các tác vụ nền (FR-HT01). Bỏ qua khi TESTING."""
    from app.tasks.scheduler import init_scheduler
    init_scheduler(app)
