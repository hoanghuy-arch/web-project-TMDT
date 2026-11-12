"""Kiểm thử tồn kho, điều chỉnh thủ công và phiếu nhập (Task 8B)."""
import re

import pytest

from app.constants import (ROLE_ADMIN, ROLE_STAFF, EntityStatus, Perm, ReceiptStatus, StockTxType)
from app.extensions import db
from app.models import AuditLog, StockReceipt, StockTransaction, Supplier
from app.services.errors import CheckoutError
from tests.helpers import make_variant, put_in_cart, place, refresh


@pytest.fixture()
def suppliers(app):
    active, inactive = Supplier(name="Nhà cung cấp A", phone="0901234567"), Supplier(name="NCC cũ", phone="0907654321", status=EntityStatus.INACTIVE)
    db.session.add_all([active, inactive])
    db.session.commit()
    return active, inactive


def stock_of(v):
    db.session.refresh(v)
    return v.stock_quantity, v.reserved_quantity


def receipt_data(supplier, lines, note="Nhập hàng mùa đông"):
    data = {"supplier_id": supplier.id, "note": note}
    for i, (sku, qty, cost) in enumerate(lines, 1):
        data.update({f"sku_{i}": sku, f"qty_{i}": qty, f"cost_{i}": cost})
    return data


def audit_actions():
    return [a.action for a in db.session.scalars(db.select(AuditLog).order_by(AuditLog.id)).all()]


# ================================================================== phân quyền
def test_stock_area_permissions(client, staff, shop, login, make_account):
    v = make_variant(shop)
    assert client.get("/staff/stock").status_code == 200 and client.get(f"/staff/stock/{v.id}").status_code == 200
    # nhân viên mặc định KHÔNG có quyền điều chỉnh tồn kho thủ công (dành cho quản trị viên)
    assert client.post(f"/staff/stock/{v.id}/adjust", data={"delta": 5, "reason": "Kiểm kê"}).status_code == 403
    assert "Điều chỉnh tồn kho thủ công" not in client.get(f"/staff/stock/{v.id}").get_data(as_text=True)
    client.post("/auth/logout")
    make_account(email="ad@test.com", role=ROLE_ADMIN)
    login("ad@test.com")
    assert "Điều chỉnh tồn kho thủ công" in client.get(f"/staff/stock/{v.id}").get_data(as_text=True)
    assert client.post(f"/staff/stock/{v.id}/adjust", data={"delta": 5, "reason": "Kiểm kê định kỳ"}).status_code == 302


def test_customer_and_anonymous_blocked(client, make_account, login, shop):
    v = make_variant(shop)
    for path in ("/staff/stock", f"/staff/stock/{v.id}", "/staff/receipts", "/staff/receipts/new"):
        assert client.get(path).status_code == 302
    make_account(email="kh@test.com")
    login("kh@test.com")
    for path in ("/staff/stock", f"/staff/stock/{v.id}", "/staff/receipts", "/staff/receipts/new"):
        assert client.get(path).status_code == 403


# ================================================================== xem tồn kho
def test_stock_list_search_and_low_filter(client, staff, shop):
    ok = make_variant(shop, "Áo đủ hàng", stock=50)
    low = make_variant(shop, "Áo sắp hết", stock=3)
    zero = make_variant(shop, "Áo hết sạch", stock=4, reserved=4)
    hidden = make_variant(shop, "Áo ngừng bán thấp", stock=1)
    hidden.status = EntityStatus.INACTIVE
    db.session.commit()
    page = client.get("/staff/stock").get_data(as_text=True)
    assert all(n in page for n in ("Áo đủ hàng", "Áo sắp hết", "Áo hết sạch"))
    assert page.index("Áo hết sạch") < page.index("Áo sắp hết") < page.index("Áo đủ hàng")           # thiếu hàng nhất lên đầu
    only_low = client.get("/staff/stock?low=1").get_data(as_text=True)
    assert "Áo sắp hết" in only_low and "Áo hết sạch" in only_low
    assert "Áo đủ hàng" not in only_low and "Áo ngừng bán thấp" not in only_low                      # lọc bỏ biến thể ngừng kinh doanh
    assert "Áo đủ hàng" in client.get(f"/staff/stock?q={ok.sku}").get_data(as_text=True)               # tìm theo SKU
    by_name = client.get("/staff/stock?q=sắp hết").get_data(as_text=True)
    assert "Áo sắp hết" in by_name and "Áo đủ hàng" not in by_name
    assert "Không có biến thể nào phù hợp" in client.get("/staff/stock?q=%25").get_data(as_text=True)


