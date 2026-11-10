"""Kiểm thử khu vực nhân viên: phân quyền, danh sách/chi tiết đơn, xác nhận, đóng gói, bàn giao + xuất kho,
giao thành công, sự cố, hủy đơn (Task 8A)."""
from datetime import timedelta

import pytest

from app.constants import (ROLE_ADMIN, ROLE_STAFF, OrderStatus, PaymentStatus, Perm, StockTxType)
from app.extensions import db
from app.models import AuditLog, Carrier, Permission, Shipment, StockTransaction
from app.models.base import utcnow
from app.services import fulfillment_service as fs
from app.services import order_service, staff_service

from tests.helpers import VNPAY, make_variant, place, put_in_cart, refresh


@pytest.fixture()
def carrier(app):
    active, inactive = Carrier(name="GHN"), Carrier(name="Hãng cũ", is_active=False)
    db.session.add_all([active, inactive])
    db.session.commit()
    return active, inactive


def new_order(buyer, shop, qty=2, stock=10, price=250000, name="Áo A"):
    acc, addr = buyer
    v = make_variant(shop, name, price, stock)
    put_in_cart(acc, [(v, qty)])
    return place(acc, addr), v


def advance(order, actor, carrier, *steps):
    for step in steps:
        if step == "confirm":
            fs.confirm_order(order, actor)
        elif step == "pack":
            fs.start_packing(order, actor)
        elif step == "ship":
            fs.ship_order(order, actor, carrier.id, f"TRK{order.id:05d}")
        elif step == "deliver":
            fs.mark_delivered(order, actor)


def post(client, order, action, **data):
    return client.post(f"/staff/orders/{order.order_code}/{action}", data=data, follow_redirects=True).get_data(as_text=True)


def stock(v):
    db.session.refresh(v)
    return v.stock_quantity, v.reserved_quantity


# ================================================================== phân quyền
def test_staff_area_requires_staff_role(client, make_account, login):
    assert client.get("/staff/").status_code == 302 and "/auth/login" in client.get("/staff/").headers["Location"]
    make_account(email="kh@test.com")
    login("kh@test.com")
    for path in ("/staff/", "/staff/orders", "/staff/orders/SZ000000AAAAAA"):
        assert client.get(path).status_code == 403, path


def test_staff_without_permissions_sees_dashboard_but_not_orders(client, make_account, login):
    make_account(email="nv@test.com", role=ROLE_STAFF)                       # vai trò nhân viên chưa được cấp quyền nào
    login("nv@test.com")
    assert client.get("/staff/").status_code == 200
    assert client.get("/staff/orders").status_code == 403


def test_permissions_are_enforced_per_action(client, roles, make_account, login, shop, buyer, carrier):
    """Nhân viên chỉ có order.view + order.process: xác nhận được nhưng không được bàn giao vận chuyển."""
    perms = [Permission(code=Perm.ORDER_VIEW), Permission(code=Perm.ORDER_PROCESS)]
    db.session.add_all(perms)
    roles[ROLE_STAFF].permissions.extend(perms)
    db.session.commit()
    nv = make_account(email="nv@test.com", role=ROLE_STAFF)
    order, _ = new_order(buyer, shop)
    login("nv@test.com")
    assert "Đã xác nhận đơn hàng" in post(client, order, "confirm")
    post(client, order, "pack")
    resp = client.post(f"/staff/orders/{order.order_code}/ship", data=dict(carrier_id=carrier[0].id, tracking_code="TRK12345"))
    assert resp.status_code == 403
    assert client.post(f"/staff/orders/{order.order_code}/deliver").status_code == 403
    assert client.post(f"/staff/orders/{order.order_code}/incident", data=dict(note="x" * 10)).status_code == 403
    refresh(order)
    assert order.status == OrderStatus.PACKING and db.session.query(Shipment).count() == 0


def test_admin_has_all_staff_abilities(client, make_account, login, shop, buyer):
    make_account(email="ad@test.com", role=ROLE_ADMIN)
    login("ad@test.com")
    order, _ = new_order(buyer, shop)
    assert client.get("/staff/orders").status_code == 200
    assert "Đã xác nhận đơn hàng" in post(client, order, "confirm")


