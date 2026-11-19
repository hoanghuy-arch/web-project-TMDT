"""Kiểm thử khu vực cửa hàng: danh sách, tìm kiếm, lọc, sắp xếp, phân trang, chi tiết (Task 4)."""
import json
import re
from datetime import timedelta

import pytest

from app.constants import EntityStatus, OrderStatus
from app.extensions import db
from app.models import (Account, Address, Category, Color, Product, ProductImage, ProductVariant,
                        Province, Review, SalesOrder, SalesOrderItem, Size, Ward)
from app.models.base import utcnow


def _names(html):
    """Lấy thứ tự tên sản phẩm xuất hiện trong thẻ sản phẩm."""
    return re.findall(r'class="text-decoration-none text-dark">([^<]+)</a>', html)


# ------------------------------------------------------------------ hiển thị
def test_home_page_lists_new_products(client, shop):
    shop["make"]("Áo Chạy Bộ Pro", 250000, shop["ao"], [(shop["m"], shop["den"], 10, 0)])
    body = client.get("/").get_data(as_text=True)
    assert "Áo Chạy Bộ Pro" in body and "Sản phẩm mới" in body


def test_hidden_products_not_listed(client, shop):
    mk = shop["make"]
    mk("Hiện", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    mk("Ngừng bán", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], status=EntityStatus.INACTIVE)
    mk("Danh mục ẩn", 100000, shop["an"], [(shop["m"], shop["den"], 5, 0)])
    mk("Không biến thể", 100000, shop["ao"], [])
    names = _names(client.get("/products").get_data(as_text=True))
    assert names == ["Hiện"]


def test_out_of_stock_product_still_shown_with_badge(client, shop):
    shop["make"]("Hết sạch", 100000, shop["ao"], [(shop["m"], shop["den"], 3, 3)])    # khả dụng = 0
    body = client.get("/products").get_data(as_text=True)
    assert "Hết sạch" in body and "Hết hàng" in body


def test_product_name_is_escaped(client, shop):
    shop["make"]('<script>alert(1)</script>', 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], slug="xss")
    assert "<script>alert(1)</script>" not in client.get("/products").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in client.get("/products/xss").get_data(as_text=True)


# ------------------------------------------------------------------ tìm kiếm
def test_search_matches_name_and_description(client, shop):
    mk = shop["make"]
    mk("Áo Chạy Bộ", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    mk("Quần Short", 100000, shop["quan"], [(shop["m"], shop["den"], 5, 0)], description="Vải thoáng khí cho chạy bộ")
    mk("Giày", 100000, shop["quan"], [(shop["m"], shop["den"], 5, 0)])
    assert set(_names(client.get("/products?q=chạy bộ").get_data(as_text=True))) == {"Áo Chạy Bộ", "Quần Short"}
    assert _names(client.get("/products?q=short").get_data(as_text=True)) == ["Quần Short"]


def test_search_all_terms_must_match(client, shop):
    mk = shop["make"]
    mk("Áo Chạy Bộ", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    mk("Áo Thun", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    # (SQLite chỉ so khớp hoa/thường với chữ ASCII; MySQL utf8mb4_unicode_ci so khớp cả chữ có dấu)
    assert _names(client.get("/products?q=Áo Thun").get_data(as_text=True)) == ["Áo Thun"]


def test_search_escapes_wildcards(client, shop):
    shop["make"]("Áo Chạy Bộ", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    assert _names(client.get("/products?q=%25").get_data(as_text=True)) == []       # '%' không phải ký tự đại diện
    assert _names(client.get("/products?q=_").get_data(as_text=True)) == []


def test_search_no_result_message(client, shop):
    body = client.get("/products?q=khong-co-gi").get_data(as_text=True)
    assert "Không tìm thấy sản phẩm phù hợp" in body


# ------------------------------------------------------------------ lọc
def test_category_filter_includes_children(client, shop):
    mk = shop["make"]
    mk("Áo cha", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    mk("Áo con", 100000, shop["ao_chay"], [(shop["m"], shop["den"], 5, 0)])
    mk("Quần", 100000, shop["quan"], [(shop["m"], shop["den"], 5, 0)])
    assert set(_names(client.get("/products?category=ao").get_data(as_text=True))) == {"Áo cha", "Áo con"}
    assert _names(client.get("/products?category=ao-chay-bo").get_data(as_text=True)) == ["Áo con"]


def test_unknown_or_inactive_category_404(client, shop):
    assert client.get("/products?category=khong-co").status_code == 404
    assert client.get("/products?category=an").status_code == 404


def test_category_url_redirects(client, shop):
    resp = client.get("/category/ao")
    assert resp.status_code == 302 and "category=ao" in resp.headers["Location"]


def test_size_and_color_must_match_same_variant(client, shop):
    s, m, den, trang = shop["s"], shop["m"], shop["den"], shop["trang"]
    shop["make"]("Chỉ M đen và S trắng", 100000, shop["ao"], [(m, den, 5, 0), (s, trang, 5, 0)])
    shop["make"]("Có M trắng", 100000, shop["ao"], [(m, trang, 5, 0)])
    body = client.get(f"/products?size={m.id}&color={trang.id}").get_data(as_text=True)
    assert _names(body) == ["Có M trắng"]


def test_in_stock_filter_uses_available_quantity(client, shop):
    mk = shop["make"]
    mk("Còn hàng", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 2)])
    mk("Đã giữ hết", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 5)])
    assert _names(client.get("/products?in_stock=1").get_data(as_text=True)) == ["Còn hàng"]


def test_price_range_filter(client, shop):
    mk = shop["make"]
    for name, price in (("Rẻ", 100000), ("Vừa", 300000), ("Đắt", 900000)):
        mk(name, price, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    assert _names(client.get("/products?min_price=200000&max_price=500000").get_data(as_text=True)) == ["Vừa"]
    # min > max thì hoán đổi, không báo lỗi
    assert _names(client.get("/products?min_price=500000&max_price=200000").get_data(as_text=True)) == ["Vừa"]
    assert set(_names(client.get("/products?min_price=300.000").get_data(as_text=True))) == {"Vừa", "Đắt"}


def test_invalid_params_do_not_crash(client, shop):
    shop["make"]("A", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    for qs in ("page=abc", "page=-5", "page=99999999999999", "size=x&color=y", "min_price=abc", "sort=hack",
               "min_price=99999999999999999999", "q=" + "a" * 5000, "_external=1&endpoint=x"):
        # 200, hoặc 302 khi số trang vượt quá trang cuối (chuyển về trang cuối); tuyệt đối không được lỗi 4xx/5xx
        assert client.get("/products?" + qs).status_code in (200, 302), qs


# ------------------------------------------------------------------ sắp xếp, phân trang
def test_sorting(client, shop):
    mk = shop["make"]
    mk("B", 300000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], age=2)
    mk("A", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], age=3)
    mk("C", 200000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], age=1)
    order = lambda sort: _names(client.get(f"/products?sort={sort}").get_data(as_text=True))
    assert order("price_asc") == ["A", "C", "B"]
    assert order("price_desc") == ["B", "C", "A"]
    assert order("name_asc") == ["A", "B", "C"]
    assert order("newest") == ["C", "B", "A"]
    assert order("khong-hop-le") == ["C", "B", "A"]        # sort lạ -> mặc định


