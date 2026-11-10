from flask import Blueprint

bp = Blueprint("staff", __name)

from app.staff import routes  # noqa: E402,F401
