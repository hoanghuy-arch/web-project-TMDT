from flask import Blueprint

bp = Blueprint("account", __name)

from app.account import routes, order_routes  # noqa: E402,F401
