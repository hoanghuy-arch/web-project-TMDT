"""Sinh mã đơn hàng và mã tham chiếu giao dịch."""
import secrets
from datetime import timedelta

# Bỏ các ký tự dễ nhầm (0/O, 1/I)
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_VN_OFFSET = timedelta(hours=7)


def generate_order_code(now_utc):
    """SZ + ngày (giờ Việt Nam, yyMMdd) + 6 ký tự ngẫu nhiên. Ví dụ: SZ261107K7M2QX."""
    local = now_utc + _VN_OFFSET
    return f"SZ{local:%y%m%d}" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def generate_txn_ref(order_code):
    """Mã tham chiếu giao dịch gửi cổng thanh toán: duy nhất cho từng lần thanh toán (kể cả thử lại)."""
    return f"{order_code}{secrets.token_hex(3).upper()}"