def test_login_redirects_staff_to_staff_area(client, staff_perms, make_account):
    make_account(email="nv@test.com", role=ROLE_STAFF)
    make_account(email="kh@test.com")
    nv = client.post("/auth/login", data=dict(email="nv@test.com", password="Matkhau123"))
    assert nv.headers["Location"].endswith("/staff/")
    client.post("/auth/logout")
    kh = client.post("/auth/login", data=dict(email="kh@test.com", password="Matkhau123"))
    assert kh.headers["Location"].endswith("/") and "/staff" not in kh.headers["Location"]


def test_navbar_staff_link_only_for_staff(client, staff, login, make_account):
    assert "Khu vực nhân viên" in client.get("/").get_data(as_text=True)
    client.post("/auth/logout")
    make_account(email="kh@test.com")
    login("kh@test.com")
    assert "Khu vực nhân viên" not in client.get("/").get_data(as_text=True)


# ================================================================== bảng điều khiển, danh sách, chi tiết
def test_dashboard_stats(client, staff, shop, buyer, buyer2, carrier):
    o1, _ = new_order(buyer, shop, name="A")
    o2, _ = new_order(buyer2, shop, name="B")
    advance(o2, staff, carrier[0], "confirm")
    make_variant(shop, "Sắp hết", stock=3)                                   # khả dụng 3 <= ngưỡng 5
    make_variant(shop, "Còn nhiều", stock=50)
    stats = staff_service.dashboard_stats()
    assert stats["counts"] == {OrderStatus.PENDING_CONFIRM: 1, OrderStatus.CONFIRMED: 1}
    assert stats["today"] == 2 and stats["low_stock"] >= 1
    body = client.get("/staff/").get_data(as_text=True)
    assert "Đơn hôm nay" in body and "Chờ xác nhận" in body and "biến thể sắp hết hàng" in body


def test_orders_list_shows_all_customers_and_filters(client, staff, shop, buyer, buyer2, carrier):
    o1, _ = new_order(buyer, shop, name="A")
    o2, _ = new_order(buyer2, shop, name="B")
    advance(o2, staff, carrier[0], "confirm")
    page = client.get("/staff/orders").get_data(as_text=True)
    assert o1.order_code in page and o2.order_code in page
    only_pending = client.get("/staff/orders?status=PENDING_CONFIRM").get_data(as_text=True)
    assert o1.order_code in only_pending and o2.order_code not in only_pending
    assert client.get("/staff/orders?status=HACK&page=abc").status_code == 200


def test_orders_search(client, staff, shop, buyer, buyer2):
    o1, _ = new_order(buyer, shop, name="A")
    o2, _ = new_order(buyer2, shop, name="B")
    buyer2[0].full_name = "Lê Thị Mai"
    db.session.commit()
    by_code = client.get(f"/staff/orders?q={o1.order_code.lower()}").get_data(as_text=True)       # không phân biệt hoa thường
    assert o1.order_code in by_code and o2.order_code not in by_code
    by_email = client.get("/staff/orders?q=buyer2@").get_data(as_text=True)
    assert o2.order_code in by_email and o1.order_code not in by_email
    assert o2.order_code in client.get("/staff/orders?q=Mai").get_data(as_text=True)
    assert o1.order_code in client.get("/staff/orders?q=0912345678").get_data(as_text=True)
    assert "Không có đơn hàng phù hợp" in client.get("/staff/orders?q=khong-co-ai").get_data(as_text=True)
    assert "Không có đơn hàng phù hợp" in client.get("/staff/orders?q=%25").get_data(as_text=True)   # '%' không phải ký tự đại diện


def test_orders_list_pagination(app, client, staff, shop, buyer):
    app.config["ADMIN_ITEMS_PER_PAGE"] = 2
    codes = [new_order(buyer, shop, qty=1, name=f"SP{i}")[0].order_code for i in range(3)]
    assert all(c in client.get("/staff/orders").get_data(as_text=True) for c in codes[1:])
    assert codes[0] in client.get("/staff/orders?page=2").get_data(as_text=True)
    assert client.get("/staff/orders?page=99").status_code == 302


def test_order_detail_for_staff(client, staff, shop, buyer, carrier):
    order, v = new_order(buyer, shop, qty=2, name="Áo Pro")
    body = client.get(f"/staff/orders/{order.order_code}").get_data(as_text=True)
    assert "Áo Pro" in body and "buyer@test.com" in body and "Người Nhận" in body and "1 Lê Lợi" in body
    assert f"SKU {v.sku}" in body and "tồn 10" in body and "đang giữ 2" in body and "khả dụng 8" in body
    assert "Xác nhận đơn" in body and "Hủy đơn" in body and "Khách đặt hàng" in body
    assert client.get("/staff/orders/SZ000000AAAAAA").status_code == 404


