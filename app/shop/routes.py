"""Khu vực cửa hàng (công khai): trang chủ, danh sách/tìm kiếm/lọc, chi tiết sản phẩm (FR-KH05, FR-KH06)."""
from flask import abort, current_app, redirect, render_template, request, url_for

from app.constants import SettingKey
from app.models import AppSetting
from app.services import catalog_service as catalog
from app.services.catalog_filters import DEFAULT_SORT, SORTS, ProductFilters
from app.shop import bp


def _list_url(f, page=None):
    """Dựng lại URL danh sách từ bộ lọc ĐÃ chuẩn hóa (không đọc thẳng query string -> không lọt tham số lạ)."""
    args = {
        "q": f.q or None,
        "category": f.category or None,
        "size": f.sizes or None,
        "color": f.colors or None,
        "min_price": f.min_price,
        "max_price": f.max_price,
        "in_stock": 1 if f.in_stock else None,
        "sort": f.sort if f.sort != DEFAULT_SORT else None,
        "page": page if page and page > 1 else None,
    }
    return url_for("shop.product_list", **{k: v for k, v in args.items() if v is not None})


@bp.route("/")
def home():
    cfg = current_app.config
    return render_template(
        "shop/home.html",
        categories=catalog.root_categories(),
        new_products=catalog.new_products(8),
        best_sellers=catalog.best_selling_products(8),
        return_days=AppSetting.get_int(SettingKey.RETURN_WINDOW_DAYS, cfg["DEFAULT_RETURN_WINDOW_DAYS"]),
    )


@bp.route("/products")
def product_list():
    f = ProductFilters.from_args(request.args)

    category, category_ids = None, None
    if f.category:
        category = catalog.get_active_category(f.category)
        if category is None:
            abort(404)
        category_ids = catalog.category_ids_with_descendants(category)

    pagination = catalog.search_products(f, category_ids)
    if pagination.total and not pagination.items:          # trang vượt quá số trang: về trang cuối
        return redirect(_list_url(f, pagination.pages))

    sizes, colors = catalog.filter_options()
    return render_template(
        "shop/product_list.html",
        f=f,
        category=category,
        breadcrumb=catalog.category_breadcrumb(category) if category else [],
        pagination=pagination,
        products=pagination.items,
        categories=catalog.root_categories(),
        sizes=sizes,
        colors=colors,
        sorts=SORTS,
        list_url=lambda page: _list_url(f, page),
        clear_url=url_for("shop.product_list", category=f.category) if f.category else url_for("shop.product_list"),
    )


@bp.route("/category/<slug>")
def category(slug):
    return redirect(url_for("shop.product_list", category=slug))


@bp.route("/products/<slug>")
def product_detail(slug):
    product = catalog.get_product_or_404(slug)
    sizes, colors, variants_data = catalog.variant_options(product)
    return render_template(
        "shop/product_detail.html",
        product=product,
        breadcrumb=catalog.category_breadcrumb(product.category),
        sizes=sizes,
        colors=colors,
        variants_data=variants_data,
        low_stock=catalog.low_stock_threshold(),
        max_per_item=current_app.config["CART_MAX_QUANTITY_PER_ITEM"],
        reviews=catalog.review_summary(product),
        related=catalog.related_products(product),
    )


# ------------------------------------------------------------------ Chính sách & Pháp lý
@bp.route("/privacy-policy")
def privacy_policy():
    """Chính sách bảo vệ dữ liệu cá nhân theo Luật BV dữ liệu cá nhân 2025."""
    return render_template("shop/policies/privacy.html")


@bp.route("/terms")
def terms_of_service():
    """Điều khoản mua bán & giao kết dịch vụ theo Luật TMĐT 122/2025/QH15."""
    return render_template("shop/policies/terms.html")


@bp.route("/returns-policy")
def returns_policy():
    """Chính sách đổi trả & hoàn tiền (7 ngày)."""
    return render_template("shop/policies/returns.html")


@bp.route("/shipping-policy")
def shipping_policy():
    """Chính sách giao nhận & vận chuyển (tích hợp GHN)."""
    return render_template("shop/policies/shipping.html")

