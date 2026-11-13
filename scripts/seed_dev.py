"""Script seed dữ liệu mẫu cho môi trường phát triển (development).

Chạy một lần để có ngay tài khoản, danh mục, sản phẩm và cấu hình cơ bản.
An toàn khi chạy nhiều lần — kiểm tra trước khi thêm, không tạo trùng.

Cách dùng:
    python scripts/seed_dev.py          (nếu đang ở thư mục gốc dự án)
    .venv/Scripts/python scripts/seed_dev.py
"""
import logging
import os
import sys

# Đảm bảo thư mục gốc dự án trong sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Tắt log APScheduler và werkzeug khi chạy script seed (không phải web server)
logging.getLogger("apscheduler").setLevel(logging.CRITICAL)
logging.getLogger("werkzeug").setLevel(logging.CRITICAL)

from app import create_app
from app.constants import (
    ROLE_ADMIN, ROLE_CUSTOMER, ROLE_STAFF,
    Perm, SettingKey,
)
from app.extensions import db
from app.models import (
    Account, AppSetting, Carrier, Category, Color, Permission,
    Product, ProductVariant, Province, Role, ShippingFeeRule, Size,
    Supplier, Ward,
)

# ============================================================ dữ liệu mẫu

ROLES = [ROLE_CUSTOMER, ROLE_STAFF, ROLE_ADMIN]

# Toàn bộ quyền trong hệ thống
ALL_PERMS = list(Perm.LABELS.keys())

ACCOUNTS = [
    dict(email="admin@sportzone.local",  password="Admin123456",  role=ROLE_ADMIN,
         full_name="Quản Trị Viên",   phone="0900000001"),
    dict(email="staff@sportzone.local",  password="Staff123456",  role=ROLE_STAFF,
         full_name="Nhân Viên A",     phone="0900000002"),
    dict(email="khach1@test.com",        password="Khach123456",  role=ROLE_CUSTOMER,
         full_name="Nguyễn Văn Khách",  phone="0900000003"),
    dict(email="khach2@test.com",        password="Khach123456",  role=ROLE_CUSTOMER,
         full_name="Trần Thị Mua",   phone="0900000004"),
]

CATEGORIES = [
    # (name, slug, parent_slug)
    ("Áo thể thao",   "ao-the-thao",    None),
    ("Quần thể thao", "quan-the-thao",   None),
    ("Áo chạy bộ",    "ao-chay-bo",     "ao-the-thao"),
    ("Áo tập gym",    "ao-tap-gym",      "ao-the-thao"),
    ("Quần jogger",   "quan-jogger",     "quan-the-thao"),
]

SIZES = [("S", 1), ("M", 2), ("L", 3), ("XL", 4), ("XXL", 5)]

COLORS = [
    ("Đen",       "#000000"),
    ("Trắng",     "#FFFFFF"),
    ("Xanh Navy", "#001F5B"),
    ("Đỏ",        "#CC0000"),
]

SETTINGS = [
    (SettingKey.PAYMENT_TIMEOUT_MINUTES, "15",  "Thời gian giữ hàng chờ thanh toán online (phút)"),
    (SettingKey.RETURN_WINDOW_DAYS,      "7",   "Thời hạn gửi yêu cầu đổi trả (ngày tính từ khi giao)"),
    (SettingKey.LOW_STOCK_THRESHOLD,     "5",   "Ngưỡng tồn kho thấp hiển thị cảnh báo"),
]


# ============================================================ helpers

def _get_or_create(model, defaults=None, **kwargs):
    """Lấy bản ghi theo kwargs; nếu chưa có thì tạo mới với defaults."""
    obj = db.session.scalar(
        db.select(model).filter_by(**kwargs)
    )
    if obj is None:
        params = dict(**kwargs)
        if defaults:
            params.update(defaults)
        obj = model(**params)
        db.session.add(obj)
        return obj, True
    return obj, False


# ============================================================ seed functions

def seed_roles_and_permissions():
    print("\n[1] Vai trò và quyền")
    roles = {}
    for name in ROLES:
        role, created = _get_or_create(Role, name=name)
        roles[name] = role
        print(f"    {'TẠO' if created else 'có '} Role: {name}")

    perms = {}
    for code in ALL_PERMS:
        perm, created = _get_or_create(Permission, code=code,
                                       defaults={"description": Perm.LABELS[code]})
        perms[code] = perm
        if created:
            print(f"    TẠO Permission: {code}")

    db.session.flush()

    # Gán quyền cho STAFF (Perm.STAFF_DEFAULT)
    staff_role = roles[ROLE_STAFF]
    existing_perm_codes = {p.code for p in staff_role.permissions}
    added = 0
    for code in Perm.STAFF_DEFAULT:
        if code not in existing_perm_codes:
            staff_role.permissions.append(perms[code])
            added += 1
    if added:
        print(f"    Gán {added} quyền mặc định cho STAFF")

    db.session.commit()
    return roles, perms


