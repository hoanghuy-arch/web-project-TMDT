"""Kiểm thử đặt hàng: tạo đơn, giữ hàng, khuyến mãi, phí vận chuyển, hủy đơn, hết hạn thanh toán (Task 6)."""
from datetime import timedelta

import pytest

from app.constants import (ROLE_STAFF, DiscountType, EntityStatus, OrderStatus, PaymentMethod, PaymentStatus,
                           SettingKey, StockTxType)
from app.extensions import db, mail
from app.models import (Address, AppSetting, AuditLog, CartItem, Payment, ProductVariant, Promotion, Province,
                        SalesOrder, SalesOrderStatusHistory, ShippingFeeRule, StockTransaction, Ward)
from app.models.base import utcnow
from app.services import cart_service, order_service
from app.services.errors import CheckoutError, OrderStateError, PromotionError, StockShortageError

from tests.helpers import (COD, VNPAY, make_promo, make_variant, new_buyer as _new_buyer, place,
                           put_in_cart, refresh)


# ================================================================== tạo đơn
def test_place_cod_order(app, shop, buyer):
    acc, addr = buyer
    v1 = make_variant(shop, "Áo A", 250000, stock=10)
    v2 = make_variant(shop, "Quần B", 150000, stock=5, reserved=1)
    put_in_cart(acc, [(v1, 2), (v2, 1)])
    with mail.record_messages() as outbox:
        order = place(acc, addr, note="  Giao giờ hành chính  ")

    assert order.status == OrderStatus.PENDING_CONFIRM
    assert order.order_code.startswith("SZ") and len(order.order_code) == 14
    assert (order.subtotal, order.discount_amount, order.shipping_fee, order.total_amount) == (650000, 0, 0, 650000)
    assert order.note == "Giao giờ hành chính" and order.address_id == addr.id
    assert {i.product_variant_id: (i.quantity, i.unit_price) for i in order.items} == {v1.id: (2, 250000), v2.id: (1, 150000)}

    refresh(v1, v2)
    assert (v1.reserved_quantity, v1.stock_quantity) == (2, 10) and (v2.reserved_quantity, v2.stock_quantity) == (2, 5)
    txs = db.session.scalars(db.select(StockTransaction).where(StockTransaction.sales_order_id == order.id)).all()
    assert sorted((t.product_variant_id, t.transaction_type, t.reserved_delta, t.stock_delta) for t in txs) == \
        sorted([(v1.id, StockTxType.RESERVE, 2, 0), (v2.id, StockTxType.RESERVE, 1, 0)])

    (hist,) = order.status_history
    assert hist.to_status == OrderStatus.PENDING_CONFIRM and hist.changed_by_account_id == acc.id
    (pay,) = order.payments
    assert (pay.method, pay.status, pay.amount, pay.gateway_txn_ref) == (COD, PaymentStatus.UNPAID, 650000, None)
    assert db.session.query(CartItem).filter_by(account_id=acc.id).count() == 0           # giỏ đã được xóa
    assert len(outbox) == 1 and order.order_code in outbox[0].subject and outbox[0].recipients == ["buyer@test.com"]


def test_order_codes_are_unique(app, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, stock=50)
    codes = set()
    for _ in range(5):
        put_in_cart(acc, [(v, 1)])
        codes.add(place(acc, addr).order_code)
    assert len(codes) == 5


def test_shipping_fee_by_province_and_threshold(app, shop, buyer, make_account, geo):
    acc, addr = buyer
    v = make_variant(shop, price=250000, stock=50)
    put_in_cart(acc, [(v, 1)])                                                     # 250.000 < ngưỡng 500.000
    assert place(acc, addr).shipping_fee == 30000                                  # mức mặc định
    put_in_cart(acc, [(v, 2)])                                                     # 500.000 = ngưỡng
    assert place(acc, addr).shipping_fee == 0                                      # miễn phí
    hn_acc, hn_addr = _new_buyer(make_account, geo["w2"], "hn@test.com")
    put_in_cart(hn_acc, [(v, 4)])                                                  # 1.000.000, Hà Nội không có ngưỡng
    order = place(hn_acc, hn_addr)
    assert order.shipping_fee == 45000 and order.total_amount == 1045000


