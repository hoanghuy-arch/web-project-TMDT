"""Đối chiếu models với ERD trong tài liệu phân tích (Hình ERD Phân hệ A-G), không cần cài SQLAlchemy.
Kiểm tra: đúng tập cột từng bảng, đúng cột cho phép NULL, FK trỏ đúng, back_populates đối xứng.
Chạy: python scripts/check_models_static.py"""
import ast
import glob
import re
import sys

# Cột từng bảng, chép từ 7 ERD (thứ tự không quan trọng)
ERD = {
    # A
    "role": "id name",
    "permission": "id code description",
    "role_permission": "role_id permission_id",
    "account": "id role_id full_name email phone password_hash is_active failed_login_count locked_until created_at",
    "province": "id name",
    "ward": "id province_id name",
    "address": "id account_id ward_id recipient_name phone street_detail is_default is_active",
    "password_reset_token": "id account_id token_hash created_at expires_at used_at",
    # B
    "category": "id parent_category_id name slug is_active",
    "product": "id category_id name slug description price status created_at",
    "product_image": "id product_id url is_primary sort_order",
    "size": "id name sort_order",
    "color": "id name hex_code",
    "product_variant": "id product_id size_id color_id sku stock_quantity reserved_quantity status",
    # C
    "cart_item": "account_id product_variant_id quantity updated_at",
    "promotion": "id code discount_type discount_value min_order_value max_discount start_at end_at usage_limit status",
    "sales_order": "id order_code account_id address_id promotion_id status discount_amount shipping_fee note created_at updated_at",
    "sales_order_item": "id sales_order_id product_variant_id quantity unit_price",
    "sales_order_status_history": "id sales_order_id changed_by_account_id to_status reason changed_at",
    # D
    "shipping_fee_rule": "id province_id fee free_threshold is_active",
    "carrier": "id name is_active",
    "shipment": "sales_order_id carrier_id tracking_code shipped_at delivered_at",
    "payment": "id sales_order_id method status amount gateway_txn_ref paid_at created_at",
    # E
    "return_request": "id sales_order_id handled_by_account_id reason status resolution created_at resolved_at",
    "return_item": "id return_request_id sales_order_item_id quantity accepted_quantity",
    "review": "id sales_order_item_id rating comment created_at",
    # F
    "supplier": "id name contact_name phone email address_detail status",
    "stock_receipt": "id receipt_code supplier_id created_by_account_id status note created_at confirmed_at",
    "stock_receipt_item": "id stock_receipt_id product_variant_id ordered_quantity received_quantity unit_cost",
    "stock_transaction": ("id product_variant_id sales_order_id stock_receipt_item_id return_item_id "
                          "created_by_account_id transaction_type stock_delta reserved_delta note created_at"),
    # G
    "app_setting": "setting_key setting_value description updated_at",
    "audit_log": "id account_id action entity_name entity_id old_value new_value ip_address created_at",
}
ERD = {t: set(c.split()) for t, c in ERD.items()}

# Cột đánh dấu NULL trong ERD
ERD_NULLABLE = {
    "permission": {"description"},
    "account": {"locked_until"},
    "password_reset_token": {"used_at"},
    "category": {"parent_category_id"},
    "product": {"description"},
    "promotion": {"max_discount", "usage_limit"},
    "sales_order": {"promotion_id", "note"},
    "sales_order_status_history": {"changed_by_account_id", "reason"},
    "shipping_fee_rule": {"province_id", "free_threshold"},
    "shipment": {"delivered_at"},
    "payment": {"gateway_txn_ref", "paid_at"},
    "return_request": {"handled_by_account_id", "resolution", "resolved_at"},
    "return_item": {"accepted_quantity"},
    "review": {"comment"},
    "supplier": {"contact_name", "email", "address_detail"},
    "stock_receipt": {"note", "confirmed_at"},
    "stock_transaction": {"sales_order_id", "stock_receipt_item_id", "return_item_id",
                          "created_by_account_id", "note"},
    "app_setting": {"description"},
    "audit_log": {"account_id", "old_value", "new_value"},
}

