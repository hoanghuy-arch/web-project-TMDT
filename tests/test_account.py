"""Kiểm thử khu vực tài khoản: hồ sơ, đổi mật khẩu, sổ địa chỉ, giỏ hàng (Task 5)."""
import re

import pytest

from app.constants import ROLE_STAFF, EntityStatus, OrderStatus
from app.extensions import db
from app.models import Address, CartItem, Province, SalesOrder, Ward

PASSWORD = "Matkhau123"


# ------------------------------------------------------------------ dữ liệu mẫu
@pytest.fixture()
def geo(app):
    hcm, hn = Province(name="TP. Hồ Chí Minh"), Province(name="Hà Nội")
    w1, w2, w3 = Ward(province=hcm, name="Phường Bến Nghé"), Ward(province=hcm, name="Phường Tân Hưng"), \
        Ward(province=hn, name="Phường Cửa Nam")
    db.session.add_all([hcm, hn, w1, w2, w3])
    db.session.commit()
    return dict(hcm=hcm, hn=hn, w1=w1, w2=w2, w3=w3)


@pytest.fixture()
def customer(make_account, login):
    acc = make_account(email="kh@test.com")
    login("kh@test.com")
    return acc


def _addr_data(geo, **over):
    data = dict(recipient_name="Nguyễn Văn An", phone="0912 345 678", province_id=geo["hcm"].id,
                ward_id=geo["w1"].id, street_detail="12 Lê Lợi")
    data.update(over)
    return data


def _active(account_id):
    return db.session.scalars(
        db.select(Address).where(Address.account_id == account_id, Address.is_active.is_(True))
        .order_by(Address.id)).all()


# ================================================================== hồ sơ
def test_profile_requires_login(client):
    resp = client.get("/account/profile")
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


def test_profile_update(client, customer):
    resp = client.post("/account/profile", data=dict(full_name="  Trần Thị B  ", phone="+84 987 654 321",
                                                     email="hacker@evil.com"))
    assert resp.status_code == 302
    db.session.refresh(customer)
    assert customer.full_name == "Trần Thị B" and customer.phone == "0987654321"
    assert customer.email == "kh@test.com"                       # không đổi được email


def test_profile_form_prefilled(client, customer):
    body = client.get("/account/profile").get_data(as_text=True)
    assert 'value="Người Dùng"' in body and 'value="0912345678"' in body and "kh@test.com" in body


@pytest.mark.parametrize("field,value,message", [
    ("phone", "123", "Số điện thoại không hợp lệ"), ("full_name", "A", "từ 2 đến 100 ký tự")])
def test_profile_validation(client, customer, field, value, message):
    data = dict(full_name="Tên Hợp Lệ", phone="0912345678")
    data[field] = value
    resp = client.post("/account/profile", data=data)
    assert resp.status_code == 200 and message in resp.get_data(as_text=True)


def test_staff_can_open_profile(client, make_account, login):
    make_account(email="nv@test.com", role=ROLE_STAFF)
    login("nv@test.com")
    assert client.get("/account/profile").status_code == 200


# ================================================================== đổi mật khẩu
@pytest.mark.parametrize("current,new,confirm,message", [
    ("Sai-mat-khau1", "MatKhauMoi99", "MatKhauMoi99", "Mật khẩu hiện tại không đúng"),
    (PASSWORD, PASSWORD, PASSWORD, "phải khác mật khẩu hiện tại"),
    (PASSWORD, "yeu", "yeu", "ít nhất 8 ký tự"),
    (PASSWORD, "MatKhauMoi99", "KhacHoan123", "không khớp"),
])
def test_change_password_rejected(client, customer, current, new, confirm, message):
    resp = client.post("/account/password", data=dict(current_password=current, new_password=new,
                                                      confirm_password=confirm))
    assert resp.status_code == 200 and message in resp.get_data(as_text=True)
    db.session.refresh(customer)
    assert customer.check_password(PASSWORD)


def test_change_password_success(client, customer):
    resp = client.post("/account/password", data=dict(current_password=PASSWORD, new_password="MatKhauMoi99",
                                                      confirm_password="MatKhauMoi99"))
    assert resp.status_code == 302
    db.session.refresh(customer)
    assert customer.check_password("MatKhauMoi99") and not customer.check_password(PASSWORD)
    assert client.get("/account/profile").status_code == 200       # vẫn đăng nhập


