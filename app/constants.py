"""Hằng số dùng chung: vai trò, trạng thái đơn, trạng thái thanh toán...
Mã (code) khớp với tài liệu phân tích hệ thống mục 2.5."""

# --- Vai trò ---
ROLE_CUSTOMER = "CUSTOMER"
ROLE_STAFF = "STAFF"
ROLE_ADMIN = "ADMIN"

ROLE_LABELS = {ROLE_CUSTOMER: "Khách hàng", ROLE_STAFF: "Nhân viên", ROLE_ADMIN: "Quản trị viên"}


# --- Trạng thái kinh doanh dùng chung (product, product_variant, promotion, supplier) ---
class EntityStatus:
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ALL = (ACTIVE, INACTIVE)
    LABELS = {ACTIVE: "Đang kinh doanh", INACTIVE: "Ngừng kinh doanh"}

# --- Trạng thái đơn hàng (sales_order.status) ---
class OrderStatus:
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PENDING_CONFIRM = "PENDING_CONFIRM"
    CONFIRMED = "CONFIRMED"
    PACKING = "PACKING"
    SHIPPING = "SHIPPING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RETURNING = "RETURNING"
    RETURNED = "RETURNED"

    ALL = (PENDING_PAYMENT, PENDING_CONFIRM, CONFIRMED, PACKING, SHIPPING,
           COMPLETED, CANCELLED, RETURNING, RETURNED)

    LABELS = {
        PENDING_PAYMENT: "Chờ thanh toán",
        PENDING_CONFIRM: "Chờ xác nhận",
        CONFIRMED: "Đã xác nhận",
        PACKING: "Đang đóng gói",
        SHIPPING: "Đang giao",
        COMPLETED: "Hoàn thành",
        CANCELLED: "Đã hủy",
        RETURNING: "Đang đổi trả",
        RETURNED: "Đã đổi trả",
    }

    # Màu badge Bootstrap để hiển thị
    BADGES = {
        PENDING_PAYMENT: "warning",
        PENDING_CONFIRM: "info",
        CONFIRMED: "primary",
        PACKING: "primary",
        SHIPPING: "primary",
        COMPLETED: "success",
        CANCELLED: "danger",
        RETURNING: "warning",
        RETURNED: "secondary",
    }


# --- Trạng thái thanh toán (payment.status) ---
class PaymentStatus:
    UNPAID = "UNPAID"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

    ALL = (UNPAID, PENDING, PAID, FAILED, REFUNDED)

    LABELS = {
        UNPAID: "Chưa thanh toán",
        PENDING: "Chờ thanh toán",
        PAID: "Đã thanh toán",
        FAILED: "Thanh toán thất bại",
        REFUNDED: "Đã hoàn tiền",
    }

    BADGES = {
        UNPAID: "secondary",
        PENDING: "warning",
        PAID: "success",
        FAILED: "danger",
        REFUNDED: "info",
    }


# --- Phương thức thanh toán ---
class PaymentMethod:
    COD = "COD"
    VNPAY = "VNPAY"

    ALL = (COD, VNPAY)
    LABELS = {COD: "Thanh toán khi nhận hàng (COD)", VNPAY: "Thanh toán online (VNPay sandbox)"}


# --- Máy trạng thái đơn hàng: ĐÚNG THEO Hình 2.6 trong tài liệu phân tích ---
# Chuyển trạng thái ngoài bảng này đều không hợp lệ. Đơn SHIPPING không được hủy trực tiếp.
ORDER_TRANSITIONS = {
    OrderStatus.PENDING_PAYMENT: (OrderStatus.PENDING_CONFIRM,   # thanh toán thành công
                                  OrderStatus.CANCELLED),        # thất bại hoặc quá 15 phút
    OrderStatus.PENDING_CONFIRM: (OrderStatus.CONFIRMED,         # nhân viên xác nhận
                                  OrderStatus.CANCELLED),        # khách hoặc nhân viên hủy
    OrderStatus.CONFIRMED: (OrderStatus.PACKING,                 # bắt đầu đóng gói
                            OrderStatus.CANCELLED),              # khách hoặc nhân viên hủy
    OrderStatus.PACKING: (OrderStatus.SHIPPING,                  # bàn giao vận chuyển
                          OrderStatus.CANCELLED),                # nhân viên hoặc quản trị viên hủy kèm lý do
    OrderStatus.SHIPPING: (OrderStatus.COMPLETED,),              # giao thành công
    OrderStatus.COMPLETED: (OrderStatus.RETURNING,),             # yêu cầu đổi trả được chấp nhận
    OrderStatus.RETURNING: (OrderStatus.RETURNED,),              # xử lý xong
    OrderStatus.CANCELLED: (),                                   # trạng thái kết thúc
    OrderStatus.RETURNED: (),                                    # trạng thái kết thúc
}

# Khách hàng tự hủy được khi đơn còn ở các trạng thái này ("Khách hoặc nhân viên hủy").
# Đang đóng gói: chỉ nhân viên/quản trị viên hủy, bắt buộc có lý do.
CUSTOMER_CANCELLABLE_STATUSES = (OrderStatus.PENDING_CONFIRM, OrderStatus.CONFIRMED)
STAFF_CANCELLABLE_STATUSES = (OrderStatus.PENDING_CONFIRM, OrderStatus.CONFIRMED, OrderStatus.PACKING)


def can_transition(from_status, to_status):
    return to_status in ORDER_TRANSITIONS.get(from_status, ())


