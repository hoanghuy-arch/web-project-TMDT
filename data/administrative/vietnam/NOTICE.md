# Ghi công bản quyền dữ liệu hành chính (Attribution Notice)

Thư mục này chứa bản sao dữ liệu phân cấp hành chính Việt Nam (34 Tỉnh/Thành phố và 3.321 Xã/Phường theo cấu trúc sắp xếp mới). Dữ liệu được lưu trữ trực tiếp trong repository để ứng dụng hoạt động độc lập (offline), hoàn toàn không phụ thuộc vào kết nối Internet hay tình trạng hoạt động của GitHub/API bên ngoài khi vận hành.

---

## 1. Nguồn gốc dữ liệu (Source & Attribution)
- **Đơn vị cung cấp:** Open Admin Data
- **Repository nguồn:** [https://github.com/open-admin-data/vietnam-administrative-divisions](https://github.com/open-admin-data/vietnam-administrative-divisions)
- **Website dự án:** [https://openadmindata.org/vn/](https://openadmindata.org/vn/)
- **Phiên bản:** Cấu trúc hành chính mới (34 Tỉnh/Thành phố trực thuộc Trung ương, 3.321 Xã/Phường trực thuộc, không còn cấp quận/huyện trung gian).

---

## 2. Giấy phép sử dụng (License)
Dữ liệu được phân phối theo giấy phép:
**Creative Commons Attribution 4.0 International (CC BY 4.0)**
- Chi tiết giấy phép: [https://creativecommons.org/licenses/by/4.0/](https://creativecommons.org/licenses/by/4.0/)
- Bạn được tự do chia sẻ và điều chỉnh dữ liệu cho bất kỳ mục đích nào, bao gồm cả thương mại, với điều kiện phải ghi nhận bản quyền tác giả và nguồn gốc ban đầu.

---

## 3. Các file dữ liệu trong dự án
- `all-province.json`: Danh mục 34 Tỉnh/Thành phố.
- `all-ward.json`: Danh mục 3.321 Xã/Phường tương ứng kèm tham chiếu tỉnh cha (`parent.id`).

Dữ liệu được đọc và đồng bộ vào cơ sở dữ liệu nội bộ qua script:
```bash
python scripts/import_new_provinces.py
```
*(Chỉ thao tác trên file local, an toàn và bảo toàn dữ liệu).*