# ================================================================== sổ địa chỉ
def test_addresses_customer_only(client, make_account, login):
    assert client.get("/account/addresses").status_code == 302                     # chưa đăng nhập
    make_account(email="nv@test.com", role=ROLE_STAFF)
    login("nv@test.com")
    assert client.get("/account/addresses").status_code == 403


def test_first_address_is_default_second_is_not(client, customer, geo):
    client.post("/account/addresses/new", data=_addr_data(geo))
    client.post("/account/addresses/new", data=_addr_data(geo, recipient_name="Người Khác", ward_id=geo["w2"].id))
    first, second = _active(customer.id)
    assert first.is_default and not second.is_default
    assert first.phone == "0912345678"                                           # số điện thoại được chuẩn hóa


def test_new_default_address_replaces_old_default(client, customer, geo):
    client.post("/account/addresses/new", data=_addr_data(geo))
    client.post("/account/addresses/new", data=_addr_data(geo, ward_id=geo["w2"].id, is_default="y"))
    first, second = _active(customer.id)
    assert not first.is_default and second.is_default


def test_set_default_endpoint(client, customer, geo):
    client.post("/account/addresses/new", data=_addr_data(geo))
    client.post("/account/addresses/new", data=_addr_data(geo, ward_id=geo["w2"].id))
    first, second = _active(customer.id)
    assert client.post(f"/account/addresses/{second.id}/default").status_code == 302
    db.session.refresh(first); db.session.refresh(second)
    assert not first.is_default and second.is_default


def test_ward_must_belong_to_selected_province(client, customer, geo):
    resp = client.post("/account/addresses/new", data=_addr_data(geo, ward_id=geo["w3"].id))   # w3 thuộc Hà Nội
    assert resp.status_code == 200 and "Lựa chọn không hợp lệ" in resp.get_data(as_text=True)
    assert _active(customer.id) == []


def test_address_required_fields(client, customer, geo):
    resp = client.post("/account/addresses/new", data=dict(recipient_name="", phone="", province_id="0",
                                                           ward_id="0", street_detail=""))
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    for msg in ("Vui lòng nhập họ tên người nhận", "Vui lòng nhập số điện thoại", "Vui lòng chọn tỉnh/thành phố",
                "Vui lòng chọn phường/xã", "Vui lòng nhập số nhà, tên đường"):
        assert msg in body, msg
    assert _active(customer.id) == []


def test_address_limit(app, client, customer, geo):
    app.config["MAX_ADDRESSES_PER_ACCOUNT"] = 2
    for _ in range(3):
        client.post("/account/addresses/new", data=_addr_data(geo))
    assert len(_active(customer.id)) == 2


def test_edit_address_in_place_when_no_orders(client, customer, geo):
    client.post("/account/addresses/new", data=_addr_data(geo))
    (addr,) = _active(customer.id)
    resp = client.post(f"/account/addresses/{addr.id}/edit",
                       data=_addr_data(geo, street_detail="99 Nguyễn Huệ", ward_id=geo["w2"].id))
    assert resp.status_code == 302
    db.session.refresh(addr)
    assert addr.street_detail == "99 Nguyễn Huệ" and addr.ward_id == geo["w2"].id and addr.is_active
    assert len(_active(customer.id)) == 1                                       # không sinh bản ghi mới


def _make_order(account, address):
    o = SalesOrder(order_code=f"SZ-{address.id}", account_id=account.id, address_id=address.id,
                   status=OrderStatus.PENDING_CONFIRM)
    db.session.add(o)
    db.session.commit()
    return o


def test_edit_address_used_by_order_creates_new_version(client, customer, geo):
    """BR: không sửa đè địa chỉ đã gắn đơn: sửa = tạo mới, bản cũ is_active = false."""
    client.post("/account/addresses/new", data=_addr_data(geo))
    (old,) = _active(customer.id)
    order = _make_order(customer, old)
    resp = client.post(f"/account/addresses/{old.id}/edit", data=_addr_data(geo, street_detail="Địa chỉ mới 1"))
    assert resp.status_code == 302
    db.session.refresh(old); db.session.refresh(order)
    assert old.is_active is False and old.is_default is False and old.street_detail == "12 Lê Lợi"
    assert order.address_id == old.id                                           # đơn cũ giữ nguyên địa chỉ cũ
    (new,) = _active(customer.id)
    assert new.id != old.id and new.street_detail == "Địa chỉ mới 1" and new.is_default   # kế thừa mặc định