def test_stock_list_pagination(app, client, staff, shop):
    app.config["ADMIN_ITEMS_PER_PAGE"] = 2
    for i in range(3):
        make_variant(shop, f"SP{i}", stock=10 + i)
    assert client.get("/staff/stock?page=2").status_code == 200
    assert client.get("/staff/stock?page=99").status_code == 302
    assert client.get("/staff/stock?page=abc&low=zzz").status_code == 200


def test_stock_detail_shows_history_with_labels(client, staff, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, "Áo Pro", stock=10)
    put_in_cart(acc, [(v, 2)])
    place(acc, addr)
    page = client.get(f"/staff/stock/{v.id}").get_data(as_text=True)
    assert "Áo Pro" in page and f"SKU {v.sku}" in page and "Giữ hàng" in page and "+2" in page
    assert client.get("/staff/stock/99999").status_code == 404


# ================================================================== điều chỉnh thủ công
@pytest.fixture()
def admin(make_account, login):
    acc = make_account(email="ad@test.com", role=ROLE_ADMIN, full_name="Quản Trị")
    login("ad@test.com")
    return acc


def adjust(client, v, delta, reason="Kiểm kê định kỳ"):
    return client.post(f"/staff/stock/{v.id}/adjust", data={"delta": delta, "reason": reason}, follow_redirects=True).get_data(as_text=True)


def test_adjust_stock_up_and_down_with_audit(client, admin, shop):
    v = make_variant(shop, stock=10)
    assert "Đã điều chỉnh tồn kho" in adjust(client, v, "+5", "Kiểm kê thấy dư 5 cái")
    assert stock_of(v) == (15, 0)
    assert "Đã điều chỉnh tồn kho" in adjust(client, v, "-3", "Hàng hỏng do ẩm")
    assert stock_of(v) == (12, 0)
    txs = db.session.scalars(db.select(StockTransaction).where(StockTransaction.transaction_type == StockTxType.ADJUST)
                             .order_by(StockTransaction.id)).all()
    assert [(t.stock_delta, t.reserved_delta, t.note, t.created_by_account_id) for t in txs] == [
        (5, 0, "Kiểm kê thấy dư 5 cái", admin.id), (-3, 0, "Hàng hỏng do ẩm", admin.id)]
    logs = db.session.scalars(db.select(AuditLog).where(AuditLog.action == "stock.adjust").order_by(AuditLog.id)).all()
    assert [(l.old_value, l.new_value["stock_quantity"], l.account_id) for l in logs] == [
        ({"stock_quantity": 10}, 15, admin.id), ({"stock_quantity": 15}, 12, admin.id)]
    assert "Hàng hỏng do ẩm" in client.get(f"/staff/stock/{v.id}").get_data(as_text=True)


@pytest.mark.parametrize("delta,reason,message", [
    ("0", "Kiểm kê định kỳ", "khác 0"), ("", "Kiểm kê định kỳ", "khác 0"), ("abc", "Kiểm kê định kỳ", "khác 0"),
    ("1000001", "Kiểm kê định kỳ", "khác 0"), ("5", "ngắn", "ít nhất 5 ký tự"), ("5", "   ", "ít nhất 5 ký tự")])
def test_adjust_validation(client, admin, shop, delta, reason, message):
    v = make_variant(shop, stock=10)
    assert message in adjust(client, v, delta, reason)
    assert stock_of(v) == (10, 0) and db.session.query(AuditLog).count() == 0


def test_cannot_adjust_below_reserved_or_zero(client, admin, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, stock=5)
    put_in_cart(acc, [(v, 3)])
    place(acc, addr)                                                              # giữ 3 cái cho đơn chưa bàn giao
    assert stock_of(v) == (5, 3)
    assert "thấp hơn số lượng đang được giữ" in adjust(client, v, "-3", "Kiểm kê thấy thiếu")   # 5-3=2 < 3
    assert "Đã điều chỉnh tồn kho" in adjust(client, v, "-2", "Kiểm kê thấy thiếu 2")           # 5-2=3 = số đang giữ
    assert stock_of(v) == (3, 3)
    assert "thấp hơn số lượng đang được giữ" in adjust(client, v, "-1", "Thêm nữa")
    assert stock_of(v) == (3, 3)
    assert audit_actions() == ["stock.adjust"]                                    # lần bị từ chối không để lại nhật ký


