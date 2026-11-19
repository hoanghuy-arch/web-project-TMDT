#!/usr/bin/env python3
"""Nạp dữ liệu hành chính Việt Nam mới (34 tỉnh/thành + 3321 xã/phường) từ file JSON nội bộ.

Nguồn: open-admin-data/vietnam-administrative-divisions (CC BY 4.0)
  - Cấu trúc mới: Chỉ còn 2 cấp (Tỉnh/Thành phố → Xã/Phường), không còn Quận/Huyện.
  - 34 Tỉnh/Thành phố (phản ánh sáp nhập hành chính 2025)
  - 3321 Xã/Phường

File đọc:
  data/administrative/vietnam/all-province.json
  data/administrative/vietnam/all-ward.json

Chiến lược:
  - Nếu chưa có địa chỉ/đơn hàng nào tham chiếu → Xóa sạch dữ liệu cũ, nạp mới.
  - Nếu đã có địa chỉ → Chỉ thêm mới, không xóa dữ liệu cũ.

Cách dùng:
    python scripts/import_new_provinces.py              # nạp thật
    python scripts/import_new_provinces.py --dry-run    # xem trước, không ghi DB
    python scripts/import_new_provinces.py --force      # buộc xóa sạch rồi nạp lại
"""
import argparse
import json
import logging
import sys
from pathlib import Path

