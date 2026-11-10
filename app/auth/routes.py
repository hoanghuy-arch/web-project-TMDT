"""Đăng ký, đăng nhập, đăng xuất, quên và đặt lại mật khẩu (FR-KH01, FR-KH02, FR-KH03). Công khai."""
from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.auth import bp
from app.auth.forms import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm
from app.constants import ROLE_ADMIN, ROLE_STAFF
from app.extensions import limiter
from app.services import auth_service
from app.services.auth_service import AuthStatus, EmailAlreadyUsedError
from app.utils.security import is_safe_url


def post_login_url(user):
    """Nhân viên/quản trị viên vào khu vực làm việc của mình (nếu đã có), khách hàng về trang chủ."""
    candidates = {ROLE_ADMIN: ("admin.dashboard", "staff.dashboard"), ROLE_STAFF: ("staff.dashboard",)}
    for endpoint in candidates.get(user.role_code, ()):
        if endpoint in current_app.view_functions:
            return url_for(endpoint)
    return url_for("shop.home")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_REGISTER"], methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(post_login_url(current_user))
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            account = auth_service.register_customer(
                form.full_name.data, form.email.data, form.phone.data, form.password.data)
        except EmailAlreadyUsedError:
            form.email.errors = list(form.email.errors) + ["Email này đã được đăng ký."]
        else:
            login_user(account)
            session.permanent = True
            flash("Đăng ký thành công. Chào mừng bạn đến với SportZone!", "success")
            return redirect(url_for("shop.home"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_LOGIN"], methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(post_login_url(current_user))
    form = LoginForm()
    next_url = request.args.get("next")
    if form.validate_on_submit():
        result = auth_service.authenticate(form.email.data, form.password.data)
        if result.status == AuthStatus.OK:
            login_user(result.account, remember=form.remember.data)
            session.permanent = True
            if next_url and is_safe_url(next_url):
                return redirect(next_url)
            return redirect(post_login_url(result.account))
        if result.status == AuthStatus.LOCKED:
            flash(f"Tài khoản tạm khóa do đăng nhập sai nhiều lần. Vui lòng thử lại sau "
                  f"{result.minutes_left} phút hoặc dùng chức năng quên mật khẩu.", "danger")
        elif result.status == AuthStatus.INACTIVE:
            flash("Tài khoản đã bị vô hiệu hóa. Vui lòng liên hệ cửa hàng.", "danger")
        else:
            flash("Email hoặc mật khẩu không đúng.", "danger")
    return render_template("auth/login.html", form=form, next_url=next_url)


@bp.route("/logout", methods=["POST"])      # POST + CSRF để trang web khác không tự đăng xuất người dùng
@login_required
def logout():
    logout_user()
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for("shop.home"))


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_FORGOT_PASSWORD"], methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("shop.home"))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        auth_service.request_password_reset(form.email.data)
        # Cùng một thông báo dù email có tồn tại hay không
        flash("Nếu email đã đăng ký, chúng tôi đã gửi hướng dẫn đặt lại mật khẩu. "
              "Vui lòng kiểm tra hộp thư (kể cả mục thư rác).", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["RATELIMIT_RESET_PASSWORD"], methods=["POST"])
def reset_password(token):
    if auth_service.get_valid_reset_token(token) is None:
        flash("Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn. Vui lòng yêu cầu lại.", "danger")
        return redirect(url_for("auth.forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        if auth_service.complete_password_reset(token, form.password.data):
            flash("Đặt lại mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới.", "success")
            return redirect(url_for("auth.login"))
        flash("Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.", "danger")
        return redirect(url_for("auth.forgot_password"))
    return render_template("auth/reset_password.html", form=form, token=token)