def test_adjust_unknown_variant_404(client, admin):
    assert client.post("/staff/stock/99999/adjust", data={"delta": 1, "reason": "Kiểm kê định kỳ"}).status_code == 404


# ================================================================== lập phiếu nhập
def test_create_receipt(client, staff, shop, suppliers):
    v1, v2 = make_variant(shop, "Áo A", stock=0), make_variant(shop, "Áo B", stock=2)
    resp = client.post("/staff/receipts/new", data=receipt_data(suppliers[0], [(v1.sku.lower(), 20, "120.000"), (v2.sku, 5, "95000")]))
    receipt = db.session.scalar(db.select(StockReceipt))
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/staff/receipts/{receipt.id}")
    assert re.fullmatch(r"PN\d{6}[A-Z2-9]{4}", receipt.receipt_code)
    assert (receipt.status, receipt.supplier_id, receipt.created_by_account_id, receipt.note) == (
        ReceiptStatus.DRAFT, suppliers[0].id, staff.id, "Nhập hàng mùa đông")
    assert sorted((i.variant.sku, i.ordered_quantity, i.received_quantity, i.unit_cost) for i in receipt.items) == sorted(
        [(v1.sku, 20, 0, 120000), (v2.sku, 5, 0, 95000)])                          # SKU không phân biệt hoa/thường
    assert stock_of(v1) == (0, 0) and stock_of(v2) == (2, 0)                      # nháp chưa ảnh hưởng tồn kho
    body = client.get(f"/staff/receipts/{receipt.id}").get_data(as_text=True)
    assert receipt.receipt_code in body and "Nhà cung cấp A" in body and "Xác nhận nhập kho" in body
    assert receipt.receipt_code in client.get("/staff/receipts").get_data(as_text=True)


@pytest.mark.parametrize("supplier,lines,message", [
    ("none", [("SKU", 1, 1000)], "nhà cung cấp hợp lệ"),
    ("inactive", [("SKU", 1, 1000)], "nhà cung cấp hợp lệ"),
    ("ok", [], "ít nhất một dòng hàng"),
    ("ok", [("KHONGCO", 1, 1000)], "Không tìm thấy mã SKU"),
    ("ok", [("SKU", 0, 1000)], "phải từ 1 đến"),
    ("ok", [("SKU", "", 1000)], "phải từ 1 đến"),
    ("ok", [("SKU", 1, "")], "Đơn giá nhập"),
    ("ok", [("SKU", 1, "abc")], "Đơn giá nhập"),
])
def test_create_receipt_validation(client, staff, shop, suppliers, supplier, lines, message):
    v = make_variant(shop)
    lines = [(v.sku if sku == "SKU" else sku, qty, cost) for sku, qty, cost in lines]
    sup = {"none": None, "inactive": suppliers[1], "ok": suppliers[0]}[supplier]
    data = receipt_data(sup, lines) if sup else {"note": "x", **receipt_data(suppliers[0], lines)}
    if sup is None:
        data.pop("supplier_id")
    resp = client.post("/staff/receipts/new", data=data)
    assert resp.status_code == 200 and message in resp.get_data(as_text=True)
    assert db.session.query(StockReceipt).count() == 0


def test_create_receipt_rejects_duplicate_sku(client, staff, shop, suppliers):
    v = make_variant(shop)
    resp = client.post("/staff/receipts/new", data=receipt_data(suppliers[0], [(v.sku, 1, 1000), (v.sku.lower(), 2, 1000)]))
    assert "bị lặp trong phiếu nhập" in resp.get_data(as_text=True) and db.session.query(StockReceipt).count() == 0


