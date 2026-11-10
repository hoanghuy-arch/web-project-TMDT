"""Render thật các template khu vực nhân viên (dashboard, danh sách, chi tiết đơn) theo từng trạng thái đơn và từng
bộ quyền, bằng dữ liệu giả. Chạy: python scripts/check_staff_templates.py"""
import re
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace as NS

sys.path.insert(0, "scripts")
from _render_env import Checker, Customer, Pag, Staff, make_app, set_user

from flask import render_template

from app.constants import OrderStatus

app = make_app()
ok = Checker()
D = Decimal


class ViewOnly(Staff):
    permissions = ("order.view",)


class ShipOnly(Staff):
    permissions = ("order.view", "shipment.update")


class Admin(Staff):
    role_code = "ADMIN"

    def has_permission(self, code):
        return True


def forms(html):
    """Các form thao tác trên đơn (bỏ qua form đăng xuất ở thanh menu)."""
    return [a for a in re.findall(r'<form method="post" action="([^"]+)"', html) if a.startswith("/staff/orders/")]


with app.test_request_context("/staff/"):
    # ================= dashboard =================
    set_user(app, Staff())
    stats = {"counts": {"PENDING_CONFIRM": 3, "CONFIRMED": 2, "PACKING": 1, "SHIPPING": 4}, "today": 7, "low_stock": 2,
             "low_stock_threshold": 5}
    html = render_template("staff/dashboard.html", stats=stats, labels=OrderStatus.LABELS, badges=OrderStatus.BADGES)
    ok("Đơn hôm nay" in html and 'fs-3 fw-bold">7<' in html, "dashboard: số đơn hôm nay")
    ok(all(f'href="/staff/orders?status={c}"' in html for c in ("PENDING_CONFIRM", "CONFIRMED", "PACKING", "SHIPPING")), "dashboard: liên kết tới từng hàng đợi")
    ok('<span class="badge text-bg-info">3</span> đơn chờ xác nhận' in html and "text-bg-danger\">2</span>" in html, "dashboard: tóm tắt và cảnh báo tồn kho")
    html0 = render_template("staff/dashboard.html", stats=dict(stats, counts={}, low_stock=0), labels=OrderStatus.LABELS, badges=OrderStatus.BADGES)
    ok('text-bg-success">0</span>' in html0 and 'text-bg-info">0</span> đơn chờ xác nhận' in html0, "dashboard: không có việc / tồn kho ổn")

    # ================= menu bên trái =================
    ok('href="/staff/orders"' in html, "nav: nhân viên có quyền xem đơn thấy mục Đơn hàng")
    set_user(app, type("NoPerm", (Staff,), {"permissions": ()})())
    ok('href="/staff/orders"' not in render_template("staff/dashboard.html", stats=stats, labels=OrderStatus.LABELS, badges=OrderStatus.BADGES),
       "nav: không có quyền xem đơn thì ẩn mục Đơn hàng")

    # ================= danh sách =================
    set_user(app, Staff())
    def order(code, status, pay="UNPAID", name="Nguyễn Văn An"):
        return NS(order_code=code, status=status, payment_status=pay, total_amount=D(680000), created_at=datetime(2026, 11, 6, 20, 0),
                  account=NS(full_name=name, phone="0912345678"))
    rows = [order("SZ261107AAAAAA", "PENDING_CONFIRM", name="<b>Hack</b>"), order("SZ261107BBBBBB", "SHIPPING", "PAID")]
    list_url = lambda p: f"/staff/orders?page={p}"
    html = render_template("staff/orders.html", pagination=Pag(rows, 2, 1, 1), orders=rows, status=None, q="", labels=OrderStatus.LABELS,
                           counts={"PENDING_CONFIRM": 1, "SHIPPING": 1}, list_url=list_url)
    ok("SZ261107AAAAAA" in html and "07/11/2026 03:00" in html and "680.000 ₫" in html, "list: mã đơn, giờ VN, tổng tiền")
    ok("&lt;b&gt;Hack&lt;/b&gt;" in html and "<b>Hack</b>" not in html, "list: escape tên khách (chống XSS)")
    ok("Chờ xác nhận (1)" in html and "Đang giao (1)" in html and "Hoàn thành (" not in html, "list: thẻ lọc chỉ hiện trạng thái có đơn")
    ok('href="/staff/orders/SZ261107AAAAAA"' in html and "text-bg-info" in html and "Đã thanh toán" in html, "list: liên kết chi tiết, huy hiệu")
    html = render_template("staff/orders.html", pagination=Pag(rows[:1], 1, 1, 1), orders=rows[:1], status="PENDING_CONFIRM", q='mã "x"',
                           labels=OrderStatus.LABELS, counts={"PENDING_CONFIRM": 1}, list_url=list_url)
    ok('name="status" value="PENDING_CONFIRM"' in html and 'value="mã &#34;x&#34;"' in html and 'btn btn-sm btn-dark">Chờ xác nhận' in html,
       "list: giữ bộ lọc trạng thái và từ khóa (đã escape) khi tìm kiếm")
    html = render_template("staff/orders.html", pagination=Pag([], 0, 1, 0), orders=[], status=None, q="abc", labels=OrderStatus.LABELS,
                           counts={}, list_url=list_url)
    ok("Không có đơn hàng phù hợp" in html, "list: trạng thái rỗng")

    # ================= chi tiết đơn =================
    carriers = [NS(id=1, name="GHN"), NS(id=2, name="GHTK")]

    def detail(status, user, carriers=carriers, incidents=(), shipment=None, pay=("COD", "UNPAID"), **kw):
        set_user(app, user)
        variant = NS(sku="AO-M-DEN", stock_quantity=10, reserved_quantity=2, available_quantity=8, product=NS(name="Áo Pro"),
                     size=NS(name="M"), color=NS(name="Đen"))
        items = [NS(variant=variant, quantity=2, unit_price=D(250000), line_total=D(500000))]
        hist = [NS(to_status="PENDING_CONFIRM", changed_at=datetime(2026, 11, 6, 20, 0), reason="Khách đặt hàng", changed_by=NS(full_name="Nguyễn Văn An")),
                NS(to_status="CANCELLED", changed_at=datetime(2026, 11, 6, 21, 0), reason="Quá hạn", changed_by=None)]
        base = dict(order_code="SZ261107AAAAAA", created_at=datetime(2026, 11, 6, 20, 0), status=status, items=items, status_history=hist,
                    subtotal=D(500000), discount_amount=D(0), shipping_fee=D(30000), total_amount=D(530000), promotion=None,
                    account=NS(full_name="Nguyễn Văn An", email="kh@test.com"), note="Giao giờ hành chính", shipment=shipment,
                    address=NS(recipient_name="Người Nhận", phone="0912345678", full_address="1 Lê Lợi, Phường Bến Nghé, TP. Hồ Chí Minh"),
                    latest_payment=NS(amount=D(530000)), payment_method=pay[0], payment_status=pay[1])
        base.update(kw)
        return render_template("staff/order_detail.html", order=NS(**base), carriers=carriers, incidents=list(incidents), deadline=datetime(2026, 11, 6, 20, 15))

    html = detail("PENDING_PAYMENT", Staff())
    ok("chờ khách thanh toán online" in html and "hạn 07/11/2026 03:15" in html and forms(html) == [], "detail PENDING_PAYMENT: chỉ thông tin, không có nút thao tác")

    html = detail("PENDING_CONFIRM", Staff())
    ok(forms(html) == ["/staff/orders/SZ261107AAAAAA/confirm", "/staff/orders/SZ261107AAAAAA/cancel"], "detail PENDING_CONFIRM: xác nhận + hủy")
    ok(re.search(r'name="reason"[^>]*required', html) and "bắt buộc nhập lý do" in html, "detail: ô lý do hủy bắt buộc")
    ok("Kho: tồn 10" in html and "đang giữ 2" in html and "khả dụng 8" in html and "SKU AO-M-DEN" in html, "detail: thông tin kho khi đang xử lý")
    ok(html.count('name="csrf_token"') == len(forms(html)) + 1, "detail: mỗi form thao tác đều có CSRF (cộng form đăng xuất ở menu)")

    html = detail("PENDING_CONFIRM", ViewOnly())
    ok(forms(html) == [] and "không có quyền" in html, "detail: chỉ có quyền xem thì không có thao tác")

    html = detail("CONFIRMED", Staff())
    ok(forms(html) == ["/staff/orders/SZ261107AAAAAA/pack", "/staff/orders/SZ261107AAAAAA/cancel"] and "Bắt đầu đóng gói" in html, "detail CONFIRMED: đóng gói + hủy")

    html = detail("PACKING", Staff())
    ok(forms(html) == ["/staff/orders/SZ261107AAAAAA/ship", "/staff/orders/SZ261107AAAAAA/cancel"], "detail PACKING: bàn giao + hủy")
    ok('<option value="1">GHN</option>' in html and '<option value="2">GHTK</option>' in html and re.search(r'name="tracking_code"[^>]*required', html)
       and "xuất kho" in html, "detail PACKING: chọn đơn vị vận chuyển, mã vận đơn bắt buộc, giải thích xuất kho")
    ok("Chưa có đơn vị vận chuyển" not in html, "detail PACKING: không cảnh báo khi đã có đơn vị vận chuyển")
    ok("Chưa có đơn vị vận chuyển nào đang hoạt động" in detail("PACKING", Staff(), carriers=[]), "detail PACKING: cảnh báo khi chưa có đơn vị vận chuyển")
    html = detail("PACKING", ShipOnly())
    ok(forms(html) == ["/staff/orders/SZ261107AAAAAA/ship"], "detail PACKING: chỉ có quyền giao hàng thì không có nút hủy")

    shipment = NS(carrier=NS(name="GHN"), tracking_code="GHN123456", shipped_at=datetime(2026, 11, 6, 22, 0), delivered_at=None)
    incidents = [NS(new_value={"note": "Khách <i>không</i> nghe máy"}, created_at=datetime(2026, 11, 7, 1, 0), account=NS(full_name="Nhân Viên A"))]
    html = detail("SHIPPING", Staff(), shipment=shipment, incidents=incidents)
    ok(forms(html) == ["/staff/orders/SZ261107AAAAAA/deliver", "/staff/orders/SZ261107AAAAAA/incident"], "detail SHIPPING: giao thành công + sự cố, không có hủy")
    ok("Đơn COD: sẽ ghi nhận đã thu tiền" in html and "Kho: tồn" not in html, "detail SHIPPING: nhắc thu tiền COD, không hiện số liệu kho")
    ok("GHN123456" in html and "Sự cố giao hàng" in html and "Khách &lt;i&gt;không&lt;/i&gt; nghe máy" in html and "Nhân Viên A" in html, "detail SHIPPING: vận đơn, sự cố (escape)")
    ok("Đơn COD: sẽ ghi nhận" not in detail("SHIPPING", Staff(), shipment=shipment, pay=("VNPAY", "PAID")), "detail SHIPPING: đơn online không nhắc thu tiền")

    done = NS(carrier=NS(name="GHN"), tracking_code="GHN123456", shipped_at=datetime(2026, 11, 6, 22, 0), delivered_at=datetime(2026, 11, 8, 3, 0))
    for status in ("COMPLETED", "CANCELLED", "RETURNING", "RETURNED"):
        html = detail(status, Staff(), shipment=done)
        ok(forms(html) == [] and "trạng thái cuối" in html, f"detail {status}: không còn thao tác")
    ok("Giao thành công: 08/11/2026 10:00" in html, "detail: thời điểm giao thành công theo giờ VN")

    html = detail("PENDING_CONFIRM", Admin())
    ok(len(forms(html)) == 2, "detail: quản trị viên có đủ thao tác")
    ok(html.index("Nguyễn Văn An") > 0 and "Hệ thống" in html and "Quá hạn" in html, "detail: lịch sử, người thực hiện ('Hệ thống' khi không có người)")
    hist = html.split("Lịch sử trạng thái")[1]
    ok(hist.index("Quá hạn") < hist.index("Khách đặt hàng"), "detail: lịch sử mới nhất lên đầu")

print(f"OK: {ok.count} kiểm tra giao diện nhân viên đều đạt")
