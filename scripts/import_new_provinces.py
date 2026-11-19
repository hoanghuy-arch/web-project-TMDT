#!/usr/bin/env python3
"""Nạp dữ liệu hành chính Việt Nam (34 tỉnh/thành + 3321 xã/phường) từ file JSON nội bộ.

Nguồn: open-admin-data/vietnam-administrative-divisions (CC BY 4.0)
  Xem: data/administrative/vietnam/NOTICE.md

File đọc (lưu sẵn trong repo, không cần Internet khi chạy):
  data/administrative/vietnam/all-province.json
  data/administrative/vietnam/all-ward.json

Chiến lược đồng bộ theo code (mã hành chính quốc gia):
  - Province.code và Ward.code là khóa nhận diện chính.
  - Nếu code đã tồn tại → cập nhật tên nếu thay đổi.
  - Nếu code chưa có  → thêm mới.
  - KHÔNG xóa bản ghi cũ đang được Address/Order tham chiếu.
  - Nếu chưa có địa chỉ nào → tự động làm sạch dữ liệu cũ (không có code) trước khi nạp.

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
        print(f"    Hãy tải file từ: https://github.com/open-admin-data/vietnam-administrative-divisions")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    if isinstance(data, list):
        return data
    print(f"[!] File {path.name} không đúng định dạng.")
    sys.exit(1)


def _get_name(item: dict) -> str:
    """Lấy tên tiếng Việt từ trường name (có thể là dict hoặc string)."""
    name = item.get("name", "")
    if isinstance(name, dict):
        return name.get("local", "").strip()
    return str(name).strip()


def _get_code(item: dict) -> str:
    """Lấy mã hành chính từ trường id (luôn là string)."""
    return str(item.get("id", "")).strip()


def run(dry_run: bool = False, force: bool = False):
    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"\n{prefix}Nạp dữ liệu hành chính Việt Nam (34 tỉnh / 3321 xã phường)")
    print("=" * 65)

    # 1. Đọc file JSON
    print("[1/5] Đọc file dữ liệu...")
    provinces_raw = load_json(PROVINCE_FILE)
    wards_raw     = load_json(WARD_FILE)
    print(f"      → {len(provinces_raw)} tỉnh/thành phố, {len(wards_raw)} phường/xã")

    # Validate cấu trúc nhanh
    for tag, items in [("Province", provinces_raw), ("Ward", wards_raw)]:
        s = items[0] if items else {}
        if not _get_code(s) or not _get_name(s):
            print(f"[!] File {tag}: thiếu trường 'id' hoặc 'name'. Mẫu: {s}")
            sys.exit(1)

    # 2. Kiểm tra trạng thái DB
    print("\n[2/5] Kiểm tra trạng thái database...")
    cur_prov = db.session.query(Province).count()
    cur_ward = db.session.query(Ward).count()
    cur_addr = db.session.query(Address).count()
    prov_with_code = db.session.query(Province).filter(Province.code.isnot(None)).count()
    print(f"      Hiện có: {cur_prov} tỉnh ({prov_with_code} có code), {cur_ward} phường/xã, {cur_addr} địa chỉ")

    # 3. Làm sạch dữ liệu cũ nếu an toàn
    if not dry_run:
        should_clear = force or (cur_addr == 0 and prov_with_code == 0 and cur_prov > 0)
        if should_clear:
            print(f"\n[3/5] Làm sạch dữ liệu cũ ({cur_ward} phường/xã, {cur_prov} tỉnh)...")
            db.session.execute(db.delete(Ward))
            db.session.execute(db.delete(Province))
            db.session.commit()
            print("      → Đã xóa xong.")
        else:
            print(f"\n[3/5] Giữ nguyên dữ liệu cũ, chỉ thêm/cập nhật theo code.")
    else:
        print(f"\n[3/5] [Dry-run] Bỏ qua bước làm sạch.")

    # 4. Đồng bộ Tỉnh/Thành phố theo Province.code
    print("\n[4/5] Đồng bộ Tỉnh/Thành phố (khóa nhận diện: code)...")

    # Cache toàn bộ tỉnh đang có: code → Province, name → Province
    cache_by_code: dict[str, Province] = {
        p.code: p for p in db.session.query(Province).filter(Province.code.isnot(None)).all()
    }
    cache_by_name: dict[str, Province] = {
        p.name: p for p in db.session.query(Province).all()
    }

    prov_new = prov_upd = prov_skip = 0
    # Map: mã JSON → Province.id trong DB (dùng cho bước nạp Ward)
    json_code_to_db_id: dict[str, int] = {}
    # Map dùng cho dry-run (id giả âm)
    json_code_to_dry_id: dict[str, int] = {}

    for item in provinces_raw:
        code = _get_code(item)
        name = _get_name(item)
        if not code or not name:
            continue

        if code in cache_by_code:
            # Đã có theo code → chỉ cập nhật tên nếu khác
            prov = cache_by_code[code]
            json_code_to_db_id[code] = prov.id
            json_code_to_dry_id[code] = prov.id
            if prov.name != name:
                if not dry_run:
                    prov.name = name
                prov_upd += 1
            else:
                prov_skip += 1
        elif name in cache_by_name:
            # Tồn tại theo tên nhưng chưa có code → gán code
            prov = cache_by_name[name]
            json_code_to_db_id[code] = prov.id
            json_code_to_dry_id[code] = prov.id
            if not dry_run:
                prov.code = code
                cache_by_code[code] = prov
            prov_upd += 1
        else:
            # Mới hoàn toàn → thêm mới
            prov_new += 1
            if not dry_run:
                new_p = Province(code=code, name=name)
                db.session.add(new_p)
                db.session.flush()
                cache_by_code[code] = new_p
                json_code_to_db_id[code] = new_p.id
            else:
                # Dry-run: gán id tạm để simulate map
                json_code_to_dry_id[code] = -(len(json_code_to_dry_id) + 1)

    if not dry_run:
        db.session.commit()

    effective_map = json_code_to_db_id if not dry_run else json_code_to_dry_id
    print(f"      → Thêm mới: {prov_new:3d}, Cập nhật: {prov_upd:3d}, Không đổi: {prov_skip:3d}")

    # 5. Đồng bộ Phường/Xã theo Ward.code
    print("\n[5/5] Đồng bộ Phường/Xã (khóa nhận diện: code)...")

    cache_ward_by_code: dict[str, Ward] = {
        w.code: w for w in db.session.query(Ward).filter(Ward.code.isnot(None)).all()
    }
    cache_ward_by_key: dict[tuple, Ward] = {
        (w.province_id, w.name): w
        for w in db.session.query(Ward).filter(Ward.code.is_(None)).all()
    }

    ward_new = ward_upd = ward_skip = ward_no_parent = 0
    wards_to_add: list[Ward] = []

    for item in wards_raw:
        code   = _get_code(item)
        name   = _get_name(item)
        parent = item.get("parent")
        if not parent or "id" not in parent:
            ward_no_parent += 1
            continue
        p_code = str(parent["id"])

        if p_code not in effective_map:
            ward_no_parent += 1
            continue

        province_id = effective_map[p_code]

        if code in cache_ward_by_code:
            # Đã có theo code → cập nhật tên nếu khác
            w = cache_ward_by_code[code]
            if w and w.name != name:
                if not dry_run:
                    w.name = name
                ward_upd += 1
            else:
                ward_skip += 1
        elif (province_id, name) in cache_ward_by_key:
            # Trùng (province_id, name) nhưng chưa có code → gán code
            w = cache_ward_by_key.pop((province_id, name))
            if not dry_run:
                w.code = code
                cache_ward_by_code[code] = w
            ward_upd += 1
        else:
            # Mới hoàn toàn → thêm mới
            if not dry_run:
                wards_to_add.append(Ward(code=code, province_id=province_id, name=name))
                cache_ward_by_code[code] = None
            ward_new += 1

    if not dry_run and wards_to_add:
        for i in range(0, len(wards_to_add), 500):
            db.session.add_all(wards_to_add[i:i + 500])
            db.session.flush()
        db.session.commit()

    print(f"      → Thêm mới: {ward_new:4d}, Cập nhật: {ward_upd:4d}, Không đổi: {ward_skip:4d}", end="")
    if ward_no_parent:
        print(f", Bỏ qua (không xác định tỉnh): {ward_no_parent}", end="")
    print()

    # Báo cáo cuối
    print("\n" + "=" * 65)
    if not dry_run:
        total_p = db.session.query(Province).count()
        total_w = db.session.query(Ward).count()
        print(f"Kết quả DB: {total_p} tỉnh/thành phố, {total_w} phường/xã")
        print("→ Hoàn tất!")
    else:
        print(f"[Dry-run] Sẽ thêm: {prov_new} tỉnh, {ward_new} phường/xã (không ghi DB)")


def main():
    parser = argparse.ArgumentParser(
        description="Nạp dữ liệu hành chính Việt Nam vào SportZone từ file JSON nội bộ"
    )
    parser.add_argument("--dry-run", action="store_true", help="Xem trước, không ghi DB")
    parser.add_argument("--force",   action="store_true",
                        help="Buộc xóa sạch dữ liệu cũ rồi nạp lại (chỉ dùng khi chắc chắn chưa có đơn hàng/địa chỉ)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        run(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
