"""Lỗi nghiệp vụ của luồng đặt hàng. Thông báo (str) là tiếng Việt, hiển thị trực tiếp cho người dùng."""


class CheckoutError(Exception):
    """Không thể đặt hàng (giỏ rỗng, địa chỉ sai, phương thức thanh toán sai...)."""


class PromotionError(CheckoutError):
    """Mã khuyến mãi không áp dụng được."""


class StockShortageError(CheckoutError):
    """Không đủ tồn khả dụng cho ít nhất một sản phẩm."""


class OrderStateError(Exception):
    """Thao tác không hợp lệ với trạng thái hiện tại của đơn (ví dụ hủy đơn đang giao)."""


class ConcurrentUpdateError(OrderStateError):
    """Đơn vừa bị thay đổi bởi một thao tác khác."""


class InventoryError(Exception):
    """Số liệu kho không nhất quán (lỗi hệ thống, không phải lỗi người dùng)."""


class FulfillmentError(Exception):
    """Dữ liệu xử lý đơn không hợp lệ (thiếu đơn vị vận chuyển, mã vận đơn sai/trùng, thiếu ghi chú...)."""