def seed_accounts(roles):
    print("\n[2] Tài khoản")
    result = []
    for acc_data in ACCOUNTS:
        email = acc_data["email"]
        existing = db.session.scalar(db.select(Account).filter_by(email=email))
        if existing:
            print(f"    có  {email}")
            result.append(existing)
            continue
        acc = Account(
            email=email,
            full_name=acc_data["full_name"],
            phone=acc_data["phone"],
            role=roles[acc_data["role"]],
        )
        acc.set_password(acc_data["password"])
        db.session.add(acc)
        print(f"    TẠO {email}")
        result.append(acc)
    db.session.commit()
    return result


def seed_geography():
    print("\n[3] Địa lý")
    hcm, c1 = _get_or_create(Province, name="TP. Hồ Chí Minh")
    hn,  c2 = _get_or_create(Province, name="Hà Nội")
    db.session.flush()
    w1, c3 = _get_or_create(Ward, province_id=hcm.id, name="Phường Bến Nghé")
    w2, c4 = _get_or_create(Ward, province_id=hcm.id, name="Phường Bến Thành")
    w3, c5 = _get_or_create(Ward, province_id=hn.id,  name="Phường Cửa Nam")
    db.session.commit()
    for obj, created in [(hcm, c1), (hn, c2), (w1, c3), (w2, c4), (w3, c5)]:
        print(f"    {'TẠO' if created else 'có '} {obj.__class__.__name__}: {obj.name}")
    return hcm, hn, w1


def seed_shipping(hcm_province):
    print("\n[4] Phí vận chuyển")
    # Mức mặc định (province_id = NULL)
    default_rule = db.session.scalar(
        db.select(ShippingFeeRule).where(ShippingFeeRule.province_id.is_(None))
    )
    if not default_rule:
        db.session.add(ShippingFeeRule(province_id=None, fee=30000, free_threshold=500000))
        print("    TẠO quy tắc mặc định: 30.000đ, miễn phí từ 500.000đ")
    else:
        print("    có  quy tắc mặc định")
    db.session.commit()


def seed_carrier():
    print("\n[5] Đơn vị vận chuyển")
    carrier, created = _get_or_create(Carrier, name="Giao Hàng Nhanh (GHN)")
    if created:
        print(f"    TẠO Carrier: {carrier.name}")
    else:
        print(f"    có  Carrier: {carrier.name}")
    db.session.commit()
    return carrier


def seed_supplier():
    print("\n[6] Nhà cung cấp")
    supplier, created = _get_or_create(
        Supplier, name="Xưởng May Thể Thao ABC",
        defaults={"phone": "0901234567", "email": "abc@supplier.com",
                  "address_detail": "123 Lê Lợi, Q.1, TP.HCM"})
    if created:
        print(f"    TẠO Supplier: {supplier.name}")
    else:
        print(f"    có  Supplier: {supplier.name}")
    db.session.commit()
    return supplier


def seed_catalog():
    print("\n[7] Danh mục, kích cỡ, màu sắc")
    # Sizes
    sizes = {}
    for name, order in SIZES:
        s, created = _get_or_create(Size, name=name, defaults={"sort_order": order})
        sizes[name] = s
        if created:
            print(f"    TẠO Size: {name}")
    # Colors
    colors = {}
    for name, hex_code in COLORS:
        c, created = _get_or_create(Color, name=name, defaults={"hex_code": hex_code})
        colors[name] = c
        if created:
            print(f"    TẠO Color: {name}")
    db.session.flush()

    # Categories
    cats = {}
    # Tạo parent trước
    for name, slug, parent_slug in CATEGORIES:
        if parent_slug is None:
            cat, created = _get_or_create(Category, slug=slug,
                                          defaults={"name": name})
            cats[slug] = cat
            if created:
                print(f"    TẠO Category: {name}")
    db.session.flush()
    # Tạo child
    for name, slug, parent_slug in CATEGORIES:
        if parent_slug is not None:
            parent = cats[parent_slug]
            cat, created = _get_or_create(Category, slug=slug,
                                          defaults={"name": name, "parent_category_id": parent.id})
            cats[slug] = cat
            if created:
                print(f"    TẠO Category: {name} (con của {parent.name})")
    db.session.commit()
    return sizes, colors, cats


