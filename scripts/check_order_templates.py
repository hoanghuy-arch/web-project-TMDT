"""Render thật các template đặt hàng (checkout, danh sách đơn, chi tiết đơn, email xác nhận) bằng dữ liệu giả.
Chạy: python scripts/check_order_templates.py"""
import re
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace as NS

sys.path.insert(0, "scripts")
from _render_env import Anon, Checker, Customer, Pag, make_app, set_user

from flask import render_template

from app.constants import OrderStatus, PaymentMethod
from app.services.cart_view import CartLine, CartView, line_issue

app = make_app()
ok = Checker()
D = Decimal


def line(name, price, qty, color="Đen", size="M", vid=1):
    product = NS(name=name, slug=name.lower(), primary_image=None)
    variant = NS(id=vid, color=NS(name=color), size=NS(name=size), product=product)
    return CartLine(item=None, variant=variant, product=product, quantity=qty, unit_price=D(price),
                    available=10, purchasable=True, issue=line_issue(True, 10, qty))


ward = NS(name="Phường Bến Nghé", province=NS(name="TP. Hồ Chí Minh"))
def addr(i, default=False):
    return NS(id=i, recipient_name=f"Người {i}", phone="0912345678", street_detail=f"{i} Lê Lợi", is_default=default, ward=ward,
              full_address=f"{i} Lê Lợi, Phường Bến Nghé, TP. Hồ Chí Minh")


def summary(**o):
    cart = CartView([line("Áo Pro", 250000, 2), line("Quần Short", 150000, 1, vid=2)])
    base = dict(cart=cart, address=addr(1, True), promo_code="", promotion=None, promo_error=None, discount=D(0),
                shipping_fee=D(0), free_shipping=False)
    base.update(o)
    s = NS(**base)
    s.subtotal = cart.subtotal
    s.total = s.subtotal - s.discount + s.shipping_fee
    return s