# ================================================================== xác nhận, đóng gói
def test_confirm_then_pack(client, staff, shop, buyer):
    order, _ = new_order(buyer, shop)
    assert "Đã xác nhận đơn hàng" in post(client, order, "confirm")
    refresh(order)
    assert order.status == OrderStatus.CONFIRMED
    last = order.status_history[-1]
    assert last.changed_by_account_id == staff.id and last.reason == "Nhân viên xác nhận đơn"
    assert "Bắt đầu đóng gói" in client.get(f"/staff/orders/{order.order_code}").get_data(as_text=True)
    assert "Đã chuyển đơn sang đóng gói" in post(client, order, "pack")
    refresh(order)
    assert order.status == OrderStatus.PACKING


def test_invalid_transitions_are_rejected(client, staff, shop, buyer):
    order, _ = new_order(buyer, shop)
    assert "Không thể chuyển" in post(client, order, "pack")                    # chưa xác nhận đã đóng gói
    post(client, order, "confirm")
    assert "Không thể chuyển" in post(client, order, "confirm")                 # xác nhận hai lần
    assert "Không thể chuyển" in post(client, order, "deliver")
    refresh(order)
    assert order.status == OrderStatus.CONFIRMED
    assert [h.to_status for h in order.status_history] == [OrderStatus.PENDING_CONFIRM, OrderStatus.CONFIRMED]


def test_cannot_process_unpaid_online_order(client, staff, shop, buyer):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr, VNPAY)
    page = client.get(f"/staff/orders/{order.order_code}").get_data(as_text=True)
    assert "Đơn đang chờ khách thanh toán online" in page and "Xác nhận đơn" not in page
    assert "Không thể chuyển" in post(client, order, "confirm")


# ================================================================== bàn giao vận chuyển + xuất kho
def test_ship_order_issues_stock(client, staff, shop, buyer, carrier):
    order, v = new_order(buyer, shop, qty=2, stock=10)
    advance(order, staff, carrier[0], "confirm", "pack")
    assert stock(v) == (10, 2)
    body = post(client, order, "ship", carrier_id=carrier[0].id, tracking_code="  GHN123456  ")
    assert "Đã bàn giao cho GHN, mã vận đơn GHN123456" in body and "Hàng đã được xuất kho" in body
    refresh(order)
    assert order.status == OrderStatus.SHIPPING
    assert (order.shipment.carrier.name, order.shipment.tracking_code, order.shipment.delivered_at) == ("GHN", "GHN123456", None)
    assert stock(v) == (8, 0)                                                   # trừ tồn kho và nhả lượng giữ
    tx = db.session.scalars(db.select(StockTransaction).where(
        StockTransaction.sales_order_id == order.id, StockTransaction.transaction_type == StockTxType.ISSUE)).one()
    assert (tx.stock_delta, tx.reserved_delta, tx.created_by_account_id) == (-2, -2, staff.id)
    assert "Bàn giao cho GHN" in order.status_history[-1].reason


@pytest.mark.parametrize("carrier_value,tracking,message", [
    ("", "GHN123456", "đơn vị vận chuyển hợp lệ"),
    ("INACTIVE", "GHN123456", "đơn vị vận chuyển hợp lệ"),
    ("999", "GHN123456", "đơn vị vận chuyển hợp lệ"),
    ("OK", "", "Mã vận đơn"),
    ("OK", "ab", "Mã vận đơn"),
    ("OK", "mã vận đơn!", "Mã vận đơn"),
    ("OK", "x" * 61, "Mã vận đơn"),
])
def test_ship_validates_input(client, staff, shop, buyer, carrier, carrier_value, tracking, message):
    order, v = new_order(buyer, shop)
    advance(order, staff, carrier[0], "confirm", "pack")
    cid = {"OK": carrier[0].id, "INACTIVE": carrier[1].id}.get(carrier_value, carrier_value)
    assert message in post(client, order, "ship", carrier_id=cid, tracking_code=tracking)
    refresh(order)
    assert order.status == OrderStatus.PACKING and db.session.query(Shipment).count() == 0 and stock(v) == (10, 2)