def test_delete_address_is_soft_and_reassigns_default(client, customer, geo):
    for ward in ("w1", "w2", "w1"):
        client.post("/account/addresses/new", data=_addr_data(geo, ward_id=geo[ward].id))
    a1, a2, a3 = _active(customer.id)
    assert a1.is_default
    client.post(f"/account/addresses/{a1.id}/delete")
    db.session.refresh(a1)
    assert a1.is_active is False and a1.is_default is False and db.session.get(Address, a1.id) is not None
    db.session.refresh(a3)
    assert a3.is_default                                                         # mặc định chuyển sang địa chỉ mới nhất còn lại
    assert [a.id for a in _active(customer.id)] == [a2.id, a3.id]


def test_cannot_touch_other_customers_address(client, customer, geo, make_account, login):
    client.post("/account/addresses/new", data=_addr_data(geo))
    (mine,) = _active(customer.id)
    client.post("/auth/logout")
    other = make_account(email="khac@test.com")
    login("khac@test.com")
    for method, path in (("get", "edit"), ("post", "edit"), ("post", "default"), ("post", "delete")):
        resp = getattr(client, method)(f"/account/addresses/{mine.id}/{path}", data=_addr_data(geo))
        assert resp.status_code == 404, (method, path)
    db.session.refresh(mine)
    assert mine.is_active and mine.street_detail == "12 Lê Lợi"
    assert _active(other.id) == []


def test_deleted_address_cannot_be_edited(client, customer, geo):
    client.post("/account/addresses/new", data=_addr_data(geo))
    (addr,) = _active(customer.id)
    client.post(f"/account/addresses/{addr.id}/delete")
    assert client.get(f"/account/addresses/{addr.id}/edit").status_code == 404


def test_edit_form_is_prefilled(client, customer, geo):
    client.post("/account/addresses/new", data=_addr_data(geo, ward_id=geo["w2"].id))
    (addr,) = _active(customer.id)
    body = client.get(f"/account/addresses/{addr.id}/edit").get_data(as_text=True)
    assert 'value="12 Lê Lợi"' in body and "Phường Tân Hưng" in body and "Phường Bến Nghé" in body
    assert "Phường Cửa Nam" not in body                                          # chỉ nạp phường của tỉnh đang chọn
    for option_id in (geo["hcm"].id, geo["w2"].id):
        assert re.search(r'<option[^>]*selected[^>]*value="%d"|<option[^>]*value="%d"[^>]*selected' % (option_id, option_id), body)


def test_wards_api(client, customer, geo):
    data = client.get(f"/account/api/wards?province_id={geo['hcm'].id}").get_json()
    assert [w["name"] for w in data] == ["Phường Bến Nghé", "Phường Tân Hưng"]
    assert client.get("/account/api/wards").status_code == 400
    assert client.get("/account/api/wards?province_id=abc").status_code == 400
    assert client.get("/account/api/wards?province_id=9999").get_json() == []


def test_wards_api_requires_login(client, geo):
    resp = client.get(f"/account/api/wards?province_id={geo['hcm'].id}")
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


# ================================================================== giỏ hàng
@pytest.fixture()
def variant(shop):
    return shop["make"]("Áo Pro", 250000, shop["ao"], [(shop["m"], shop["den"], 10, 0)], slug="ao-pro").variants[0]


def _add(client, variant_id, quantity=1):
    return client.post("/account/cart/add", data=dict(variant_id=variant_id, quantity=quantity), follow_redirects=True)


def _items(account_id):
    return {i.product_variant_id: i.quantity for i in
            db.session.scalars(db.select(CartItem).where(CartItem.account_id == account_id)).all()}


def test_cart_requires_customer(client, variant, make_account, login):
    assert client.get("/account/cart").status_code == 302
    assert client.post("/account/cart/add", data=dict(variant_id=variant.id, quantity=1)).status_code == 302
    make_account(email="nv@test.com", role=ROLE_STAFF)
    login("nv@test.com")
    assert client.get("/account/cart").status_code == 403
    assert client.post("/account/cart/add", data=dict(variant_id=variant.id, quantity=1)).status_code == 403


def test_add_to_cart_and_accumulate(client, customer, variant):
    body = _add(client, variant.id, 2).get_data(as_text=True)
    assert "Đã thêm Áo Pro - M - Đen vào giỏ hàng" in body and "Áo Pro" in body and "500.000" in body
    _add(client, variant.id, 3)
    assert _items(customer.id) == {variant.id: 5}