def test_pagination(app, client, shop):
    app.config["PRODUCTS_PER_PAGE"] = 2
    for i in range(5):
        shop["make"](f"SP{i}", 100000 + i, shop["ao"], [(shop["m"], shop["den"], 5, 0)], age=i)
    page1 = client.get("/products").get_data(as_text=True)
    assert len(_names(page1)) == 2 and "5 sản phẩm" in page1 and 'aria-label="Phân trang"' in page1
    assert len(_names(client.get("/products?page=3").get_data(as_text=True))) == 1
    far = client.get("/products?page=99")                    # vượt trang cuối: chuyển về trang cuối
    assert far.status_code == 302 and "page=3" in far.headers["Location"]


def test_pagination_links_keep_filters(app, client, shop):
    app.config["PRODUCTS_PER_PAGE"] = 1
    for i in range(3):
        shop["make"](f"SP{i}", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], age=i)
    body = client.get(f"/products?sort=price_asc&category=ao&size={shop['m'].id}").get_data(as_text=True)
    assert "page=2" in body and "sort=price_asc" in body and "category=ao" in body


# ------------------------------------------------------------------ bán chạy
def _order(account, address, status, items):
    o = SalesOrder(order_code=f"SZ{db.session.query(SalesOrder).count() + 1}", account_id=account.id,
                   address_id=address.id, status=status)
    for variant, qty in items:
        o.items.append(SalesOrderItem(product_variant_id=variant.id, quantity=qty, unit_price=variant.product.price))
    db.session.add(o)
    db.session.commit()
    return o


@pytest.fixture()
def buyer(app, roles, make_account):
    acc = make_account(email="buyer@test.com", full_name="Nguyễn Văn An")
    prov = Province(name="HCM")
    ward = Ward(province=prov, name="Q1")
    db.session.add_all([prov, ward])
    db.session.flush()
    addr = Address(account=acc, ward=ward, recipient_name="An", phone="0912345678", street_detail="1 Lê Lợi")
    db.session.add(addr)
    db.session.commit()
    return acc, addr


def test_bestselling_ignores_cancelled_and_unpaid_orders(client, shop, buyer):
    acc, addr = buyer
    a = shop["make"]("Bán ít", 100000, shop["ao"], [(shop["m"], shop["den"], 50, 0)])
    b = shop["make"]("Bán nhiều", 100000, shop["ao"], [(shop["m"], shop["den"], 50, 0)])
    c = shop["make"]("Chỉ có đơn hủy", 100000, shop["ao"], [(shop["m"], shop["den"], 50, 0)])
    _order(acc, addr, OrderStatus.COMPLETED, [(a.variants[0], 1), (b.variants[0], 5)])
    _order(acc, addr, OrderStatus.CANCELLED, [(c.variants[0], 100)])
    _order(acc, addr, OrderStatus.PENDING_PAYMENT, [(c.variants[0], 100)])
    order = _names(client.get("/products?sort=bestselling").get_data(as_text=True))
    assert order[:2] == ["Bán nhiều", "Bán ít"]
    home = client.get("/").get_data(as_text=True)
    assert "Bán chạy" in home and "Chỉ có đơn hủy" in home.split("Sản phẩm mới")[1]   # chỉ xuất hiện ở mục mới
    assert "Chỉ có đơn hủy" not in home.split("Sản phẩm mới")[0]


