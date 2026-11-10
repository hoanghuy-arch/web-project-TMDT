"""Kiểm thử thanh toán online: bắt đầu thanh toán, xử lý IPN/Return, thử lại, trễ/trùng, cổng giả lập (Task 7)."""
import re
import urllib.parse
from datetime import timedelta

import pytest

from app.constants import OrderStatus, PaymentStatus
from app.extensions import db, mail
from app.models import AuditLog, Payment, SalesOrder, StockTransaction
from app.models.base import utcnow
from app.services import order_service, payment_service, vnpay
from app.services.payment_service import PaymentStartError

from tests.helpers import VNPAY, COD, make_variant, place, put_in_cart, refresh

TMN, SECRET = "TMN001", "S3CRET-KEY"


# ------------------------------------------------------------------ cấu hình cổng
@pytest.fixture()
def vnpay_gateway(app):
    app.config.update(VNPAY_TMN_CODE=TMN, VNPAY_HASH_SECRET=SECRET)


@pytest.fixture()
def mock_gateway(app):
    app.config["PAYMENT_MOCK_ENABLED"] = True


@pytest.fixture()
def online_order(app, shop, buyer, vnpay_gateway):
    """Đơn online đang chờ thanh toán (250.000 + phí ship 30.000 = 280.000)."""
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop, price=250000, stock=10), 1)])
    return place(acc, addr, VNPAY)


def result_params(payment, code="00", amount=None, secret=SECRET, tmn=TMN, txn_ref=None):
    return vnpay.build_result_params(
        secret, tmn_code=tmn, txn_ref=txn_ref or payment.gateway_txn_ref,
        amount=int(payment.amount) if amount is None else amount, response_code=code, pay_date="20261107120000",
        order_info="Thanh toan don hang")


def ipn(client, params):
    return client.get("/payment/vnpay/ipn", query_string=params).get_json()


def audit_actions():
    return [a.action for a in db.session.scalars(db.select(AuditLog).order_by(AuditLog.id)).all()]


# ================================================================== chọn cổng
def test_gateway_mode(app):
    assert payment_service.gateway_mode() is None and not payment_service.is_online_enabled()
    app.config["PAYMENT_MOCK_ENABLED"] = True
    assert payment_service.gateway_mode() == "mock" and payment_service.is_online_enabled()
    app.config.update(VNPAY_TMN_CODE=TMN, VNPAY_HASH_SECRET=SECRET)
    assert payment_service.gateway_mode() == "vnpay"                           # khóa thật luôn ưu tiên cổng giả lập
    app.config.update(VNPAY_TMN_CODE=TMN, VNPAY_HASH_SECRET="", PAYMENT_MOCK_ENABLED=False)
    assert payment_service.gateway_mode() is None                              # thiếu khóa bí mật thì coi như chưa cấu hình


def test_mock_secret_differs_from_real_and_is_stable(app, mock_gateway):
    a = payment_service.secret()
    assert a == payment_service.secret() and len(a) == 64
    app.config.update(VNPAY_TMN_CODE=TMN, VNPAY_HASH_SECRET=SECRET)
    assert payment_service.secret() == SECRET != a


# ================================================================== bắt đầu thanh toán
def test_start_payment_builds_signed_vnpay_url(app, online_order):
    payment = online_order.payments[0]
    url = payment_service.start_payment(online_order, "1.2.3.4")
    base, _, query = url.partition("?")
    q = dict(urllib.parse.parse_qsl(query))
    assert base == app.config["VNPAY_URL"]
    assert q["vnp_Amount"] == "28000000" and q["vnp_TmnCode"] == TMN and q["vnp_TxnRef"] == payment.gateway_txn_ref
    assert q["vnp_IpAddr"] == "1.2.3.4" and q["vnp_ReturnUrl"] == app.config["VNPAY_RETURN_URL"]
    assert q["vnp_OrderInfo"] == f"Thanh toan don hang {online_order.order_code}"
    assert q["vnp_ExpireDate"] == vnpay.vn_timestamp(online_order.created_at + timedelta(minutes=15))   # cổng cũng chặn quá hạn
    assert vnpay.verify(q, SECRET)