def test_no_shipping_rule_means_zero_fee(app, shop, make_account, geo):
    acc, addr = _new_buyer(make_account, geo["w1"], "norule@test.com")             # không dùng fixture rules
    put_in_cart(acc, [(make_variant(shop), 1)])
    assert place(acc, addr).shipping_fee == 0


def test_online_order_waits_for_payment(app, shop, buyer):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    with mail.record_messages() as outbox:
        order = place(acc, addr, VNPAY)
    assert order.status == OrderStatus.PENDING_PAYMENT
    (pay,) = order.payments
    assert (pay.method, pay.status) == (VNPAY, PaymentStatus.PENDING) and pay.gateway_txn_ref.startswith(order.order_code)
    assert pay.amount == order.total_amount
    assert outbox == []                                                            # đơn online gửi email sau khi thanh toán xong


def test_unit_price_is_snapshot(app, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, price=250000)
    put_in_cart(acc, [(v, 2)])
    order = place(acc, addr)
    v.product.price = 999000
    db.session.commit()
    refresh(order)
    assert order.items[0].unit_price == 250000 and order.subtotal == 500000       # BR05: giá không đổi theo sản phẩm


# ------------------------------------------------------------------ kiểm tra đầu vào
def test_place_order_rejects_bad_input(app, shop, buyer, buyer2):
    acc, addr = buyer
    _, other_addr = buyer2
    with pytest.raises(CheckoutError, match="trống"):
        place(acc, addr)
    put_in_cart(acc, [(make_variant(shop), 1)])
    with pytest.raises(CheckoutError, match="Phương thức thanh toán"):
        place(acc, addr, "BITCOIN")
    with pytest.raises(CheckoutError, match="địa chỉ nhận hàng"):
        place(acc, other_addr)                                                     # địa chỉ của người khác
    with pytest.raises(CheckoutError, match="địa chỉ nhận hàng"):
        order_service.place_order(acc, None, "", COD)
    addr.is_active = False
    db.session.commit()
    with pytest.raises(CheckoutError, match="địa chỉ nhận hàng"):
        place(acc, addr)                                                           # địa chỉ đã xóa
    assert db.session.query(SalesOrder).count() == 0


def test_place_order_rejects_cart_with_issues(app, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, stock=5)
    put_in_cart(acc, [(v, 4)])
    v.stock_quantity = 2                                                           # tồn giảm sau khi bỏ vào giỏ
    db.session.commit()
    with pytest.raises(CheckoutError, match="không thể đặt"):
        place(acc, addr)
    assert db.session.query(SalesOrder).count() == 0 and v.reserved_quantity == 0


# ================================================================== chống bán vượt
def test_race_for_last_items_only_one_wins(app, shop, buyer, buyer2, monkeypatch):
    """Hai khách cùng thấy còn hàng rồi đặt. Giỏ của khách 2 được "đóng băng" ở thời điểm trước khi khách 1 đặt để
    mô phỏng cửa sổ chạy đua; chốt chặn là câu UPDATE có điều kiện khi giữ hàng."""
    acc1, addr1 = buyer
    acc2, addr2 = buyer2
    v = make_variant(shop, stock=5)
    put_in_cart(acc1, [(v, 3)])
    put_in_cart(acc2, [(v, 3)])
    stale_cart = cart_service.get_cart(acc2)                                       # khách 2 thấy khả dụng 5

    place(acc1, addr1)
    refresh(v)
    assert v.reserved_quantity == 3

    monkeypatch.setattr(cart_service, "get_cart", lambda account: stale_cart)
    with pytest.raises(StockShortageError, match="chỉ còn 2"):
        place(acc2, addr2)

    monkeypatch.undo()
    refresh(v)
    assert v.reserved_quantity == 3 and v.available_quantity == 2                  # không bán vượt
    assert db.session.query(SalesOrder).filter_by(account_id=acc2.id).count() == 0
    assert db.session.query(CartItem).filter_by(account_id=acc2.id).count() == 1   # giỏ khách 2 còn nguyên


