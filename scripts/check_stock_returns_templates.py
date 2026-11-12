"""Render thật các template đổi trả, đánh giá, tồn kho, phiếu nhập bằng dữ liệu giả.
Chạy: python scripts/check_stock_returns_templates.py"""
import re
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace as NS

sys.path.insert(0, "scripts")
from _render_env import Checker, Customer, Pag, Staff, make_app, set_user

from flask import render_template

from app.constants import ReceiptStatus, ReturnStatus, StockTxType

app = make_app()
ok = Checker()
D = Decimal


class Admin(Staff):
    role_code = "ADMIN"

    def has_permission(self, code):
        return True


def forms(html, prefix):
    return [a for a in re.findall(r'<form method="post" action="([^"]+)"', html) if a.startswith(prefix)]


with app.test_request_context("/"):
    # ================================================================== khách: đổi trả, đánh giá
    set_user(app, Customer())
    variant = NS(product=NS(name="Áo Pro"), size=NS(name="M"), color=NS(name="Đen"))
    item = NS(id=11, variant=variant, quantity=3, unit_price=D(250000))
    order = NS(order_code="SZ261107AAAAAA", items=[item])
    html = render_template("account/return_form.html", order=order, form={"reason": "Lỗi <b>chỉ</b>", "quantities": {11: 2}},
                           deadline=datetime(2026, 11, 14, 12, 0))
    ok('action="/account/orders/SZ261107AAAAAA/return"' in html and 'name="qty_11" min="0" max="3" value="2"' in html, "return_form: số lượng và giới hạn")
    ok("14/11/2026" in html and "Áo Pro" in html and "250.000 ₫" in html, "return_form: hạn gửi, sản phẩm")
    ok("Lỗi &lt;b&gt;chỉ&lt;/b&gt;" in html and "<b>chỉ</b>" not in html, "return_form: giữ lý do đã nhập (đã escape)")
    ok(re.search(r'<textarea[^>]*required', html) and 'name="csrf_token"' in html, "return_form: lý do bắt buộc, CSRF")
    html = render_template("account/return_form.html", order=order, form={"reason": "", "quantities": {}}, deadline=datetime(2026, 11, 14))
    ok('name="qty_11" min="0" max="3" value="0"' in html, "return_form: mặc định 0")

    html = render_template("account/review_form.html", order=order, item=item, form={"rating": 4, "comment": "Tốt <i>lắm</i>"})
    ok(re.search(r'id="rating-4" value="4" checked', html) and not re.search(r'id="rating-5" value="5" checked', html), "review_form: giữ số sao đã chọn")
    ok(html.count('name="rating"') == 5 and "Tốt &lt;i&gt;lắm&lt;/i&gt;" in html and 'action="/account/orders/SZ261107AAAAAA/review/11"' in html, "review_form: 5 mức sao, escape nhận xét")

    # trang chi tiết đơn của khách: khối đổi trả và đánh giá
    def customer_detail(status, items, requests=(), return_blocker=None, can_review=True):
        base = dict(order_code="SZ261107AAAAAA", created_at=datetime(2026, 11, 6, 20, 0), status=status, items=items, status_history=[],
                    subtotal=D(500000), discount_amount=D(0), shipping_fee=D(0), total_amount=D(500000), promotion=None,
                    address=NS(recipient_name="A", phone="0912345678", full_address="1 Lê Lợi"), note=None, shipment=None,
                    latest_payment=None, payment_method=None, payment_status=None, return_requests=list(requests))
        return render_template("account/order_detail.html", order=NS(**base), can_cancel=False, deadline=None, online_enabled=False,
                               return_blocker=return_blocker, return_deadline=datetime(2026, 11, 14, 12, 0), can_review=can_review)
    plain = NS(id=1, variant=variant, quantity=2, unit_price=D(250000), line_total=D(500000), review=None)
    rated = NS(id=2, variant=variant, quantity=1, unit_price=D(250000), line_total=D(250000), review=NS(rating=4))
    html = customer_detail("COMPLETED", [plain, rated])
    ok('href="/account/orders/SZ261107AAAAAA/review/1"' in html and "Đánh giá sản phẩm</a>" in html and 'review/2' not in html and "Bạn đã đánh giá" in html,
       "detail: link đánh giá chỉ ở dòng chưa đánh giá")
    ok('href="/account/orders/SZ261107AAAAAA/return"' in html and "Hạn gửi yêu cầu: 14/11/2026" in html, "detail: nút đổi trả và hạn gửi khi được phép")
    html = customer_detail("COMPLETED", [plain], return_blocker="Đã quá thời hạn đổi trả (7 ngày kể từ khi nhận hàng).")
    ok("Đã quá thời hạn đổi trả" in html and 'href="/account/orders/SZ261107AAAAAA/return"' not in html, "detail: thông báo khi hết hạn đổi trả")
    req = NS(id=5, status="REJECTED", created_at=datetime(2026, 11, 8, 1, 0), reason="Lỗi chỉ", resolution="Sản phẩm đã sử dụng nhiều")
    html = customer_detail("COMPLETED", [plain], requests=[req])
    ok("Yêu cầu #5" in html and "text-bg-danger\">Từ chối" in html and "Sản phẩm đã sử dụng nhiều" in html and "Lý do: Lỗi chỉ" in html, "detail: lịch sử yêu cầu đổi trả và phản hồi")
    html = customer_detail("SHIPPING", [plain], can_review=False)
    ok("Đánh giá sản phẩm" not in html and "Yêu cầu đổi trả" not in html and "<h2 class=\"h6 mb-3\">Đổi trả</h2>" not in html, "detail: đang giao thì chưa có đổi trả/đánh giá")
    html = customer_detail("RETURNING", [plain], requests=[NS(id=6, status="APPROVED", created_at=datetime(2026, 11, 8), reason="x", resolution="Gửi hàng về")])
    ok("Đã chấp nhận" in html and "Yêu cầu đổi trả</a>" not in html, "detail: đang đổi trả không cho gửi thêm")

    # ================================================================== nhân viên: đổi trả
    set_user(app, Staff())
    req_items = [NS(id=21, quantity=2, accepted_quantity=None, order_item=NS(quantity=3, unit_price=D(250000), variant=NS(product=NS(name="Áo Pro"), sku="AO-M-DEN")))]
    order_obj = NS(order_code="SZ261107AAAAAA", status="COMPLETED", payment_status="PAID", account=NS(full_name="Nguyễn Văn An", email="kh@test.com", phone="0912345678"))

    def ret(status, **kw):
        base = dict(id=7, order=order_obj, status=status, reason="Lỗi đường may\nchỉ bung", resolution=None, created_at=datetime(2026, 11, 8, 1, 0),
                    resolved_at=None, handled_by=None, items=req_items)
        base.update(kw)
        return NS(**base)

    html = render_template("staff/return_detail.html", req=ret("PENDING"), suggested=D(500000), window_days=7)
    ok(forms(html, "/staff/returns/") == ["/staff/returns/7/approve", "/staff/returns/7/reject"], "return_detail PENDING: chấp nhận + từ chối")
    ok(re.search(r'name="reason"[^>]*required', html) and "Lỗi đường may" in html and "kh@test.com" in html and "7 ngày" in html, "return_detail: lý do từ chối bắt buộc, thông tin khách")
    html = render_template("staff/return_detail.html", req=ret("APPROVED"), suggested=D(500000), window_days=7)
    ok(forms(html, "/staff/returns/") == ["/staff/returns/7/complete"] and 'name="accepted_21" min="0" max="2" value="2"' in html, "return_detail APPROVED: nhập số lượng đạt")
    ok('placeholder="Gợi ý: 500.000 ₫"' in html and "chưa gồm phí vận chuyển" in html, "return_detail: gợi ý số tiền hoàn")
    unpaid = ret("APPROVED", order=NS(**dict(vars(order_obj), payment_status="UNPAID")))
    ok("đơn này hiện: Chưa thanh toán" in render_template("staff/return_detail.html", req=unpaid, suggested=D(0), window_days=7), "return_detail: cảnh báo đơn chưa thu tiền")
    done = ret("COMPLETED", resolution="Số lượng đạt: Áo Pro 1/2; Đã hoàn tiền 250.000 ₫", resolved_at=datetime(2026, 11, 9, 3, 0), handled_by=NS(full_name="Nhân Viên A"),
               items=[NS(**dict(vars(req_items[0]), accepted_quantity=1))])
    html = render_template("staff/return_detail.html", req=done, suggested=D(250000), window_days=7)
    ok(forms(html, "/staff/returns/") == [] and "Đã hoàn tiền 250.000 ₫" in html and "Nhân Viên A" in html and "09/11/2026 10:00" in html, "return_detail COMPLETED: không còn thao tác, kết quả xử lý")
    ok(re.search(r'<td class="text-end">1</td>\s*</tr>', html), "return_detail: hiện số lượng đạt")

    rows = [NS(id=7, order=order_obj, created_at=datetime(2026, 11, 8, 1, 0), status="PENDING", items=req_items)]
    html = render_template("staff/returns.html", pagination=Pag(rows, 1, 1, 1), requests=rows, status=None, counts={"PENDING": 1}, labels=ReturnStatus.LABELS,
                           list_url=lambda p: f"/staff/returns?page={p}")
    ok('href="/staff/returns/7"' in html and "Chờ xử lý (1)" in html and "Hoàn tất (" not in html and ">2</td>" in html, "returns: danh sách, tổng số lượng")
    ok("Không có yêu cầu đổi trả nào" in render_template("staff/returns.html", pagination=Pag([], 0, 1, 0), requests=[], status=None, counts={},
                                                          labels=ReturnStatus.LABELS, list_url=lambda p: "/"), "returns: rỗng")

    # ================================================================== nhân viên: tồn kho
    def var(i, name, stock, reserved, status="ACTIVE"):
        v = NS(id=i, product=NS(name=name), size=NS(name="M"), color=NS(name="Đen"), sku=f"SKU{i}", stock_quantity=stock, reserved_quantity=reserved, status=status)
        v.available_quantity = stock - reserved
        return v
    vs = [var(1, "Áo hết", 4, 4), var(2, "Áo sắp hết", 8, 3), var(3, "Áo đủ", 50, 0, "INACTIVE")]
    html = render_template("staff/stock.html", pagination=Pag(vs, 3, 1, 1), variants=vs, q="áo", low=True, threshold=5, list_url=lambda p: f"/staff/stock?page={p}")
    ok(re.search(r'text-bg-danger">0<', html) and re.search(r'text-bg-warning">5<', html) and re.search(r'text-bg-success">50<', html), "stock: màu theo mức khả dụng (hết, sắp hết, đủ)")
    ok('name="low" value="1" id="low" checked' in html and 'value="áo"' in html and "(&le; 5)" in html and "Ngừng kinh doanh" in html, "stock: giữ bộ lọc, ngưỡng, trạng thái")
    ok('href="/staff/stock/1"' in html, "stock: liên kết chi tiết")

    txs = [NS(created_at=datetime(2026, 11, 6, 20, 0), transaction_type="ISSUE", stock_delta=-2, reserved_delta=-2, note="Xuất kho", created_by=NS(full_name="Nhân Viên A")),
           NS(created_at=datetime(2026, 11, 6, 19, 0), transaction_type="RESERVE", stock_delta=0, reserved_delta=2, note=None, created_by=None),
           NS(created_at=datetime(2026, 11, 6, 18, 0), transaction_type="RECEIPT", stock_delta=10, reserved_delta=0, note="Nhập <b>kho</b>", created_by=NS(full_name="Nhân Viên A"))]
    v = var(1, "Áo Pro", 8, 0)
    set_user(app, Staff())
    html = render_template("staff/stock_detail.html", variant=v, transactions=txs, threshold=5, tx_labels=StockTxType.LABELS)
    ok("Xuất kho (bàn giao)" in html and "Giữ hàng" in html and "Nhập kho (phiếu nhập)" in html and ">-2<" in html and ">+10<" in html and ">+2<" in html, "stock_detail: nhãn loại giao dịch, dấu +/-")
    ok("Hệ thống" in html and "Nhập &lt;b&gt;kho&lt;/b&gt;" in html and forms(html, "/staff/stock/") == [], "stock_detail: người thực hiện, escape, nhân viên không có form điều chỉnh")
    set_user(app, Admin())
    html = render_template("staff/stock_detail.html", variant=v, transactions=[], threshold=5, tx_labels=StockTxType.LABELS)
    ok(forms(html, "/staff/stock/") == ["/staff/stock/1/adjust"] and re.search(r'name="reason"[^>]*required', html) and "Chưa có biến động nào" in html, "stock_detail: quản trị viên có form điều chỉnh, lý do bắt buộc")

    # ================================================================== nhân viên: phiếu nhập
    set_user(app, type("S", (Staff,), {"permissions": ("stock.view", "stock.receipt")})())
    recs = [NS(id=3, receipt_code="PN261107ABCD", supplier=NS(name="Nhà cung cấp A"), created_at=datetime(2026, 11, 6, 20, 0), items=[1, 2], created_by=NS(full_name="Nhân Viên A"), status="DRAFT")]
    html = render_template("staff/receipts.html", receipts=recs, pagination=Pag(recs, 1, 1, 1), status=None, labels=ReceiptStatus.LABELS, list_url=lambda p: "/")
    ok('href="/staff/receipts/3"' in html and "PN261107ABCD" in html and 'href="/staff/receipts/new"' in html and "text-bg-warning\">Nháp" in html, "receipts: danh sách, nút lập phiếu")
    set_user(app, type("V", (Staff,), {"permissions": ("stock.view",)})())
    ok('href="/staff/receipts/new"' not in render_template("staff/receipts.html", receipts=recs, pagination=Pag(recs, 1, 1, 1), status=None, labels=ReceiptStatus.LABELS,
                                                               list_url=lambda p: "/"), "receipts: ẩn nút lập phiếu khi không có quyền")

    set_user(app, Staff())
    rows = [{"sku": "AO-M-DEN", "qty": "7", "cost": "1.500"}] + [{"sku": "", "qty": "", "cost": ""}] * 2
    html = render_template("staff/receipt_form.html", suppliers=[NS(id=1, name="Nhà cung cấp A"), NS(id=2, name="NCC B")], rows=rows, supplier_id=2, note="Ghi <b>chú</b>")
    ok('<option value="2" selected>NCC B</option>' in html and 'value="AO-M-DEN"' in html and 'name="sku_3"' in html and 'name="cost_1"' in html, "receipt_form: giữ dữ liệu đã nhập, đánh số dòng")
    ok("Ghi &lt;b&gt;chú&lt;/b&gt;" in html and 'data-max-lines="50"' in html and "js/receipt.js" in html and 'id="add-line"' in html, "receipt_form: escape, nút thêm dòng")
    ok("Chưa có nhà cung cấp đang hoạt động" in render_template("staff/receipt_form.html", suppliers=[], rows=rows, supplier_id=None, note=""), "receipt_form: cảnh báo chưa có nhà cung cấp")

    def receipt(status, items_received=(0, 0), confirmed=None):
        items = [NS(id=31 + n, ordered_quantity=q, received_quantity=items_received[n], unit_cost=D(c), variant=NS(sku=f"SKU{n}", product=NS(name=f"Hàng {n}"), size=NS(name="M"), color=NS(name="Đen")))
                 for n, (q, c) in enumerate(((20, 120000), (5, 95000)))]
        return NS(id=3, receipt_code="PN261107ABCD", status=status, supplier=NS(name="Nhà cung cấp A"), created_at=datetime(2026, 11, 6, 20, 0),
                  created_by=NS(full_name="Nhân Viên A"), confirmed_at=confirmed, note="Nhập mùa đông", items=items,
                  total_cost=sum(i.received_quantity * i.unit_cost for i in items))
    html = render_template("staff/receipt_detail.html", receipt=receipt("DRAFT"))
    ok(forms(html, "/staff/receipts/") == ["/staff/receipts/3/confirm", "/staff/receipts/3/cancel"], "receipt_detail DRAFT: xác nhận + hủy")
    ok('name="received_31" min="0" value="20"' in html and 'name="received_32" min="0" value="5"' in html and "Giá trị nhập" not in html, "receipt_detail DRAFT: nhập thực nhận mặc định = đặt nhập")
    html = render_template("staff/receipt_detail.html", receipt=receipt("CONFIRMED", (18, 5), datetime(2026, 11, 7, 3, 0)))
    ok(forms(html, "/staff/receipts/") == [] and "received_" not in html and "nhập kho 07/11/2026 10:00" in html, "receipt_detail CONFIRMED: chỉ xem")
    ok("2.635.000 ₫" in html and "Đã nhập kho" in html, "receipt_detail: giá trị nhập = Σ thực nhận × đơn giá")
    ok(forms(render_template("staff/receipt_detail.html", receipt=receipt("CANCELLED")), "/staff/receipts/") == [], "receipt_detail CANCELLED: không còn thao tác")

    # ================================================================== menu, dashboard
    set_user(app, Staff())
    stats = {"counts": {}, "today": 0, "low_stock": 2, "low_stock_threshold": 5, "returns_pending": 3}
    from app.constants import OrderStatus
    html = render_template("staff/dashboard.html", stats=stats, labels=OrderStatus.LABELS, badges=OrderStatus.BADGES)
    ok('href="/staff/returns?status=PENDING"' in html and "text-bg-warning\">3" in html and 'href="/staff/stock?low=1"' in html, "dashboard: đổi trả chờ xử lý, liên kết tồn kho")
    ok(all(h in html for h in ('href="/staff/returns"', 'href="/staff/stock"', 'href="/staff/receipts"')), "nav: đủ quyền thì thấy Đổi trả, Tồn kho, Phiếu nhập")
    set_user(app, type("O", (Staff,), {"permissions": ("order.view",)})())
    nav = render_template("staff/dashboard.html", stats=stats, labels=OrderStatus.LABELS, badges=OrderStatus.BADGES)
    ok('href="/staff/returns"' not in nav and 'href="/staff/stock"' not in nav and 'href="/staff/receipts"' not in nav and 'href="/staff/orders"' in nav,
       "nav: ẩn các mục không có quyền")
    ok('href="/staff/returns?status=PENDING"' not in nav and 'href="/staff/stock?low=1"' not in nav, "dashboard: ẩn liên kết khi không có quyền")

print(f"OK: {ok.count} kiểm tra giao diện đổi trả/kho đều đạt")