def test_receipt_form_keeps_input_on_error(client, staff, shop, suppliers):
    resp = client.post("/staff/receipts/new", data=receipt_data(suppliers[0], [("KHONGCO", 7, "1.500")], note="Ghi chú giữ lại"))
    body = resp.get_data(as_text=True)
    assert 'value="KHONGCO"' in body and 'value="7"' in body and "Ghi chú giữ lại" in body and f'value="{suppliers[0].id}" selected' in body


def test_receipt_form_page(client, staff, suppliers):
    body = client.get("/staff/receipts/new").get_data(as_text=True)
    assert "Nhà cung cấp A" in body and "NCC cũ" not in body and body.count('name="sku_') == 3 and "js/receipt.js" in body


def test_create_receipt_requires_permission(client, roles, staff_perms, make_account, login, suppliers):
    roles[ROLE_STAFF].permissions = [p for p in roles[ROLE_STAFF].permissions if p.code != Perm.STOCK_RECEIPT]
    db.session.commit()
    make_account(email="nv@test.com", role=ROLE_STAFF)
    login("nv@test.com")
    assert client.get("/staff/receipts").status_code == 200                       # vẫn xem được
    assert client.get("/staff/receipts/new").status_code == 403
    assert client.post("/staff/receipts/new", data={}).status_code == 403
    assert "Lập phiếu nhập" not in client.get("/staff/receipts").get_data(as_text=True)


# ================================================================== xác nhận nhập kho
def make_receipt(client, suppliers, shop, items=((20, 120000), (5, 95000)), stocks=(0, 2)):
    variants = [make_variant(shop, f"Hàng {i}", stock=s) for i, s in enumerate(stocks)]
    lines = [(v.sku, qty, cost) for v, (qty, cost) in zip(variants, items)]
    client.post("/staff/receipts/new", data=receipt_data(suppliers[0], lines))
    return db.session.scalar(db.select(StockReceipt)), variants


def confirm(client, receipt, received, follow=True):
    data = {f"received_{i.id}": received[n] for n, i in enumerate(receipt.items)}
    return client.post(f"/staff/receipts/{receipt.id}/confirm", data=data, follow_redirects=follow).get_data(as_text=True)


def test_confirm_receipt_adds_only_received_quantity(client, staff, shop, suppliers):
    receipt, (v1, v2) = make_receipt(client, suppliers, shop)
    body = confirm(client, receipt, [18, 5])                                    # nhận 18/20 và 5/5
    assert "Đã xác nhận nhập kho" in body
    refresh(receipt)
    assert receipt.status == ReceiptStatus.CONFIRMED and receipt.confirmed_at is not None
    got = {i.variant.sku: i.received_quantity for i in receipt.items}
    assert got == {v1.sku: 18, v2.sku: 5}
    assert stock_of(v1) == (18, 0) and stock_of(v2) == (7, 0)                      # chỉ cộng số lượng THỰC NHẬN
    txs = db.session.scalars(db.select(StockTransaction).where(StockTransaction.transaction_type == StockTxType.RECEIPT)).all()
    assert sorted((t.stock_delta, t.reserved_delta, t.created_by_account_id) for t in txs) == [(5, 0, staff.id), (18, 0, staff.id)]
    assert all(t.stock_receipt_item_id is not None and t.sales_order_id is None and t.return_item_id is None for t in txs)
    assert receipt.total_cost == 18 * 120000 + 5 * 95000
    assert audit_actions() == ["stock.receipt_confirm"]
    page = client.get(f"/staff/receipts/{receipt.id}").get_data(as_text=True)
    assert "Đã nhập kho" in page and "Xác nhận nhập kho" not in page and "Giá trị nhập" in page


def test_confirm_receipt_validation(client, staff, shop, suppliers):
    receipt, (v1, v2) = make_receipt(client, suppliers, shop)
    assert "Chưa có số lượng thực nhận nào" in confirm(client, receipt, [0, 0])
    body = client.post(f"/staff/receipts/{receipt.id}/confirm", data={f"received_{receipt.items[0].id}": "5"}, follow_redirects=True).get_data(as_text=True)
    assert "không hợp lệ" in body                                                  # thiếu số lượng của dòng còn lại
    assert "không hợp lệ" in client.post(f"/staff/receipts/{receipt.id}/confirm", data={f"received_{i.id}": "-1" for i in receipt.items},
                                         follow_redirects=True).get_data(as_text=True)
    refresh(receipt)
    assert receipt.status == ReceiptStatus.DRAFT and stock_of(v1) == (0, 0) and stock_of(v2) == (2, 0)
    assert db.session.query(StockTransaction).filter_by(transaction_type=StockTxType.RECEIPT).count() == 0


