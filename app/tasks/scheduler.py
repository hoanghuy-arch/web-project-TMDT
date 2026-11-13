"""Tác vụ nền chạy định kỳ (FR-HT01).

Khởi động cùng create_app(), tự dừng khi process kết thúc.
Không chạy trong môi trường Testing hoặc khi SCHEDULER_DISABLED=True.

Các tác vụ:
  - expire_unpaid_orders_job: hủy đơn online chưa thanh toán quá hạn (mỗi 1 phút).
"""
import logging

from app.extensions import db, scheduler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------- jobs


def _expire_unpaid_orders_job(app):
    """Chạy trong luồng riêng của APScheduler — phải tự tạo app context."""
    with app.app_context():
        try:
            from app.services import order_service
            cancelled = order_service.expire_unpaid_orders()
            if cancelled:
                logger.info("[scheduler] expire_unpaid_orders: đã hủy %d đơn quá hạn.", cancelled)
        except Exception:
            logger.exception("[scheduler] expire_unpaid_orders: lỗi không mong đợi.")
            try:
                db.session.rollback()
            except Exception:
                pass


# ---------------------------------------------------------------------- khởi động


def init_scheduler(app):
    """Đăng ký tác vụ và khởi động scheduler.

    Gọi một lần trong create_app() sau khi các extension đã được init.
    Không làm gì khi TESTING=True hoặc SCHEDULER_DISABLED=True để tránh
    can thiệp vào test suite.
    """
    if app.config.get("TESTING") or app.config.get("SCHEDULER_DISABLED"):
        app.logger.debug("[scheduler] Bỏ qua khởi động (TESTING hoặc SCHEDULER_DISABLED).")
        return

    # Hủy đơn online quá hạn thanh toán — chạy mỗi 1 phút
    scheduler.add_job(
        func=_expire_unpaid_orders_job,
        args=[app],
        trigger="interval",
        minutes=1,
        id="expire_unpaid_orders",
        replace_existing=True,          # an toàn khi hot-reload (Flask debug mode)
        misfire_grace_time=30,          # cho phép trễ tối đa 30 giây
    )

    if not scheduler.running:
        scheduler.start()
        app.logger.info(
            "[scheduler] Đã khởi động với %d tác vụ: %s",
            len(scheduler.get_jobs()),
            [j.id for j in scheduler.get_jobs()],
        )