def test_start_payment_rejections(app, shop, buyer, online_order):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop, "Áo COD"), 1)])
    cod = place(acc, addr, COD)
    with pytest.raises(PaymentStartError, match="không ở trạng thái chờ thanh toán"):
        payment_service.start_payment(cod, "1.1.1.1")
    online_order.created_at = utcnow() - timedelta(minutes=20)                 # quá hạn nhưng job chưa kịp hủy
    db.session.commit()
    with pytest.raises(PaymentStartError, match="quá hạn"):
        payment_service.start_payment(online_order, "1.1.1.1")
    app.config.update(VNPAY_TMN_CODE="", VNPAY_HASH_SECRET="")
    with pytest.raises(PaymentStartError, match="chưa khả dụng"):
        payment_service.start_payment(online_order, "1.1.1.1")


def test_start_reuses_pending_payment_and_creates_new_attempt_after_failure(client, online_order):
    first = online_order.payments[0]
    ref_of = lambda url: dict(urllib.parse.parse_qsl(url.partition("?")[2]))["vnp_TxnRef"]
    u1 = payment_service.start_payment(online_order, "1.1.1.1")
    u2 = payment_service.start_payment(online_order, "1.1.1.1")                # khách quay lại cổng khi chưa trả
    assert ref_of(u1) == ref_of(u2) == first.gateway_txn_ref
    assert db.session.query(Payment).filter_by(sales_order_id=online_order.id).count() == 1

    assert ipn(client, result_params(first, "51"))["RspCode"] == "00"          # lần 1 thất bại
    u3 = payment_service.start_payment(online_order, "1.1.1.1")
    payments = db.session.scalars(db.select(Payment).where(Payment.sales_order_id == online_order.id).order_by(Payment.id)).all()
    assert len(payments) == 2 and ref_of(u3) == payments[1].gateway_txn_ref != first.gateway_txn_ref
    assert [p.status for p in payments] == [PaymentStatus.FAILED, PaymentStatus.PENDING] and payments[1].amount == first.amount


def test_start_route_redirects_to_gateway_and_checks_owner(client, online_order, login, make_account):
    login("buyer@test.com")
    resp = client.get(f"/payment/start/{online_order.order_code}")
    assert resp.status_code == 302 and resp.headers["Location"].startswith("https://sandbox.vnpayment.vn/")
    client.post("/auth/logout")
    make_account(email="khac@test.com")
    login("khac@test.com")
    assert client.get(f"/payment/start/{online_order.order_code}").status_code == 404      # không thanh toán hộ đơn người khác


def test_start_route_shows_error_for_non_pending_order(client, shop, buyer, vnpay_gateway, login):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop), 1)])
    cod = place(acc, addr, COD)
    login("buyer@test.com")
    resp = client.get(f"/payment/start/{cod.order_code}", follow_redirects=True)
    assert "không ở trạng thái chờ thanh toán" in resp.get_data(as_text=True)


# ================================================================== IPN: thanh toán thành công
def test_ipn_success_confirms_order(client, online_order):
    payment = online_order.payments[0]
    with mail.record_messages() as outbox:
        assert ipn(client, result_params(payment)) == {"RspCode": "00", "Message": "Confirm Success"}
    refresh(online_order, payment)
    assert payment.status == PaymentStatus.PAID and payment.paid_at is not None and payment.amount == 280000
    assert online_order.status == OrderStatus.PENDING_CONFIRM
    last = online_order.status_history[-1]
    assert last.to_status == OrderStatus.PENDING_CONFIRM and last.changed_by_account_id is None
    assert last.reason == "Thanh toán online thành công"
    assert audit_actions() == ["payment.paid"]
    assert len(outbox) == 1 and online_order.order_code in outbox[0].subject          # gửi email xác nhận sau khi thanh toán xong


def test_ipn_is_idempotent(client, online_order):
    payment = online_order.payments[0]
    params = result_params(payment)
    ipn(client, params)
    with mail.record_messages() as outbox:
        again = ipn(client, params)
    assert again["RspCode"] == "02"                                            # VNPay: đơn hàng đã được xác nhận
    refresh(online_order)
    assert [h.to_status for h in online_order.status_history] == [OrderStatus.PENDING_PAYMENT, OrderStatus.PENDING_CONFIRM]
    assert audit_actions() == ["payment.paid"] and outbox == []                # không ghi trùng, không gửi email lần nữa