def test_add_to_cart_caps_at_available_stock(shop, client, customer):
    v = shop["make"]("Ít hàng", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 2)]).variants[0]   # khả dụng 3
    body = _add(client, v.id, 2).get_data(as_text=True)
    assert _items(customer.id) == {v.id: 2}
    body = _add(client, v.id, 5).get_data(as_text=True)                         # cần 7, chỉ còn 3
    assert _items(customer.id) == {v.id: 3} and "được giới hạn ở mức 3" in body
    body = _add(client, v.id, 1).get_data(as_text=True)
    assert "số lượng tối đa có thể mua" in body and _items(customer.id) == {v.id: 3}


def test_add_to_cart_respects_per_item_limit(app, client, customer, variant):
    app.config["CART_MAX_QUANTITY_PER_ITEM"] = 4
    _add(client, variant.id, 3)
    _add(client, variant.id, 3)
    assert _items(customer.id) == {variant.id: 4}


@pytest.mark.parametrize("quantity", ["0", "-1", "11", "abc", ""])
def test_add_to_cart_invalid_quantity(client, customer, variant, quantity):
    body = _add(client, variant.id, quantity).get_data(as_text=True)
    assert "Số lượng phải từ 1 đến 10" in body
    assert _items(customer.id) == {}


def test_add_to_cart_rejects_unavailable(shop, client, customer):
    mk = shop["make"]
    inactive_variant = mk("A", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)]).variants[0]
    inactive_variant.status = EntityStatus.INACTIVE
    hidden_product = mk("B", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)], status=EntityStatus.INACTIVE).variants[0]
    hidden_category = mk("C", 100000, shop["an"], [(shop["m"], shop["den"], 5, 0)]).variants[0]
    db.session.commit()
    for vid in (inactive_variant.id, hidden_product.id, hidden_category.id, 99999):
        assert "không còn được bán" in _add(client, vid).get_data(as_text=True), vid
    body = client.post("/account/cart/add", data=dict(quantity=1), follow_redirects=True).get_data(as_text=True)
    assert "không còn được bán" in body                                          # thiếu variant_id
    sold_out = mk("D", 100000, shop["ao"], [(shop["m"], shop["den"], 3, 3)]).variants[0]
    assert "đã hết hàng" in _add(client, sold_out.id).get_data(as_text=True)
    assert _items(customer.id) == {}


def test_cart_line_limit(app, shop, client, customer):
    app.config["CART_MAX_LINES"] = 2
    vs = [shop["make"](f"SP{i}", 100000, shop["ao"], [(shop["m"], shop["den"], 5, 0)]).variants[0] for i in range(3)]
    for v in vs:
        body = _add(client, v.id).get_data(as_text=True)
    assert "tối đa 2 sản phẩm khác nhau" in body and len(_items(customer.id)) == 2


def test_cart_does_not_reserve_stock(client, customer, variant):
    _add(client, variant.id, 5)
    db.session.refresh(variant)
    assert variant.reserved_quantity == 0 and variant.stock_quantity == 10      # giữ hàng chỉ xảy ra khi tạo đơn


def test_update_quantity(client, customer, variant):
    _add(client, variant.id, 2)
    body = client.post("/account/cart/update", data=dict(variant_id=variant.id, quantity=6), follow_redirects=True).get_data(as_text=True)
    assert "Đã cập nhật số lượng" in body and _items(customer.id) == {variant.id: 6}
    variant.stock_quantity = 4
    db.session.commit()
    body = client.post("/account/cart/update", data=dict(variant_id=variant.id, quantity=9), follow_redirects=True).get_data(as_text=True)
    assert "Chỉ còn 4 sản phẩm trong kho" in body and _items(customer.id) == {variant.id: 4}


@pytest.mark.parametrize("quantity", ["0", "99", "x", ""])
def test_update_quantity_invalid(client, customer, variant, quantity):
    _add(client, variant.id, 2)
    body = client.post("/account/cart/update", data=dict(variant_id=variant.id, quantity=quantity), follow_redirects=True).get_data(as_text=True)
    assert "Số lượng phải từ 1 đến" in body and _items(customer.id) == {variant.id: 2}