def seed_products(sizes, colors, cats):
    print("\n[8] Sản phẩm mẫu")

    products_data = [
        {
            "name": "Áo chạy bộ nam DryFit",
            "slug": "ao-chay-bo-nam-dryfit",
            "category_slug": "ao-chay-bo",
            "price": 350_000,
            "description": "Áo chạy bộ chất liệu DryFit thoáng khí, thấm hút mồ hôi tốt. "
                           "Phù hợp cho chạy bộ, tập gym nhẹ.",
            "variants": [
                # (size, color, stock)
                ("S", "Đen", 15), ("M", "Đen", 20), ("L", "Đen", 10),
                ("S", "Trắng", 12), ("M", "Trắng", 18), ("L", "Trắng", 8),
                ("M", "Xanh Navy", 10),
            ],
        },
        {
            "name": "Quần jogger thể thao",
            "slug": "quan-jogger-the-thao",
            "category_slug": "quan-jogger",
            "price": 290_000,
            "description": "Quần jogger co giãn 4 chiều, cạp chun có dây rút, hai túi bên tiện lợi.",
            "variants": [
                ("S", "Đen", 10), ("M", "Đen", 25), ("L", "Đen", 15), ("XL", "Đen", 8),
                ("M", "Xanh Navy", 12), ("L", "Xanh Navy", 10),
            ],
        },
        {
            "name": "Áo tập gym nam Compression",
            "slug": "ao-tap-gym-nam-compression",
            "category_slug": "ao-tap-gym",
            "price": 420_000,
            "description": "Áo compression ôm sát, hỗ trợ cơ bắp khi tập luyện nặng.",
            "variants": [
                ("M", "Đen", 10), ("L", "Đen", 10), ("XL", "Đen", 5),
                ("M", "Đỏ", 8), ("L", "Đỏ", 6),
            ],
        },
    ]

    for pdata in products_data:
        existing = db.session.scalar(db.select(Product).filter_by(slug=pdata["slug"]))
        if existing:
            print(f"    có  Product: {pdata['name']}")
            continue

        cat = db.session.scalar(db.select(Category).filter_by(slug=pdata["category_slug"]))
        p = Product(
            name=pdata["name"], slug=pdata["slug"],
            category=cat, price=pdata["price"],
            description=pdata["description"],
        )
        db.session.add(p)
        db.session.flush()

        for i, (size_name, color_name, stock) in enumerate(pdata["variants"]):
            sku = f"{pdata['slug']}-{size_name.lower()}-{color_name.lower().replace(' ', '-')}"
            db.session.add(ProductVariant(
                product=p,
                size=sizes[size_name],
                color=colors[color_name],
                sku=sku,
                stock_quantity=stock,
                reserved_quantity=0,
            ))

        print(f"    TẠO Product: {pdata['name']} ({len(pdata['variants'])} biến thể)")

    db.session.commit()


def seed_settings():
    print("\n[9] Cấu hình hệ thống")
    for key, value, desc in SETTINGS:
        setting, created = _get_or_create(AppSetting, setting_key=key,
                                          defaults={"setting_value": value, "description": desc})
        if created:
            print(f"    TẠO Setting: {key} = {value}")
        else:
            print(f"    có  Setting: {key} = {setting.setting_value}")
    db.session.commit()


# ============================================================ main

def main():
    app = create_app("development")
    with app.app_context():
        db.create_all()
        print("=" * 55)
        print("  SportZone — Seed dữ liệu phát triển")
        print("=" * 55)

        roles, perms = seed_roles_and_permissions()
        accounts      = seed_accounts(roles)
        hcm, hn, w1   = seed_geography()
        seed_shipping(hcm)
        seed_carrier()
        seed_supplier()
        sizes, colors, cats = seed_catalog()
        seed_products(sizes, colors, cats)
        seed_settings()

        print("\n" + "=" * 55)
        print("  Tài khoản mẫu")
        print("=" * 55)
        print(f"  {'Email':<30} {'Mật khẩu':<16} {'Vai trò'}")
        print(f"  {'-'*30} {'-'*16} {'-'*12}")
        for acc_data in ACCOUNTS:
            role_label = {"ADMIN": "Quản trị viên", "STAFF": "Nhân viên",
                          "CUSTOMER": "Khách hàng"}[acc_data["role"]]
            print(f"  {acc_data['email']:<30} {acc_data['password']:<16} {role_label}")

        print("\n  URL ứng dụng: http://127.0.0.1:5000")
        print("  Admin:        http://127.0.0.1:5000/admin/")
        print("  Staff:        http://127.0.0.1:5000/staff/")
        print("=" * 55)


if __name__ == "__main__":
    main()
