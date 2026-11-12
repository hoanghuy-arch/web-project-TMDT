from flask import Blueprint

bp = Blueprint("payment", __name__)

from app.payment import routes  # noqa: E402,F401