def test_home_hides_bestseller_section_without_sales(client, shop):
    shop["make"]("Mới", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    assert "<h2 class=\"h4 mb-0\">Bán chạy</h2>" not in client.get("/").get_data(as_text=True)


# ------------------------------------------------------------------ chi tiết
def test_product_detail_shows_options_and_data(client, shop):
    p = shop["make"]("Áo Pro", 250000, shop["ao"],
                     [(shop["m"], shop["den"], 10, 0), (shop["l"], shop["den"], 2, 0), (shop["m"], shop["trang"], 4, 4)],
                     slug="ao-pro", description="Chất liệu thoáng khí")
    db.session.add_all([ProductImage(product=p, url="a.jpg", is_primary=False, sort_order=1),
                        ProductImage(product=p, url="https://cdn.test/b.jpg", is_primary=True, sort_order=2)])
    db.session.commit()
    body = client.get("/products/ao-pro").get_data(as_text=True)
    assert "250.000 ₫" in body and "Chất liệu thoáng khí" in body
    data = json.loads(re.search(r'id="variants-data">(.*?)</script>', body, re.S).group(1))
    assert sorted(v["available"] for v in data) == [0, 2, 10]          # (M,Trắng) đã bị giữ hết -> 0
    assert 'src="https://cdn.test/b.jpg" alt="Áo Pro"' in body            # ảnh chính (is_primary) làm ảnh đầu
    assert 'id="size-%d"' % shop["l"].id in body and 'id="color-%d"' % shop["trang"].id in body
    assert "Đăng nhập để mua hàng" in body and "next=/products/ao-pro" in body        # khách vãng lai


def test_product_detail_out_of_stock(client, shop):
    shop["make"]("Hết", 100000, shop["ao"], [(shop["m"], shop["den"], 3, 3)], slug="het")
    body = client.get("/products/het").get_data(as_text=True)
    assert "Sản phẩm tạm hết hàng" in body and 'id="variants-data"' not in body


@pytest.mark.parametrize("slug", ["khong-co", "ngung-ban", "danh-muc-an"])
def test_product_detail_404_when_not_visible(client, shop, slug):
    mk = shop["make"]
    mk("Ngừng", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], slug="ngung-ban", status=EntityStatus.INACTIVE)
    mk("Ẩn", 100000, shop["an"], [(shop["m"], shop["den"], 5, 0)], slug="danh-muc-an")
    assert client.get(f"/products/{slug}").status_code == 404


def test_product_detail_reviews_masked(client, shop, buyer):
    acc, addr = buyer
    p = shop["make"]("Có đánh giá", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], slug="co-danh-gia")
    o = _order(acc, addr, OrderStatus.COMPLETED, [(p.variants[0], 1)])
    db.session.add(Review(sales_order_item_id=o.items[0].id, rating=4, comment="Mặc rất thoải mái"))
    db.session.commit()
    body = client.get("/products/co-danh-gia").get_data(as_text=True)
    assert "Mặc rất thoải mái" in body and "4.0</strong>/5" in body and "1 đánh giá" in body
    assert "N. V. An" in body and "Nguyễn Văn An" not in body            # che bớt họ tên


def test_related_products_same_category(client, shop):
    mk = shop["make"]
    main = mk("Chính", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], slug="chinh")
    mk("Cùng loại", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)])
    mk("Khác loại", 100000, shop["quan"], [(shop["m"], shop["den"], 5, 0)])
    related = client.get("/products/chinh").get_data(as_text=True).split("Sản phẩm liên quan")[1]
    assert "Cùng loại" in related and "Khác loại" not in related and ">Chính<" not in related


def test_policy_pages_render_successfully(client):
    """Kiểm tra 4 trang chính sách pháp lý theo Luật TMĐT 122/2025 và Luật BV DLCN 2025."""
    r_privacy = client.get("/privacy-policy")
    assert r_privacy.status_code == 200
    assert "CHÍNH SÁCH BẢO VỆ DỮ LIỆU CÁ NHÂN" in r_privacy.get_data(as_text=True)

    r_terms = client.get("/terms")
    assert r_terms.status_code == 200
    assert "ĐIỀU KHOẢN MUA BÁN & SỬ DỤNG DỊCH VỤ" in r_terms.get_data(as_text=True)

    r_returns = client.get("/returns-policy")
    assert r_returns.status_code == 200
    assert "CHÍNH SÁCH ĐỔI TRẢ & HOÀN TIỀN" in r_returns.get_data(as_text=True)

    r_shipping = client.get("/shipping-policy")
    assert r_shipping.status_code == 200
    assert "CHÍNH SÁCH VẬN CHUYỂN & GIAO NHẬN" in r_shipping.get_data(as_text=True)

