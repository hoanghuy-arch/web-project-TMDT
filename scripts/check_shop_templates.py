"""Render thật các template cửa hàng bằng dữ liệu giả (không cần DB/SQLAlchemy) để kiểm tra logic giao diện.
Chạy: python scripts/check_shop_templates.py"""
import json
import re
import sys
from datetime import datetime
from types import SimpleNamespace as NS

sys.path.insert(0, "scripts")
from _render_env import Anon, Checker, Customer, Pag, Staff, make_app, set_user

from flask import render_template, url_for
from werkzeug.datastructures import MultiDict

from app.services.catalog_filters import SORTS, ProductFilters

app = make_app()
ok = Checker()

den, trang = NS(id=1, name="Đen", hex_code="#000000"), NS(id=2, name="Trắng", hex_code="#ffffff")
img = NS(url="https://cdn.test/a.jpg")


def product(i, name, price, in_stock=True, image=None, colors=(den,)):
    return NS(id=i, name=name, slug=f"sp-{i}", price=price, in_stock=in_stock, primary_image=image,
              available_colors=list(colors), description="Dòng 1\nDòng 2", images=[image] if image else [],
              category=NS(name="Áo", slug="ao"))


P = [product(1, "Áo <b>Pro</b>", 250000, image=img, colors=(den, trang)), product(2, "Quần Short", 180000, in_stock=False)]
with app.test_request_context("/"):
    set_user(app, Anon())

    # ---------------- trang chủ ----------------
    html = render_template("shop/home.html", categories=[NS(name="Áo", slug="ao", children=[])], new_products=P,
                           best_sellers=P[:1], return_days=7)
    ok("Đổi trả trong 7 ngày" in html and "Bán chạy" in html and "Sản phẩm mới" in html, "home: các mục")
    ok("&lt;b&gt;Pro&lt;/b&gt;" in html and "<b>Pro</b>" not in html, "home: escape tên sản phẩm")
    ok(html.count("Hết hàng") == 1, "home: nhãn hết hàng chỉ ở sản phẩm hết hàng")
    ok('src="https://cdn.test/a.jpg"' in html and "/static/img/placeholder.svg" in html, "home: ảnh / ảnh mặc định")
    ok('title="Trắng"' in html and 'href="/products/sp-2"' in html, "home: chấm màu, liên kết")
    html0 = render_template("shop/home.html", categories=[], new_products=[], best_sellers=[], return_days=7)
    ok("đang cập nhật sản phẩm" in html0 and '<h2 class="h4 mb-0">Bán chạy</h2>' not in html0 and "Danh mục" not in html0,
       "home: trạng thái rỗng")

    # ---------------- danh sách ----------------
    f = ProductFilters.from_args(MultiDict([("q", "áo"), ("category", "ao"), ("size", "2"), ("color", "1"),
                                            ("min_price", "100000"), ("in_stock", "1"), ("sort", "price_asc")]))
    list_url = lambda page: url_for("shop.product_list", **{"q": "áo", "page": page})
    cat = NS(name="Áo", slug="ao")
    sizes = [NS(id=1, name="S"), NS(id=2, name="M")]
    cats = [NS(name="Áo", slug="ao", children=[NS(name="Áo chạy bộ", slug="ao-chay-bo", is_active=True)])]
    html = render_template("shop/product_list.html", f=f, category=cat, breadcrumb=[cat], pagination=Pag(P, 25, 3, 5),
                           products=P, categories=cats, sizes=sizes, colors=[den, trang], sorts=SORTS,
                           list_url=list_url, clear_url="/products?category=ao")
    ok("25 sản phẩm" in html and 'cho từ khóa "<strong>áo</strong>"' in html, "list: tiêu đề kết quả")
    ok(re.search(r'id="size-2" value="2" checked', html) and not re.search(r'id="size-1" value="1" checked', html),
       "list: kích cỡ đang chọn")
    ok(re.search(r'id="color-1" value="1" checked', html) and not re.search(r'id="color-2" value="2" checked', html),
       "list: màu đang chọn")
    ok('value="100000"' in html and 'value="" aria-label="Giá đến"' in html, "list: ô giá")
    ok(re.search(r'name="in_stock" value="1" id="in_stock" checked', html), "list: còn hàng")
    ok('<option value="price_asc" selected>' in html and html.count(" selected>") == 1, "list: sắp xếp")
    ok('name="category" value="ao"' in html and 'name="q" value="áo"' in html, "list: giữ ngữ cảnh khi lọc")
    ok('href="/products?q=%C3%A1o&amp;page=4"' in html and 'aria-label="Trang trước"' in html, "list: liên kết phân trang")
    ok('<li class="page-item active"><a class="page-link" href="/products?q=%C3%A1o&amp;page=3">3</a>' in html, "list: trang hiện tại")
    ok("&hellip;" not in html and "Xóa lọc" in html and "Áo chạy bộ" in html, "list: 5 trang liền nhau, xóa lọc, danh mục con")
    html = render_template("shop/product_list.html", f=f, category=cat, breadcrumb=[cat], pagination=Pag(P, 100, 5, 10),
                           products=P, categories=cats, sizes=sizes, colors=[den, trang], sorts=SORTS,
                           list_url=list_url, clear_url="/products")
    ok(html.count("&hellip;") == 2 and ">10</a>" in html and ">1</a>" in html and ">5</a>" in html, "list: 10 trang có dấu ba chấm")
    html = render_template("shop/product_list.html", f=f, category=cat, breadcrumb=[cat], pagination=Pag(P, 100, 1, 1),
                           products=P, categories=cats, sizes=sizes, colors=[den, trang], sorts=SORTS,
                           list_url=list_url, clear_url="/products")
    ok('aria-label="Phân trang"' not in html, "list: 1 trang thì không hiện phân trang")

    empty = dict(category=None, breadcrumb=[], pagination=Pag([], 0, 1, 0), products=[], categories=[], sizes=[], colors=[],
                 sorts=SORTS, list_url=list_url, clear_url="/products")
    html = render_template("shop/product_list.html", f=ProductFilters(q="xyz"), **empty)
    ok("Không tìm thấy sản phẩm phù hợp" in html and "Xóa tất cả bộ lọc" in html and "0 sản phẩm" in html, "list: rỗng có lọc")
    html = render_template("shop/product_list.html", f=ProductFilters(), **empty)
    ok("Không tìm thấy sản phẩm phù hợp" in html and "Xóa tất cả bộ lọc" not in html, "list: rỗng không lọc")

    # ---------------- chi tiết ----------------
    p = product(1, "Áo Pro", 250000, image=img)
    p.images = [img, NS(url="b.jpg")]
    variants = [{"id": 1, "size_id": 1, "color_id": 1, "available": 10, "sku": "A"},
                {"id": 2, "size_id": 2, "color_id": 1, "available": 0, "sku": "B"}]
    reviews = {"average": 4.5, "count": 2, "items": [
        NS(account=NS(full_name="Nguyễn Văn An"), rating=5, comment="Rất <i>tốt</i>", created_at=datetime(2026, 11, 6, 20, 0)),
        NS(account=NS(full_name="Lê Mai"), rating=4, comment=None, created_at=datetime(2026, 11, 5, 1, 0))]}
    html = render_template("shop/product_detail.html", product=p, breadcrumb=[NS(name="Áo", slug="ao")],
                           sizes=[NS(id=1, name="M"), NS(id=2, name="L")], colors=[den], variants_data=variants,
                           low_stock=5, max_per_item=10, reviews=reviews, related=P[1:])
    ok('data-low-stock="5"' in html and 'id="size-1"' in html and 'id="color-1" value="1" data-name="Đen"' in html,
       "detail: tùy chọn biến thể")
    ok(json.loads(re.search(r'id="variants-data">(.*?)</script>', html, re.S).group(1)) == variants, "detail: JSON biến thể")
    ok("Đăng nhập để mua hàng" in html and 'id="add-to-cart-form"' not in html, "detail: khách vãng lai thấy liên kết đăng nhập")
    ok("product.js" in html and 'data-full="/static/b.jpg"' in html and 'data-max-per-item="10"' in html, "detail: script, ảnh nhỏ, giới hạn")
    detail_args = dict(product=p, breadcrumb=[NS(name="Áo", slug="ao")], sizes=[NS(id=1, name="M"), NS(id=2, name="L")],
                       colors=[den], variants_data=variants, low_stock=5, max_per_item=10, reviews=reviews, related=[])
    set_user(app, Customer())
    html_c = render_template("shop/product_detail.html", **detail_args)
    ok('id="add-to-cart-form"' in html_c and 'action="/account/cart/add"' in html_c and 'name="csrf_token"' in html_c
       and 'name="variant_id" id="variant_id"' in html_c and 'id="add-to-cart-btn"' in html_c and 'id="quantity"' in html_c,
       "detail: khách hàng thấy form thêm vào giỏ")
    set_user(app, Staff())
    html_s = render_template("shop/product_detail.html", **detail_args)
    ok("không dùng để mua hàng" in html_s and 'id="add-to-cart-form"' not in html_s, "detail: nhân viên không mua được")
    set_user(app, Anon())
    ok("N. V. An" in html and "L. Mai" in html and "Nguyễn Văn An" not in html and "Lê Mai" not in html,
       "detail: che họ tên người đánh giá")
    ok("Rất &lt;i&gt;tốt&lt;/i&gt;" in html and "07/11/2026" in html and "05/11/2026" in html, "detail: escape bình luận, giờ VN (UTC+7)")
    ok("2 đánh giá" in html and "Sản phẩm liên quan" in html and "Quần Short" in html, "detail: tổng hợp, liên quan")
    rows = re.findall(r'<span class="sz-stars"[^>]*>(.*?)</span>', html, re.S)
    ok(any(r.count("bi-star-fill") == 4 and r.count("bi-star-half") == 1 and r.count('bi-star"') == 0 for r in rows), "detail: 4.5 sao")
    ok(any(r.count("bi-star-fill") == 5 for r in rows), "detail: 5 sao")

    html = render_template("shop/product_detail.html", product=product(3, "Hết", 1000, in_stock=False), breadcrumb=[], sizes=[],
                           colors=[], variants_data=[], low_stock=5, max_per_item=10, reviews={"average": None, "count": 0, "items": []}, related=[])
    ok("Sản phẩm tạm hết hàng" in html and 'id="variants-data"' not in html, "detail: hết hàng")
    ok("Chưa có đánh giá nào" in html and "Sản phẩm liên quan" not in html, "detail: chưa có đánh giá/liên quan")

    # ---------------- ô tìm kiếm trên navbar ----------------
    with app.test_request_context("/products?q=%C3%A1o%20ch%E1%BA%A1y"):
        set_user(app, Anon())
        html = render_template("shop/product_list.html", f=ProductFilters(q="áo chạy"), **empty)
        ok('type="search" name="q" maxlength="100"' in html and 'value="áo chạy"' in html, "navbar: giữ từ khóa tìm kiếm")

print(f"OK: {ok.count} kiểm tra giao diện cửa hàng đều đạt")