def test_failed_line_rolls_back_earlier_reservations(app, shop, buyer, buyer2, monkeypatch):
    acc1, addr1 = buyer
    acc2, addr2 = buyer2
    ok_variant = make_variant(shop, "Đủ hàng", stock=10)
    scarce = make_variant(shop, "Khan hiếm", stock=2)
    assert ok_variant.id < scarce.id                                               # dòng đủ hàng được giữ trước
    put_in_cart(acc1, [(scarce, 2)])
    put_in_cart(acc2, [(ok_variant, 4), (scarce, 2)])
    stale_cart = cart_service.get_cart(acc2)
    place(acc1, addr1)                                                             # lấy hết hàng khan hiếm

    monkeypatch.setattr(cart_service, "get_cart", lambda account: stale_cart)
    with pytest.raises(StockShortageError):
        place(acc2, addr2)
    monkeypatch.undo()

    refresh(ok_variant, scarce)
    assert ok_variant.reserved_quantity == 0                                       # lần giữ hàng đầu đã được hoàn tác
    assert scarce.reserved_quantity == 2
    assert db.session.query(StockTransaction).filter_by(product_variant_id=ok_variant.id).count() == 0
    assert db.session.query(SalesOrder).filter_by(account_id=acc2.id).count() == 0


# ================================================================== khuyến mãi
def test_percent_promotion_with_cap(app, shop, buyer):
    acc, addr = buyer
    promo = make_promo("SAVE10", value=10, max_discount=20000)
    put_in_cart(acc, [(make_variant(shop, price=250000), 1)])
    order = place(acc, addr, promo=" save10 ")                                     # không phân biệt hoa thường, bỏ khoảng trắng
    assert order.discount_amount == 20000 and order.promotion_id == promo.id       # 10% = 25.000 nhưng trần 20.000
    assert order.total_amount == 250000 - 20000 + 30000


def test_fixed_promotion_never_exceeds_subtotal(app, shop, buyer):
    acc, addr = buyer
    make_promo("BIG", DiscountType.FIXED, 999999)
    put_in_cart(acc, [(make_variant(shop, price=100000), 1)])
    order = place(acc, addr, promo="BIG")
    assert order.discount_amount == 100000 and order.total_amount == 30000         # chỉ còn phí vận chuyển


@pytest.mark.parametrize("kwargs,code,message", [
    ({}, "KHONGCO", "không tồn tại"),
    (dict(status=EntityStatus.INACTIVE), "SAVE10", "ngừng áp dụng"),
    (dict(start=2, end=10), "SAVE10", "chưa đến thời gian"),
    (dict(start=-10, end=-1), "SAVE10", "đã hết hạn"),
    (dict(min_order=300000), "SAVE10", "tối thiểu 300.000"),
])
def test_invalid_promotions_block_order(app, shop, buyer, kwargs, code, message):
    acc, addr = buyer
    make_promo("SAVE10", **kwargs)
    put_in_cart(acc, [(make_variant(shop, price=250000), 1)])
    with pytest.raises(PromotionError, match=message):
        place(acc, addr, promo=code)
    assert db.session.query(SalesOrder).count() == 0                               # không âm thầm bỏ mã rồi vẫn tạo đơn


def test_promotion_usage_limit_and_release_on_cancel(app, shop, buyer, buyer2):
    acc1, addr1 = buyer
    acc2, addr2 = buyer2
    make_promo("ONCE", limit=1)
    v = make_variant(shop, stock=20)
    put_in_cart(acc1, [(v, 1)])
    first = place(acc1, addr1, promo="ONCE")
    put_in_cart(acc2, [(v, 1)])
    with pytest.raises(PromotionError, match="hết lượt sử dụng"):
        place(acc2, addr2, promo="ONCE")
    order_service.cancel_order(first, acc1)                                        # hủy đơn thì trả lại lượt dùng
    assert place(acc2, addr2, promo="ONCE").promotion_id is not None


def test_checkout_preview_reports_promo_error_without_raising(app, shop, buyer):
    acc, addr = buyer
    make_promo("SAVE10", min_order=900000)
    put_in_cart(acc, [(make_variant(shop, price=250000), 1)])
    s = order_service.build_checkout(acc, addr.id, "save10")
    assert s.promo_error and "tối thiểu" in s.promo_error and s.discount == 0 and s.promotion is None
    assert (s.subtotal, s.shipping_fee, s.total) == (250000, 30000, 280000)
    s = order_service.build_checkout(acc, None, "")
    assert s.address.id == addr.id                                                 # mặc định chọn địa chỉ mặc định


# ================================================================== hủy đơn
def _stock(v):
    db.session.refresh(v)
    return v.stock_quantity, v.reserved_quantity