with app.test_request_context("/account/checkout"):
    set_user(app, Customer())
    methods = PaymentMethod.LABELS

    # ================= checkout =================
    def checkout(**kw):
        args = dict(summary=summary(), addresses=[addr(1, True), addr(2)], method="COD", note="", online_enabled=False,
                    payment_methods=methods)
        args.update(kw)
        return render_template("account/checkout.html", **args)

    html = checkout(summary=summary(shipping_fee=D(30000)))
    ok(re.search(r'id="addr-1" value="1"\s+checked', html) and not re.search(r'id="addr-2" value="2"\s+checked', html), "checkout: chọn sẵn địa chỉ mặc định")
    ok("Mặc định</span>" in html and "2 Lê Lợi, Phường Bến Nghé, TP. Hồ Chí Minh" in html, "checkout: danh sách địa chỉ")
    ok("650.000 ₫" in html and "680.000 ₫" in html and "30.000 ₫" in html and "0 ₫" in html, "checkout: tạm tính, phí ship, tổng, không giảm giá")
    ok("Áo Pro" in html and "&times; 2" in html and "500.000 ₫" in html, "checkout: dòng sản phẩm")
    ok(re.search(r'id="pm-cod" value="COD" checked', html) and "chưa khả dụng" in html and re.search(r'id="pm-online"[^>]*disabled', html),
       "checkout: COD mặc định, online bị khóa khi chưa bật")
    ok('name="action" value="apply"' in html and 'name="action" value="place"' in html and html.index('value="apply"') < html.index('value="place"'),
       "checkout: nút Áp dụng đứng trước nút Đặt hàng (Enter không đặt nhầm đơn)")
    ok('name="csrf_token"' in html and "js/checkout.js" in html, "checkout: CSRF, script")

    html = checkout(summary=summary(promo_code="SAVE10", promotion=NS(code="SAVE10"), discount=D(65000), free_shipping=True), online_enabled=True, method="VNPAY")
    ok("Đã áp dụng mã SAVE10: giảm 65.000 ₫" in html and "-65.000 ₫" in html and "585.000 ₫" in html, "checkout: đã áp mã, tổng sau giảm")
    ok("Miễn phí" in html and 'value="SAVE10"' in html, "checkout: miễn phí vận chuyển, giữ mã")
    ok(re.search(r'id="pm-online" value="VNPAY"\s+checked', html) and not re.search(r'id="pm-online"[^>]*disabled', html) and "(chưa khả dụng)" not in html,
       "checkout: online bật thì chọn được")

    html = checkout(summary=summary(promo_code="SAI", promo_error="Mã khuyến mãi không tồn tại."))
    ok("is-invalid" in html and "Mã khuyến mãi không tồn tại." in html, "checkout: lỗi mã khuyến mãi")

    html = checkout(summary=summary(address=None), addresses=[])
    ok("Bạn chưa có địa chỉ nhận hàng" in html and "Chọn địa chỉ" in html and re.search(r'value="place"[^>]*disabled', html), "checkout: chưa có địa chỉ thì khóa nút đặt hàng")

    # ================= danh sách đơn =================
    def order(code, status, qty_items=1, pay="UNPAID"):
        items = [NS(variant=NS(product=NS(name=f"SP {i}")), quantity=i + 1) for i in range(qty_items)]
        return NS(order_code=code, created_at=datetime(2026, 11, 6, 20, 0), status=status, payment_status=pay,
                  total_amount=D(680000), items=items)
    orders = [order("SZ261107AAAAAA", "PENDING_CONFIRM"), order("SZ261107BBBBBB", "CANCELLED", 5, "FAILED")]
    list_url = lambda p: f"/account/orders?page={p}"
    html = render_template("account/orders.html", pagination=Pag(orders, 2, 1, 1), orders=orders, status=None,
                           counts={"PENDING_CONFIRM": 1, "CANCELLED": 1}, order_status_labels=OrderStatus.LABELS, list_url=list_url)
    ok("SZ261107AAAAAA" in html and "07/11/2026 03:00" in html, "orders: mã đơn, giờ Việt Nam (UTC+7)")
    ok("Chờ xác nhận (1)" in html and "Đã hủy (1)" in html and "Đã giao (" not in html and "Hoàn thành (" not in html, "orders: thẻ lọc chỉ hiện trạng thái có đơn")
    ok("và 2 sản phẩm khác" in html and html.count("SP 0") == 2, "orders: tối đa 3 dòng rồi 'và N sản phẩm khác'")
    ok("text-bg-info" in html and "text-bg-danger" in html and "Thanh toán thất bại" in html and "680.000 ₫" in html, "orders: huy hiệu trạng thái và thanh toán")
    ok('class="btn btn-sm btn-dark">Tất cả' in html, "orders: 'Tất cả' đang chọn")
    html = render_template("account/orders.html", pagination=Pag(orders[:1], 1, 1, 1), orders=orders[:1], status="PENDING_CONFIRM",
                           counts={"PENDING_CONFIRM": 1}, order_status_labels=OrderStatus.LABELS, list_url=list_url)
    ok('btn btn-sm btn-dark">Chờ xác nhận (1)' in html, "orders: thẻ lọc đang chọn")
    html = render_template("account/orders.html", pagination=Pag([], 0, 1, 0), orders=[], status="CANCELLED", counts={},
                           order_status_labels=OrderStatus.LABELS, list_url=list_url)
    ok("Không có đơn hàng nào ở trạng thái này" in html, "orders: rỗng theo bộ lọc")
    html = render_template("account/orders.html", pagination=Pag([], 0, 1, 0), orders=[], status=None, counts={},
                           order_status_labels=OrderStatus.LABELS, list_url=list_url)
    ok("Bạn chưa có đơn hàng nào" in html, "orders: rỗng")

    # ================= chi tiết đơn =================
    def detail_order(status="PENDING_CONFIRM", **o):
        items = [NS(variant=NS(product=NS(name="Áo Pro"), size=NS(name="M"), color=NS(name="Đen")), quantity=2, unit_price=D(250000), line_total=D(500000))]
        hist = [NS(to_status="PENDING_CONFIRM", changed_at=datetime(2026, 11, 6, 20, 0), reason="Khách đặt hàng"),
                NS(to_status="CONFIRMED", changed_at=datetime(2026, 11, 6, 21, 30), reason=None)]
        pay = NS(status="UNPAID", method="COD")
        base = dict(order_code="SZ261107AAAAAA", created_at=datetime(2026, 11, 6, 20, 0), status=status, items=items,
                    status_history=hist, subtotal=D(500000), discount_amount=D(50000), shipping_fee=D(30000),
                    total_amount=D(480000), promotion=NS(code="SAVE10"), address=addr(1), note="Gọi trước khi giao",
                    shipment=None, latest_payment=pay, payment_method="COD", payment_status="UNPAID")
        base.update(o)
        return NS(**base)

    html = render_template("account/order_detail.html", order=detail_order(), can_cancel=True, deadline=None)
    ok("Đơn SZ261107AAAAAA" in html and "Đặt lúc 07/11/2026 03:00" in html, "detail: tiêu đề, giờ VN")
    ok("Áo Pro" in html and "250.000 ₫" in html and "500.000 ₫" in html and "Giảm giá (SAVE10)" in html and "-50.000 ₫" in html and "480.000 ₫" in html,
       "detail: dòng, giảm giá, tổng")
    ok("Người 1" in html and "1 Lê Lợi, Phường Bến Nghé, TP. Hồ Chí Minh" in html and "Gọi trước khi giao" in html, "detail: địa chỉ, ghi chú")
    timeline = html.split("Lịch sử trạng thái")[1]
    ok(timeline.index("Đã xác nhận") < timeline.index("Chờ xác nhận") and "Khách đặt hàng" in timeline and "07/11/2026 04:30" in timeline,
       "detail: lịch sử mới nhất lên đầu, có lý do, giờ VN")
    ok("Thanh toán khi nhận hàng (COD)" in html and "Chưa thanh toán" in html, "detail: thanh toán")
    ok("Hủy đơn hàng</h2>" in html and 'action="/account/orders/SZ261107AAAAAA/cancel"' in html and 'name="csrf_token"' in html, "detail: form hủy đơn khi cho phép")

    html = render_template("account/order_detail.html", order=detail_order("PACKING", promotion=None, discount_amount=D(0), note=None,
                           shipment=NS(carrier=NS(name="GHN"), tracking_code="GHN123")), can_cancel=False, deadline=None)
    ok("Hủy đơn hàng</h2>" not in html and "Giảm giá</span>" in html and "0 ₫" in html and "Ghi chú" not in html, "detail: ẩn hủy đơn, không mã giảm")
    ok("GHN" in html and "GHN123" in html, "detail: thông tin vận chuyển")

    html = render_template("account/order_detail.html", order=detail_order("PENDING_PAYMENT"), can_cancel=False,
                           deadline=datetime(2026, 11, 6, 20, 15), online_enabled=False)
    ok("tự hủy nếu chưa thanh toán trước 07/11/2026 03:15" in html and "Thanh toán ngay" not in html, "detail: hạn thanh toán, ẩn nút khi cổng tắt")
    html = render_template("account/order_detail.html", order=detail_order("PENDING_PAYMENT"), can_cancel=False,
                           deadline=datetime(2026, 11, 6, 20, 15), online_enabled=True)
    ok('href="/payment/start/SZ261107AAAAAA"' in html and "Thanh toán ngay" in html, "detail: nút Thanh toán ngay khi cổng bật")
    html = render_template("account/order_detail.html", order=detail_order("PENDING_CONFIRM"), can_cancel=True, deadline=None, online_enabled=True)
    ok("Thanh toán ngay" not in html, "detail: đơn đã thanh toán không có nút thanh toán")

    # ================= trang thanh toán =================
    html = render_template("payment/mock_gateway.html", txn_ref="SZ261107AAAAAA1B2C3D", amount=280000, order_info="Thanh toan don hang SZ261107AAAAAA")
    ok("Cổng thanh toán GIẢ LẬP" in html and "280.000 ₫" in html and 'name="txn_ref" value="SZ261107AAAAAA1B2C3D"' in html
       and 'name="amount" value="280000"' in html and 'name="csrf_token"' in html, "mock gateway: thông tin giao dịch, CSRF")
    ok(all(f'name="outcome" value="{v}"' in html for v in ("success", "fail", "cancel", "tamper")) and 'action="/payment/mock/complete"' in html,
       "mock gateway: 4 kết quả giả lập")
    html = render_template("payment/result.html", ok=True, order=None, message="Thanh toán thành công! Đơn hàng X.", status_code=200)
    ok("check-circle-fill" in html and "Thanh toán thành công</h1>" in html and "Đăng xuất" in html and "/account/orders" in html, "result: thành công, người đã đăng nhập")
    html = render_template("payment/result.html", ok=False, order=None, message="Số tiền không khớp.", status_code=400)
    ok("x-circle-fill" in html and "Giao dịch chưa hoàn tất" in html and "Số tiền không khớp." in html, "result: thất bại")
    set_user(app, Anon())
    ok('href="/auth/login"' in render_template("payment/result.html", ok=True, order=None, message="m", status_code=200)
       and "Đăng nhập để xem đơn hàng" in render_template("payment/result.html", ok=True, order=None, message="m", status_code=200),
       "result: khách chưa đăng nhập được mời đăng nhập")
    set_user(app, Customer())

    # ================= email =================
    order_obj = detail_order()
    order_obj.address = addr(1)
    ctx = dict(order=order_obj, full_name="Nguyễn Văn A", address=order_obj.address)
    txt, htm = render_template("emails/order_confirmation.txt", **ctx), render_template("emails/order_confirmation.html", **ctx)
    ok("SZ261107AAAAAA" in txt and "Áo Pro (M, Đen) x 2: 500.000 ₫" in txt and "Giảm giá: -50.000 ₫" in txt and "Tổng thanh toán: 480.000 ₫" in txt, "email txt")
    ok("Thanh toán khi nhận hàng (COD)" in txt and "1 Lê Lợi, Phường Bến Nghé" in txt, "email txt: địa chỉ, thanh toán")
    ok("SZ261107AAAAAA" in htm and "480.000 ₫" in htm and "-50.000 ₫" in htm, "email html")
    order_obj.discount_amount = D(0)
    ok("Giảm giá" not in render_template("emails/order_confirmation.txt", **ctx), "email: không có dòng giảm giá khi 0 đồng")


print(f"OK: {ok.count} kiểm tra giao diện đặt hàng đều đạt")
