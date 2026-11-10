"""Kiểm thử xác thực: đăng ký, đăng nhập, khóa tạm, đặt lại mật khẩu, phân quyền (Task 3)."""
import re
from datetime import timedelta

import pytest

from app.constants import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_STAFF, Perm
from app.extensions import db, mail
from app.models import Account, Permission, PasswordResetToken
from app.models.base import utcnow
from app.utils.decorators import admin_required, permission_required, staff_required
from app.utils.security import hash_token, is_safe_url

PASSWORD = "Matkhau123"


def _register(client, **overrides):
    data = dict(full_name="Nguyễn Văn A", email="A@Test.com", phone="0912 345 678",
                password=PASSWORD, confirm_password=PASSWORD)
    data.update(overrides)
    return client.post("/auth/register", data=data, follow_redirects=False)


def _login(client, email, password=PASSWORD, **extra):
    return client.post("/auth/login", data=dict(email=email, password=password, **extra),
                       follow_redirects=False)


# ------------------------------------------------------------------ đăng ký
def test_register_creates_customer_and_logs_in(client, roles):
    resp = _register(client)
    assert resp.status_code == 302
    acc = db.session.execute(db.select(Account)).scalar_one()
    assert acc.email == "a@test.com"                    # chuẩn hóa chữ thường
    assert acc.phone == "0912345678"                    # chuẩn hóa số điện thoại
    assert acc.role_code == ROLE_CUSTOMER
    assert acc.password_hash != PASSWORD and acc.check_password(PASSWORD)
    assert client.get("/").status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == str(acc.id)      # đã đăng nhập


def test_register_duplicate_email_case_insensitive(client, roles, make_account):
    make_account(email="a@test.com")
    resp = _register(client, email="A@TEST.COM")
    assert resp.status_code == 200
    assert "Email này đã được đăng ký" in resp.get_data(as_text=True)
    assert db.session.query(Account).count() == 1


@pytest.mark.parametrize("field,value,message", [
    ("password", "abc12", "ít nhất 8 ký tự"),
    ("password", "chiconchu", "gồm cả chữ và số"),
    ("password", "123456789", "gồm cả chữ và số"),
    ("phone", "12345", "Số điện thoại không hợp lệ"),
    ("phone", "0212345678", "Số điện thoại không hợp lệ"),
    ("email", "khong-phai-email", "Email không hợp lệ"),
    ("full_name", "A", "từ 2 đến 100 ký tự"),
])
def test_register_validation(client, roles, field, value, message):
    overrides = {field: value}
    if field == "password":
        overrides["confirm_password"] = value
    resp = _register(client, **overrides)
    assert resp.status_code == 200
    assert message in resp.get_data(as_text=True)
    assert db.session.query(Account).count() == 0


def test_register_password_mismatch(client, roles):
    resp = _register(client, confirm_password="Khac12345")
    assert "không khớp" in resp.get_data(as_text=True)


def test_register_cannot_choose_role(client, roles):
    """Gửi kèm role_id/role giả mạo vẫn chỉ tạo khách hàng."""
    _register(client, role="ADMIN", role_id="3")
    assert db.session.execute(db.select(Account)).scalar_one().role_code == ROLE_CUSTOMER


# ------------------------------------------------------------------ đăng nhập
def test_login_success(client, make_account):
    make_account(email="u@test.com")
    resp = _login(client, "U@Test.com")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")


def test_login_failures_use_same_generic_message(client, make_account):
    make_account(email="u@test.com")
    wrong_pw = _login(client, "u@test.com", "Sai-mat-khau1").get_data(as_text=True)
    unknown = _login(client, "khong-co@test.com").get_data(as_text=True)
    assert "Email hoặc mật khẩu không đúng" in wrong_pw
    assert "Email hoặc mật khẩu không đúng" in unknown


def test_account_locked_after_5_failed_logins(client, make_account):
    acc = make_account(email="u@test.com")
    for _ in range(5):
        _login(client, "u@test.com", "Sai-mat-khau1")
    db.session.refresh(acc)
    assert acc.is_locked
    # Đã khóa: đúng mật khẩu vẫn không vào được
    body = _login(client, "u@test.com", PASSWORD).get_data(as_text=True)
    assert "tạm khóa" in body
    # Hết thời gian khóa thì đăng nhập lại được và bộ đếm được xóa
    acc.locked_until = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert _login(client, "u@test.com", PASSWORD).status_code == 302
    db.session.refresh(acc)
    assert acc.failed_login_count == 0 and acc.locked_until is None