def test_customer_cancel_releases_stock(app, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, stock=10)
    put_in_cart(acc, [(v, 3)])
    order = place(acc, addr)
    assert _stock(v) == (10, 3)
    order_service.cancel_order(order, acc, "Đổi ý")
    assert order.status == OrderStatus.CANCELLED and _stock(v) == (10, 0)
    assert [h.to_status for h in order.status_history] == [OrderStatus.PENDING_CONFIRM, OrderStatus.CANCELLED]
    assert order.status_history[-1].reason == "Đổi ý" and order.status_history[-1].changed_by_account_id == acc.id
    rel = db.session.scalars(db.select(StockTransaction).where(
        StockTransaction.sales_order_id == order.id, StockTransaction.transaction_type == StockTxType.RELEASE)).one()
    assert rel.reserved_delta == -3 and rel.stock_delta == 0
    assert order.payment_status == PaymentStatus.UNPAID                            # COD chưa thu tiền: giữ nguyên
    assert db.session.query(AuditLog).count() == 0                                 # hành động của khách không cần nhật ký nhạy cảm


def test_customer_cancel_default_reason(app, shop, buyer):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = order_service.cancel_order(place(acc, addr), acc)
    assert order.status_history[-1].reason == "Khách hàng hủy đơn"


@pytest.mark.parametrize("status,allowed", [
    (OrderStatus.PENDING_CONFIRM, True), (OrderStatus.CONFIRMED, True),
    (OrderStatus.PACKING, False), (OrderStatus.SHIPPING, False), (OrderStatus.COMPLETED, False)])
def test_customer_cancel_by_status(app, shop, buyer, status, allowed):
    acc, addr = buyer
    v = make_variant(shop, stock=10)
    put_in_cart(acc, [(v, 2)])
    order = place(acc, addr)
    path = {OrderStatus.CONFIRMED: [OrderStatus.CONFIRMED],
            OrderStatus.PACKING: [OrderStatus.CONFIRMED, OrderStatus.PACKING],
            OrderStatus.SHIPPING: [OrderStatus.CONFIRMED, OrderStatus.PACKING, OrderStatus.SHIPPING],
            OrderStatus.COMPLETED: [OrderStatus.CONFIRMED, OrderStatus.PACKING, OrderStatus.SHIPPING, OrderStatus.COMPLETED],
            OrderStatus.PENDING_CONFIRM: []}[status]
    for step in path:
        order_service.change_status(order, step)
    db.session.commit()
    if allowed:
        order_service.cancel_order(order, acc)
        assert order.status == OrderStatus.CANCELLED and _stock(v) == (10, 0)
    else:
        with pytest.raises(OrderStateError, match="không thể hủy"):
            order_service.cancel_order(order, acc)
        assert order.status == status and _stock(v) == (10, 2)                     # không nhả hàng khi hủy bị từ chối


def test_cannot_cancel_someone_elses_order(app, shop, buyer, buyer2):
    acc1, addr1 = buyer
    acc2, _ = buyer2
    put_in_cart(acc1, [(make_variant(shop), 1)])
    order = place(acc1, addr1)
    with pytest.raises(OrderStateError, match="không có quyền"):
        order_service.cancel_order(order, acc2)
    assert order.status == OrderStatus.PENDING_CONFIRM


def test_double_cancel_does_not_release_twice(app, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, stock=10)
    other = make_variant(shop, "Khác", stock=10)
    put_in_cart(acc, [(v, 2)])
    first = place(acc, addr)
    put_in_cart(acc, [(v, 3)])
    place(acc, addr)                                                               # đơn khác cùng giữ hàng
    assert _stock(v) == (10, 5)
    order_service.cancel_order(first, acc)
    with pytest.raises(OrderStateError):
        order_service.cancel_order(first, acc)
    assert _stock(v) == (10, 3)                                                    # chỉ nhả đúng một lần (5 - 2)


