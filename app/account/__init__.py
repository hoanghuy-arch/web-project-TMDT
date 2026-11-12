from flask import Blueprint

bp = Blueprint("account", __name__)

from app.account import routes, order_routes, return_routes  # noqa: E402,F401
