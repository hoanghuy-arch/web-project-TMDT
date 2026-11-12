"""Kiểm thử đổi trả (khách gửi yêu cầu, nhân viên xử lý) và đánh giá sản phẩm (Task 8B)."""
from datetime import timedelta

import pytest

from app.constants import (ROLE_STAFF, OrderStatus, PaymentStatus, Perm, ReturnStatus, SettingKey, StockTxType)
from app.extensions import db
from app.models import AppSetting, AuditLog, Permission, Review, ReturnRequest, StockTransaction
from app.models.base import utcnow
from app.services import return_service

from tests.helpers import advance, make_variant, new_order, put_in_cart, place, refresh

REASON = "Sản phẩm bị lỗi đường may"


@pytest.fixture()
def staff_acc(make_account, staff_perms):
    """Nhân viên đủ quyền (chưa đăng nhập), dùng để chạy các bước nghiệp vụ."""
    return make_account(email="nv@test.com", role=ROLE_STAFF, full_name="Nhân Viên A")


def go(client, login, email):
    client.post("/auth/logout")
    login(email)


def completed_order(buyer, shop, staff_acc, carrier, qty=3, stock=10, price=250000, name="Áo A"):
    order, v = new_order(buyer, shop, qty=qty, stock=stock, price=price, name=name)
    advance(order, staff_acc, carrier[0], "confirm", "pack", "ship", "deliver")
    refresh(order)
    return order, v


def submit_return(client, order, qty=1, reason=REASON, item=None):
    item = item or order.items[0]
    return client.post(f"/account/orders/{order.order_code}/return",
                       data={f"qty_{item.id}": qty, "reason": reason}, follow_redirects=True).get_data(as_text=True)


def make_request(order, qty=2, reason=REASON):
    return return_service.create_return_request(order.account, order, {order.items[0].id: qty}, reason)


def stock_of(v):
    db.session.refresh(v)
    return v.stock_quantity, v.reserved_quantity


# ================================================================== khách: gửi yêu cầu
def test_return_option_visible_only_when_allowed(client, buyer, shop, staff_acc, carrier, login):
    pending, _ = new_order(buyer, shop, name="Chưa giao")
    done, _ = completed_order(buyer, shop, staff_acc, carrier, name="Đã giao")
    go(client, login, "buyer@test.com")
    page = client.get(f"/account/orders/{pending.order_code}").get_data(as_text=True)
    assert "Yêu cầu đổi trả" not in page and "<h2 class=\"h6 mb-3\">Đổi trả</h2>" not in page
    page = client.get(f"/account/orders/{done.order_code}").get_data(as_text=True)
    assert f"/account/orders/{done.order_code}/return" in page and "Hạn gửi yêu cầu" in page


def test_submit_return_request(client, buyer, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier, qty=3)
    go(client, login, "buyer@test.com")
    form = client.get(f"/account/orders/{order.order_code}/return").get_data(as_text=True)
    assert "Số lượng trả" in form and 'max="3"' in form and "Áo A" in form
    body = submit_return(client, order, qty=2)
    assert "Đã gửi yêu cầu đổi trả" in body and "Chờ xử lý" in body and REASON in body
    (req,) = db.session.scalars(db.select(ReturnRequest)).all()
    assert req.status == ReturnStatus.PENDING and req.reason == REASON and req.sales_order_id == order.id
    assert [(i.sales_order_item_id, i.quantity, i.accepted_quantity) for i in req.items] == [(order.items[0].id, 2, None)]
    assert "Yêu cầu đổi trả</a>" not in body and "đang có yêu cầu đổi trả chờ xử lý" in body      # không gửi trùng khi còn yêu cầu chờ


@pytest.mark.parametrize("qty,reason,message", [
    (0, REASON, "ít nhất một sản phẩm"), (4, REASON, "từ 0 đến 3"), (-1, REASON, "từ 0 đến 3"), ("abc", REASON, "từ 0 đến 3"),
    (1, "ngắn", "ít nhất 5 ký tự"), (1, "", "ít nhất 5 ký tự"), (1, "      ", "ít nhất 5 ký tự")])
def test_return_validation(client, buyer, shop, staff_acc, carrier, login, qty, reason, message):
    order, _ = completed_order(buyer, shop, staff_acc, carrier, qty=3)
    go(client, login, "buyer@test.com")
    resp = client.post(f"/account/orders/{order.order_code}/return", data={f"qty_{order.items[0].id}": qty, "reason": reason})
    assert resp.status_code == 200 and message in resp.get_data(as_text=True)
    assert db.session.query(ReturnRequest).count() == 0


