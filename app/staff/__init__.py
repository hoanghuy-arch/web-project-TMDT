from flask import Blueprint

bp = Blueprint("staff", __name__)

from app.staff import routes, return_routes, stock_routes  # noqa: E402,F401