tables, nullable_cols, class_of_table, fk_targets, rels = {}, {}, {}, [], []

for path in sorted(glob.glob("app/models/*.py")):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    mixin_cols = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "Table":
            cols = {a.args[0].value for a in node.args[1:]
                    if isinstance(a, ast.Call) and getattr(a.func, "attr", "") == "Column"}
            tables[node.args[0].value] = cols
            nullable_cols[node.args[0].value] = set()
        if isinstance(node, ast.ClassDef):
            tname, cols, nulls, bases = None, set(), set(), [getattr(b, "id", "") for b in node.bases]
            for st in node.body:
                if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name):
                    attr = st.targets[0].id
                    if attr == "__tablename__":
                        tname = st.value.value
                    elif isinstance(st.value, ast.Call):
                        fn = getattr(st.value.func, "attr", "")
                        if fn == "Column":
                            cols.add(attr)
                            kw = {k.arg: getattr(k.value, "value", None) for k in st.value.keywords}
                            if kw.get("nullable") is not False and not kw.get("primary_key"):
                                nulls.add(attr)
                        elif fn == "relationship":
                            target = st.value.args[0].value if st.value.args else None
                            bp = next((k.value.value for k in st.value.keywords if k.arg == "back_populates"), None)
                            rels.append((node.name, attr, target, bp))
            if "TimestampMixin" in bases:               # mixin: created_at, updated_at (NOT NULL)
                cols |= {"created_at", "updated_at"}
            if tname:
                tables[tname], nullable_cols[tname] = cols, nulls
                class_of_table[node.name] = tname
    for m in re.finditer(r'ForeignKey\("([a-z_]+)\.([a-z_]+)"', src):
        fk_targets.append((path, m.group(1), m.group(2)))
    for m in re.finditer(r'ForeignKeyConstraint\(\[.*?\],\s*\[(.*?)\]', src, re.S):
        for t in re.findall(r'"([a-z_]+)\.([a-z_]+)"', m.group(1)):
            fk_targets.append((path, t[0], t[1]))

errors = []
for t in sorted(set(ERD) - set(tables)):
    errors.append(f"Thiếu bảng theo ERD: {t}")
for t in sorted(set(tables) - set(ERD)):
    errors.append(f"Bảng không có trong ERD: {t}")

for t, expected in ERD.items():
    if t not in tables:
        continue
    got = tables[t]
    if got != expected:
        errors.append(f"[{t}] cột lệch ERD: thừa {sorted(got - expected)} | thiếu {sorted(expected - got)}")
    exp_null = ERD_NULLABLE.get(t, set())
    got_null = nullable_cols.get(t, set())
    if got_null != exp_null:
        errors.append(f"[{t}] cột NULL lệch ERD: model cho NULL thừa {sorted(got_null - exp_null)} "
                      f"| model thiếu NULL {sorted(exp_null - got_null)}")

for path, t, c in fk_targets:
    if t not in tables:
        errors.append(f"{path}: FK trỏ bảng không tồn tại {t}.{c}")
    elif c not in tables[t]:
        errors.append(f"{path}: FK trỏ cột không tồn tại {t}.{c}")

by_cls = {(c, a): (tgt, bp) for c, a, tgt, bp in rels}
for c, a, tgt, bp in rels:
    if tgt not in class_of_table:
        errors.append(f"relationship {c}.{a} -> lớp không tồn tại {tgt}")
    if bp:
        other = by_cls.get((tgt, bp))
        if not other or other[1] != a or other[0] != c:
            errors.append(f"back_populates {c}.{a} <-> {tgt}.{bp} không đối xứng")

total_cols = sum(len(v) for v in tables.values())
print(f"Bảng: {len(tables)}/{len(ERD)} | tổng số cột: {total_cols} | FK: {len(fk_targets)} | relationship: {len(rels)}")
if errors:
    print("LỖI:")
    [print(" -", e) for e in errors]
    sys.exit(1)
print("OK: 32 bảng khớp ERD từng cột, đúng cột NULL, FK và relationship nhất quán.")
