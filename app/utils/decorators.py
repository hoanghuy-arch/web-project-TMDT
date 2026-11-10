"""Kiểm tra quyền ở BACKEND (không chỉ ẩn/hiện nút trên giao diện)."""
from functools import wraps

from flask import abort, current_app
from flask_login import current_user

from app.constants import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_STAFF


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if getattr(current_user, "role_code", None) not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


customer_required = roles_required(ROLE_CUSTOMER)
# Quản trị viên bao gồm toàn bộ quyền nghiệp vụ của nhân viên
staff_required = roles_required(ROLE_STAFF, ROLE_ADMIN)
admin_required = roles_required(ROLE_ADMIN)


def permission_required(code):
    """Yêu cầu quyền cụ thể (bảng role_permission). Quản trị viên luôn qua; khách hàng luôn bị chặn."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if getattr(current_user, "role_code", None) == ROLE_CUSTOMER or not current_user.has_permission(code):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
