"""Kiểm tra dữ liệu dùng chung (hàm thuần, dễ kiểm thử). Form bọc lại thành validator của WTForms."""
import re

_PHONE_RE = re.compile(r"^0(3|5|7|8|9)\d{8}$")        # di động Việt Nam: 10 số, bắt đầu 03/05/07/08/09


def normalize_email(value):
    return (value or "").strip().lower()


def normalize_phone(value):
    """Bỏ khoảng trắng, dấu chấm, gạch ngang; đổi +84/84 đầu số thành 0."""
    s = re.sub(r"[\s.\-()]", "", value or "")
    if s.startswith("+84"):
        s = "0" + s[3:]
    elif s.startswith("84") and len(s) == 11:
        s = "0" + s[2:]
    return s


def is_valid_phone(value):
    return bool(_PHONE_RE.match(normalize_phone(value)))


def password_problem(password):
    """Trả về thông báo lỗi tiếng Việt nếu mật khẩu chưa đạt, ngược lại trả None."""
    password = password or ""
    if len(password) < 8:
        return "Mật khẩu phải có ít nhất 8 ký tự."
    if len(password) > 128:
        return "Mật khẩu tối đa 128 ký tự."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Mật khẩu phải gồm cả chữ và số."
    return None