def test_failed_count_resets_on_success(client, make_account):
    acc = make_account(email="u@test.com")
    for _ in range(3):
        _login(client, "u@test.com", "Sai-mat-khau1")
    _login(client, "u@test.com", PASSWORD)
    client.post("/auth/logout")
    db.session.refresh(acc)
    assert acc.failed_login_count == 0


def test_inactive_account_cannot_login(client, make_account):
    make_account(email="u@test.com", is_active=False)
    body = _login(client, "u@test.com").get_data(as_text=True)
    assert "vô hiệu hóa" in body


def test_logout_requires_post(client, make_account):
    make_account(email="u@test.com")
    _login(client, "u@test.com")
    assert client.get("/auth/logout").status_code == 405
    assert client.post("/auth/logout").status_code == 302
    with client.session_transaction() as sess:
        assert "_user_id" not in sess


@pytest.mark.parametrize("target", ["https://evil.com/x", "//evil.com", "///evil.com", "/%5Cevil.com",
                                    "javascript:alert(1)"])
def test_login_blocks_open_redirect(client, make_account, target):
    make_account(email="u@test.com")
    resp = client.post("/auth/login?next=" + target, data=dict(email="u@test.com", password=PASSWORD))
    assert "evil.com" not in resp.headers["Location"]


def test_login_follows_safe_next(client, make_account):
    make_account(email="u@test.com")
    resp = client.post("/auth/login?next=/account/orders", data=dict(email="u@test.com", password=PASSWORD))
    assert resp.headers["Location"].endswith("/account/orders")


def test_is_safe_url(app):
    with app.test_request_context("/", base_url="http://localhost"):
        assert is_safe_url("/account/orders")
        assert not is_safe_url("https://evil.com/x")
        assert not is_safe_url("//evil.com")
        assert not is_safe_url("///evil.com")           # trình duyệt hiểu là //evil.com
        assert not is_safe_url("/\\evil.com")            # '\\' bị chuẩn hóa thành '/'
        assert not is_safe_url("http://localhost.evil.com/")
        assert not is_safe_url("")


# ------------------------------------------------------------------ đặt lại mật khẩu
def _extract_token(message):
    return re.search(r"/auth/reset-password/([\w\-]+)", message.body).group(1)


def test_forgot_password_unknown_email_same_response_no_mail(client, roles):
    with mail.record_messages() as outbox:
        resp = client.post("/auth/forgot-password", data=dict(email="khong-co@test.com"), follow_redirects=True)
    assert "Nếu email đã đăng ký" in resp.get_data(as_text=True)
    assert outbox == []


def test_password_reset_full_flow(client, make_account):
    acc = make_account(email="u@test.com")
    acc.failed_login_count, acc.locked_until = 0, utcnow() + timedelta(minutes=10)   # đang bị khóa
    db.session.commit()

    with mail.record_messages() as outbox:
        resp = client.post("/auth/forgot-password", data=dict(email="U@test.com"), follow_redirects=True)
    assert "Nếu email đã đăng ký" in resp.get_data(as_text=True)
    assert len(outbox) == 1 and outbox[0].recipients == ["u@test.com"]
    token = _extract_token(outbox[0])

    # DB chỉ lưu bản băm của token
    rows = db.session.scalars(db.select(PasswordResetToken)).all()
    assert len(rows) == 1 and rows[0].token_hash == hash_token(token) and token not in rows[0].token_hash

    assert client.get(f"/auth/reset-password/{token}").status_code == 200
    resp = client.post(f"/auth/reset-password/{token}",
                       data=dict(password="MatKhauMoi99", confirm_password="MatKhauMoi99"))
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/auth/login")

    db.session.refresh(acc)
    assert acc.check_password("MatKhauMoi99") and not acc.check_password(PASSWORD)
    assert acc.locked_until is None                       # đặt lại mật khẩu cũng mở khóa
    assert _login(client, "u@test.com", "MatKhauMoi99").status_code == 302

    # Token chỉ dùng một lần
    client.post("/auth/logout")
    resp = client.post(f"/auth/reset-password/{token}",
                       data=dict(password="LanHai12345", confirm_password="LanHai12345"))
    assert resp.status_code == 302 and "forgot-password" in resp.headers["Location"]