def test_staff_cancel_requires_reason_and_is_audited(app, shop, buyer, make_account):
    acc, addr = buyer
    staff = make_account(email="nv@test.com", role=ROLE_STAFF)
    v = make_variant(shop, stock=10)
    put_in_cart(acc, [(v, 2)])
    order = place(acc, addr)
    for step in (OrderStatus.CONFIRMED, OrderStatus.PACKING):
        order_service.change_status(order, step, staff)
    db.session.commit()
    with pytest.raises(OrderStateError, match="lý do hủy đơn"):
        order_service.cancel_order(order, staff, "   ")
    assert order.status == OrderStatus.PACKING
    order_service.cancel_order(order, staff, "Hết hàng thực tế trong kho")         # nhân viên được hủy đơn đang đóng gói
    assert order.status == OrderStatus.CANCELLED and _stock(v) == (10, 0)
    log = db.session.scalars(db.select(AuditLog)).one()
    assert (log.action, log.entity_name, log.entity_id, log.account_id) == ("order.cancel", "sales_order", order.id, staff.id)
    assert log.old_value == {"status": OrderStatus.PACKING} and log.new_value["reason"] == "Hết hàng thực tế trong kho"


def test_staff_cannot_cancel_shipping_order(app, shop, buyer, make_account):
    acc, addr = buyer
    staff = make_account(email="nv@test.com", role=ROLE_STAFF)
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr)
    for step in (OrderStatus.CONFIRMED, OrderStatus.PACKING, OrderStatus.SHIPPING):
        order_service.change_status(order, step, staff)
    db.session.commit()
    with pytest.raises(OrderStateError, match="không thể hủy"):
        order_service.cancel_order(order, staff, "Muốn hủy")


def test_cancel_settles_online_payment(app, shop, buyer):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    paid = place(acc, addr, VNPAY)
    order_service.change_status(paid, OrderStatus.PENDING_CONFIRM)                 # mô phỏng đã thanh toán thành công
    paid.payments[0].status = PaymentStatus.PAID
    db.session.commit()
    order_service.cancel_order(paid, acc)
    assert paid.payment_status == PaymentStatus.REFUNDED                           # đã thu tiền -> đánh dấu hoàn tiền

    put_in_cart(acc, [(make_variant(shop, "Khác"), 1)])
    pending = place(acc, addr, VNPAY)
    order_service.cancel_order(pending, None, "Thanh toán thất bại")               # hệ thống hủy
    assert pending.payment_status == PaymentStatus.FAILED


def test_system_cancel_only_for_pending_payment(app, shop, buyer):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    cod = place(acc, addr, COD)
    with pytest.raises(OrderStateError):
        order_service.cancel_order(cod, None, "Hệ thống")
    assert cod.status == OrderStatus.PENDING_CONFIRM


def test_change_status_validates_transitions(app, shop, buyer):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr)
    with pytest.raises(OrderStateError, match="Không thể chuyển"):
        order_service.change_status(order, OrderStatus.SHIPPING)                   # nhảy cóc
    with pytest.raises(OrderStateError):
        order_service.change_status(order, OrderStatus.PENDING_CONFIRM)            # chuyển về chính nó
    order_service.change_status(order, OrderStatus.CONFIRMED)
    db.session.commit()
    assert [h.to_status for h in order.status_history] == [OrderStatus.PENDING_CONFIRM, OrderStatus.CONFIRMED]


# ================================================================== hết hạn thanh toán (FR-HT01)
def _age(order, minutes):
    order.created_at = utcnow() - timedelta(minutes=minutes)
    db.session.commit()


def test_expire_unpaid_orders(app, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, stock=20)
    orders = {}
    for key, method in (("old_online", VNPAY), ("fresh_online", VNPAY), ("old_cod", COD)):
        put_in_cart(acc, [(v, 2)])
        orders[key] = place(acc, addr, method)
    _age(orders["old_online"], 20)
    _age(orders["old_cod"], 600)
    assert _stock(v) == (20, 6)

    assert order_service.expire_unpaid_orders() == 1
    assert orders["old_online"].status == OrderStatus.CANCELLED
    assert orders["fresh_online"].status == OrderStatus.PENDING_PAYMENT
    assert orders["old_cod"].status == OrderStatus.PENDING_CONFIRM                 # đơn COD không bao giờ hết hạn thanh toán
    assert _stock(v) == (20, 4)
    last = orders["old_online"].status_history[-1]
    assert last.to_status == OrderStatus.CANCELLED and last.changed_by_account_id is None and "Quá hạn" in last.reason
    assert orders["old_online"].payment_status == PaymentStatus.FAILED
    assert order_service.expire_unpaid_orders() == 0                               # chạy lại không tác dụng phụ
    assert _stock(v) == (20, 4)