def test_ship_rejects_duplicate_tracking_code_per_carrier(client, staff, shop, buyer, buyer2, carrier):
    o1, v1 = new_order(buyer, shop, name="A")
    o2, v2 = new_order(buyer2, shop, name="B")
    for o in (o1, o2):
        advance(o, staff, carrier[0], "confirm", "pack")
    assert "Đã bàn giao" in post(client, o1, "ship", carrier_id=carrier[0].id, tracking_code="SAMECODE1")
    body = post(client, o2, "ship", carrier_id=carrier[0].id, tracking_code="SAMECODE1")
    assert "đã tồn tại với đơn vị vận chuyển GHN" in body
    refresh(o2)
    assert o2.status == OrderStatus.PACKING and stock(v2) == (10, 2)            # hoàn tác toàn bộ: chưa xuất kho


def test_ship_requires_packing_status(client, staff, shop, buyer, carrier):
    order, v = new_order(buyer, shop)
    advance(order, staff, carrier[0], "confirm")
    assert "Không thể chuyển" in post(client, order, "ship", carrier_id=carrier[0].id, tracking_code="GHN123456")
    assert db.session.query(Shipment).count() == 0 and stock(v) == (10, 2)


def test_double_ship_issues_stock_only_once(client, staff, shop, buyer, carrier):
    order, v = new_order(buyer, shop, qty=3, stock=10)
    advance(order, staff, carrier[0], "confirm", "pack")
    post(client, order, "ship", carrier_id=carrier[0].id, tracking_code="GHN111111")
    assert "Không thể chuyển" in post(client, order, "ship", carrier_id=carrier[0].id, tracking_code="GHN222222")
    assert stock(v) == (7, 0) and db.session.query(Shipment).count() == 1


def test_ship_rolls_back_when_stock_data_is_inconsistent(client, staff, shop, buyer, carrier):
    """Số liệu kho lệch (lượng giữ ít hơn số cần xuất): không được bàn giao dở dang."""
    order, v = new_order(buyer, shop, qty=2)
    advance(order, staff, carrier[0], "confirm", "pack")
    v.reserved_quantity = 0
    db.session.commit()
    body = post(client, order, "ship", carrier_id=carrier[0].id, tracking_code="GHN123456")
    assert "Số liệu kho không nhất quán" in body
    refresh(order)
    assert order.status == OrderStatus.PACKING and db.session.query(Shipment).count() == 0
    assert db.session.query(StockTransaction).filter_by(sales_order_id=order.id, transaction_type=StockTxType.ISSUE).count() == 0


# ================================================================== giao thành công, sự cố
def test_deliver_cod_order_collects_payment(client, staff, shop, buyer, carrier):
    order, _ = new_order(buyer, shop)
    advance(order, staff, carrier[0], "confirm", "pack", "ship")
    assert order.payment_status == PaymentStatus.UNPAID
    assert "Đã ghi nhận giao hàng thành công" in post(client, order, "deliver")
    refresh(order)
    assert order.status == OrderStatus.COMPLETED and order.shipment.delivered_at is not None
    assert order.payment_status == PaymentStatus.PAID and order.latest_payment.paid_at is not None     # COD: thu tiền khi giao xong
    assert order.status_history[-1].reason == "Giao hàng thành công"
    page = client.get(f"/staff/orders/{order.order_code}").get_data(as_text=True)
    assert "</i> Giao hàng thành công</button>" not in page and "trạng thái cuối" in page      # đã hoàn thành: hết nút thao tác


def test_deliver_online_paid_order_keeps_payment(client, staff, shop, buyer, carrier):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr, VNPAY)
    order_service.change_status(order, OrderStatus.PENDING_CONFIRM)
    order.payments[0].status = PaymentStatus.PAID
    order.payments[0].paid_at = utcnow() - timedelta(hours=1)
    db.session.commit()
    paid_at = order.payments[0].paid_at
    assert paid_at is not None
    advance(order, staff, carrier[0], "confirm", "pack", "ship", "deliver")
    refresh(order)
    assert order.status == OrderStatus.COMPLETED and order.payment_status == PaymentStatus.PAID
    assert order.latest_payment.paid_at == paid_at                              # không ghi đè thời điểm đã thanh toán online


def test_deliver_requires_shipping_status(client, staff, shop, buyer, carrier):
    order, _ = new_order(buyer, shop)
    advance(order, staff, carrier[0], "confirm", "pack")
    assert "Không thể chuyển" in post(client, order, "deliver")


