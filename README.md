# SportZone — Hệ thống thương mại điện tử thể thao

Dự án web B2C bán đồ thể thao, xây dựng bằng Flask (Python).  
Hỗ trợ khách hàng mua sắm, nhân viên xử lý đơn và quản trị viên quản lý toàn bộ hệ thống.

---

## Mục lục

1. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
2. [Cài đặt nhanh (Python thuần)](#cài-đặt-nhanh-python-thuần)
3. [Chạy bằng Docker](#chạy-bằng-docker)
4. [Tài khoản mẫu](#tài-khoản-mẫu)
5. [Thanh toán VNPay sandbox](#thanh-toán-vnpay-sandbox)
6. [Sơ đồ URL](#sơ-đồ-url)
7. [Cấu trúc thư mục](#cấu-trúc-thư-mục)
8. [Chạy kiểm thử](#chạy-kiểm-thử)
9. [Biến môi trường](#biến-môi-trường)

---

## Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu |
|---|---|
| Python | 3.12 |
| pip | 24+ |
| (tuỳ chọn) Docker | 24+ |
| (tuỳ chọn) Docker Compose | v2.20+ |

> **Lưu ý:** Phát triển cục bộ dùng **SQLite** (tự động, không cần cài MySQL). Docker Compose mới dùng MySQL 8.

---

## Cài đặt nhanh (Python thuần)

```bash
# 1. Clone hoặc giải nén dự án
cd sportzone

# 2. Tạo virtualenv
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Cài thư viện (Windows: set PYTHONUTF8=1 nếu gặp lỗi encoding)
pip install -r requirements.txt

# 4. Tạo file cấu hình
copy .env.example .env     # Windows
# cp .env.example .env     # macOS/Linux
# (Có thể để nguyên để dùng SQLite + thanh toán giả lập)

# 5. Khởi tạo database
flask db upgrade

# 6. Seed dữ liệu mẫu
python scripts/seed_dev.py

# 7. Chạy ứng dụng
flask run
```

Mở trình duyệt: **http://127.0.0.1:5000**

> **Mẹo Windows:** Nếu `pip install -r requirements.txt` báo lỗi encoding, chạy trước:
> ```powershell
> $env:PYTHONUTF8="1"
> ```

---

## Chạy bằng Docker

```bash
# Build và khởi động tất cả dịch vụ (MySQL 8 + Flask/Gunicorn + Nginx)
docker compose up --build

# Chạy nền
docker compose up --build -d

# Mở trình duyệt: http://localhost
# (Nginx cổng 80 → Gunicorn cổng 8000)

# Xem log
docker compose logs -f app

# Dừng
docker compose down

# Dừng và xóa toàn bộ dữ liệu
docker compose down -v
```

> **Quan trọng:** Lần đầu khởi động, `app` tự chạy `flask db upgrade` và `python scripts/seed_dev.py`.
> Thay `SECRET_KEY` và mật khẩu MySQL trong `docker-compose.yml` trước khi deploy thực tế.

---

## Tài khoản mẫu

Sau khi chạy `python scripts/seed_dev.py`:

| Email | Mật khẩu | Vai trò | Quyền hạn |
|---|---|---|---|
| `admin@sportzone.local` | `Admin123456` | Quản trị viên | Toàn bộ hệ thống |
| `staff@sportzone.local` | `Staff123456` | Nhân viên | Xem/xử lý đơn, kho, đổi trả |
| `khach1@test.com` | `Khach123456` | Khách hàng | Mua sắm, đổi trả, đánh giá |
| `khach2@test.com` | `Khach123456` | Khách hàng | Mua sắm, đổi trả, đánh giá |

**Nhân viên** được cấp quyền mặc định: xem đơn, xác nhận/hủy đơn, cập nhật giao hàng, xử lý đổi trả, xem kho, lập phiếu nhập/xuất kho.

**Quản trị viên** có thêm: quản lý sản phẩm, danh mục, tài khoản, nhà cung cấp, khuyến mãi, báo cáo, nhật ký hoạt động.

---

## Thanh toán VNPay sandbox

Mặc định `PAYMENT_MOCK_ENABLED=true` → trang thanh toán **giả lập** (không cần tài khoản VNPay).

Để thử VNPay sandbox thực:

1. Đăng ký tài khoản tại [sandbox.vnpayment.vn](https://sandbox.vnpayment.vn/devreg/)
2. Lấy `TMN_CODE` và `HASH_SECRET`
3. Điền vào `.env`:
   ```
   PAYMENT_MOCK_ENABLED=false
   VNPAY_TMN_CODE=your_tmn_code
   VNPAY_HASH_SECRET=your_hash_secret
   ```
4. Dùng thẻ test của VNPay:

| Thông tin | Giá trị |
|---|---|
| Ngân hàng | NCB |
| Số thẻ | `9704198526191432198` |
| Tên chủ thẻ | `NGUYEN VAN A` |
| Ngày phát hành | `07/15` |
| OTP | `123456` |

---

## Sơ đồ URL

### Công khai (không cần đăng nhập)

| URL | Chức năng |
|---|---|
| `/` | Trang chủ — sản phẩm nổi bật |
| `/products` | Danh sách sản phẩm (lọc, tìm kiếm) |
| `/products/<slug>` | Chi tiết sản phẩm + đánh giá |
| `/category/<slug>` | Lọc theo danh mục |
| `/auth/login` | Đăng nhập |
| `/auth/register` | Đăng ký |
| `/auth/forgot-password` | Quên mật khẩu |

### Khách hàng `/account/`

| URL | Chức năng |
|---|---|
| `/account/profile` | Hồ sơ cá nhân |
| `/account/addresses` | Quản lý địa chỉ |
| `/account/cart` | Giỏ hàng |
| `/account/checkout` | Đặt hàng |
| `/account/orders` | Lịch sử đơn hàng |
| `/account/orders/<code>` | Chi tiết đơn, hủy đơn |
| `/account/orders/<code>/return` | Yêu cầu đổi trả |
| `/account/orders/<code>/review/<id>` | Đánh giá sản phẩm |
| `/payment/start/<code>` | Thanh toán online |

### Nhân viên `/staff/`

| URL | Chức năng |
|---|---|
| `/staff/` | Bảng điều khiển |
| `/staff/orders` | Danh sách đơn hàng |
| `/staff/orders/<code>` | Xử lý đơn (xác nhận, đóng gói, giao) |
| `/staff/returns` | Yêu cầu đổi trả chờ xử lý |
| `/staff/stock` | Tồn kho — danh sách biến thể |
| `/staff/stock/<id>` | Chi tiết tồn kho + sổ biến động |
| `/staff/receipts` | Phiếu nhập kho |
| `/staff/receipts/new` | Lập phiếu nhập mới |

### Quản trị viên `/admin/`

| URL | Chức năng |
|---|---|
| `/admin/` | Bảng điều khiển quản trị |
| `/admin/reports` | Báo cáo doanh thu, sản phẩm bán chạy |
| `/admin/products` | Quản lý sản phẩm, biến thể, ảnh |
| `/admin/categories` | Quản lý danh mục |
| `/admin/attributes` | Kích cỡ và màu sắc |
| `/admin/suppliers` | Nhà cung cấp |
| `/admin/carriers` | Đơn vị vận chuyển |
| `/admin/promotions` | Khuyến mãi |
| `/admin/shipping-fees` | Phí vận chuyển theo tỉnh |
| `/admin/users` | Tài khoản và phân quyền |
| `/admin/settings` | Tham số cấu hình hệ thống |
| `/admin/audit-logs` | Nhật ký hoạt động |

---

## Cấu trúc thư mục

```
sportzone/
├── app/
│   ├── auth/           # Đăng nhập, đăng ký, quên mật khẩu
│   ├── shop/           # Trang chủ, danh mục, sản phẩm (công khai)
│   ├── account/        # Giỏ hàng, đặt hàng, lịch sử, đổi trả, đánh giá
│   ├── payment/        # COD, VNPay, thanh toán giả lập
│   ├── staff/          # Nhân viên: đơn hàng, kho, đổi trả
│   ├── admin/          # Quản trị: sản phẩm, người dùng, báo cáo
│   ├── models/         # SQLAlchemy models (ERD 7 phân hệ)
│   ├── services/       # Business logic layer
│   ├── tasks/          # APScheduler background jobs (FR-HT01)
│   ├── templates/      # Jinja2 HTML + email templates
│   ├── static/         # CSS, JS, ảnh tĩnh
│   └── utils/          # Helpers, decorators, formatters
├── scripts/
│   ├── seed_dev.py              # Seed dữ liệu phát triển
│   ├── check_static.py          # Kiểm tra tên biến/import tĩnh
│   ├── check_model_usage.py     # Kiểm tra thuộc tính model
│   └── check_*_templates.py    # Kiểm tra render template (không cần DB)
├── tests/              # pytest — 370+ test functions
├── migrations/         # Flask-Migrate (Alembic)
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── config.py
├── wsgi.py
├── .env.example
└── requirements.txt
```

---

## Chạy kiểm thử

```bash
# Toàn bộ test suite
pytest

# Một module cụ thể
pytest tests/test_orders.py -v

# Với coverage report
pip install pytest-cov
pytest --cov=app --cov-report=term-missing

# Kiểm tra tĩnh (không cần DB, không cần cài thêm package)
python scripts/check_static.py
python scripts/check_model_usage.py
```

---

## Biến môi trường

Sao chép `.env.example` → `.env` rồi điền giá trị:

| Biến | Mô tả | Mặc định |
|---|---|---|
| `SECRET_KEY` | Khóa bí mật Flask session | *(bắt buộc đổi khi production)* |
| `DATABASE_URL` | MySQL connection string | SQLite nếu để trống |
| `PAYMENT_MOCK_ENABLED` | Dùng cổng thanh toán giả lập | `true` |
| `VNPAY_TMN_CODE` | Mã merchant VNPay sandbox | *(để trống = mock)* |
| `VNPAY_HASH_SECRET` | Khóa bí mật VNPay | *(để trống = mock)* |
| `MAIL_SERVER` | SMTP server | `localhost` |
| `MAIL_USERNAME` | Tài khoản SMTP | *(để trống = chỉ ghi log)* |
| `MAIL_PASSWORD` | Mật khẩu SMTP | — |
| `RATELIMIT_STORAGE_URI` | Backend rate limit | `memory://` |

> **Cảnh báo:** Không commit file `.env` vào git. File `.gitignore` đã loại trừ sẵn.

---

## Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Web framework | Flask 3.1 |
| ORM | Flask-SQLAlchemy 3.1 + Flask-Migrate (Alembic) |
| Xác thực | Flask-Login + Bcrypt |
| Form validation | Flask-WTF + WTForms |
| Rate limiting | Flask-Limiter |
| Email | Flask-Mail |
| Tác vụ nền | APScheduler 3.x |
| Thanh toán | VNPay sandbox (HMAC-SHA512) |
| DB (dev) | SQLite |
| DB (prod) | MySQL 8 (utf8mb4) |
| Deploy | Gunicorn + Nginx |
| Container | Docker + Docker Compose |
| Test | pytest |