def test_expire_uses_configured_timeout(app, shop, buyer):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr, VNPAY)
    _age(order, 20)
    AppSetting.set_value(SettingKey.PAYMENT_TIMEOUT_MINUTES, 60)
    db.session.commit()
    assert order_service.expire_unpaid_orders() == 0                               # 20 phút < 60 phút cấu hình
    AppSetting.set_value(SettingKey.PAYMENT_TIMEOUT_MINUTES, 10)
    db.session.commit()
    assert order_service.expire_unpaid_orders() == 1
    assert order_service.payment_deadline(order) is None                           # đã hủy thì không còn hạn thanh toán


def test_payment_deadline_is_derived(app, shop, buyer):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr, VNPAY)
    assert order_service.payment_deadline(order) == order.created_at + timedelta(minutes=15)


# ================================================================== giao diện / route
@pytest.fixture()
def logged_in(buyer, login):
    login("buyer@test.com")
    return buyer


def test_checkout_requires_customer(client, make_account, login):
    assert client.get("/account/checkout").status_code == 302
    make_account(email="nv@test.com", role=ROLE_STAFF)
    login("nv@test.com")
    assert client.get("/account/checkout").status_code == 403


def test_checkout_with_empty_cart_redirects(client, logged_in):
    resp = client.get("/account/checkout", follow_redirects=True)
    assert "Giỏ hàng của bạn đang trống" in resp.get_data(as_text=True)


def test_checkout_page_shows_summary(client, shop, logged_in):
    acc, addr = logged_in
    put_in_cart(acc, [(make_variant(shop, price=250000), 1)])
    body = client.get("/account/checkout").get_data(as_text=True)
    assert "1 Lê Lợi, Phường Bến Nghé" in body and f'value="{addr.id}"' in body and "checked" in body
    assert "250.000 ₫" in body and "30.000 ₫" in body and "280.000 ₫" in body       # tạm tính, phí ship, tổng
    assert "chưa khả dụng" in body and 'id="pm-online" value="VNPAY"' in body and "disabled" in body


def test_checkout_apply_promo_previews_without_creating_order(client, shop, logged_in):
    acc, addr = logged_in
    make_promo("SAVE10")
    put_in_cart(acc, [(make_variant(shop, price=250000), 1)])
    body = client.post("/account/checkout", data=dict(address_id=addr.id, promo_code="save10", payment_method="COD",
                                                      action="apply")).get_data(as_text=True)
    assert "Đã áp dụng mã SAVE10" in body and "-25.000 ₫" in body and "255.000 ₫" in body
    bad = client.post("/account/checkout", data=dict(address_id=addr.id, promo_code="SAI", action="apply")).get_data(as_text=True)
    assert "Mã khuyến mãi không tồn tại" in bad
    assert db.session.query(SalesOrder).count() == 0 and db.session.query(CartItem).count() == 1


def test_place_cod_order_via_route(client, shop, logged_in):
    acc, addr = logged_in
    v = make_variant(shop)
    put_in_cart(acc, [(v, 2)])
    resp = client.post("/account/checkout", data=dict(address_id=addr.id, payment_method="COD", action="place",
                                                      note="Gọi trước khi giao"))
    order = db.session.scalar(db.select(SalesOrder))
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/account/orders/{order.order_code}")
    body = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "Đặt hàng thành công" in body and order.order_code in body and "Gọi trước khi giao" in body
    assert "Chờ xác nhận" in body and "Hủy đơn hàng" in body
    assert db.session.query(CartItem).count() == 0


def test_place_order_via_route_rejections(client, shop, logged_in, buyer2):
    acc, addr = logged_in
    _, other_addr = buyer2
    put_in_cart(acc, [(make_variant(shop), 1)])
    online = client.post("/account/checkout", data=dict(address_id=addr.id, payment_method="VNPAY", action="place"))
    assert "Thanh toán online hiện chưa khả dụng" in online.get_data(as_text=True)
    stolen = client.post("/account/checkout", data=dict(address_id=other_addr.id, payment_method="COD", action="place"))
    assert "địa chỉ nhận hàng hợp lệ" in stolen.get_data(as_text=True)
    missing = client.post("/account/checkout", data=dict(payment_method="COD", action="place"))
    assert "địa chỉ nhận hàng hợp lệ" in missing.get_data(as_text=True)
    assert db.session.query(SalesOrder).count() == 0


