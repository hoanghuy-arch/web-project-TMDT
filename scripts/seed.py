#!/usr/bin/env python3
"""Seed dữ liệu ban đầu cho SportZone.

- tạo bảng nếu chưa có
- tạo role mặc định: CUSTOMER, STAFF, ADMIN
- tạo permission cơ bản
- tạo tài khoản quản trị viên mặc định
"""

import os
import sys
from time import sleep

from sqlalchemy.exc import OperationalError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app
from app.constants import Perm, ROLE_ADMIN, ROLE_CUSTOMER, ROLE_STAFF
from app.extensions import db
from app.models import Account, Permission, Role


def wait_for_db(app):
    """Chờ MySQL/SQLite sẵn sàng khi container khởi động đồng thời."""
    for _ in range(30):
        try:
            with app.app_context():
                db.session.execute(db.text("SELECT 1"))
                db.session.commit()
            return
        except OperationalError:
            sleep(1)
    raise RuntimeError("Cơ sở dữ liệu không sẵn sàng sau nhiều lần thử.")


def seed_roles_and_permissions():
    role_names = (ROLE_CUSTOMER, ROLE_STAFF, ROLE_ADMIN)
    roles = {}
    for name in role_names:
        role = db.session.execute(db.select(Role).filter_by(name=name)).scalar_one_or_none()
        if role is None:
            role = Role(name=name)
            db.session.add(role)
        roles[name] = role

    permissions = {}
    all_codes = tuple(sorted(Perm.LABELS.keys()))
    for code in all_codes:
        permission = db.session.execute(db.select(Permission).filter_by(code=code)).scalar_one_or_none()
        if permission is None:
            permission = Permission(code=code, description=Perm.LABELS[code])
            db.session.add(permission)
        permissions[code] = permission

    db.session.flush()

    staff_role = roles[ROLE_STAFF]
    admin_role = roles[ROLE_ADMIN]
    customer_role = roles[ROLE_CUSTOMER]

    staff_default = [permissions[code] for code in Perm.STAFF_DEFAULT]
    admin_all = list(permissions.values())

    staff_role.permissions = staff_default
    admin_role.permissions = admin_all
    customer_role.permissions = []

    db.session.commit()
    return roles, permissions


def seed_admin_account():
    admin_email = os.getenv("ADMIN_EMAIL", "admin@sportzone.local")
    admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")

    admin_role = db.session.execute(db.select(Role).filter_by(name=ROLE_ADMIN)).scalar_one_or_none()
    if admin_role is None:
        raise RuntimeError("Vai trò ADMIN chưa được tạo. Hãy chạy seed_roles_and_permissions trước.")

    account = db.session.execute(db.select(Account).filter_by(email=admin_email)).scalar_one_or_none()
    if account is None:
        account = Account(
            full_name="Quản trị viên",
            email=admin_email,
            phone="0900000000",
            role=admin_role,
            is_active=True,
        )
        db.session.add(account)
    account.role = admin_role
    account.full_name = account.full_name or "Quản trị viên"
    account.is_active = True
    account.set_password(admin_password)
    db.session.commit()

    print(f"Seed admin account: {admin_email} / {admin_password}")


def main():
    app = create_app()
    with app.app_context():
        wait_for_db(app)
        db.create_all()
        seed_roles_and_permissions()
        seed_admin_account()
        print("Seed completed successfully.")


if __name__ == "__main__":
    main()