def test_confirm_receipt_twice_adds_stock_once(client, staff, shop, suppliers):
    receipt, (v1, v2) = make_receipt(client, suppliers, shop)
    confirm(client, receipt, [10, 5])
    assert "đã được xử lý" in confirm(client, receipt, [10, 5])
    assert stock_of(v1) == (10, 0) and stock_of(v2) == (7, 0)
    assert db.session.query(StockTransaction).filter_by(transaction_type=StockTxType.RECEIPT).count() == 2


def test_confirm_receipt_rolls_back_on_failure(client, staff, shop, suppliers, monkeypatch):
    from app.services import inventory_service
    receipt, (v1, v2) = make_receipt(client, suppliers, shop)
    real = inventory_service.receive_receipt_item
    calls = []

    def flaky(item, qty, actor):
        calls.append(item.id)
        if len(calls) == 2:
            raise RuntimeError("lỗi giữa chừng")
        return real(item, qty, actor)
    monkeypatch.setattr(inventory_service, "receive_receipt_item", flaky)
    with pytest.raises(RuntimeError):
        confirm(client, receipt, [10, 5])
    monkeypatch.undo()
    refresh(receipt)
    assert receipt.status == ReceiptStatus.DRAFT and receipt.confirmed_at is None            # hoàn tác toàn bộ, kể cả dòng đã cộng
    assert stock_of(v1) == (0, 0) and stock_of(v2) == (2, 0)
    assert all(i.received_quantity == 0 for i in receipt.items)


def test_cancel_receipt(client, staff, shop, suppliers):
    receipt, (v1, v2) = make_receipt(client, suppliers, shop)
    body = client.post(f"/staff/receipts/{receipt.id}/cancel", follow_redirects=True).get_data(as_text=True)
    assert "Đã hủy phiếu nhập" in body
    refresh(receipt)
    assert receipt.status == ReceiptStatus.CANCELLED and stock_of(v1) == (0, 0)
    assert "đã được xử lý" in confirm(client, receipt, [10, 5])                    # đã hủy thì không nhập kho được nữa
    assert "Chỉ hủy được phiếu nhập" in client.post(f"/staff/receipts/{receipt.id}/cancel", follow_redirects=True).get_data(as_text=True)
    assert stock_of(v1) == (0, 0) and audit_actions() == ["stock.receipt_cancel"]


def test_cannot_cancel_confirmed_receipt(client, staff, shop, suppliers):
    receipt, (v1, _) = make_receipt(client, suppliers, shop)
    confirm(client, receipt, [10, 5])
    assert "Chỉ hủy được phiếu nhập" in client.post(f"/staff/receipts/{receipt.id}/cancel", follow_redirects=True).get_data(as_text=True)
    refresh(receipt)
    assert receipt.status == ReceiptStatus.CONFIRMED and stock_of(v1) == (10, 0)


def test_receipt_list_filter_and_unknown(client, staff, shop, suppliers):
    receipt, _ = make_receipt(client, suppliers, shop)
    assert receipt.receipt_code in client.get("/staff/receipts?status=DRAFT").get_data(as_text=True)
    assert receipt.receipt_code not in client.get("/staff/receipts?status=CONFIRMED").get_data(as_text=True)
    assert client.get("/staff/receipts?status=HACK&page=abc").status_code == 200
    assert client.get("/staff/receipts/99999").status_code == 404


def test_received_stock_becomes_available_to_customers(client, staff, shop, suppliers, buyer):
    """Nhập kho xong thì khách đặt được số hàng mới (kết nối nhập kho với bán hàng)."""
    acc, addr = buyer
    receipt, (v1, _) = make_receipt(client, suppliers, shop, stocks=(0, 0))
    put_in_cart(acc, [(v1, 1)])
    with pytest.raises(CheckoutError):
        place(acc, addr)                                                          # chưa có hàng: không đặt được
    confirm(client, receipt, [10, 5])
    order = place(acc, addr)
    assert order.total_quantity == 1 and stock_of(v1) == (10, 1)
