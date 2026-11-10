"""Tiện ích bảo mật: token, băm token, chống open-redirect."""
import hashlib
import secrets
from urllib.parse import urlparse

from flask import redirect, request, url_for


def generate_token():
    """Token ngẫu nhiên an toàn (256 bit) gửi cho người dùng qua email."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token):
    """Chỉ lưu SHA-256 của token trong DB; lộ DB cũng không dùng được liên kết đặt lại."""
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def is_safe_url(target):
    """Chỉ cho phép chuyển hướng nội bộ sau đăng nhập.
    - Đường dẫn tương đối phải bắt đầu bằng đúng MỘT dấu '/' ('//host' và '///host' bị trình duyệt hiểu là site khác).
    - Cấm dấu '\\' và ký tự điều khiển (trình duyệt chuẩn hóa '\\' thành '/').
    - URL tuyệt đối chỉ chấp nhận khi cùng host và dùng http/https."""
    if not target:
        return False
    target = target.strip()
    if "\\" in target or any(ord(c) < 32 for c in target):
        return False
    if target.startswith("//"):
        return False
    parsed = urlparse(target)
    if not parsed.scheme and not parsed.netloc:
        return target.startswith("/")
    ref = urlparse(request.host_url)
    return parsed.scheme in ("http", "https") and parsed.netloc == ref.netloc


def redirect_back(default_endpoint, **values):
    """Quay lại trang người dùng vừa ở (Referer) nếu cùng site, ngược lại về trang mặc định."""
    target = request.referrer
    if target and is_safe_url(target):
        return redirect(target)
    return redirect(url_for(default_endpoint, **values))