logging.getLogger("apscheduler").setLevel(logging.CRITICAL)
logging.getLogger("werkzeug").setLevel(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROVINCE_FILE = ROOT / "data" / "administrative" / "vietnam" / "all-province.json"
WARD_FILE     = ROOT / "data" / "administrative" / "vietnam" / "all-ward.json"

from app import create_app
from app.extensions import db
from app.models import Address, Province, Ward


def load_json(path: Path) -> list:
    if not path.exists():
        print(f"[!] Không tìm thấy file: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    if isinstance(data, list):
        return data
    print(f"[!] File {path.name} không đúng định dạng.")
    sys.exit(1)


def run(dry_run: bool = False, force: bool = False):
    label = "[DRY-RUN] " if dry_run else ""
    print(f"\n{label}Nạp dữ liệu hành chính Việt Nam mới (34 tỉnh / 3321 xã phường)")
    print("=" * 65)

    # 1. Đọc file JSON
    print("[1/4] Đọc file dữ liệu...")
    provinces_raw = load_json(PROVINCE_FILE)
    wards_raw     = load_json(WARD_FILE)
    print(f"      → {len(provinces_raw)} tỉnh/thành phố, {len(wards_raw)} phường/xã")

    # Kiểm tra nhanh cấu trúc
    for label_str, items in [("Tỉnh", provinces_raw), ("Phường", wards_raw)]:
        s = items[0]
        if "id" not in s or "name" not in s:
            print(f"[!] File {label_str} không đúng cấu trúc: {s}")
            sys.exit(1)

    # 2. Kiểm tra dữ liệu hiện có
    print("\n[2/4] Kiểm tra dữ liệu hiện có...")
    cur_prov  = db.session.query(Province).count()
    cur_ward  = db.session.query(Ward).count()
    cur_addr  = db.session.query(Address).count()
    print(f"      Hiện có: {cur_prov} tỉnh, {cur_ward} phường/xã, {cur_addr} địa chỉ")

    # Quyết định có xóa sạch không
    can_clear = cur_addr == 0  # An toàn khi chưa có địa chỉ nào
    will_clear = (force or can_clear) and not dry_run

    if not dry_run:
        if will_clear and cur_prov > 0:
            print(f"      → Xóa {cur_ward} phường/xã và {cur_prov} tỉnh cũ trước khi nạp mới...")
            db.session.execute(db.delete(Ward))
            db.session.execute(db.delete(Province))
            db.session.commit()
            print("      → Đã xóa xong.")
        elif cur_addr > 0 and not force:
            print(f"      → Đã có {cur_addr} địa chỉ, chỉ thêm tỉnh/phường chưa có (không xóa cũ).")

    # 3. Nạp Tỉnh/Thành phố
    print("\n[3/4] Nạp Tỉnh/Thành phố...")
    # Map: code (string từ JSON) → Province.id trong DB
    # Build cả map tạm để dùng cho cả dry-run
    code_to_name: dict[str, str] = {}
    for item in provinces_raw:
        code = str(item["id"])
        name = item["name"]["local"].strip() if isinstance(item.get("name"), dict) else str(item["name"]).strip()
        code_to_name[code] = name

    code_to_db_id: dict[str, int] = {}
    prov_new = prov_skip = 0

    for code, name in code_to_name.items():
        # Kiểm tra đã tồn tại chưa (theo tên)
        existing = db.session.query(Province).filter_by(name=name).first()
        if existing:
            code_to_db_id[code] = existing.id
            prov_skip += 1
            continue

        if not dry_run:
            new_prov = Province(name=name)
            db.session.add(new_prov)
            db.session.flush()
            code_to_db_id[code] = new_prov.id
        else:
            # Dry-run: dùng id tạm để simulate
            code_to_db_id[code] = -(len(code_to_db_id) + 1)
        prov_new += 1

    if not dry_run:
        db.session.commit()

    print(f"      → Thêm mới: {prov_new}, Đã có (bỏ qua): {prov_skip}")

    # 4. Nạp Phường/Xã
    print("\n[4/4] Nạp Phường/Xã...")
    ward_new = ward_skip = ward_no_parent = 0
    wards_to_add: list[Ward] = []

    # Dùng set để detect trùng tên trong cùng tỉnh
    seen_keys: set[tuple] = set()
    if not dry_run:
        # Lấy sẵn các ward đã có để tránh trùng
        for w in db.session.query(Ward).all():
            seen_keys.add((w.province_id, w.name))

    for item in wards_raw:
        parent = item.get("parent")
        if not parent or "id" not in parent:
            ward_no_parent += 1
            continue

        p_code = str(parent["id"])
        if p_code not in code_to_db_id:
            ward_no_parent += 1
            continue

        province_id = code_to_db_id[p_code]
        name = item["name"]["local"].strip() if isinstance(item.get("name"), dict) else str(item["name"]).strip()

        if (province_id, name) in seen_keys:
            ward_skip += 1
            continue

        if not dry_run:
            wards_to_add.append(Ward(province_id=province_id, name=name))
            seen_keys.add((province_id, name))
        ward_new += 1

    if not dry_run and wards_to_add:
        batch = 500
        for i in range(0, len(wards_to_add), batch):
            db.session.add_all(wards_to_add[i:i + batch])
            db.session.flush()
        db.session.commit()

    print(f"      → Thêm mới: {ward_new}, Đã có (bỏ qua): {ward_skip}", end="")
    if ward_no_parent:
        print(f", Không xác định tỉnh cha: {ward_no_parent}", end="")
    print()

    # Báo cáo cuối
    print("\n" + "=" * 65)
    if not dry_run:
        total_p = db.session.query(Province).count()
        total_w = db.session.query(Ward).count()
        print(f"Kết quả cuối: {total_p} tỉnh/thành phố, {total_w} phường/xã trong database")
        print("→ Hoàn tất! Khởi động lại server để áp dụng.")
    else:
        print(f"[Dry-run] Sẽ thêm: {prov_new} tỉnh, {ward_new} phường/xã (không ghi DB)")


def main():
    parser = argparse.ArgumentParser(description="Nạp dữ liệu hành chính Việt Nam mới vào SportZone")
    parser.add_argument("--dry-run", action="store_true", help="Xem trước, không ghi DB")
    parser.add_argument("--force",   action="store_true", help="Buộc xóa sạch dữ liệu cũ rồi nạp lại")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        run(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
