# SportZone — Hệ thống thương mại điện tử thể thao

Dự án web B2C chuyên kinh doanh sản phẩm thể thao (giày, quần áo, phụ kiện), xây dựng trên nền tảng Flask (Python).  
Hệ thống cung cấp trải nghiệm mua sắm hoàn chỉnh cho khách hàng, phân hệ tác nghiệp chuyên biệt cho nhân viên và bảng điều khiển quản trị toàn diện.

---

## Mục lục

1. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
2. [Cài đặt nhanh (Python thuần)](#cài-đặt-nhanh-python-thuần)
3. [Chạy bằng Docker](#chạy-bằng-docker)
4. [Tài khoản mẫu](#tài-khoản-mẫu)
5. [Thanh toán trực tuyến & Cơ chế triển khai (Dev vs Prod)](#thanh-toán-trực-tuyến--cơ-chế-triển-khai-dev-vs-prod)
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
# Khởi động toàn bộ dịch vụ (tự động build và chạy nền)
docker compose up --build -d

# Xem log hoạt động của ứng dụng
docker compose logs -f app

# Dừng hệ thống
docker compose down

# Dừng và xóa toàn bộ dữ liệu database để khởi động lại từ đầu
docker compose down -v
```

Mở trình duyệt: **http://localhost** *(Nginx điều hướng cổng 80 vào ứng dụng)*

> **Đặc điểm nổi bật trong chế độ phát triển:**
> - Docker Compose đã được cấu hình Volume Mount (`- .:/app`), cho phép **Hot-reload**: chỉnh sửa giao diện HTML/CSS chỉ cần `F5` trình duyệt, thay đổi code Python server sẽ tự khởi động lại mà không cần rebuild container.
> - Lần đầu khởi động, container `app` sẽ tự động thực thi `flask db upgrade` và `python scripts/seed_dev.py`.

---

## Tài khoản mẫu

Sau khi chạy lệnh nạp dữ liệu mẫu (`seed_dev.py`), hệ thống cung cấp sẵn các tài khoản thử nghiệm:

| Email | Mật khẩu | Vai trò | Quyền hạn chính |
|---|---|---|---|
| `admin@sportzone.local` | `Admin123456` | Quản trị viên (`ADMIN`) | Toàn quyền cấu hình, nhân sự, hàng hóa, tài chính, phân quyền |
| `staff@sportzone.local` | `Staff123456` | Nhân viên (`STAFF`) | Xử lý đơn hàng, quản lý kho, duyệt yêu cầu đổi trả |
| `khach1@test.com` | `Khach123456` | Khách hàng (`CUSTOMER`) | Xem sản phẩm, đặt hàng, thanh toán, đổi trả, đánh giá |
| `khach2@test.com` | `Khach123456` | Khách hàng (`CUSTOMER`) | Khách hàng phụ dùng kiểm thử tương tác chéo |

---

## Thanh toán trực tuyến & Cơ chế triển khai (Dev vs Prod)

SportZone xây dựng kiến trúc cổng thanh toán đa chế độ (*Multi-mode Payment Gateway*), hỗ trợ linh hoạt cho cả mục đích **báo cáo đồ án** lẫn **triển khai thực tế trên Internet (Production)**:

```
                            [ KHÁCH ĐẶT HÀNG ]
                                    |
                    Chọn phương thức thanh toán
                    /                        \
         [ Thanh toán COD ]            [ Thanh toán Trực tuyến ]
                 |                                   |
           Tạo đơn ngay                    Kiểm tra cấu hình .env
                                           /                    \
                         PAYMENT_MOCK_ENABLED=true        PAYMENT_MOCK_ENABLED=false
                                    |                                    |
                         [ Cổng giả lập nội bộ ]             Có cấu hình VNPay thật?
                         - Demo đồ án, bảo vệ               /                      \
                         - Giả lập 4 kịch bản             CÓ                       KHÔNG
                         - Chữ ký HMAC-SHA512              |                         |
                                                  [ Cổng VNPay thật ]      [ Tự động vô hiệu hóa ]
                                                  Chuyển sang cổng VNPay    - Trả về 404 cho mock URL
                                                  với Merchant chính thức   - Nút thanh toán online bị ẩn/khóa
                                                                            - Khách chỉ chọn COD an toàn
```

---

### Kịch bản 1: Báo cáo đồ án / Đánh giá học thuật (Mặc định)
*Phù hợp nhất khi chấm đồ án, chạy demo nội bộ không phụ thuộc mạng ngoài.*

1. Trong file `.env`, giữ nguyên:
   ```ini
   PAYMENT_MOCK_ENABLED=true
   ```
2. **Trải nghiệm demo:**
   - Sau khi bấm Đặt hàng, khách hàng được chuyển đến **Cổng thanh toán mô phỏng** (`/payment/mock/pay`).
   - Cung cấp sẵn 4 nút bấm kiểm thử nghiệp vụ:
     1. **Thanh toán thành công**: Tạo chữ ký hợp lệ, cập nhật trạng thái đơn sang `PAID`, kích hoạt trừ tồn kho và ghi log giao dịch.
     2. **Thất bại (Số dư không đủ)**: Mô phỏng mã lỗi thẻ ngân hàng, cập nhật trạng thái `FAILED`.
     3. **Khách hàng hủy bỏ**: Mô phỏng thao tác hủy giao dịch, đơn hàng tự hoàn tiền/hủy an toàn.
     4. **Kiểm tra an ninh (Phát hiện can thiệp số tiền)**: Giả lập hacker sửa đổi số tiền trên URL, hệ thống bắt lỗi sai mã xác thực SHA-512 và từ chối xử lý.

---

### Kịch bản 2: Kết nối trực tiếp Cổng VNPay Sandbox
*Phù hợp khi muốn demo thao tác thực tế với cổng thanh toán VNPay thật.*

1. Cấu hình thông số Merchant Sandbox vào file `.env`:
   ```ini
   PAYMENT_MOCK_ENABLED=false
   VNPAY_TMN_CODE=CGXZLS0Z
   VNPAY_HASH_SECRET=XNBCJFAKAZQSGTARRLKNOAKXZTCXMSKZ
   VNPAY_URL=https://sandbox.vnpayment.vn/paymentv2/vpcpay.html
   VNPAY_RETURN_URL=http://localhost/payment/vnpay/return
   ```
2. Khi chuyển hướng sang VNPay Sandbox, chọn **Thẻ ATM & Tài khoản ngân hàng**, nhập thông tin thẻ test của VNPay:

| Thông tin | Giá trị thẻ test |
|---|---|
| **Ngân hàng** | **NCB** (Ngân hàng Quốc Dân) |
| **Số thẻ** | `9704198526191432198` |
| **Tên chủ thẻ** | `NGUYEN VAN A` |
| **Ngày phát hành** | `07/15` |
| **Mật khẩu OTP** | `123456` |

---

### Kịch bản 3: Triển khai thực tế lên Internet (Production)
*Khi đưa website lên môi trường thực tế cho khách hàng thật sử dụng.*

**Quy tắc an toàn cốt lõi:** Tuyệt đối không cho phép truy cập cổng giả lập trên môi trường Production. Hệ thống đã có cơ chế tự động bảo vệ:

1. Trên server Production, đặt file `.env`:
   ```ini
   PAYMENT_MOCK_ENABLED=false
   # Nếu chưa ký hợp đồng với VNPay: để trống thông tin VNPay
   VNPAY_TMN_CODE=
   VNPAY_HASH_SECRET=
   ```
2. **Hệ thống tự động kích hoạt chế độ an toàn:**
   - Mọi nỗ lực truy cập vào các đường dẫn giả lập `/payment/mock/*` đều bị chặn ngay lập tức và trả về mã lỗi **404 Not Found** (thông qua hàm bảo vệ `_require_mock()`).
   - Tại trang Đặt hàng (`/account/checkout`), tùy chọn *Thanh toán trực tuyến* tự động bị vô hiệu hóa do hệ thống nhận diện chưa có cổng thanh toán thật. Khách hàng chỉ có thể chọn **Thanh toán khi nhận hàng (COD)**.
   - Khi doanh nghiệp ký kết hợp đồng chính thức với VNPay, chỉ cần điền thông tin Merchant thực tế vào `.env`, cổng thanh toán thật sẽ tự động hoạt động mà **không cần chỉnh sửa mã nguồn**.

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
| `/account/checkout` | Xác nhận đơn hàng, chọn địa chỉ và thanh toán | Khách hàng |
| `/account/orders` | Danh sách và lịch sử đơn hàng đã đặt | Khách hàng |
| `/account/orders/<code>` | Chi tiết tiến trình đơn hàng, hủy đơn | Khách hàng |
| `/account/orders/<code>/return` | Gửi yêu cầu đổi/trả sản phẩm | Khách hàng |
| `/payment/start/<code>` | Bắt đầu quy trình thanh toán trực tuyến | Khách hàng |

### Phân hệ Tác nghiệp Nhân viên (`/staff/`)

| URL | Chức năng | Phân quyền |
|---|---|---|
| `/staff/` | Bảng điều khiển nhân viên | Nhân viên |
| `/staff/orders` | Tiếp nhận và quản lý danh sách đơn hàng | Quản lý đơn hàng |
| `/staff/orders/<code>` | Cập nhật trạng thái: Duyệt, Đóng gói, Giao hàng | Quản lý đơn hàng |
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
│   ├── account/        # Phân hệ khách hàng (Giỏ hàng, Đặt hàng, Lịch sử, Đổi trả)
│   ├── payment/        # Xử lý thanh toán (COD, VNPay Sandbox, Cổng giả lập HMAC-SHA512)
│   ├── staff/          # Phân hệ nghiệp vụ Nhân viên (Đơn hàng, Kho, Đổi trả)
│   ├── admin/          # Phân hệ Quản trị viên (Sản phẩm, Người dùng, Phân quyền, Báo cáo)
│   ├── models/         # SQLAlchemy Models (Thiết kế ERD 7 phân hệ chuẩn hóa)
│   ├── services/       # Lớp xử lý nghiệp vụ trung tâm (Business Logic Layer)
│   ├── tasks/          # Tiến trình nền tự động (Tự hủy đơn quá hạn, cảnh báo kho)
│   ├── templates/      # Giao diện Jinja2 (HTML5, Bootstrap 5.3, Bootstrap Icons)
│   ├── static/         # Tài nguyên tĩnh (CSS tùy biến, JS tương tác, hình ảnh)
│   └── utils/          # Hàm tiện ích, định dạng tiền tệ/ngày tháng, Decorators bảo mật
├── scripts/
│   ├── seed_dev.py              # Kịch bản nạp dữ liệu mẫu ban đầu
│   ├── check_static.py          # Kiểm tra tính toàn vẹn biến giao diện và static
│   ├── check_model_usage.py     # Kiểm tra tính đúng đắn của thuộc tính model
│   └── check_*_templates.py    # Kiểm tra render tất cả template không cần kết nối DB
├── tests/              # Bộ kiểm thử tự động pytest (bao phủ đơn hàng, thanh toán, kho)
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

Dự án áp dụng quy trình kiểm thử tự động để đảm bảo tính ổn định của hệ thống trước mỗi lần bàn giao hoặc triển khai:

```bash
# 1. Chạy toàn bộ test suite
pytest

# 2. Chạy riêng kiểm thử phân hệ thanh toán và đơn hàng
pytest tests/test_payment.py tests/test_orders.py -v

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
| `PAYMENT_MOCK_ENABLED` | Kích hoạt cổng thanh toán giả lập | `true` *(để demo)* | **`false` *(tự động khóa cổng giả lập)*** |
| `VNPAY_TMN_CODE` | Mã định danh Merchant VNPay | `CGXZLS0Z` *(sandbox)* | Mã do VNPay cấp chính thức |
| `VNPAY_HASH_SECRET` | Khóa bí mật tạo chữ ký số VNPay | Khóa sandbox | Khóa do VNPay cấp chính thức |
| `VNPAY_URL` | Đường dẫn API cổng thanh toán | URL sandbox | URL Production của VNPay |
| `VNPAY_RETURN_URL` | URL nhận kết quả trả về từ cổng | `http://localhost/payment/vnpay/return` | Domain thật của website |
| `MAIL_SERVER` | Địa chỉ máy chủ gửi email SMTP | `localhost` | `smtp.gmail.com` hoặc SendGrid |
| `MAIL_USERNAME` | Tài khoản gửi thư thông báo | Để trống *(chỉ log console)* | Email quản trị |
| `MAIL_PASSWORD` | Mật khẩu ứng dụng SMTP | Để trống | Mật khẩu ứng dụng 16 ký tự |
| `RATELIMIT_STORAGE_URI` | Bộ nhớ lưu trữ giới hạn tần suất gọi API | `memory://` | `redis://...` hoặc `memory://` |

> **Cảnh báo an ninh:** Tuyệt đối không đưa file `.env` lên các kho mã nguồn công khai như GitHub. File `.gitignore` của dự án đã được cấu hình để tự động bỏ qua file này.

---

## Công nghệ sử dụng

- **Backend:** Python 3.12, Flask 3.1, SQLAlchemy ORM, Flask-Login, Flask-WTF, Flask-Limiter, Flask-Migrate (Alembic).
- **Frontend:** Jinja2 Template Engine, HTML5, CSS3, Bootstrap 5.3.3, Bootstrap Icons 1.11.3.
- **Cơ sở dữ liệu:** SQLite (phát triển cục bộ), MySQL 8.0 (triển khai Docker/Production).
- **Bảo mật & Tác vụ:** Chữ ký số HMAC-SHA512 cho giao dịch, Bcrypt mã hóa mật khẩu, CSRF Protection, Rate Limiting, APScheduler cho tác vụ nền tự động.
- **Triển khai & Đóng gói:** Gunicorn WSGI, Nginx Reverse Proxy, Docker, Docker Compose.
- **Kiểm thử:** Pytest, Pytest-cov, kịch bản tự động kiểm tra template.