def test_enter_key_in_promo_field_does_not_place_order(client, shop, logged_in):
    acc, addr = logged_in
    put_in_cart(acc, [(make_variant(shop), 1)])
    client.post("/account/checkout", data=dict(address_id=addr.id, promo_code="X"))      # không có action
    assert db.session.query(SalesOrder).count() == 0


def test_order_list_filter_pagination_and_isolation(app, client, shop, logged_in, buyer2):
    acc, addr = logged_in
    acc2, addr2 = buyer2
    app.config["ORDERS_PER_PAGE"] = 2
    v = make_variant(shop, stock=50)
    codes = []
    for _ in range(3):
        put_in_cart(acc, [(v, 1)])
        codes.append(place(acc, addr).order_code)
    put_in_cart(acc2, [(v, 1)])
    foreign = place(acc2, addr2)
    order_service.cancel_order(db.session.scalar(db.select(SalesOrder).where(SalesOrder.order_code == codes[0])), acc)

    page1 = client.get("/account/orders").get_data(as_text=True)
    assert codes[2] in page1 and codes[1] in page1 and codes[0] not in page1        # mới nhất trước, 2 đơn mỗi trang
    assert foreign.order_code not in page1                                          # không thấy đơn của người khác
    assert codes[0] in client.get("/account/orders?page=2").get_data(as_text=True)
    cancelled = client.get("/account/orders?status=CANCELLED").get_data(as_text=True)
    assert codes[0] in cancelled and codes[1] not in cancelled
    assert client.get("/account/orders?status=HACK&page=abc").status_code == 200
    assert client.get("/account/orders?page=99").status_code == 302


def test_order_detail_isolation_and_content(client, shop, logged_in, buyer2):
    acc, addr = logged_in
    acc2, addr2 = buyer2
    put_in_cart(acc, [(make_variant(shop, "Áo Pro", price=250000), 2)])
    mine = place(acc, addr)
    put_in_cart(acc2, [(make_variant(shop, "Áo Khác"), 1)])
    theirs = place(acc2, addr2)
    body = client.get(f"/account/orders/{mine.order_code}").get_data(as_text=True)
    assert "Áo Pro" in body and "500.000 ₫" in body and "Người Nhận" in body and "Lịch sử trạng thái" in body
    assert client.get(f"/account/orders/{theirs.order_code}").status_code == 404       # không xem được đơn người khác
    assert client.get("/account/orders/SZ000000AAAAAA").status_code == 404
    assert client.post(f"/account/orders/{theirs.order_code}/cancel").status_code == 404
    db.session.refresh(theirs)
    assert theirs.status == OrderStatus.PENDING_CONFIRM


def test_cancel_via_route(client, shop, logged_in):
    acc, addr = logged_in
    v = make_variant(shop, stock=10)
    put_in_cart(acc, [(v, 2)])
    order = place(acc, addr)
    resp = client.post(f"/account/orders/{order.order_code}/cancel", data=dict(reason="Đặt nhầm"), follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "Đã hủy đơn hàng" in body and "Đặt nhầm" in body and "Hủy đơn hàng</h2>" not in body
    assert _stock(v) == (10, 0)
    again = client.post(f"/account/orders/{order.order_code}/cancel", follow_redirects=True).get_data(as_text=True)
    assert "không thể hủy" in again


def test_cancel_button_hidden_once_packing(client, shop, logged_in):
    acc, addr = logged_in
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr)
    for step in (OrderStatus.CONFIRMED, OrderStatus.PACKING):
        order_service.change_status(order, step)
    db.session.commit()
    body = client.get(f"/account/orders/{order.order_code}").get_data(as_text=True)
    assert "Đang đóng gói" in body and "Hủy đơn hàng</h2>" not in body
    resp = client.post(f"/account/orders/{order.order_code}/cancel", follow_redirects=True)
    assert "không thể hủy" in resp.get_data(as_text=True)


def test_pending_payment_order_shows_deadline(client, shop, logged_in):
    acc, addr = logged_in
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr, VNPAY)
    body = client.get(f"/account/orders/{order.order_code}").get_data(as_text=True)
    assert "Chờ thanh toán" in body and "tự hủy nếu chưa thanh toán trước" in body