def test_report_incident_keeps_status_and_is_logged(client, staff, shop, buyer, carrier):
    order, _ = new_order(buyer, shop)
    advance(order, staff, carrier[0], "confirm", "pack", "ship")
    assert "ít nhất 5 ký tự" in post(client, order, "incident", note="ok")
    assert "Đã ghi nhận sự cố giao hàng" in post(client, order, "incident", note="Khách không nghe máy, hẹn giao lại")
    refresh(order)
    assert order.status == OrderStatus.SHIPPING                                 # sự cố không đổi trạng thái đơn
    log = db.session.scalars(db.select(AuditLog).where(AuditLog.action == "shipment.incident")).one()
    assert log.account_id == staff.id and log.entity_id == order.id
    assert log.new_value == {"note": "Khách không nghe máy, hẹn giao lại", "tracking_code": order.shipment.tracking_code}
    page = client.get(f"/staff/orders/{order.order_code}").get_data(as_text=True)
    assert "Sự cố giao hàng" in page and "Khách không nghe máy, hẹn giao lại" in page


def test_incident_only_for_shipping_orders(client, staff, shop, buyer, carrier):
    order, _ = new_order(buyer, shop)
    assert "Chỉ ghi nhận sự cố cho đơn đang giao" in post(client, order, "incident", note="Khách không nghe máy")
    assert db.session.query(AuditLog).count() == 0


# ================================================================== hủy đơn bởi nhân viên
def test_staff_cancel_requires_reason_and_releases_stock(client, staff, shop, buyer, carrier):
    order, v = new_order(buyer, shop, qty=2)
    advance(order, staff, carrier[0], "confirm", "pack")
    assert "Vui lòng nhập lý do hủy đơn" in post(client, order, "cancel", reason="   ")
    assert stock(v) == (10, 2)
    assert "Đã hủy đơn hàng" in post(client, order, "cancel", reason="Hết hàng thực tế trong kho")
    refresh(order)
    assert order.status == OrderStatus.CANCELLED and stock(v) == (10, 0)
    assert order.status_history[-1].reason == "Hết hàng thực tế trong kho"
    log = db.session.scalars(db.select(AuditLog).where(AuditLog.action == "order.cancel")).one()
    assert log.account_id == staff.id


def test_staff_cannot_cancel_shipping_order(client, staff, shop, buyer, carrier):
    order, v = new_order(buyer, shop)
    advance(order, staff, carrier[0], "confirm", "pack", "ship")
    page = client.get(f"/staff/orders/{order.order_code}").get_data(as_text=True)
    assert "Hủy đơn (bắt buộc nhập lý do" not in page
    assert "không thể hủy" in post(client, order, "cancel", reason="Muốn hủy")


# ================================================================== vòng đời đầy đủ và phía khách hàng
def test_full_order_lifecycle_and_customer_view(client, staff, shop, buyer, carrier, login):
    order, v = new_order(buyer, shop, qty=2, stock=10)
    post(client, order, "confirm")
    post(client, order, "pack")
    post(client, order, "ship", carrier_id=carrier[0].id, tracking_code="GHN777888")
    post(client, order, "deliver")
    refresh(order)
    assert order.status == OrderStatus.COMPLETED and stock(v) == (8, 0)
    assert [h.to_status for h in order.status_history] == [
        OrderStatus.PENDING_CONFIRM, OrderStatus.CONFIRMED, OrderStatus.PACKING, OrderStatus.SHIPPING, OrderStatus.COMPLETED]
    # sổ kho: giữ hàng rồi xuất kho, tổng biến động khớp số dư
    txs = db.session.scalars(db.select(StockTransaction).where(StockTransaction.product_variant_id == v.id)).all()
    assert sum(t.stock_delta for t in txs) == -2 and sum(t.reserved_delta for t in txs) == 0

    client.post("/auth/logout")
    login("buyer@test.com")
    body = client.get(f"/account/orders/{order.order_code}").get_data(as_text=True)
    assert "Hoàn thành" in body and "GHN" in body and "GHN777888" in body and "Đã thanh toán" in body
    assert "Hủy đơn hàng</h2>" not in body
    assert client.get(f"/staff/orders/{order.order_code}").status_code == 403    # khách không vào được trang của nhân viên
