"""Cấu hình ứng dụng SportZone theo từng môi trường."""
import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


def _bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-doi-khi-chay-that")

    # --- Cơ sở dữ liệu: MySQL 8 (utf8mb4). Không khai báo thì dùng SQLite để dev nhanh ---
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(basedir, "sportzone.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # --- Phiên đăng nhập và cookie ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 giờ
    REMEMBER_COOKIE_DURATION = timedelta(days=7)   # "Ghi nhớ đăng nhập"

    # --- CSRF (Flask-WTF) ---
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 4

    # --- Rate limit (Flask-Limiter) ---
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_LOGIN = "10 per minute"        # theo IP, chỉ áp dụng cho POST
    RATELIMIT_REGISTER = "20 per hour"
    RATELIMIT_FORGOT_PASSWORD = "10 per hour"
    RATELIMIT_RESET_PASSWORD = "20 per hour"

    # --- Đơn vị vận chuyển GHN (Giao Hàng Nhanh Open API) ---
    GHN_API_URL = os.environ.get("GHN_API_URL", "https://dev-online-gateway.ghn.vn/shiip/public-api")
    GHN_API_TOKEN = os.environ.get("GHN_API_TOKEN", "")
    GHN_SHOP_ID = os.environ.get("GHN_SHOP_ID", "")
    GHN_FROM_DISTRICT_ID = int(os.environ.get("GHN_FROM_DISTRICT_ID", "1454"))   # Quận 1, TP.HCM
    GHN_FROM_WARD_CODE = os.environ.get("GHN_FROM_WARD_CODE", "21211")           # Phường Bến Nghé

    # --- Email (Flask-Mail) ---
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 25))
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "SportZone <no-reply@sportzone.local>")
    MAIL_SUPPRESS_SEND = not os.environ.get("MAIL_USERNAME")  # chưa cấu hình thì chỉ in log, không gửi

    # --- Thanh toán sandbox ---
    PAYMENT_SANDBOX_MODE = _bool("PAYMENT_SANDBOX_MODE", True)
    VNPAY_TMN_CODE = os.environ.get("VNPAY_TMN_CODE", "")
    VNPAY_HASH_SECRET = os.environ.get("VNPAY_HASH_SECRET", "")
    VNPAY_URL = os.environ.get("VNPAY_URL", "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html")
    VNPAY_RETURN_URL = os.environ.get("VNPAY_RETURN_URL", "http://127.0.0.1:5000/payment/vnpay/return")
    # Cổng thanh toán GIẢ LẬP dùng khi chưa có tài khoản VNPay sandbox (chỉ để phát triển/demo, tự tắt ở production)
    PAYMENT_MOCK_ENABLED = _bool("PAYMENT_MOCK_ENABLED", True)

    # --- Giá trị mặc định khi seed bảng app_setting (sau đó quản trị viên chỉnh trong DB) ---
    DEFAULT_PAYMENT_TIMEOUT_MINUTES = 15        # thời gian giữ hàng đơn online
    DEFAULT_RETURN_WINDOW_DAYS = 7              # thời hạn đổi trả
    DEFAULT_FREE_SHIP_THRESHOLD = 500_000       # miễn phí vận chuyển từ ngưỡng này (VND)
    DEFAULT_LOW_STOCK_THRESHOLD = 5             # cảnh báo sắp hết hàng

    # --- Đăng nhập sai: khóa tạm ---
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15

    # --- Đặt lại mật khẩu ---
    PASSWORD_RESET_TTL_MINUTES = 30          # thời hạn liên kết
    PASSWORD_RESET_COOLDOWN_SECONDS = 60     # không gửi lại quá dày cho cùng một tài khoản

    # --- Giỏ hàng, sổ địa chỉ ---
    CART_MAX_QUANTITY_PER_ITEM = 10          # tối đa mỗi biến thể trong giỏ
    CART_MAX_LINES = 30                      # tối đa số dòng trong giỏ
    MAX_ADDRESSES_PER_ACCOUNT = 10           # số địa chỉ đang dùng tối đa

    # --- Phân trang ---
    PRODUCTS_PER_PAGE = 12
    ORDERS_PER_PAGE = 10
    ADMIN_ITEMS_PER_PAGE = 20

    # --- Log: giữ tối thiểu 30 ngày ---
    LOG_DIR = os.path.join(basedir, "logs")
    LOG_RETENTION_DAYS = 30

    # --- Tác vụ nền ---
    SCHEDULER_ENABLED = _bool("SCHEDULER_ENABLED", True)
    EXPIRE_ORDERS_INTERVAL_MINUTES = 1


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SCHEDULER_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = None
    PAYMENT_MOCK_ENABLED = False          # bật riêng trong từng test cần cổng giả lập
    VNPAY_TMN_CODE = ""
    VNPAY_HASH_SECRET = ""


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True      # chỉ gửi cookie qua HTTPS
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    PAYMENT_MOCK_ENABLED = False          # production tuyệt đối không dùng cổng giả lập

    @classmethod
    def validate(cls):
        if cls.SECRET_KEY.startswith("dev-secret"):
            raise RuntimeError("Production bắt buộc đặt SECRET_KEY riêng trong biến môi trường.")


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(name=None):
    name = name or os.environ.get("FLASK_ENV", "default")
    cfg = CONFIG_MAP.get(name, DevelopmentConfig)
    if hasattr(cfg, "validate"):
        cfg.validate()
    return cfg
