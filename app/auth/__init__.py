from flask import Blueprint

bp = Blueprint("auth", __name)

from app.auth import routes  # noqa: E402,F401
