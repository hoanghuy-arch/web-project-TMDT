"""Cấu trúc dữ liệu và quy tắc hiển thị của giỏ hàng (thuần Python, không truy cập DB nên dễ kiểm thử)."""
from dataclasses import dataclass, field
from decimal import Decimal


def line_issue(purchasable, available, quantity):
    """Lý do một dòng không thể đặt (None nếu hợp lệ)."""
    if not purchasable:
        return "Sản phẩm đã ngừng kinh doanh."
    if available <= 0:
        return "Đã hết hàng."
    if quantity > available:
        return f"Chỉ còn {available} sản phẩm."
    return None


@dataclass
class CartLine:
    item: object
    variant: object
    product: object
    quantity: int
    unit_price: Decimal
    available: int
    purchasable: bool                 # biến thể và sản phẩm còn được bán
    issue: str = None                 # lý do không thể đặt dòng này (nếu có)

    @property
    def line_total(self):
        return self.quantity * self.unit_price


@dataclass
class CartView:
    lines: list = field(default_factory=list)

    @property
    def subtotal(self):
        """Chỉ cộng các dòng còn được bán và còn hàng (dòng ngừng bán hoặc hết hàng không tính)."""
        return sum((l.line_total for l in self.lines if l.purchasable and l.available > 0), Decimal(0))

    @property
    def total_quantity(self):
        return sum(l.quantity for l in self.lines)

    @property
    def issue_count(self):
        return sum(1 for l in self.lines if l.issue)

    @property
    def can_checkout(self):
        """Đặt hàng được khi giỏ không rỗng và mọi dòng đều hợp lệ."""
        return bool(self.lines) and self.issue_count == 0
