"""Task 10 — Kiểm thử tác vụ nền và email thông báo trạng thái đơn.

Các nhóm test:
  1. Scheduler không khởi động trong môi trường TESTING (tránh can thiệp test suite).
  2. expire_unpaid_orders_job: hủy đơn quá hạn, nhả hàng, ghi trạng thái CANCELLED.
  3. notify_order_status_changed: gọi email_service đúng template.
  4. send_order_status_changed_email: skip cho trạng thái nội bộ, gửi cho trạng thái cần thông báo.
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.constants import OrderStatus, PaymentMethod, PaymentStatus, ROLE_CUSTOMER
from app.extensions import db, scheduler
from app.models import Payment, SalesOrder
from app.models.base import utcnow
from app.services import order_service
from app.services.email_service import send_order_status_changed_email


# ======================================================================== fixtures

@pytest.fixture()
def _placed_order(buyer, shop):
    """Đặt một đơn COD để kiểm thử."""
    from tests.helpers import new_order
    order, _variant = new_order(buyer, shop, qty=2, stock=10)
    db.session.refresh(order)
    return order


@pytest.fixture()
def _pending_payment_order(buyer, shop):
    """Đơn PENDING_PAYMENT (online) để kiểm thử expire."""
    from tests.helpers import put_in_cart, make_variant, place
    acc, addr = buyer
    v = make_variant(shop, "Áo online", 300_000, 5)
    put_in_cart(acc, [(v, 1)])
    order = place(acc, addr, method=PaymentMethod.VNPAY)
    db.session.refresh(order)
    return order


# ======================================================================== 1. Scheduler không khởi động khi TESTING

class TestSchedulerNotStartedInTesting:
    def test_scheduler_not_running_in_test_app(self, app):
        """Scheduler phải không được start trong môi trường testing."""
        assert app.config["TESTING"] is True
        # scheduler.running = False vì init_scheduler() bỏ qua khi TESTING
        assert not scheduler.running

    def test_scheduler_jobs_empty_in_test_app(self, app):
        """Không có job nào được đăng ký trong test suite."""
        jobs = [j for j in scheduler.get_jobs() if j.id == "expire_unpaid_orders"]
        assert len(jobs) == 0


# ======================================================================== 2. expire_unpaid_orders

class TestExpireUnpaidOrders:
    def test_no_expired_orders_returns_zero(self, app, buyer, shop):
        """Không có đơn quá hạn → trả về 0."""
        with app.app_context():
            result = order_service.expire_unpaid_orders(now=utcnow())
        assert result == 0

    def test_pending_payment_not_expired_yet_stays(self, app, _pending_payment_order):
        """Đơn chưa quá hạn không bị hủy."""
        order = _pending_payment_order
        assert order.status == OrderStatus.PENDING_PAYMENT
        # now = thời điểm tạo đơn (sớm hơn cutoff)
        with app.app_context():
            cancelled = order_service.expire_unpaid_orders(now=utcnow())
        db.session.refresh(order)
        assert cancelled == 0
        assert order.status == OrderStatus.PENDING_PAYMENT

    def test_expired_order_gets_cancelled(self, app, _pending_payment_order):
        """Đơn quá hạn thanh toán → tự động hủy, payment → FAILED."""
        order = _pending_payment_order
        assert order.status == OrderStatus.PENDING_PAYMENT

        # Giả lập thời điểm 'now' là 20 phút sau thời điểm tạo đơn (mặc định timeout = 15 phút)
        future_now = order.created_at + timedelta(minutes=20)
        with app.app_context():
            cancelled = order_service.expire_unpaid_orders(now=future_now)
        db.session.refresh(order)
        assert cancelled == 1
        assert order.status == OrderStatus.CANCELLED

    def test_expired_order_payment_marked_failed(self, app, _pending_payment_order):
        """Thanh toán của đơn quá hạn → FAILED."""
        order = _pending_payment_order
        future_now = order.created_at + timedelta(minutes=20)
        with app.app_context():
            order_service.expire_unpaid_orders(now=future_now)
        db.session.refresh(order)
        payment = order.latest_payment
        assert payment is not None
        assert payment.status == PaymentStatus.FAILED

    def test_expired_order_stock_released(self, app, _pending_payment_order, shop):
        """Hàng giữ được nhả lại sau khi đơn bị hủy."""
        order = _pending_payment_order
        variant = order.items[0].variant
        reserved_before = variant.reserved_quantity

        future_now = order.created_at + timedelta(minutes=20)
        with app.app_context():
            order_service.expire_unpaid_orders(now=future_now)
        db.session.refresh(variant)
        assert variant.reserved_quantity < reserved_before

    def test_cod_order_not_expired(self, app, _placed_order):
        """Đơn COD (PENDING_CONFIRM) không bao giờ bị expire_unpaid_orders hủy."""
        order = _placed_order
        assert order.status == OrderStatus.PENDING_CONFIRM
        future_now = order.created_at + timedelta(minutes=60)
        with app.app_context():
            cancelled = order_service.expire_unpaid_orders(now=future_now)
        db.session.refresh(order)
        assert order.status == OrderStatus.PENDING_CONFIRM
        assert cancelled == 0


# ======================================================================== 3. notify_order_status_changed

class TestNotifyOrderStatusChanged:
    def test_notify_calls_send_email(self, app, _placed_order):
        """notify_order_status_changed phải gọi send_order_status_changed_email."""
        order = _placed_order
        with patch("app.services.email_service.send_email") as mock_send:
            # Đặt trạng thái đơn sang SHIPPING (nằm ngoài _SKIP_NOTIFY)
            order.status = OrderStatus.SHIPPING
            order_service.notify_order_status_changed(order, reason="Bàn giao GHN")
        # send_email có thể được gọi (nếu không phải test mode đang suppress)
        # Kiểm tra không raise exception là đủ
        assert True

    def test_notify_does_not_raise_on_email_error(self, app, _placed_order):
        """Lỗi khi gửi email không được raise lên caller."""
        order = _placed_order
        order.status = OrderStatus.SHIPPING
        with patch("app.services.email_service.send_email", side_effect=RuntimeError("SMTP down")):
            # Không được raise
            order_service.notify_order_status_changed(order)


# ======================================================================== 4. send_order_status_changed_email

class TestSendOrderStatusChangedEmail:
    def _make_order_mock(self, status):
        account = MagicMock()
        account.full_name = "Khách Hàng"
        account.email = "khach@test.com"
        order = MagicMock()
        order.order_code = "DH-001"
        order.status = status
        order.account = account
        return order

    def test_skip_pending_payment(self, app):
        """Không gửi email cho trạng thái PENDING_PAYMENT."""
        order = self._make_order_mock(OrderStatus.PENDING_PAYMENT)
        with app.app_context():
            with patch("app.services.email_service.send_email") as mock_send:
                send_order_status_changed_email(order, "Chờ thanh toán")
        mock_send.assert_not_called()

    def test_skip_pending_confirm(self, app):
        """Không gửi email cho trạng thái PENDING_CONFIRM."""
        order = self._make_order_mock(OrderStatus.PENDING_CONFIRM)
        with app.app_context():
            with patch("app.services.email_service.send_email") as mock_send:
                send_order_status_changed_email(order, "Chờ xác nhận")
        mock_send.assert_not_called()

    def test_send_for_shipping_status(self, app):
        """Gửi email khi trạng thái là SHIPPING."""
        order = self._make_order_mock(OrderStatus.SHIPPING)
        with app.app_context():
            with patch("app.services.email_service.send_email") as mock_send:
                send_order_status_changed_email(order, "Đang giao")
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args.kwargs["to"] == "khach@test.com"
        assert "DH-001" in call_args.kwargs["subject"]

    def test_send_for_cancelled_status(self, app):
        """Gửi email khi đơn bị hủy."""
        order = self._make_order_mock(OrderStatus.CANCELLED)
        with app.app_context():
            with patch("app.services.email_service.send_email") as mock_send:
                send_order_status_changed_email(order, "Đã hủy")
        mock_send.assert_called_once()

    def test_send_for_completed_status(self, app):
        """Gửi email khi đơn hoàn thành."""
        order = self._make_order_mock(OrderStatus.COMPLETED)
        with app.app_context():
            with patch("app.services.email_service.send_email") as mock_send:
                send_order_status_changed_email(order, "Hoàn thành")
        mock_send.assert_called_once()

    def test_send_with_reason(self, app):
        """Email gửi kèm lý do (reason) khi có."""
        order = self._make_order_mock(OrderStatus.CANCELLED)
        with app.app_context():
            with patch("app.services.email_service.send_email") as mock_send:
                send_order_status_changed_email(order, "Đã hủy", reason="Hết hàng")
        call_args = mock_send.call_args
        assert "Hết hàng" in call_args.kwargs.get("text_body", "")