# ================================================================== IPN: bị từ chối
def test_ipn_rejects_bad_signature(client, online_order):
    payment = online_order.payments[0]
    params = result_params(payment)
    for bad in (dict(params, vnp_ResponseCode="24"), dict(params, vnp_Amount="100"),
                {k: v for k, v in params.items() if k != "vnp_SecureHash"},
                result_params(payment, secret="KHOA-KE-TAN-CONG")):
        assert ipn(client, bad)["RspCode"] == "97"
    assert ipn(client, {})["RspCode"] == "97"
    refresh(online_order, payment)
    assert payment.status == PaymentStatus.PENDING and online_order.status == OrderStatus.PENDING_PAYMENT


def test_ipn_unknown_transaction(client, online_order):
    params = result_params(online_order.payments[0], txn_ref="KHONGCOTHAT")
    assert ipn(client, params)["RspCode"] == "01"


@pytest.mark.parametrize("amount", [1000, 279000, 281000, 28000000, 0])
def test_ipn_amount_mismatch_is_rejected_even_with_valid_signature(client, online_order, amount):
    """Chữ ký đúng nhưng số tiền khác số hệ thống đã tạo: không được ghi nhận là đã thanh toán."""
    payment = online_order.payments[0]
    assert ipn(client, result_params(payment, amount=amount))["RspCode"] == "04"
    refresh(online_order, payment)
    assert payment.status == PaymentStatus.PENDING and online_order.status == OrderStatus.PENDING_PAYMENT
    assert audit_actions() == ["payment.amount_mismatch"]
    log = db.session.scalar(db.select(AuditLog))
    assert log.old_value == {"expected_amount": 280000} and log.new_value["received_vnp_amount"] == str(amount * 100)


def test_ipn_amount_not_multiple_of_100_is_rejected(client, online_order):
    payment = online_order.payments[0]
    params = vnpay.build_result_params(SECRET, tmn_code=TMN, txn_ref=payment.gateway_txn_ref, amount=1, response_code="00", pay_date="x")
    params["vnp_Amount"] = "28000050"
    params["vnp_SecureHash"] = vnpay.sign(params, SECRET)
    assert ipn(client, params)["RspCode"] == "04"


def test_ipn_error_returns_99_json(client, online_order, monkeypatch):
    def boom(_params):
        raise RuntimeError("lỗi giả lập")
    monkeypatch.setattr(payment_service, "process_gateway_result", boom)
    resp = client.get("/payment/vnpay/ipn")
    assert resp.status_code == 200 and resp.get_json() == {"RspCode": "99", "Message": "Unknown error"}


def test_ipn_only_accepts_get(client):
    assert client.post("/payment/vnpay/ipn").status_code == 405


# ================================================================== thất bại và thử lại
def test_failed_payment_keeps_order_pending_and_allows_retry(client, online_order):
    first = online_order.payments[0]
    assert ipn(client, result_params(first, "24"))["RspCode"] == "00"          # VNPay luôn nhận 00 khi đã ghi nhận kết quả
    refresh(online_order, first)
    assert first.status == PaymentStatus.FAILED and online_order.status == OrderStatus.PENDING_PAYMENT
    variant = online_order.items[0].variant
    refresh(variant)
    assert variant.reserved_quantity == 1                                      # hàng vẫn được giữ trong thời gian thử lại
    assert audit_actions() == []

    payment_service.start_payment(online_order, "1.1.1.1")                     # thử lại
    refresh(online_order)
    second = online_order.payments[1]
    assert second.status == PaymentStatus.PENDING and second.gateway_txn_ref != first.gateway_txn_ref
    assert ipn(client, result_params(second))["RspCode"] == "00"
    refresh(online_order, first, second)
    assert (first.status, second.status) == (PaymentStatus.FAILED, PaymentStatus.PAID)
    assert online_order.status == OrderStatus.PENDING_CONFIRM and online_order.payment_status == PaymentStatus.PAID