def test_reset_token_expired(client, make_account):
    make_account(email="u@test.com")
    with mail.record_messages() as outbox:
        client.post("/auth/forgot-password", data=dict(email="u@test.com"))
    token = _extract_token(outbox[0])
    row = db.session.execute(db.select(PasswordResetToken)).scalar_one()
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    resp = client.get(f"/auth/reset-password/{token}", follow_redirects=True)
    assert "không hợp lệ hoặc đã hết hạn" in resp.get_data(as_text=True)


def test_reset_invalid_token(client, roles):
    resp = client.get("/auth/reset-password/token-khong-ton-tai")
    assert resp.status_code == 302


def test_new_reset_request_invalidates_old_token(app, client, make_account):
    app.config["PASSWORD_RESET_COOLDOWN_SECONDS"] = 0
    make_account(email="u@test.com")
    with mail.record_messages() as outbox:
        client.post("/auth/forgot-password", data=dict(email="u@test.com"))
        client.post("/auth/forgot-password", data=dict(email="u@test.com"))
    old, new = _extract_token(outbox[0]), _extract_token(outbox[1])
    assert client.get(f"/auth/reset-password/{old}").status_code == 302     # token cũ vô hiệu
    assert client.get(f"/auth/reset-password/{new}").status_code == 200


def test_reset_request_cooldown(client, make_account):
    make_account(email="u@test.com")
    with mail.record_messages() as outbox:
        client.post("/auth/forgot-password", data=dict(email="u@test.com"))
        client.post("/auth/forgot-password", data=dict(email="u@test.com"))
    assert len(outbox) == 1                                  # lần hai trong 60 giây bị bỏ qua


def test_password_strength_enforced_on_reset(client, make_account):
    make_account(email="u@test.com")
    with mail.record_messages() as outbox:
        client.post("/auth/forgot-password", data=dict(email="u@test.com"))
    token = _extract_token(outbox[0])
    resp = client.post(f"/auth/reset-password/{token}", data=dict(password="yeu", confirm_password="yeu"))
    assert resp.status_code == 200 and "ít nhất 8 ký tự" in resp.get_data(as_text=True)


# ------------------------------------------------------------------ phân quyền ở backend
@pytest.fixture()
def guarded(app):
    app.add_url_rule("/_t/staff", "t_staff", staff_required(lambda: "ok"))
    app.add_url_rule("/_t/admin", "t_admin", admin_required(lambda: "ok"))
    app.add_url_rule("/_t/stock", "t_stock", permission_required(Perm.STOCK_RECEIPT)(lambda: "ok"))
    return app


@pytest.mark.parametrize("role,path,status", [
    (ROLE_CUSTOMER, "/_t/staff", 403), (ROLE_STAFF, "/_t/staff", 200), (ROLE_ADMIN, "/_t/staff", 200),
    (ROLE_CUSTOMER, "/_t/admin", 403), (ROLE_STAFF, "/_t/admin", 403), (ROLE_ADMIN, "/_t/admin", 200),
])
def test_role_guards(guarded, client, make_account, role, path, status):
    make_account(email="u@test.com", role=role)
    _login(client, "u@test.com")
    assert client.get(path).status_code == status


def test_guards_redirect_anonymous_to_login(guarded, client, roles):
    resp = client.get("/_t/staff")
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


def test_permission_required(guarded, client, make_account, roles):
    perm = Permission(code=Perm.STOCK_RECEIPT)
    roles[ROLE_STAFF].permissions.append(perm)
    db.session.commit()
    make_account(email="nv@test.com", role=ROLE_STAFF)
    make_account(email="admin@test.com", role=ROLE_ADMIN)
    make_account(email="kh@test.com", role=ROLE_CUSTOMER)

    _login(client, "nv@test.com"); assert client.get("/_t/stock").status_code == 200
    client.post("/auth/logout")
    _login(client, "admin@test.com"); assert client.get("/_t/stock").status_code == 200
    client.post("/auth/logout")
    _login(client, "kh@test.com"); assert client.get("/_t/stock").status_code == 403


def test_staff_without_permission_forbidden(guarded, client, make_account):
    make_account(email="nv@test.com", role=ROLE_STAFF)       # staff chưa được cấp quyền nào
    _login(client, "nv@test.com")
    assert client.get("/_t/stock").status_code == 403


def test_deactivated_user_is_logged_out_on_next_request(client, make_account):
    acc = make_account(email="u@test.com")
    _login(client, "u@test.com")
    acc.is_active = False
    db.session.commit()
    resp = client.post("/auth/logout")               # user_loader trả None -> coi như chưa đăng nhập
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]
