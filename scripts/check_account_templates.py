"""Render thật các template khu vực tài khoản (hồ sơ, đổi mật khẩu, địa chỉ, giỏ hàng) và menu theo vai trò,
bằng dữ liệu giả, không cần DB. Chạy: python scripts/check_account_templates.py"""
import re
import sys
from decimal import Decimal
from types import SimpleNamespace as NS

sys.path.insert(0, "scripts")
from _render_env import Anon, Checker, Customer, Fld, Form, SelectFld, Staff, make_app, set_user

from flask import render_template

from app.services.cart_view import CartLine, CartView, line_issue

app = make_app()
ok = Checker()


def make_line(name, price, qty, available, purchasable=True, color="Đen", size="M", vid=1, img=None):
    product = NS(name=name, slug=name.lower().replace(" ", "-"), primary_image=img)
    variant = NS(id=vid, color=NS(name=color), size=NS(name=size), product=product)
    return CartLine(item=None, variant=variant, product=product, quantity=qty, unit_price=Decimal(price),
                    available=available, purchasable=purchasable, issue=line_issue(purchasable, available, qty))


with app.test_request_context("/account/cart"):
    # ================= thanh menu theo vai trò =================
    base_form = Form(email=Fld("email", "Email"))

    def navbar(user, **ctx):
        set_user(app, user)
        return render_template("auth/forgot_password.html", form=base_form, **ctx)

    html = navbar(Anon())
    ok('href="/account/cart"' in html and 'href="/auth/login"' in html and 'href="/auth/register"' in html, "menu: khách vãng lai")
    ok("text-bg-danger" not in html and "/account/profile" not in html, "menu: khách vãng lai không có menu tài khoản")

    html = navbar(Customer(), cart_count=3)
    ok(re.search(r'href="/account/cart">\s*<i class="bi bi-bag"></i> Giỏ hàng\s*<span class="badge rounded-pill text-bg-danger">3</span>', html),
       "menu: khách hàng thấy giỏ hàng kèm số lượng")
    ok('href="/account/profile"' in html and 'href="/account/addresses"' in html and 'href="/account/password"' in html,
       "menu: khách hàng có hồ sơ, sổ địa chỉ, đổi mật khẩu")
    ok("&lt;b&gt;Văn&lt;/b&gt;" in html and 'action="/auth/logout"' in html, "menu: tên được escape, đăng xuất POST")
    ok("text-bg-danger" not in navbar(Customer(), cart_count=0), "menu: giỏ trống không hiện số")

    html = navbar(Staff())
    ok('href="/account/cart"' not in html, "menu: nhân viên không có giỏ hàng")
    ok('href="/account/profile"' in html and 'href="/account/addresses"' not in html and 'href="/account/password"' in html,
       "menu: nhân viên có hồ sơ và đổi mật khẩu, không có sổ địa chỉ")

    # ================= hồ sơ / đổi mật khẩu =================
    set_user(app, Customer())
    html = render_template("account/profile.html", form=Form(full_name=Fld("full_name", "Họ và tên", value="Nguyễn Văn A"),
                           phone=Fld("phone", "Số điện thoại", ["Số điện thoại không hợp lệ (ví dụ: 0912345678)."], value="123")))
    ok('value="kh@test.com" disabled' in html and "không thể thay đổi" in html, "profile: email chỉ đọc")
    ok('value="Nguyễn Văn A"' in html and "is-invalid" in html and "Số điện thoại không hợp lệ" in html, "profile: giá trị và lỗi")
    ok('list-group-item list-group-item-action active"><i class="bi bi-person"></i> Hồ sơ' in html, "profile: menu trái đánh dấu đúng mục")

    html = render_template("account/change_password.html", form=Form(
        current_password=Fld("current_password", "Mật khẩu hiện tại", ["Mật khẩu hiện tại không đúng."]),
        new_password=Fld("new_password", "Mật khẩu mới"), confirm_password=Fld("confirm_password", "Nhập lại mật khẩu mới")))
    ok('autocomplete="current-password"' in html and html.count('autocomplete="new-password"') == 2 and "không đúng" in html,
       "password: autocomplete và lỗi")

    # ================= sổ địa chỉ =================
    def addr(i, name, default=False):
        return NS(id=i, recipient_name=name, phone="0912345678", street_detail=f"{i} Lê Lợi", is_default=default,
                  ward=NS(name="Phường Bến Nghé", province=NS(name="TP. Hồ Chí Minh")))
    html = render_template("account/addresses.html", addresses=[addr(1, "An", True), addr(2, "Bình")], max_addresses=10)
    ok(html.count("Mặc định</span>") == 1 and html.count("Đặt mặc định") == 1, "addresses: chỉ địa chỉ mặc định có nhãn, các bản khác có nút đặt mặc định")
    ok('action="/account/addresses/2/default"' in html and 'action="/account/addresses/1/default"' not in html, "addresses: nút đặt mặc định đúng địa chỉ")
    ok('action="/account/addresses/1/delete"' in html and 'href="/account/addresses/2/edit"' in html and html.count('name="csrf_token"') >= 3,
       "addresses: sửa, xóa kèm CSRF")
    ok("1 Lê Lợi, Phường Bến Nghé, TP. Hồ Chí Minh" in html and "Thêm địa chỉ" in html, "addresses: địa chỉ đầy đủ, nút thêm")
    html = render_template("account/addresses.html", addresses=[addr(i, f"N{i}") for i in range(1, 11)], max_addresses=10)
    ok('href="/account/addresses/new"' not in html, "addresses: đủ giới hạn thì ẩn nút thêm")
    html = render_template("account/addresses.html", addresses=[], max_addresses=10)
    ok("chưa có địa chỉ nhận hàng nào" in html and "Thêm địa chỉ đầu tiên" in html, "addresses: trạng thái rỗng")

    prov = [(0, "-- Chọn tỉnh/thành phố --"), (1, "TP. Hồ Chí Minh"), (2, "Hà Nội")]
    wards = [(0, "-- Chọn phường/xã --"), (5, "Phường Bến Nghé")]
    form = Form(recipient_name=Fld("recipient_name", "Họ tên người nhận", value="An"), phone=Fld("phone", "Số điện thoại người nhận"),
                province_id=SelectFld("province_id", "Tỉnh/Thành phố", prov, selected=1),
                ward_id=SelectFld("ward_id", "Phường/Xã", wards, selected=0, errors=["Vui lòng chọn phường/xã."]),
                street_detail=Fld("street_detail", "Số nhà, tên đường"), is_default=Fld("is_default", "Đặt làm địa chỉ mặc định"))
    html = render_template("account/address_form.html", form=form, address=None)
    ok('id="address-form" data-wards-url="/account/api/wards"' in html and "Thêm địa chỉ nhận hàng" in html, "address_form: thêm mới, URL API phường")
    ok('<option selected value="1">TP. Hồ Chí Minh</option>' in html and "form-select is-invalid" in html and "Vui lòng chọn phường/xã." in html,
       "address_form: tỉnh đang chọn, lỗi ở phường")
    ok("js/address.js" in html, "address_form: nạp address.js")
    ok("Sửa địa chỉ" in render_template("account/address_form.html", form=form, address=addr(1, "An")), "address_form: tiêu đề khi sửa")

    # ================= giỏ hàng =================
    ok_line = make_line("Áo Pro", 100000, 2, 10, vid=1, img=NS(url="https://cdn.test/a.jpg"))
    low = make_line("Sắp hết", 200000, 2, 1, vid=2, color="Trắng", size="L")
    gone = make_line("Ngừng bán", 300000, 2, 0, purchasable=False, vid=3)
    sold = make_line("Hết hàng", 400000, 2, 0, vid=4)

    html = render_template("account/cart.html", cart=CartView([ok_line]), max_per_item=10)
    ok("200.000 ₫" in html and 'Tạm tính</span><span class="text-sz">200.000 ₫</span>' in html, "cart: dòng và tạm tính")
    ok('src="https://cdn.test/a.jpg"' in html and "Màu: Đen" in html and "Cỡ: M" in html, "cart: ảnh, màu, cỡ")
    ok('name="quantity" min="1" max="10" value="2"' in html and 'action="/account/cart/update"' in html
       and 'action="/account/cart/remove"' in html and 'name="variant_id" value="1"' in html, "cart: form cập nhật và xóa")
    ok("xử lý các sản phẩm có cảnh báo" not in html and "Xóa sản phẩm không còn bán" not in html
       and 'href="/products/áo-pro"' in html.replace("%C3%A1o-pro", "áo-pro") and "Tiến hành đặt hàng" in html, "cart: giỏ hợp lệ, cho phép đặt hàng")

    html = render_template("account/cart.html", cart=CartView([ok_line, low, gone, sold]), max_per_item=10)
    ok("Chỉ còn 1 sản phẩm." in html and "Sản phẩm đã ngừng kinh doanh." in html and "Đã hết hàng." in html, "cart: ba loại cảnh báo")
    ok("xử lý các sản phẩm có cảnh báo" in html and "Xóa sản phẩm không còn bán" in html and 'action="/account/cart/clean"' in html,
       "cart: chặn đặt hàng, có nút dọn giỏ")
    ok('Tạm tính</span><span class="text-sz">600.000 ₫</span>' in html, "cart: tạm tính bỏ dòng ngừng bán và hết hàng")
    ok(html.count("—") == 1, "cart: dòng ngừng bán không hiện thành tiền")
    ok('href="/products/ngừng-bán"' not in html and "Ngừng bán</span>" in html, "cart: dòng ngừng bán không có liên kết sản phẩm")
    ok(html.count('<form method="post" action="/account/cart/update"') == 3, "cart: dòng ngừng bán không có ô sửa số lượng")

    html = render_template("account/cart.html", cart=CartView([]), max_per_item=10)
    ok("Giỏ hàng của bạn đang trống" in html and "Bắt đầu mua sắm" in html and "Tạm tính" not in html, "cart: trạng thái rỗng")

print(f"OK: {ok.count} kiểm tra giao diện tài khoản đều đạt")