def test_failure_after_success_does_not_downgrade(client, online_order):
    payment = online_order.payments[0]
    ipn(client, result_params(payment))
    assert ipn(client, result_params(payment, "24"))["RspCode"] == "02"
    refresh(payment)
    assert payment.status == PaymentStatus.PAID


def test_unpaid_order_expires_and_releases_stock(online_order):
    online_order.created_at = utcnow() - timedelta(minutes=20)
    db.session.commit()
    assert order_service.expire_unpaid_orders() == 1
    refresh(online_order)
    assert online_order.status == OrderStatus.CANCELLED and online_order.payment_status == PaymentStatus.FAILED
    variant = online_order.items[0].variant
    refresh(variant)
    assert variant.reserved_quantity == 0


def test_paid_order_is_not_expired(client, online_order):
    ipn(client, result_params(online_order.payments[0]))
    online_order.created_at = utcnow() - timedelta(minutes=60)
    db.session.commit()
    assert order_service.expire_unpaid_orders() == 0
    refresh(online_order)
    assert online_order.status == OrderStatus.PENDING_CONFIRM


# ================================================================== thanh toán trễ và trùng
def test_late_payment_after_cancellation_is_flagged_for_refund(client, online_order):
    payment = online_order.payments[0]
    online_order.created_at = utcnow() - timedelta(minutes=20)
    db.session.commit()
    order_service.expire_unpaid_orders()                                       # đơn bị hủy, hàng đã nhả
    with mail.record_messages() as outbox:
        assert ipn(client, result_params(payment))["RspCode"] == "00"
    refresh(online_order, payment)
    assert payment.status == PaymentStatus.PAID                                # tiền đã về
    assert online_order.status == OrderStatus.CANCELLED                        # không khôi phục đơn đã hủy
    # order.cancel: hệ thống tự hủy đơn quá hạn; sau đó tiền về trễ nên có thêm 2 mục của giao dịch
    assert audit_actions() == ["order.cancel", "payment.paid", "payment.late_after_cancel"] and outbox == []
    log = db.session.scalars(db.select(AuditLog).where(AuditLog.action == "payment.late_after_cancel")).one()
    assert log.entity_id == online_order.id and "hoàn tiền" in log.new_value["action"]
    variant = online_order.items[0].variant
    refresh(variant)
    assert variant.reserved_quantity == 0                                      # tồn kho không bị giữ lại


def test_second_successful_payment_is_flagged_as_duplicate(client, online_order):
    first = online_order.payments[0]
    ipn(client, result_params(first))
    second = Payment(sales_order_id=online_order.id, method=VNPAY, status=PaymentStatus.PENDING, amount=first.amount,
                     gateway_txn_ref=first.gateway_txn_ref + "DUP")
    db.session.add(second)
    db.session.commit()
    with mail.record_messages() as outbox:
        assert ipn(client, result_params(second))["RspCode"] == "00"
    refresh(online_order, second)
    assert second.status == PaymentStatus.PAID and online_order.status == OrderStatus.PENDING_CONFIRM
    assert audit_actions() == ["payment.paid", "payment.paid", "payment.duplicate"] and outbox == []
    assert [h.to_status for h in online_order.status_history] == [OrderStatus.PENDING_PAYMENT, OrderStatus.PENDING_CONFIRM]


# ================================================================== trang Return (trình duyệt)
def test_return_success_for_owner_redirects_to_order(client, online_order, login):
    login("buyer@test.com")
    resp = client.get("/payment/vnpay/return", query_string=result_params(online_order.payments[0]))
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/account/orders/{online_order.order_code}")
    body = client.get(resp.headers["Location"]).get_data(as_text=True)
    assert "Thanh toán thành công!" in body and "Chờ xác nhận" in body and "Đã thanh toán" in body
    assert "Thanh toán ngay" not in body


def test_return_after_ipn_still_shows_success(client, online_order, login):
    params = result_params(online_order.payments[0])
    ipn(client, params)
    login("buyer@test.com")
    resp = client.get("/payment/vnpay/return", query_string=params, follow_redirects=True)
    assert "Thanh toán thành công!" in resp.get_data(as_text=True)