def test_update_or_remove_item_not_in_cart(client, customer, variant):
    for path in ("update", "remove"):
        body = client.post(f"/account/cart/{path}", data=dict(variant_id=variant.id, quantity=1), follow_redirects=True).get_data(as_text=True)
        assert "không có trong giỏ hàng" in body


def test_remove_item(client, customer, variant):
    _add(client, variant.id, 2)
    body = client.post("/account/cart/remove", data=dict(variant_id=variant.id), follow_redirects=True).get_data(as_text=True)
    assert "Đã xóa sản phẩm khỏi giỏ hàng" in body and "Giỏ hàng của bạn đang trống" in body
    assert _items(customer.id) == {}


def test_carts_are_isolated_between_customers(client, customer, variant, make_account, login):
    _add(client, variant.id, 3)
    client.post("/auth/logout")
    make_account(email="khac@test.com")
    login("khac@test.com")
    assert "Giỏ hàng của bạn đang trống" in client.get("/account/cart").get_data(as_text=True)
    assert "không có trong giỏ hàng" in client.post("/account/cart/remove", data=dict(variant_id=variant.id),
                                                    follow_redirects=True).get_data(as_text=True)
    assert _items(customer.id) == {variant.id: 3}                                # giỏ của người kia còn nguyên


def test_cart_flags_problem_lines_and_blocks_checkout(shop, client, customer):
    mk = shop["make"]
    ok = mk("Bình thường", 100000, shop["ao"], [(shop["m"], shop["den"], 10, 0)]).variants[0]
    low = mk("Sắp hết", 200000, shop["ao"], [(shop["m"], shop["den"], 10, 0)]).variants[0]
    gone = mk("Ngừng bán", 300000, shop["ao"], [(shop["m"], shop["den"], 10, 0)])
    sold_out = mk("Hết hàng", 400000, shop["ao"], [(shop["m"], shop["den"], 10, 0)]).variants[0]
    for v in (ok, low, gone.variants[0], sold_out):
        _add(client, v.id, 2)
    body = client.get("/account/cart").get_data(as_text=True)
    assert "xử lý các sản phẩm có cảnh báo" not in body and "Chỉ còn" not in body          # giỏ hợp lệ: không cảnh báo

    low.stock_quantity = 1
    gone.status = EntityStatus.INACTIVE
    sold_out.stock_quantity, sold_out.reserved_quantity = 5, 5
    db.session.commit()
    body = client.get("/account/cart").get_data(as_text=True)
    assert "Chỉ còn 1 sản phẩm." in body and "Sản phẩm đã ngừng kinh doanh." in body and "Đã hết hàng." in body
    assert "xử lý các sản phẩm có cảnh báo" in body
    # Tạm tính chỉ cộng dòng còn bán và còn hàng: Bình thường 2x100.000 + Sắp hết 2x200.000 = 600.000
    # (dòng ngừng bán 2x300.000 và dòng hết hàng 2x400.000 không được cộng)
    assert 'Tạm tính</span><span class="text-sz">600.000 ₫</span>' in body

    removed = client.post("/account/cart/clean", follow_redirects=True).get_data(as_text=True)
    assert "Đã xóa 2 sản phẩm không còn bán" in removed
    assert set(_items(customer.id)) == {ok.id, low.id}


def test_cart_badge_in_navbar(client, customer, variant):
    assert 'badge rounded-pill text-bg-danger' not in client.get("/").get_data(as_text=True)
    _add(client, variant.id, 3)
    assert re.search(r'text-bg-danger">3</span>', client.get("/").get_data(as_text=True))


# ------------------------------------------------------------------ nút mua ở trang chi tiết
def test_product_page_buy_area_by_role(client, variant, make_account, login):
    anon = client.get("/products/ao-pro").get_data(as_text=True)
    assert "Đăng nhập để mua hàng" in anon and "add-to-cart-form" not in anon
    make_account(email="kh@test.com")
    login("kh@test.com")
    cust = client.get("/products/ao-pro").get_data(as_text=True)
    assert 'id="add-to-cart-form"' in cust and 'name="variant_id"' in cust and 'id="add-to-cart-btn"' in cust
    assert 'data-max-per-item="10"' in cust
    client.post("/auth/logout")
    make_account(email="nv@test.com", role=ROLE_STAFF)
    login("nv@test.com")
    staff = client.get("/products/ao-pro").get_data(as_text=True)
    assert "không dùng để mua hàng" in staff and "add-to-cart-form" not in staff
