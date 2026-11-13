"""Kiểm tra render template email Task 10 (không cần DB).

Các template kiểm tra:
  1. emails/order_status_changed.txt  — đủ trường, không lỗi Jinja
  2. emails/order_status_changed.html — đủ trường, không lỗi Jinja
  Mỗi template kiểm tra với nhiều trạng thái khác nhau.
"""
import sys
import types

# Mock app package để không kéo theo toàn bộ SQLAlchemy
pkg = types.ModuleType("app"); pkg.__path__ = ["app"]; sys.modules["app"] = pkg

from flask import Flask
from app.utils.formatters import register_filters

TEMPLATES_DIR = "app/templates"


def make_app():
    app = Flask("render_tasks", template_folder=TEMPLATES_DIR)
    app.secret_key = "x"
    app.config["SERVER_NAME"] = "localhost"
    register_filters(app)
    return app


def make_order_ctx(status_code, reason=None):
    """Tạo context giả để render template email thay đổi trạng thái."""
    from types import SimpleNamespace as NS
    account = NS(full_name="Nguyễn Văn A", email="kh@test.com")
    order = NS(order_code="DH-20261112-001", status=status_code, account=account)
    return dict(
        full_name=account.full_name,
        order=order,
        new_status_label={
            "SHIPPING": "Đang giao",
            "COMPLETED": "Hoàn thành",
            "CANCELLED": "Đã hủy",
            "RETURNING": "Đang đổi trả",
            "RETURNED": "Đã đổi trả",
        }.get(status_code, status_code),
        reason=reason,
        order_url="http://localhost/account/orders/DH-20261112-001",
    )


STATUSES_TO_TEST = ["SHIPPING", "COMPLETED", "CANCELLED", "RETURNING", "RETURNED"]


def run():
    app = make_app()
    ok_count = 0
    fail_count = 0

    with app.app_context():
        from flask import render_template

        for status in STATUSES_TO_TEST:
            ctx = make_order_ctx(status)

            # --- TXT ---
            try:
                html = render_template("emails/order_status_changed.txt", **ctx)
                assert ctx["order"].order_code in html, "Mã đơn không xuất hiện trong TXT"
                assert ctx["new_status_label"] in html, "Nhãn trạng thái không xuất hiện trong TXT"
                print(f"  OK  emails/order_status_changed.txt [{status}]")
                ok_count += 1
            except Exception as e:
                print(f"  FAIL emails/order_status_changed.txt [{status}]: {e}")
                fail_count += 1

            # --- HTML ---
            try:
                html = render_template("emails/order_status_changed.html", **ctx)
                assert ctx["order"].order_code in html, "Mã đơn không xuất hiện trong HTML"
                assert ctx["new_status_label"] in html, "Nhãn trạng thái không xuất hiện trong HTML"
                assert "<html" in html.lower(), "Không có thẻ <html>"
                print(f"  OK  emails/order_status_changed.html [{status}]")
                ok_count += 1
            except Exception as e:
                print(f"  FAIL emails/order_status_changed.html [{status}]: {e}")
                fail_count += 1

        # Với lý do (reason)
        for status in ["CANCELLED", "RETURNED"]:
            ctx = make_order_ctx(status, reason="Khách đổi ý")
            for ext in ["txt", "html"]:
                tmpl = f"emails/order_status_changed.{ext}"
                try:
                    out = render_template(tmpl, **ctx)
                    assert "Khách đổi ý" in out, f"Lý do không xuất hiện trong {ext}"
                    print(f"  OK  {tmpl} [{status}+reason]")
                    ok_count += 1
                except Exception as e:
                    print(f"  FAIL {tmpl} [{status}+reason]: {e}")
                    fail_count += 1

    print()
    if fail_count:
        print(f"FAIL: {fail_count} lỗi, {ok_count} đạt")
        sys.exit(1)
    else:
        print(f"OK: {ok_count} kiểm tra đạt, 0 lỗi")


if __name__ == "__main__":
    run()
