"""Môi trường render template dùng chung cho các script kiểm tra giao diện (không cần DB/SQLAlchemy).
Dựng một app Flask tối giản với đủ endpoint như app thật, cùng các đối tượng giả (form, phân trang, người dùng)."""
import sys
import types

pkg = types.ModuleType("app"); pkg.__path__ = ["app"]; sys.modules["app"] = pkg    # bỏ qua app/__init__.py

from flask import Blueprint, Flask
from markupsafe import Markup

from app.utils.formatters import register_filters

RULES = {
    "shop": {"home": "/", "product_list": "/products", "category": "/category/<slug>",
             "product_detail": "/products/<slug>"},
    "auth": {"login": "/auth/login", "register": "/auth/register", "logout": "/auth/logout",
             "forgot_password": "/auth/forgot-password", "reset_password": "/auth/reset-password/<token>"},
    "payment": {"start": "/payment/start/<order_code>", "vnpay_return": "/payment/vnpay/return",
                "vnpay_ipn": "/payment/vnpay/ipn", "mock_pay": "/payment/mock/pay",
                "mock_complete": "/payment/mock/complete"},
    "staff": {"dashboard": "/staff/", "orders": "/staff/orders", "order_detail": "/staff/orders/<order_code>",
              "order_confirm": "/staff/orders/<order_code>/confirm", "order_pack": "/staff/orders/<order_code>/pack",
              "order_cancel": "/staff/orders/<order_code>/cancel", "order_ship": "/staff/orders/<order_code>/ship",
              "order_deliver": "/staff/orders/<order_code>/deliver", "order_incident": "/staff/orders/<order_code>/incident"},
    "account": {"profile": "/account/profile", "change_password": "/account/password",
                "addresses": "/account/addresses", "address_new": "/account/addresses/new",
                "address_edit": "/account/addresses/<int:address_id>/edit",
                "address_default": "/account/addresses/<int:address_id>/default",
                "address_delete": "/account/addresses/<int:address_id>/delete",
                "wards_api": "/account/api/wards", "cart": "/account/cart", "cart_add": "/account/cart/add",
                "cart_update": "/account/cart/update", "cart_remove": "/account/cart/remove",
                "cart_clean": "/account/cart/clean", "checkout": "/account/checkout", "orders": "/account/orders",
                "order_detail": "/account/orders/<order_code>", "order_cancel": "/account/orders/<order_code>/cancel"},
}


_STATE = {"user": None}


def make_app():
    app = Flask("render", template_folder="app/templates", static_folder="app/static")
    app.secret_key = "x"
    # Giống Flask-Login thật: current_user được cấp qua context processor, KHÔNG phải biến toàn cục của Jinja.
    # (Macro import không kèm "with context" sẽ không thấy biến này, đây là lỗi hay gặp.)
    app.context_processor(lambda: {"current_user": _STATE["user"]})
    for name, rules in RULES.items():
        bp = Blueprint(name, __name__)
        for endpoint, rule in rules.items():
            bp.add_url_rule(rule, endpoint, lambda **k: "", methods=["GET", "POST"])
        app.register_blueprint(bp)
    register_filters(app)
    return app


def set_user(app, user):
    _STATE["user"] = user
    app.jinja_env.globals.update(csrf_token=lambda: "T")        # Flask-WTF đặt csrf_token là biến toàn cục


class Anon:
    is_authenticated = False


class Customer:
    is_authenticated = True
    role_code = "CUSTOMER"
    full_name = "Nguyễn <b>Văn</b> A"
    email = "kh@test.com"
    permissions = ()

    def has_permission(self, code):
        return code in self.permissions


class Staff(Customer):
    role_code = "STAFF"
    permissions = ("order.view", "order.process", "shipment.update")


class Lbl:
    text = ""


class Fld:
    """Trường form giả: __call__ trả Markup như WTForms thật."""
    def __init__(self, id_, label, errors=(), value=""):
        self.id, self.errors, self.data, self.value = id_, list(errors), value, value
        self.label = Lbl()
        self.label.text = label

    def __call__(self, **kw):
        attrs = " ".join(f'{k}="{v}"' for k, v in kw.items())
        return Markup(f'<input id="{self.id}" name="{self.id}" value="{self.value}" {attrs}>')


class SelectFld(Fld):
    def __init__(self, id_, label, options, selected=0, errors=()):
        super().__init__(id_, label, errors)
        self.options, self.selected = options, selected

    def __call__(self, **kw):
        attrs = " ".join(f'{k}="{v}"' for k, v in kw.items())
        opts = "".join(f'<option {"selected " if v == self.selected else ""}value="{v}">{t}</option>' for v, t in self.options)
        return Markup(f'<select id="{self.id}" name="{self.id}" {attrs}>{opts}</select>')


class Form:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def hidden_tag(self):
        return Markup('<input type="hidden" name="csrf_token" value="T">')


class Pag:
    def __init__(self, items, total, page, pages):
        self.items, self.total, self.page, self.pages = items, total, page, pages
    has_prev = property(lambda s: s.page > 1)
    has_next = property(lambda s: s.page < s.pages)
    prev_num = property(lambda s: s.page - 1)
    next_num = property(lambda s: s.page + 1)

    def iter_pages(self, **_):
        last = 0
        for n in range(1, self.pages + 1):
            if n <= 1 or n > self.pages - 1 or abs(n - self.page) <= 2:
                if last and n - last > 1:
                    yield None
                yield n
                last = n


class Checker:
    def __init__(self):
        self.count = 0

    def __call__(self, cond, msg):
        assert cond, msg
        self.count += 1