# --- Khuyến mãi ---
class DiscountType:
    PERCENT = "PERCENT"   # giảm theo %
    FIXED = "FIXED"       # giảm số tiền cố định
    ALL = (PERCENT, FIXED)


# --- Đổi trả ---
class ReturnStatus:
    PENDING = "PENDING"       # khách mới gửi yêu cầu
    APPROVED = "APPROVED"     # nhân viên chấp nhận, chờ nhận hàng về
    REJECTED = "REJECTED"     # từ chối
    COMPLETED = "COMPLETED"   # đã nhận hàng, kiểm tra, hoàn tiền/nhập lại kho xong
    ALL = (PENDING, APPROVED, REJECTED, COMPLETED)
    LABELS = {PENDING: "Chờ xử lý", APPROVED: "Đã chấp nhận", REJECTED: "Từ chối", COMPLETED: "Hoàn tất"}
    BADGES = {PENDING: "warning", APPROVED: "primary", REJECTED: "danger", COMPLETED: "success"}


# --- Phiếu nhập kho ---
class ReceiptStatus:
    DRAFT = "DRAFT"           # đang lập, chưa ảnh hưởng tồn kho
    CONFIRMED = "CONFIRMED"   # đã xác nhận, cộng kho theo số lượng thực nhận (confirmed_at)
    CANCELLED = "CANCELLED"
    ALL = (DRAFT, CONFIRMED, CANCELLED)
    LABELS = {DRAFT: "Nháp", CONFIRMED: "Đã nhập kho", CANCELLED: "Đã hủy"}
    BADGES = {DRAFT: "warning", CONFIRMED: "success", CANCELLED: "secondary"}


# --- Loại giao dịch kho (stock_transaction.type) ---
class StockTxType:
    RESERVE = "RESERVE"       # giữ hàng khi tạo đơn: reserved +n
    RELEASE = "RELEASE"       # nhả hàng khi hủy/hết hạn: reserved -n
    ISSUE = "ISSUE"           # xuất kho khi bàn giao vận chuyển: stock -n, reserved -n
    RECEIPT = "RECEIPT"       # nhập kho theo phiếu nhập: stock +n
    RETURN_IN = "RETURN_IN"   # nhập lại do đổi trả: stock +n
    ADJUST = "ADJUST"         # điều chỉnh thủ công (kèm lý do): stock ±n
    ALL = (RESERVE, RELEASE, ISSUE, RECEIPT, RETURN_IN, ADJUST)
    LABELS = {RESERVE: "Giữ hàng", RELEASE: "Nhả hàng giữ", ISSUE: "Xuất kho (bàn giao)", RECEIPT: "Nhập kho (phiếu nhập)",
              RETURN_IN: "Nhập lại (đổi trả)", ADJUST: "Điều chỉnh thủ công"}


# --- Quyền (permission) ---
class Perm:
    ORDER_VIEW = "order.view"
    ORDER_PROCESS = "order.process"
    SHIPMENT_UPDATE = "shipment.update"
    RETURN_HANDLE = "return.handle"
    STOCK_VIEW = "stock.view"
    STOCK_RECEIPT = "stock.receipt"
    STOCK_ISSUE = "stock.issue"
    STOCK_ADJUST = "stock.adjust"
    PRODUCT_MANAGE = "product.manage"
    CATALOG_MANAGE = "catalog.manage"
    USER_MANAGE = "user.manage"
    SUPPLIER_MANAGE = "supplier.manage"
    PROMOTION_MANAGE = "promotion.manage"
    SHIPPING_FEE_MANAGE = "shipping_fee.manage"
    SETTING_MANAGE = "setting.manage"
    REPORT_VIEW = "report.view"
    AUDIT_VIEW = "audit.view"

    LABELS = {
        ORDER_VIEW: "Xem đơn hàng",
        ORDER_PROCESS: "Xác nhận, hủy, đóng gói đơn",
        SHIPMENT_UPDATE: "Cập nhật giao hàng",
        RETURN_HANDLE: "Xử lý đổi trả",
        STOCK_VIEW: "Xem tồn kho",
        STOCK_RECEIPT: "Lập phiếu nhập kho",
        STOCK_ISSUE: "Lập phiếu xuất kho",
        STOCK_ADJUST: "Điều chỉnh tồn kho thủ công",
        PRODUCT_MANAGE: "Quản lý sản phẩm",
        CATALOG_MANAGE: "Quản lý danh mục, kích cỡ, màu sắc",
        USER_MANAGE: "Quản lý tài khoản và phân quyền",
        SUPPLIER_MANAGE: "Quản lý nhà cung cấp",
        PROMOTION_MANAGE: "Quản lý khuyến mãi",
        SHIPPING_FEE_MANAGE: "Quản lý phí vận chuyển",
        SETTING_MANAGE: "Quản lý tham số cấu hình",
        REPORT_VIEW: "Xem báo cáo",
        AUDIT_VIEW: "Xem nhật ký hoạt động",
    }

    # Quyền mặc định của vai trò nhân viên; quản trị viên có toàn bộ quyền
    STAFF_DEFAULT = (ORDER_VIEW, ORDER_PROCESS, SHIPMENT_UPDATE, RETURN_HANDLE,
                     STOCK_VIEW, STOCK_RECEIPT, STOCK_ISSUE)


# --- Khóa trong bảng app_setting ---
class SettingKey:
    PAYMENT_TIMEOUT_MINUTES = "payment_timeout_minutes"
    RETURN_WINDOW_DAYS = "return_window_days"
    LOW_STOCK_THRESHOLD = "low_stock_threshold"
