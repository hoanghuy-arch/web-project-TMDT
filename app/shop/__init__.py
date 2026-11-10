from flask import Blueprint

bp = Blueprint("shop", __name)

from app.shop import routes  # noqa: E402,F401