def test_return_blocked_unless_order_completed(client, buyer, shop, login):
    order, _ = new_order(buyer, shop)
    go(client, login, "buyer@test.com")
    resp = client.get(f"/account/orders/{order.order_code}/return", follow_redirects=True)
    assert "Chỉ đơn hàng đã hoàn thành mới có thể yêu cầu đổi trả" in resp.get_data(as_text=True)
    assert client.post(f"/account/orders/{order.order_code}/return", data={f"qty_{order.items[0].id}": 1, "reason": REASON}).status_code == 302
    assert db.session.query(ReturnRequest).count() == 0


def test_return_window(app, client, buyer, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    go(client, login, "buyer@test.com")
    order.shipment.delivered_at = utcnow() - timedelta(days=6)                    # còn trong hạn mặc định 7 ngày
    db.session.commit()
    assert client.get(f"/account/orders/{order.order_code}/return").status_code == 200
    order.shipment.delivered_at = utcnow() - timedelta(days=8)
    db.session.commit()
    resp = client.get(f"/account/orders/{order.order_code}/return", follow_redirects=True)
    assert "Đã quá thời hạn đổi trả (7 ngày" in resp.get_data(as_text=True)
    AppSetting.set_value(SettingKey.RETURN_WINDOW_DAYS, 30)                       # thời hạn lấy từ cấu hình
    db.session.commit()
    assert client.get(f"/account/orders/{order.order_code}/return").status_code == 200
    AppSetting.set_value(SettingKey.RETURN_WINDOW_DAYS, 1)
    db.session.commit()
    assert "Đã quá thời hạn đổi trả (1 ngày" in client.get(f"/account/orders/{order.order_code}/return", follow_redirects=True).get_data(as_text=True)


def test_only_one_pending_request_at_a_time(client, buyer, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    go(client, login, "buyer@test.com")
    submit_return(client, order)
    again = client.get(f"/account/orders/{order.order_code}/return", follow_redirects=True).get_data(as_text=True)
    assert "đang có yêu cầu đổi trả chờ xử lý" in again
    assert "chờ xử lý" in submit_return(client, order).lower() and db.session.query(ReturnRequest).count() == 1


def test_cannot_request_return_for_someone_elses_order(client, buyer, buyer2, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    go(client, login, "buyer2@test.com")
    assert client.get(f"/account/orders/{order.order_code}/return").status_code == 404
    assert client.post(f"/account/orders/{order.order_code}/return", data={f"qty_{order.items[0].id}": 1, "reason": REASON}).status_code == 404
    assert db.session.query(ReturnRequest).count() == 0


# ================================================================== nhân viên: phân quyền và hiển thị
def test_returns_area_permissions(client, buyer, shop, staff_acc, carrier, login, roles, make_account):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    req = make_request(order)
    go(client, login, "buyer@test.com")
    assert client.get("/staff/returns").status_code == 403 and client.get(f"/staff/returns/{req.id}").status_code == 403
    client.post("/auth/logout")
    assert client.get("/staff/returns").status_code == 302
    # nhân viên không có return.handle
    roles[ROLE_STAFF].permissions = [p for p in roles[ROLE_STAFF].permissions if p.code != Perm.RETURN_HANDLE]
    db.session.commit()
    login("nv@test.com")
    assert client.get("/staff/returns").status_code == 403
    assert client.post(f"/staff/returns/{req.id}/approve").status_code == 403


def test_returns_list_and_detail(client, buyer, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    req = make_request(order)
    login("nv@test.com")
    page = client.get("/staff/returns").get_data(as_text=True)
    assert order.order_code in page and "Chờ xử lý (1)" in page
    assert order.order_code not in client.get("/staff/returns?status=COMPLETED").get_data(as_text=True)
    assert client.get("/staff/returns?status=HACK&page=abc").status_code == 200
    detail = client.get(f"/staff/returns/{req.id}").get_data(as_text=True)
    assert REASON in detail and "Chấp nhận" in detail and "Từ chối" in detail and "buyer@test.com" in detail
    assert client.get("/staff/returns/99999").status_code == 404
    assert "yêu cầu đổi trả chờ xử lý" in client.get("/staff/").get_data(as_text=True)
    assert f"/staff/returns/{req.id}" in client.get(f"/staff/orders/{order.order_code}").get_data(as_text=True)


# ================================================================== nhân viên: chấp nhận, từ chối
def test_approve_moves_order_to_returning(client, buyer, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    req = make_request(order)
    login("nv@test.com")
    body = client.post(f"/staff/returns/{req.id}/approve", data={"note": "Gửi hàng về kho trong 3 ngày"}, follow_redirects=True).get_data(as_text=True)
    assert "Đã chấp nhận yêu cầu" in body
    refresh(req, order)
    assert req.status == ReturnStatus.APPROVED and req.handled_by_account_id == staff_acc.id and req.resolution == "Gửi hàng về kho trong 3 ngày"
    assert order.status == OrderStatus.RETURNING
    last = order.status_history[-1]
    assert last.to_status == OrderStatus.RETURNING and last.changed_by_account_id == staff_acc.id and f"#{req.id}" in last.reason
    assert [a.action for a in db.session.scalars(db.select(AuditLog)).all()] == ["return.approve"]
    again = client.post(f"/staff/returns/{req.id}/approve", follow_redirects=True).get_data(as_text=True)
    assert "không còn ở trạng thái phù hợp" in again
    refresh(order)
    assert [h.to_status for h in order.status_history].count(OrderStatus.RETURNING) == 1


def test_reject_requires_reason_and_keeps_order_completed(client, buyer, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    req = make_request(order)
    login("nv@test.com")
    assert "ít nhất 5 ký tự" in client.post(f"/staff/returns/{req.id}/reject", data={"reason": "no"}, follow_redirects=True).get_data(as_text=True)
    refresh(req)
    assert req.status == ReturnStatus.PENDING
    client.post(f"/staff/returns/{req.id}/reject", data={"reason": "Sản phẩm đã qua sử dụng nhiều lần"}, follow_redirects=True)
    refresh(req, order)
    assert req.status == ReturnStatus.REJECTED and req.resolved_at is not None and order.status == OrderStatus.COMPLETED
    go(client, login, "buyer@test.com")
    page = client.get(f"/account/orders/{order.order_code}").get_data(as_text=True)
    assert "Từ chối" in page and "Sản phẩm đã qua sử dụng nhiều lần" in page
    assert "Yêu cầu đổi trả</a>" in page                                          # bị từ chối thì khách được gửi lại yêu cầu mới
    assert "Đã gửi yêu cầu đổi trả" in submit_return(client, order, qty=1, reason="Bổ sung ảnh lỗi, xin xem lại")


# ================================================================== nhân viên: hoàn tất đổi trả
def complete(client, req, accepted, refund="", note="", **extra):
    data = {f"accepted_{ri.id}": accepted[i] for i, ri in enumerate(req.items)}
    data.update(refund_amount=refund, note=note, **extra)
    return client.post(f"/staff/returns/{req.id}/complete", data=data, follow_redirects=True).get_data(as_text=True)


def approved_request(client, login, buyer, shop, staff_acc, carrier, qty=3, ret_qty=2):
    order, v = completed_order(buyer, shop, staff_acc, carrier, qty=qty)
    req = make_request(order, ret_qty)
    return_service.approve_return(req, staff_acc)
    login("nv@test.com")
    return order, v, req


def test_complete_return_restocks_only_accepted_and_refunds(client, buyer, shop, staff_acc, carrier, login):
    order, v, req = approved_request(client, login, buyer, shop, staff_acc, carrier)
    assert stock_of(v) == (7, 0)                                                  # đã xuất 3 khi bàn giao
    body = complete(client, req, [1], refund="250.000", note="Hàng về đủ, 1 cái bị rách")
    assert "Đã hoàn tất đổi trả" in body
    refresh(req, order)
    assert req.status == ReturnStatus.COMPLETED and req.resolved_at is not None and req.items[0].accepted_quantity == 1
    assert stock_of(v) == (8, 0)                                                  # chỉ cộng lại số lượng ĐẠT (1/2)
    tx = db.session.scalars(db.select(StockTransaction).where(StockTransaction.transaction_type == StockTxType.RETURN_IN)).one()
    assert (tx.stock_delta, tx.reserved_delta, tx.return_item_id, tx.created_by_account_id) == (1, 0, req.items[0].id, staff_acc.id)
    assert order.status == OrderStatus.RETURNED and order.status_history[-1].reason == f"Hoàn tất đổi trả #{req.id}"
    assert order.payment_status == PaymentStatus.REFUNDED
    assert "Hàng về đủ, 1 cái bị rách" in req.resolution and "Số lượng đạt: Áo A 1/2" in req.resolution and "Đã hoàn tiền 250.000 ₫" in req.resolution
    actions = [a.action for a in db.session.scalars(db.select(AuditLog).order_by(AuditLog.id)).all()]
    assert actions == ["return.approve", "return.refund", "return.complete"]
    refund_log = db.session.scalars(db.select(AuditLog).where(AuditLog.action == "return.refund")).one()
    assert refund_log.new_value["refund_amount"] == 250000 and refund_log.entity_name == "payment"


def test_complete_with_nothing_accepted_changes_no_stock(client, buyer, shop, staff_acc, carrier, login):
    order, v, req = approved_request(client, login, buyer, shop, staff_acc, carrier)
    complete(client, req, [0])
    refresh(req, order)
    assert req.status == ReturnStatus.COMPLETED and order.status == OrderStatus.RETURNED
    assert stock_of(v) == (7, 0)
    assert db.session.query(StockTransaction).filter_by(transaction_type=StockTxType.RETURN_IN).count() == 0
    assert order.payment_status == PaymentStatus.PAID                             # không nhập hoàn tiền thì giữ nguyên


@pytest.mark.parametrize("accepted,refund,message", [
    ("3", "", "từ 0 đến 2"), ("", "", "từ 0 đến 2"), ("abc", "", "từ 0 đến 2"),
    ("1", "abc", "Số tiền hoàn không hợp lệ"), ("1", "-5", "Số tiền hoàn không hợp lệ"), ("1", "1,5", "Số tiền hoàn không hợp lệ"),
    ("1", "99999999", "không được lớn hơn số tiền khách đã thanh toán"),
])
def test_complete_validation_changes_nothing(client, buyer, shop, staff_acc, carrier, login, accepted, refund, message):
    order, v, req = approved_request(client, login, buyer, shop, staff_acc, carrier)
    assert message in complete(client, req, [accepted], refund=refund)
    refresh(req, order)
    assert req.status == ReturnStatus.APPROVED and order.status == OrderStatus.RETURNING and req.items[0].accepted_quantity is None
    assert stock_of(v) == (7, 0) and order.payment_status == PaymentStatus.PAID


def test_refund_requires_collected_payment(client, buyer, shop, staff_acc, carrier, login):
    order, v, req = approved_request(client, login, buyer, shop, staff_acc, carrier)
    order.latest_payment.status = PaymentStatus.UNPAID
    db.session.commit()
    assert "chưa thu tiền" in complete(client, req, [1], refund="100000")
    refresh(req)
    assert req.status == ReturnStatus.APPROVED


def test_cannot_complete_before_approval_or_twice(client, buyer, shop, staff_acc, carrier, login):
    order, v = completed_order(buyer, shop, staff_acc, carrier)
    req = make_request(order)
    login("nv@test.com")
    assert "Chỉ hoàn tất được yêu cầu đã chấp nhận" in complete(client, req, [1])
    assert stock_of(v) == (7, 0)
    return_service.approve_return(req, staff_acc)
    complete(client, req, [2])
    assert stock_of(v) == (9, 0)
    assert "Chỉ hoàn tất được yêu cầu đã chấp nhận" in complete(client, req, [2])
    assert stock_of(v) == (9, 0)                                                  # không cộng kho lần hai
    assert db.session.query(StockTransaction).filter_by(transaction_type=StockTxType.RETURN_IN).count() == 1


def test_return_completion_rolls_back_on_stock_failure(client, buyer, shop, staff_acc, carrier, login, monkeypatch):
    """Lỗi giữa chừng (ví dụ ở bước cập nhật kho) không để lại trạng thái dở dang."""
    from app.services import inventory_service
    from app.services.errors import InventoryError
    order, v, req = approved_request(client, login, buyer, shop, staff_acc, carrier)
    monkeypatch.setattr(inventory_service, "receive_return_item", lambda *a, **k: (_ for _ in ()).throw(InventoryError("giả lập")))
    assert "Không cập nhật được tồn kho" in complete(client, req, [2])
    monkeypatch.undo()
    refresh(req, order)
    assert req.status == ReturnStatus.APPROVED and order.status == OrderStatus.RETURNING and stock_of(v) == (7, 0)
    assert req.items[0].accepted_quantity is None


# ================================================================== đánh giá sản phẩm
def review(client, order, item, rating=5, comment="Mặc rất thoải mái"):
    return client.post(f"/account/orders/{order.order_code}/review/{item.id}", data={"rating": rating, "comment": comment},
                       follow_redirects=True).get_data(as_text=True)


def test_review_flow_and_public_display(client, buyer, shop, staff_acc, carrier, login):
    order, v = completed_order(buyer, shop, staff_acc, carrier)
    item = order.items[0]
    go(client, login, "buyer@test.com")
    assert "Đánh giá sản phẩm" in client.get(f"/account/orders/{order.order_code}").get_data(as_text=True)
    assert "Mức độ hài lòng" in client.get(f"/account/orders/{order.order_code}/review/{item.id}").get_data(as_text=True)
    body = review(client, order, item, 4, "  Mặc rất thoải mái  ")
    assert "Cảm ơn bạn đã đánh giá" in body and "Bạn đã đánh giá" in body and "Đánh giá sản phẩm</a>" not in body
    saved = db.session.scalar(db.select(Review))
    assert (saved.sales_order_item_id, saved.rating, saved.comment) == (item.id, 4, "Mặc rất thoải mái")
    client.post("/auth/logout")
    product_page = client.get(f"/products/{v.product.slug}").get_data(as_text=True)
    assert "Mặc rất thoải mái" in product_page and "4.0</strong>/5" in product_page and "1 đánh giá" in product_page
    assert "Người Dùng" not in product_page and "buyer@test.com" not in product_page      # không lộ danh tính


def test_review_only_once_per_item(client, buyer, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    item = order.items[0]
    go(client, login, "buyer@test.com")
    review(client, order, item)
    assert "đã đánh giá sản phẩm này rồi" in review(client, order, item, 1, "đổi ý")
    assert db.session.query(Review).count() == 1 and db.session.scalar(db.select(Review)).rating == 5


@pytest.mark.parametrize("rating,comment,message", [
    (0, "ok", "từ 1 đến 5"), (6, "ok", "từ 1 đến 5"), ("abc", "ok", "từ 1 đến 5"), ("", "ok", "từ 1 đến 5"),
    (5, "x" * 1001, "tối đa 1000 ký tự")])
def test_review_validation(client, buyer, shop, staff_acc, carrier, login, rating, comment, message):
    order, _ = completed_order(buyer, shop, staff_acc, carrier)
    go(client, login, "buyer@test.com")
    resp = client.post(f"/account/orders/{order.order_code}/review/{order.items[0].id}", data={"rating": rating, "comment": comment})
    assert resp.status_code == 200 and message in resp.get_data(as_text=True)
    assert db.session.query(Review).count() == 0


def test_review_requires_delivered_order(client, buyer, shop, staff_acc, carrier, login):
    order, _ = new_order(buyer, shop)
    advance(order, staff_acc, carrier[0], "confirm", "pack", "ship")             # đang giao, chưa nhận hàng
    go(client, login, "buyer@test.com")
    body = client.get(f"/account/orders/{order.order_code}/review/{order.items[0].id}", follow_redirects=True).get_data(as_text=True)
    assert "sau khi đã nhận hàng" in body
    assert "Đánh giá sản phẩm" not in client.get(f"/account/orders/{order.order_code}").get_data(as_text=True)
    assert db.session.query(Review).count() == 0


def test_review_still_allowed_after_return(client, buyer, shop, staff_acc, carrier, login):
    order, v, req = approved_request(client, login, buyer, shop, staff_acc, carrier)
    complete(client, req, [2])
    go(client, login, "buyer@test.com")
    assert "Cảm ơn bạn đã đánh giá" in review(client, order, order.items[0])


def test_review_isolation(client, buyer, buyer2, shop, staff_acc, carrier, login):
    order, _ = completed_order(buyer, shop, staff_acc, carrier, name="A")
    other, _ = completed_order(buyer2, shop, staff_acc, carrier, name="B")
    go(client, login, "buyer2@test.com")
    assert client.get(f"/account/orders/{order.order_code}/review/{order.items[0].id}").status_code == 404      # đơn người khác
    assert client.get(f"/account/orders/{other.order_code}/review/{order.items[0].id}").status_code == 404      # dòng đơn không thuộc đơn này
    assert client.post(f"/account/orders/{order.order_code}/review/{order.items[0].id}", data={"rating": 5}).status_code == 404
    assert db.session.query(Review).count() == 0
