from datetime import timedelta

import pytest

from app import create_app
from app.constants import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_STAFF, EntityStatus, Perm
from app.extensions import db
from app.models import (Account, Carrier, Category, Color, Permission, Product, ProductVariant, Province, Role,
                        ShippingFeeRule, Size, Ward)
from app.models.base import utcnow


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def roles(app):
    """Ba vai trò mặc định, lấy theo tên."""
    rows = {name: Role(name=name) for name in (ROLE_CUSTOMER, ROLE_STAFF, ROLE_ADMIN)}
    db.session.add_all(rows.values())
    db.session.commit()
    return rows


@pytest.fixture()
def make_account(app, roles):
    """Tạo nhanh tài khoản: make_account(email=..., password=..., role=ROLE_STAFF)."""
    counter = {"n": 0}

    def _make(email=None, password="Matkhau123", role=ROLE_CUSTOMER, **kwargs):
        counter["n"] += 1
        acc = Account(
            email=email or f"user{counter['n']}@test.com",
            full_name=kwargs.pop("full_name", "Người Dùng"),
            phone=kwargs.pop("phone", "0912345678"),
            role=roles[role],
            **kwargs,
        )
        acc.set_password(password)
        db.session.add(acc)
        db.session.commit()
        return acc

    return _make


@pytest.fixture()
def shop(app, roles):
    d = {}
    d["ao"] = Category(name="Áo", slug="ao")
    d["quan"] = Category(name="Quần", slug="quan")
    d["ao_chay"] = Category(name="Áo chạy bộ", slug="ao-chay-bo", parent=d["ao"])
    d["an"] = Category(name="Ẩn", slug="an", is_active=False)
    d["s"], d["m"], d["l"] = Size(name="S", sort_order=1), Size(name="M", sort_order=2), Size(name="L", sort_order=3)
    d["den"], d["trang"] = Color(name="Đen", hex_code="#000000"), Color(name="Trắng", hex_code="#ffffff")
    db.session.add_all([d["ao"], d["quan"], d["ao_chay"], d["an"], d["s"], d["m"], d["l"], d["den"], d["trang"]])
    db.session.flush()
    d["_n"] = 0

    def make(name, price, category, variants, slug=None, status=EntityStatus.ACTIVE, description=None, age=0):
        d["_n"] += 1
        p = Product(name=name, slug=slug or f"sp-{d['_n']}", price=price, category=category, status=status,
                    description=description, created_at=utcnow() - timedelta(days=age))
        db.session.add(p)
        db.session.flush()
        for i, (size, color, stock, reserved) in enumerate(variants):
            db.session.add(ProductVariant(product=p, size=size, color=color, sku=f"{p.slug}-{i}",
                                          stock_quantity=stock, reserved_quantity=reserved))
        db.session.commit()
        return p

    d["make"] = make
    return d



@pytest.fixture()
def login(client):
    """login(email, password): đăng nhập qua form, trả về response."""
    def _login(email, password="Matkhau123"):
        resp = client.post("/auth/login", data=dict(email=email, password=password))
        assert resp.status_code == 302, "đăng nhập thất bại trong fixture"
        return resp
    return _login


# ---- dữ liệu dùng chung cho test đặt hàng và thanh toán ----
@pytest.fixture()
def geo(app):
    hcm, hn = Province(name="TP. Hồ Chí Minh"), Province(name="Hà Nội")
    w1, w2 = Ward(province=hcm, name="Phường Bến Nghé"), Ward(province=hn, name="Phường Cửa Nam")
    db.session.add_all([hcm, hn, w1, w2])
    db.session.commit()
    return dict(hcm=hcm, hn=hn, w1=w1, w2=w2)


@pytest.fixture()
def rules(geo):
    """Phí vận chuyển: mức mặc định 30.000 (miễn phí từ 500.000); Hà Nội 45.000, không miễn phí."""
    db.session.add_all([ShippingFeeRule(province_id=None, fee=30000, free_threshold=500000),
                        ShippingFeeRule(province_id=geo["hn"].id, fee=45000, free_threshold=None)])
    db.session.commit()


@pytest.fixture()
def buyer(make_account, geo, rules):
    from tests.helpers import new_buyer
    return new_buyer(make_account, geo["w1"], "buyer@test.com")


@pytest.fixture()
def buyer2(make_account, geo, rules):
    from tests.helpers import new_buyer
    return new_buyer(make_account, geo["w1"], "buyer2@test.com")


@pytest.fixture()
def staff_perms(roles):
    """Cấp cho vai trò nhân viên bộ quyền mặc định (Perm.STAFF_DEFAULT), giống script seed."""
    perms = [Permission(code=c, description=Perm.LABELS[c]) for c in Perm.STAFF_DEFAULT]
    db.session.add_all(perms)
    roles[ROLE_STAFF].permissions.extend(perms)
    db.session.commit()
    return perms


@pytest.fixture()
def staff(make_account, staff_perms, login):
    """Nhân viên (đủ quyền mặc định) đã đăng nhập."""
    acc = make_account(email="nv@test.com", role=ROLE_STAFF, full_name="Nhân Viên A")
    login("nv@test.com")
    return acc


@pytest.fixture()
def carrier(app):
    """(đơn vị vận chuyển đang hoạt động, đơn vị đã ngừng)."""
    active, inactive = Carrier(name="GHN"), Carrier(name="Hãng cũ", is_active=False)
    db.session.add_all([active, inactive])
    db.session.commit()
    return active, inactive
