"""Toàn bộ 32 thực thể theo ERD, chia 7 phân hệ A-G.
Import đủ ở đây để SQLAlchemy và Flask-Migrate nhận biết mọi bảng."""
from app.models.base import ImmutableRecordError, TimestampMixin, utcnow  # noqa: F401

# A. Tài khoản, phân quyền, địa chỉ
from app.models.account import (  # noqa: F401
    Account, Address, PasswordResetToken, Permission, Province, Role, Ward, role_permission,
)
# B. Sản phẩm
from app.models.catalog import Category, Color, Product, ProductImage, ProductVariant, Size  # noqa: F401
# C. Giỏ hàng, khuyến mãi, đơn hàng
from app.models.order import (  # noqa: F401
    CartItem, Promotion, SalesOrder, SalesOrderItem, SalesOrderStatusHistory,
)
# D. Vận chuyển, thanh toán
from app.models.fulfillment import Carrier, Payment, Shipment, ShippingFeeRule  # noqa: F401
# E. Đổi trả, đánh giá
from app.models.returns import Review, ReturnItem, ReturnRequest  # noqa: F401
# F. Kho, nhà cung cấp
from app.models.inventory import StockReceipt, StockReceiptItem, StockTransaction, Supplier  # noqa: F401
# G. Hệ thống
from app.models.system import AppSetting, AuditLog  # noqa: F401