def test_return_failure_for_owner_explains_and_allows_retry(client, online_order, login):
    login("buyer@test.com")
    resp = client.get("/payment/vnpay/return", query_string=result_params(online_order.payments[0], "51"), follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "Thanh toán không thành công: Tài khoản không đủ số dư" in body and "thử thanh toán lại trước" in body
    assert "Thanh toán ngay" in body and "Chờ thanh toán" in body


def test_return_for_anonymous_and_other_user_shows_result_page(client, online_order, make_account, login):
    params = result_params(online_order.payments[0])
    anon = client.get("/payment/vnpay/return", query_string=params)
    body = anon.get_data(as_text=True)
    assert anon.status_code == 200 and "Thanh toán thành công" in body and "Đăng nhập để xem đơn hàng" in body
    make_account(email="khac@test.com")
    login("khac@test.com")
    other = client.get("/payment/vnpay/return", query_string=params)
    assert other.status_code == 200 and "Xem đơn hàng của tôi" in other.get_data(as_text=True)     # không chuyển tới đơn của người khác


def test_return_rejects_tampered_results(client, online_order, login):
    login("buyer@test.com")
    payment = online_order.payments[0]
    forged = client.get("/payment/vnpay/return", query_string=dict(result_params(payment, "51"), vnp_ResponseCode="00"))
    assert forged.status_code == 400 and "Không xác thực được kết quả thanh toán" in forged.get_data(as_text=True)
    mismatch = client.get("/payment/vnpay/return", query_string=result_params(payment, amount=1000))
    assert mismatch.status_code == 400 and "không khớp" in mismatch.get_data(as_text=True)
    unknown = client.get("/payment/vnpay/return", query_string=result_params(payment, txn_ref="KHONGCO"))
    assert unknown.status_code == 404
    refresh(online_order, payment)
    assert payment.status == PaymentStatus.PENDING and online_order.status == OrderStatus.PENDING_PAYMENT


def test_return_unexpected_error_shows_friendly_page(client, online_order, monkeypatch):
    monkeypatch.setattr(payment_service, "process_gateway_result", lambda params: 1 / 0)
    resp = client.get("/payment/vnpay/return")
    assert resp.status_code == 500 and "Hệ thống đang xử lý kết quả thanh toán" in resp.get_data(as_text=True)


# ================================================================== cổng giả lập: luồng đầy đủ
def _mock_pay_page(client, order):
    resp = client.get(f"/payment/start/{order.order_code}", follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "Cổng thanh toán GIẢ LẬP" in body
    return body, re.search(r'name="txn_ref" value="([^"]+)"', body).group(1), int(re.search(r'name="amount" value="(\d+)"', body).group(1))


def _complete(client, outcome, txn_ref, amount, **kw):
    return client.post("/payment/mock/complete", data=dict(outcome=outcome, txn_ref=txn_ref, amount=amount), **kw)


@pytest.fixture()
def mock_order(app, shop, buyer, mock_gateway, login):
    acc, addr = buyer
    put_in_cart(acc, [(make_variant(shop, price=250000), 1)])
    login("buyer@test.com")
    return place(acc, addr, VNPAY)


def test_mock_full_flow_success(client, mock_order):
    body, txn_ref, amount = _mock_pay_page(client, mock_order)
    assert amount == 280000 and "280.000 ₫" in body and mock_order.payments[0].gateway_txn_ref == txn_ref
    resp = _complete(client, "success", txn_ref, amount, follow_redirects=True)
    page = resp.get_data(as_text=True)
    assert "Thanh toán thành công!" in page and "Chờ xác nhận" in page and "Đã thanh toán" in page
    refresh(mock_order)
    assert mock_order.status == OrderStatus.PENDING_CONFIRM and mock_order.payment_status == PaymentStatus.PAID


@pytest.mark.parametrize("outcome,text", [("fail", "không đủ số dư"), ("cancel", "đã hủy giao dịch")])
def test_mock_failure_paths_allow_retry_then_pay(client, mock_order, outcome, text):
    _, txn_ref, amount = _mock_pay_page(client, mock_order)
    page = _complete(client, outcome, txn_ref, amount, follow_redirects=True).get_data(as_text=True)
    assert text in page and "Thanh toán ngay" in page
    refresh(mock_order)
    assert mock_order.status == OrderStatus.PENDING_PAYMENT and mock_order.payment_status == PaymentStatus.FAILED
    _, new_ref, new_amount = _mock_pay_page(client, mock_order)                # "Thanh toán ngay" = thử lại với mã mới
    assert new_ref != txn_ref
    assert "Thanh toán thành công!" in _complete(client, "success", new_ref, new_amount, follow_redirects=True).get_data(as_text=True)
    refresh(mock_order)
    assert mock_order.status == OrderStatus.PENDING_CONFIRM and len(mock_order.payments) == 2


def test_mock_amount_tampering_is_blocked(client, mock_order):
    _, txn_ref, amount = _mock_pay_page(client, mock_order)
    resp = _complete(client, "tamper", txn_ref, amount, follow_redirects=True)
    assert resp.status_code == 400 and "không khớp" in resp.get_data(as_text=True)
    refresh(mock_order)
    assert mock_order.status == OrderStatus.PENDING_PAYMENT and mock_order.payment_status == PaymentStatus.PENDING
    assert audit_actions() == ["payment.amount_mismatch"]


def test_mock_complete_validates_input(client, mock_order):
    assert _complete(client, "hack", "REF", 1000).status_code == 400
    assert _complete(client, "success", "", 1000).status_code == 400
    assert client.post("/payment/mock/complete", data=dict(outcome="success", txn_ref="REF", amount="abc")).status_code == 400
    assert _complete(client, "success", "REF", -5).status_code == 400


def test_mock_pay_requires_valid_signature(client, mock_order):
    assert client.get("/payment/mock/pay").status_code == 400
    assert client.get("/payment/mock/pay?vnp_Amount=100&vnp_TxnRef=X&vnp_SecureHash=abc").status_code == 400


def test_mock_gateway_is_disabled_unless_explicitly_enabled(app, client, online_order, login):
    """Cổng giả lập tắt khi chưa bật cấu hình, và cả khi đã có khóa VNPay thật (production không bao giờ dùng)."""
    post = lambda: client.post("/payment/mock/complete", data=dict(outcome="success", txn_ref="R", amount=1)).status_code
    app.config.update(VNPAY_TMN_CODE="", VNPAY_HASH_SECRET="")                  # chưa có khóa thật, chưa bật cổng giả lập
    assert payment_service.gateway_mode() is None
    assert client.get("/payment/mock/pay").status_code == 404 and post() == 404
    app.config.update(VNPAY_TMN_CODE=TMN, VNPAY_HASH_SECRET=SECRET, PAYMENT_MOCK_ENABLED=True)   # có khóa thật dù cờ mock bật
    assert payment_service.gateway_mode() == "vnpay"
    assert client.get("/payment/mock/pay").status_code == 404 and post() == 404


# ================================================================== giao diện đặt hàng khi bật thanh toán online
def test_checkout_enables_online_option_and_places_online_order(client, shop, buyer, mock_gateway, login):
    acc, addr = buyer
    login("buyer@test.com")
    put_in_cart(acc, [(make_variant(shop), 1)])
    page = client.get("/account/checkout").get_data(as_text=True)
    assert "chưa khả dụng" not in page and not re.search(r'id="pm-online"[^>]*disabled', page)
    resp = client.post("/account/checkout", data=dict(address_id=addr.id, payment_method="VNPAY", action="place"))
    order = db.session.scalar(db.select(SalesOrder))
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/payment/start/{order.order_code}")


def test_order_detail_pay_button_follows_gateway_availability(app, client, shop, buyer, mock_gateway, login):
    acc, addr = buyer
    login("buyer@test.com")
    put_in_cart(acc, [(make_variant(shop), 1)])
    order = place(acc, addr, VNPAY)
    url = f"/account/orders/{order.order_code}"
    assert f"/payment/start/{order.order_code}" in client.get(url).get_data(as_text=True)
    app.config["PAYMENT_MOCK_ENABLED"] = False
    assert "Thanh toán ngay" not in client.get(url).get_data(as_text=True)
