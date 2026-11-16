# SportZone — Hệ thống thương mại điện tử thể thao

Dự án web B2C chuyên kinh doanh sản phẩm thể thao (giày, quần áo, phụ kiện), xây dựng trên nền tảng Flask (Python).  
Hệ thống cung cấp trải nghiệm mua sắm hoàn chỉnh cho khách hàng, phân hệ tác nghiệp chuyên biệt cho nhân viên và bảng điều khiển quản trị toàn diện.

---

## Mục lục

1. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
2. [Cài đặt nhanh (Python thuần)](#cài-đặt-nhanh-python-thuần)
3. [Chạy bằng Docker](#chạy-bằng-docker)
4. [Tài khoản mẫu](#tài-khoản-mẫu)
5. [Quy trình Thanh toán & Phân hệ Giao vận 3PL (GHN)](#quy-trình-thanh-toán--phân-hệ-giao-vận-3pl-ghn)
6. [Sơ đồ URL](#sơ-đồ-url)
7. [Cấu trúc thư mục](#cấu-trúc-thư-mục)
8. [Chạy kiểm thử & Đảm bảo chất lượng](#chạy-kiểm-thử--đảm-bảo-chất-lượng)
9. [Biến môi trường](#biến-môi-trường)
10. [Công nghệ sử dụng](#công-nghệ-sử-dụng)

---

## Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu | Ghi chú |
|---|---|---|
| Python | 3.12+ | Môi trường chạy Flask |
| pip | 24+ | Quản lý gói thư viện |
| (Tùy chọn) Docker | 24+ | Đóng gói môi trường hoàn chỉnh |
| (Tùy chọn) Docker Compose | v2.20+ | Điều phối MySQL + App + Nginx |

> **Lưu ý:** Chạy cục bộ mặc định dùng **SQLite** (tự động tạo file, không cần cài đặt MySQL). Docker Compose sẽ chạy sẵn MySQL 8.

---

## Cài đặt nhanh (Python thuần)

```bash
# 1. Di chuyển vào thư mục dự án
cd sportzone

# 2. Tạo môi trường ảo virtualenv
python -m venv .venv

# Kích hoạt trên Windows (PowerShell)
.venv\Scripts\activate
# Kích hoạt trên macOS / Linux
source .venv/bin/activate

# 3. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt

# 4. Thiết lập file cấu hình môi trường
copy .env.example .env     # Trên Windows
# cp .env.example .env     # Trên macOS/Linux

# 5. Khởi tạo cơ sở dữ liệu và bảng
flask db upgrade

# 6. Nạp dữ liệu mẫu (sản phẩm, tài khoản, cấu hình)
python scripts/seed_dev.py

# 7. Khởi chạy máy chủ phát triển
flask run
```

Truy cập website tại: **http://127.0.0.1:5000**

> **Mẹo Windows:** Nếu lệnh `pip install` gặp cảnh báo encoding, hãy đặt biến môi trường trước:
> ```powershell
> $env:PYTHONUTF8="1"
> ```

---

## Chạy bằng Docker

Dự án đã cấu hình sẵn Docker Compose bao gồm 3 container liên kết: **MySQL 8** + **Flask Gunicorn** + **Nginx Reverse Proxy**.

```bash
# 1. Di chuyển vào thư mục chứa docker-compose.yml
cd sportzone

# 2. Khởi động toàn bộ dịch vụ (tự động build và chạy nền)
docker compose up --build -d

# 3. Xem log hoạt động của ứng dụng
docker compose logs -f app

# 4. Dừng hệ thống
docker compose down

# 5. Dừng và xóa toàn bộ dữ liệu database để khởi động lại từ đầu
docker compose down -v
```

Mở trình duyệt: **http://localhost** *(Nginx điều hướng cổng 80 vào ứng dụng)*

> **Đặc điểm nổi bật trong chế độ phát triển:**
> - Docker Compose đã được cấu hình Volume Mount (`- .:/app`), cho phép **Hot-reload**: chỉnh sửa giao diện HTML/CSS chỉ cần `F5` trình duyệt, thay đổi code Python server sẽ tự khởi động lại mà không cần rebuild container.
> - Lần đầu khởi động, container `app` sẽ tự động thực thi migrate và `python scripts/seed_dev.py`.

---

## Tài khoản mẫu

Sau khi chạy lệnh nạp dữ liệu mẫu (`seed_dev.py`), hệ thống cung cấp sẵn các tài khoản thử nghiệm:

| Email | Mật khẩu | Vai trò | Quyền hạn chính |
|---|---|---|---|
| `admin@sportzone.local` | `Admin123456` | Quản trị viên (`ADMIN`) | Toàn quyền cấu hình, nhân sự, hàng hóa, tài chính, phân quyền |
| `staff@sportzone.local` | `Staff123456` | Nhân viên (`STAFF`) | Xử lý đơn hàng, quản lý kho, duyệt yêu cầu đổi trả |
| `khach1@test.com` | `Khach123456` | Khách hàng (`CUSTOMER`) | Xem sản phẩm, đặt hàng, theo dõi đơn, đổi trả, đánh giá |
| `khach2@test.com` | `Khach123456` | Khách hàng (`CUSTOMER`) | Khách hàng phụ dùng kiểm thử tương tác chéo |

---

## Quy trình Thanh toán & Phân hệ Giao vận 3PL (GHN)

Hệ thống được thiết kế theo đúng quy trình vận hành thương mại điện tử thực tế: tập trung vào phương thức **Thanh toán khi nhận hàng (COD)** kết hợp tự động hóa toàn diện với **Đơn vị vận chuyển bên thứ ba (Giao Hàng Nhanh - GHN Open API)**.

```
[ Khách chọn sản phẩm & địa chỉ ]
              │
              ▼
   [ Chọn Gói Vận Chuyển GHN ] ──► Tự động tính cước & ngày dự kiến giao (Leadtime)
              │
              ▼
    [ Đặt hàng COD an toàn ] ──► Đơn chuyển sang "Chờ xác nhận", tự động giữ tồn kho
              │
              ▼
   [ Nhân viên Kho duyệt đơn ] ──► Xác nhận & Đóng gói sản phẩm
              │
              ▼
   [ 1-Click "Bắn đơn GHN" ] ──► Gọi API GHN cấp mã vận đơn thật (GHN...VN) & xuất kho
              │
              ▼
   [ In phiếu giao hàng A5 ] ──► In bill chuẩn có mã vạch Barcode dán lên kiện hàng
              │
              ▼
  [ Khách theo dõi hành trình ] ──► Stepper 5 bước + Lịch sử quét mã bưu tá theo thời gian thực
              │
              ▼
  [ Bưu tá giao & Thu tiền COD ] ──► Hoàn tất đơn hàng & ghi nhận doanh thu
```

---

### 1. Chính sách Thanh toán
* **Phương thức chính thức:** **Thanh toán khi nhận hàng (COD - Cash On Delivery)**. Đây là phương thức an toàn và phổ biến nhất, cho phép khách hàng kiểm tra tình trạng kiện hàng trước khi thanh toán tiền mặt cho bưu tá.
* **Định hướng Cổng thanh toán trực tuyến (VNPay / Ví điện tử):** Được định hướng tích hợp ở giai đoạn tiếp theo khi hệ thống hoàn tất thủ tục đăng ký pháp nhân và hồ sơ kết nối Merchant chính thức. Tại phiên bản hiện tại, tùy chọn thanh toán trực tuyến hiển thị thông báo tạm thời chưa khả dụng.

---

### 2. Tích hợp Phân hệ Vận chuyển 3PL (Giao Hàng Nhanh - GHN)
Phân hệ giao nhận được chuẩn hóa theo trải nghiệm của các sàn TMĐT hàng đầu:

* **Màn hình Đặt hàng (Checkout):**
  * Tự động tính cước và hiển thị thời gian giao hàng dự kiến (Estimated Delivery Date) theo địa chỉ nhận:
    * 🔘 **Giao Tiêu Chuẩn (GHN Standard):** Cước phí chuẩn &middot; *Dự kiến nhận 2 - 3 ngày*.
    * 🔘 **Giao Nhanh (GHN Express):** Phụ thu giao hỏa tốc &middot; *Dự kiến nhận trong 24h*.
  * Tự động áp dụng chính sách Miễn phí vận chuyển (Freeship) khi đơn hàng đạt ngưỡng cấu hình của shop.
* **Màn hình Quản lý đơn của Nhân viên (Staff Order):**
  * Tích hợp nút bấm **"Bắn đơn GHN"**: Hệ thống tự động liên kết với GHN Open API để tạo vận đơn, lưu mã tracking và kích hoạt xuất kho trừ tồn.
  * Hỗ trợ thiết lập chỉ dẫn bưu tá (*Cho xem hàng không cho thử, Cho thử hàng, v.v.*).
* **Trang In Phiếu Giao Hàng A5 (Shipping Label):**
  * Cung cấp mẫu phiếu giao hàng chuẩn khổ A5/A6 có **mã vạch (Barcode)**, thông tin kho gửi, người nhận, danh sách sản phẩm và khung tiền thu hộ COD viền đỏ nổi bật.
* **Màn hình Chi tiết đơn hàng của Khách (Order Tracking):**
  * **Thanh tiến trình 5 bước (Stepper):** `[Đặt hàng]` $\rightarrow$ `[Đã xác nhận]` $\rightarrow$ `[Đang đóng gói]` $\rightarrow$ `[Đang vận chuyển]` $\rightarrow$ `[Giao thành công]`.
  * **Nhật ký hành trình bưu cục (Tracking Logs):** Hiển thị chi tiết từng mốc thời gian bưu tá tiếp nhận tại kho, nhập kho phân loại trung chuyển, tên và số điện thoại bưu tá phát hàng.
* **Cơ chế Dual-Mode thông minh:**
  * Khi có `GHN_API_TOKEN`: Hệ thống gửi yêu cầu trực tiếp đến GHN Open API / Sandbox.
  * Khi chưa cấu hình Token hoặc chạy offline: Tự động kích hoạt cơ chế Smart Simulation mô phỏng chuẩn 100% quy cách của GHN, bảo đảm hệ thống luôn hoạt động ổn định khi báo cáo và đánh giá.

---

## Sơ đồ URL

### Phân hệ Khách hàng (Public & Account)

| URL | Chức năng | Phân quyền |
|---|---|---|
| `/` | Trang chủ — Banner, bộ sưu tập, sản phẩm nổi bật | Công khai |
| `/products` | Danh sách sản phẩm, bộ lọc đa tiêu chí, tìm kiếm | Công khai |
| `/products/<slug>` | Chi tiết sản phẩm, chọn size/màu, xem đánh giá | Công khai |
| `/category/<slug>` | Lọc sản phẩm theo danh mục | Công khai |
| `/auth/login` | Đăng nhập tài khoản | Công khai |
| `/auth/register` | Đăng ký tài khoản mới | Công khai |
| `/account/profile` | Xem và cập nhật thông tin cá nhân | Khách hàng |
| `/account/addresses` | Sổ địa chỉ giao hàng | Khách hàng |
| `/account/cart` | Quản lý giỏ hàng | Khách hàng |
| `/account/checkout` | Chọn địa chỉ, chọn gói giao hàng GHN và xác nhận đặt hàng | Khách hàng |
| `/account/orders` | Danh sách và lịch sử đơn hàng đã đặt | Khách hàng |
| `/account/orders/<code>` | Chi tiết tiến trình đơn, Stepper và nhật ký hành trình GHN | Khách hàng |
| `/account/orders/<code>/shipping-label` | Xem và in phiếu giao hàng A5 có mã vạch Barcode | Khách hàng / Nhân viên |
| `/account/orders/<code>/return` | Gửi yêu cầu đổi/trả sản phẩm | Khách hàng |

### Phân hệ Tác nghiệp Nhân viên (`/staff/`)

| URL | Chức năng | Phân quyền |
|---|---|---|
| `/staff/` | Bảng điều khiển nhân viên | Nhân viên |
| `/staff/orders` | Tiếp nhận và quản lý danh sách đơn hàng | Quản lý đơn hàng |
| `/staff/orders/<code>` | Duyệt đơn, đóng gói, bàn giao vận chuyển, in phiếu A5 | Quản lý đơn hàng |
| `/staff/orders/<code>/ship-ghn` | Bàn giao tự động và tạo vận đơn qua GHN Open API | Quản lý đơn hàng |
| `/staff/returns` | Thẩm định và xử lý các yêu cầu đổi trả | Xử lý đổi trả |
| `/staff/stock` | Tra cứu tồn kho theo biến thể (màu sắc/kích cỡ) | Quản lý kho |
| `/staff/stock/<id>` | Xem chi tiết lịch sử xuất nhập tồn của biến thể | Quản lý kho |
| `/staff/receipts` | Sổ phiếu nhập kho | Quản lý kho |
| `/staff/receipts/new` | Lập phiếu nhập kho từ nhà cung cấp | Quản lý kho |

### Phân hệ Quản trị viên (`/admin/`)

| URL | Chức năng | Phân quyền |
|---|---|---|
| `/admin/` | Dashboard thống kê doanh thu, đơn hàng, biểu đồ | Quản trị viên |
| `/admin/reports` | Báo cáo chi tiết kinh doanh, mặt hàng bán chạy | Quản trị viên |
| `/admin/products` | Thêm, sửa, xóa sản phẩm, biến thể và quản lý ảnh | Quản lý sản phẩm |
| `/admin/categories` | Quản lý cây danh mục sản phẩm | Quản lý danh mục |
| `/admin/attributes` | Thiết lập thông số thuộc tính (Size, Màu sắc) | Quản trị viên |
| `/admin/suppliers` | Quản lý đối tác và nhà cung cấp | Quản lý kho |
| `/admin/promotions` | Thiết lập mã giảm giá, khuyến mãi định kỳ | Quản lý khuyến mãi |
| `/admin/shipping-fees` | Bảng giá cước vận chuyển theo tỉnh/thành (Thêm, Sửa, Xóa) | Cấu hình vận chuyển |
| `/admin/users` | Quản lý danh sách người dùng và trạng thái tài khoản | Quản lý người dùng |
| `/admin/roles` | Phân quyền chi tiết theo nhóm nghiệp vụ cho Nhân viên | Quản trị viên |
| `/admin/settings` | Cấu hình tham số hệ thống (thời hạn hủy đơn, đổi trả) | Cấu hình hệ thống |
| `/admin/audit-logs` | Nhật ký ghi nhận hoạt động (Audit Trail) phục vụ giám sát | Quản trị viên |

---

## Cấu trúc thư mục

```
sportzone/
├── app/
│   ├── auth/           # Xác thực người dùng (Đăng nhập, Đăng ký, Đổi mật khẩu)
│   ├── shop/           # Phân hệ mua sắm công khai (Catalog, Chi tiết, Mega Menu)
│   ├── account/        # Phân hệ khách hàng (Giỏ hàng, Checkout, Lịch sử, Đổi trả, In bill)
│   ├── payment/        # Phân hệ thanh toán (COD chính thức, cấu trúc module sẵn sàng mở rộng)
│   ├── staff/          # Phân hệ nghiệp vụ Nhân viên (Đơn hàng, Bắn đơn GHN, Kho, Đổi trả)
│   ├── admin/          # Phân hệ Quản trị viên (Sản phẩm, Người dùng, Phân quyền, Báo cáo)
│   ├── models/         # SQLAlchemy Models (Thiết kế ERD chuẩn hóa: Account, Order, Shipment,...)
│   ├── services/       # Lớp xử lý nghiệp vụ trung tâm & tích hợp 3PL (ghn_service, order_service,...)
│   ├── tasks/          # Tiến trình nền tự động (Tự hủy đơn quá hạn, cảnh báo kho)
│   ├── templates/      # Giao diện Jinja2 (HTML5, Bootstrap 5.3, Bootstrap Icons)
│   ├── static/         # Tài nguyên tĩnh (CSS tùy biến, JS tương tác, hình ảnh)
│   └── utils/          # Hàm tiện ích, định dạng tiền tệ/ngày tháng, Decorators bảo mật
├── scripts/
│   ├── seed_dev.py              # Kịch bản nạp dữ liệu mẫu ban đầu
│   ├── check_static.py          # Kiểm tra tính toàn vẹn biến giao diện và static
│   ├── check_model_usage.py     # Kiểm tra tính đúng đắn của thuộc tính model
│   └── check_*_templates.py    # Kiểm tra render tất cả template không cần kết nối DB
├── tests/              # Bộ kiểm thử tự động pytest (đơn hàng, phân hệ vận chuyển GHN, kho)
├── migrations/         # Nhật ký dịch chuyển cơ sở dữ liệu Flask-Migrate (Alembic)
├── Dockerfile          # Định nghĩa môi trường chạy ứng dụng Flask trên container
├── docker-compose.yml  # Cấu hình đa container (App + MySQL 8 + Nginx)
├── nginx.conf          # Cấu hình máy chủ web Nginx và Reverse Proxy
├── config.py           # Cấu hình hệ thống theo môi trường (Development, Testing, Production)
├── wsgi.py             # Điểm vào WSGI cho Gunicorn server
├── .env.example        # Mẫu thiết lập biến môi trường
└── requirements.txt    # Danh sách gói thư viện Python
```

---

## Chạy kiểm thử & Đảm bảo chất lượng

Dự án áp dụng quy trình kiểm thử tự động với **pytest**, bao phủ 100% các luồng đặt hàng, xử lý kho và tích hợp giao vận:

```bash
# 1. Chạy toàn bộ test suite (86+ test cases)
pytest

# 2. Chạy riêng kiểm thử phân hệ vận chuyển GHN và đơn hàng
pytest tests/test_ghn.py tests/test_orders.py tests/test_staff_orders.py -v

# 3. Chạy kiểm thử kèm thống kê độ bao phủ mã nguồn (Coverage)
pip install pytest-cov
pytest --cov=app --cov-report=term-missing

# 4. Kiểm tra tĩnh giao diện và cú pháp template (không cần khởi động DB)
python scripts/check_static.py
python scripts/check_admin_templates.py
python scripts/check_shop_templates.py
```

---

## Biến môi trường

Hệ thống quản lý cấu hình thông qua các biến môi trường trong file `.env`. Dưới đây là các tham số quan trọng:

| Tên biến | Mô tả | Môi trường Dev | Môi trường Production |
|---|---|---|---|
| `FLASK_ENV` | Chế độ chạy của ứng dụng Flask | `development` | `production` |
| `SECRET_KEY` | Khóa bí mật mã hóa Session & CSRF | Tùy ý khi test | **Chuỗi ngẫu nhiên bảo mật cao** |
| `DATABASE_URL` | Chuỗi kết nối CSDL | Để trống *(dùng SQLite)* | `mysql+pymysql://user:pass@host/dbname` |
| `GHN_API_URL` | Địa chỉ API Giao Hàng Nhanh | `https://dev-online-gateway.ghn.vn/shiip/public-api` | Cổng API chính thức GHN |
| `GHN_API_TOKEN` | Token xác thực nhà phát triển GHN | Để trống *(chạy Smart Simulation)* | Token do GHN cấp cho chủ shop |
| `GHN_SHOP_ID` | Mã định danh cửa hàng đối tác | Để trống | Shop ID chính thức trên GHN |
| `GHN_FROM_DISTRICT_ID` | Mã Quận/Huyện kho gửi hàng | `1454` *(Quận 1, TP.HCM)* | Mã quận kho hàng thực tế |
| `GHN_FROM_WARD_CODE` | Mã Phường/Xã kho gửi hàng | `21211` *(Phường Bến Nghé)* | Mã phường kho hàng thực tế |
| `MAIL_SERVER` | Địa chỉ máy chủ gửi email SMTP | `localhost` | `smtp.gmail.com` hoặc SendGrid |
| `MAIL_USERNAME` | Tài khoản gửi thư thông báo | Để trống *(chỉ log console)* | Email quản trị |
| `MAIL_PASSWORD` | Mật khẩu ứng dụng SMTP | Để trống | Mật khẩu ứng dụng 16 ký tự |
| `RATELIMIT_STORAGE_URI` | Bộ nhớ lưu trữ giới hạn tần suất gọi API | `memory://` | `redis://...` hoặc `memory://` |

> **Cảnh báo an ninh:** Tuyệt đối không đưa file `.env` lên các kho mã nguồn công khai như GitHub. File `.gitignore` của dự án đã được cấu hình để tự động bỏ qua file này.

---

## Công nghệ sử dụng

- **Backend:** Python 3.12, Flask 3.1, SQLAlchemy ORM, Flask-Login, Flask-WTF, Flask-Limiter, Flask-Migrate (Alembic).
- **Phân hệ Vận chuyển 3PL:** Tích hợp Giao Hàng Nhanh (GHN Open API), thuật toán tính cước & thời gian dự kiến (Leadtime), phát sinh mã vận đơn, Stepper theo dõi hành trình và in phiếu giao hàng A5 có mã vạch Barcode.
- **Frontend:** Jinja2 Template Engine, HTML5, CSS3, Bootstrap 5.3.3, Bootstrap Icons 1.11.3.
- **Cơ sở dữ liệu:** SQLite (phát triển cục bộ), MySQL 8.0 (triển khai Docker/Production).
- **Bảo mật & Tác vụ:** Bcrypt mã hóa mật khẩu, CSRF Protection, Rate Limiting, APScheduler cho tác vụ nền tự động.
- **Triển khai & Đóng gói:** Gunicorn WSGI, Nginx Reverse Proxy, Docker, Docker Compose.
- **Kiểm thử:** Pytest (86+ tests), Pytest-cov, scripts kiểm tra tĩnh cú pháp template.
