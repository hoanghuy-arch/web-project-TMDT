"""Đọc và chuẩn hóa tham số tìm kiếm/lọc/sắp xếp từ URL (FR-KH05). Không phụ thuộc DB nên dễ kiểm thử.
Mọi giá trị sai định dạng đều bị bỏ qua thay vì gây lỗi."""
from dataclasses import dataclass, field

SORTS = {
    "newest": "Mới nhất",
    "bestselling": "Bán chạy",
    "price_asc": "Giá tăng dần",
    "price_desc": "Giá giảm dần",
    "name_asc": "Tên A-Z",
}
DEFAULT_SORT = "newest"
MAX_PRICE = 1_000_000_000          # chặn giá trị phi thực tế (cột tiền là DECIMAL(12,0))
MAX_PAGE = 10_000
MAX_TERMS = 5


def _money(value):
    """'250000' hoặc '250.000' -> 250000; sai định dạng hoặc ngoài khoảng -> None."""
    try:
        n = int(str(value).strip().replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= MAX_PRICE else None


@dataclass
class ProductFilters:
    q: str = ""
    category: str = ""                                 # slug danh mục
    sizes: list = field(default_factory=list)          # id kích cỡ
    colors: list = field(default_factory=list)         # id màu
    min_price: int = None
    max_price: int = None
    in_stock: bool = False
    sort: str = DEFAULT_SORT
    page: int = 1

    @classmethod
    def from_args(cls, args):
        """args: request.args (MultiDict)."""
        sizes = sorted({i for i in args.getlist("size", type=int) if i > 0})[:30]
        colors = sorted({i for i in args.getlist("color", type=int) if i > 0})[:30]
        min_price, max_price = _money(args.get("min_price")), _money(args.get("max_price"))
        if min_price is not None and max_price is not None and min_price > max_price:
            min_price, max_price = max_price, min_price
        sort = args.get("sort", DEFAULT_SORT)
        page = args.get("page", 1, type=int)
        return cls(
            q=" ".join((args.get("q") or "").split())[:100],
            category=(args.get("category") or "").strip()[:120],
            sizes=sizes,
            colors=colors,
            min_price=min_price,
            max_price=max_price,
            in_stock=(args.get("in_stock") or "").lower() in ("1", "on", "true"),
            sort=sort if sort in SORTS else DEFAULT_SORT,
            page=min(max(page, 1), MAX_PAGE),
        )

    @property
    def terms(self):
        """Từ khóa tìm kiếm: mỗi từ phải xuất hiện trong tên hoặc mô tả."""
        return self.q.split()[:MAX_TERMS]

    @property
    def has_filters(self):
        return bool(self.q or self.category or self.sizes or self.colors or self.in_stock
                    or self.min_price is not None or self.max_price is not None)
