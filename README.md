# SportZone — Hệ thống thương mại điện tử thể thao

Dự án website thương mại điện tử B2C chuyên kinh doanh trang phục và phụ kiện thể thao chính hãng, xây dựng trên nền tảng Flask (Python 3.12) kết hợp hệ quản trị cơ sở dữ liệu MySQL 8.0, triển khai thực tế trên môi trường máy chủ đám mây (VPS Ubuntu 22.04 LTS) bằng Docker Compose, Nginx Reverse Proxy và chứng chỉ bảo mật SSL Let's Encrypt tại tên miền chính thức: **[https://sportzone.id.vn](https://sportzone.id.vn)**.

---

## Mục lục

1. [Giới thiệu](#giới-thiệu)
2. [Tính năng](#tính-năng)
3. [Công nghệ sử dụng](#công-nghệ-sử-dụng)
4. [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
5. [Yêu cầu môi trường](#yêu-cầu-môi-trường)
6. [Cài đặt môi trường phát triển](#cài-đặt-môi-trường-phát-triển)
7. [Cấu hình biến môi trường](#cấu-hình-biến-môi-trường)
8. [Chạy kiểm thử](#chạy-kiểm-thử)
9. [Triển khai production](#triển-khai-production)
10. [Vận hành và giám sát](#vận-hành-và-giám-sát)
11. [Bảo mật](#bảo-mật)
12. [Hiệu năng và khả năng mở rộng](#hiệu-năng-và-khả-năng-mở-rộng)
13. [Tài khoản demo](#tài-khoản-demo)
14. [API hoặc route chính](#api-hoặc-route-chính)
15. [Hạn chế và hướng phát triển](#hạn-chế-và-hướng-phát-triển)
16. [Sao lưu và khôi phục](#sao-lưu-và-khôi-phục)
17. [Khắc phục sự cố](#khắc-phục-sự-cố)
18. [Hướng dẫn build và cấu trúc release](#hướng-dẫn-build-và-cấu-trúc-release)
19. [Tác giả](#tác-giả)
20. [License](#license)

---

## Giới thiệu

### Mục tiêu dự án
Xây dựng một hệ sinh thái thương mại điện tử hoàn chỉnh, tin cậy và đạt chuẩn vận hành doanh nghiệp thực tế. Dự án không chỉ giải quyết bài toán giao dịch trực tuyến giữa người mua và người bán, mà còn tối ưu hóa toàn bộ chuỗi cung ứng: quản lý kho đa biến thể, tích hợp đơn vị vận chuyển bên thứ ba (3PL GHN), quy trình thẩm định đổi trả tự động và bảo vệ dữ liệu cá nhân theo khuôn khổ pháp luật mới nhất của Việt Nam.

### Phạm vi chức năng
* **Thương mại B2C:** Duyệt danh mục, tìm kiếm đa tiêu chí, giỏ hàng, đặt hàng thanh toán COD & VNPay.
* **Hậu cần & Vận chuyển (Fulfillment):** Tính cước tự động, phát sinh mã vận đơn GHN, in phiếu giao hàng A5 có mã vạch Barcode, theo dõi tiến trình 5 bước.
* **Quản trị tác nghiệp:** Quản lý kho hàng xuất-nhập-tồn, duyệt phiếu đổi trả trong 7 ngày, quản lý sản phẩm, tài khoản và phân quyền vai trò động.
* **Tuân thủ pháp lý:** Ban hành đầy đủ 4 chính sách bắt buộc theo **Luật Thương mại điện tử 122/2025/QH15** và **Luật Bảo vệ dữ liệu cá nhân năm 2025**.

### Vai trò người dùng
1. **Khách vãng lai (Guest):** Duyệt xem sản phẩm, tìm kiếm, xem đánh giá, chính sách pháp lý.
2. **Khách hàng đã đăng ký (Customer):** Quản lý hồ sơ, sổ địa chỉ, giỏ hàng, đặt hàng, theo dõi hành trình đơn hàng, yêu cầu đổi/trả và đánh giá sản phẩm.
3. **Nhân viên xử lý (Staff):** Tiếp nhận đơn hàng, đóng gói, bàn giao vận chuyển GHN, in hóa đơn A5, kiểm định kho hàng và xử lý yêu cầu đổi trả.
4. **Quản trị viên (Admin):** Toàn quyền cấu hình tham số hệ thống, báo cáo doanh thu, quản lý danh mục, sản phẩm, nhà cung cấp, tài khoản, phân quyền và tra cứu nhật ký kiểm toán (Audit Log).

---

## Tính năng

### Phân hệ khách hàng
* **Trang chủ & Danh mục:** Trình diễn banner khuyến mãi, danh mục phân cấp, nhóm sản phẩm mới về, sản phẩm bán chạy.
* **Bộ lọc nâng cao:** Lọc tức thời theo danh mục con, khoảng giá, kích cỡ (Size), màu sắc (Color) và trạng thái còn hàng.
* **Chi tiết sản phẩm:** Lựa chọn biến thể động, hiển thị số lượng tồn kho theo thời gian thực, xem thư viện hình ảnh và đánh giá sao kèm nhận xét ẩn danh họ tên (`N. V. An`).
* **Quản lý giỏ hàng & Đặt hàng:** Tự động kiểm tra giới hạn tồn kho, nhập địa chỉ nhận hàng phân cấp 3 cấp hành chính chuẩn quốc gia (34 tỉnh/thành, 3.321 phường/xã).
* **Đổi trả trực tuyến (07 ngày):** Khách hàng tạo phiếu yêu cầu đổi hàng/trả hàng kèm hình ảnh minh chứng trực tiếp từ lịch sử đơn hàng.
* **Quên & Đặt lại mật khẩu tự động:** Gửi liên kết mã hóa bảo mật thời hạn 30 phút qua email thực tế (SMTP Gmail TLS).

### Phân hệ nhân viên
* **Bảng điều khiển tác nghiệp (`/staff/`):** Theo dõi số lượng đơn mới, đơn cần đóng gói và yêu cầu đổi trả đang chờ xử lý.
* **Xử lý đơn hàng:** Duyệt đơn, chuyển trạng thái đóng gói, kích hoạt lệnh xuất kho.
* **1-Click "Bắn đơn GHN":** Tự động liên kết API GHN để nhận mã tracking bưu tá thật, in phiếu giao hàng A5 chuẩn barcode dán kiện hàng.
* **Thẩm định đổi trả:** Tiếp nhận yêu cầu, đối soát tình trạng hàng lỗi, phê duyệt hoàn tiền hoặc gửi hàng đổi mới.
* **Quản lý kho:** Lập phiếu nhập kho từ nhà cung cấp, kiểm tra thẻ kho và lịch sử biến động số lượng từng biến thể.

### Phân hệ quản trị
* **Báo cáo kinh doanh (`/admin/reports`):** Thống kê biểu đồ doanh thu theo ngày/tháng, tỷ lệ hoàn tất đơn, top mặt hàng bán chạy.
* **Quản lý hàng hóa:** Thêm mới/chỉnh sửa sản phẩm, cấu hình biến thể (Size/Color), upload đa ảnh sản phẩm.
* **Phân quyền vai trò động (`/admin/roles`):** Tùy biến nhóm quyền hạt nhân (User, Catalog, Stock, Order, Promotion, System) cho từng tài khoản nhân viên.
* **Tham số hệ thống (`/admin/settings`):** Cấu hình thời gian giữ hàng online (15 phút), thời hạn đổi trả (7 ngày), ngưỡng Freeship (500.000đ).
* **Nhật ký kiểm toán (`/admin/audit-logs`):** Bảng ghi nhật ký chỉ-thêm (Append-only) theo dõi vết mọi thao tác nhạy cảm kèm IP và định danh tài khoản.

### Thanh toán và vận chuyển
* **Thanh toán:**
  * **COD (Cash On Delivery):** Thanh toán tiền mặt khi nhận hàng (phương thức an toàn mặc định).
  * **VNPay:** Tích hợp cổng thanh toán trực tuyến chuẩn HMAC-SHA512 checksum và Webhook IPN xử lý tức thời.
* **Vận chuyển:**
  * Tích hợp sâu Giao Hàng Nhanh (GHN Open API): Tính cước tự động theo tọa độ kho và người nhận, dự báo ngày giao hàng (Leadtime).
  * Hỗ trợ cơ chế **Smart Simulation** tự động giả lập bưu tá quét mã khi chạy offline/thiếu token bưu cục.

---

## Công nghệ sử dụng

* **Backend:** Python 3.12, Flask 3.1, Werkzeug, SQLAlchemy 3.1 (ORM), Flask-Login, Flask-WTF, Flask-Limiter, Flask-Migrate (Alembic), Flask-Mail.
* **Frontend:** Jinja2 Template Engine, HTML5, CSS3 hiện đại, Bootstrap 5.3.3, Bootstrap Icons 1.11.3, JavaScript ES6 thuần (không phụ thuộc framework nặng).
* **Cơ sở dữ liệu:** 
  * Development: SQLite in-memory / SQLite file cục bộ.
  * Production: MySQL 8.0 (Engine InnoDB, Character Set `utf8mb4`, Collation `utf8mb4_unicode_ci`).
* **Triển khai & Hạ tầng:** Gunicorn WSGI Server, Nginx 1.27 Alpine (Reverse Proxy & Static Cache), Docker 24+, Docker Compose v2, Let's Encrypt Certbot.
* **Kiểm thử & Đảm bảo chất lượng:** Pytest 8.0+, Locust 2.47+ (Load Testing).

---

## Kiến trúc hệ thống

### Sơ đồ kiến trúc

```
                             [ Người dùng Internet ]
                                       │
                                       ▼ (Port 80 / 443)
                         ┌───────────────────────────┐
                         │      NGINX REVERSE PROXY   │
                         │  - SSL Termination (TLS)  │
                         │  - Static Cache (/static/)│
                         │  - Security Headers       │
                         └─────────────┬─────────────┘
                                       │ (Mạng nội bộ 'internal')
                                       ▼ (Port 8000)
                         ┌───────────────────────────┐
                         │   GUNICORN + FLASK APP    │
                         │  - Web Blueprints         │
                         │  - Service Layer Logic    │
                         │  - APScheduler (Task nền) │
                         └─────────────┬─────────────┘
                                       │ (Mạng nội bộ 'internal' - No public port)
                                       ▼ (Port 3306)
                         ┌───────────────────────────┐
                         │      MYSQL 8.0 DATABASE   │
                         │  - Persistent Volume      │
                         │  - SQLAlchemy Pooling     │
                         └───────────────────────────┘
```

### Luồng xử lý request
1. Client gửi yêu cầu HTTPS ➔ Nginx tiếp nhận, giải mã TLS.
2. Nếu là file tĩnh (`/static/...`) ➔ Nginx phục vụ trực tiếp từ ổ đĩa (kèm header `Cache-Control: 7d`).
3. Nếu là request động ➔ Nginx chuyển tiếp (proxy_pass) sang Gunicorn trên cổng 8000 mạng nội bộ.
4. Flask App định tuyến request qua Middleware (Rate limiter, Session, CSRF check) ➔ Controller/Blueprint ➔ Service Layer ➔ SQLAlchemy ORM truy vấn MySQL.
5. Template Jinja2 được render thành HTML hoàn chỉnh và trả ngược về client.

### Cấu trúc thư mục

```
sportzone/
├── app/
│   ├── account/          # Phân hệ khách hàng (Profile, Đơn hàng, Giỏ hàng, Đổi trả)
│   ├── admin/            # Phân hệ quản trị (Sản phẩm, Người dùng, Quyền, Báo cáo)
│   ├── auth/             # Xác thực (Đăng nhập, Đăng ký, Quên/Đổi mật khẩu)
│   ├── models/           # Thực thể CSDL SQLAlchemy chuẩn hóa (Account, Order, Product...)
│   ├── payment/          # Module xử lý thanh toán (COD, Mock, VNPay)
│   ├── services/         # Tầng nghiệp vụ cốt lõi (order_service, ghn_service, vnpay...)
│   ├── shop/             # Mua sắm công khai (Trang chủ, Catalog, Chi tiết, 4 Trang Chính sách)
│   ├── staff/            # Nghiệp vụ nhân viên (Quản lý đơn, Kho, Xử lý đổi trả)
│   ├── static/           # CSS, JS (address.js, product.js), Hình ảnh, Favicon, Logo
│   ├── tasks/            # Tác vụ chạy nền định kỳ APScheduler (Hủy đơn quá hạn)
│   ├── templates/        # Giao diện Jinja2 HTML5
│   │   └── shop/policies/ # 4 trang chính sách pháp lý (Privacy, Terms, Returns, Shipping)
│   └── utils/            # Decorators phân quyền, mã hóa bảo mật, formatters
├── data/administrative/  # Dữ liệu hành chính 34 tỉnh/thành và 3.321 phường/xã
├── migrations/           # Nhật ký chuyển dịch cơ sở dữ liệu Flask-Migrate
├── scripts/              # Kịch bản nạp dữ liệu (seed_dev.py), backup.sh, restore.sh
├── tests/                # Bộ kiểm thử tự động 399 test cases
├── config.py             # Cấu hình môi trường (Development, Testing, Production)
├── docker-compose.prod.yml # Docker Compose triển khai môi trường Production VPS
├── docker-compose.yml    # Docker Compose môi trường Local/Dev
├── Dockerfile.prod       # Dockerfile tối ưu cho Production (User non-root, Gunicorn)
├── nginx.prod.conf       # Cấu hình Nginx Production (HTTPS, Let's Encrypt, Security Headers)
├── locustfile.py         # Kịch bản kiểm thử tải hệ thống bằng Locust
└── wsgi.py               # Điểm vào WSGI khởi chạy ứng dụng
```

### Quy trình thanh toán, đặt hàng
```
[ Khách hàng chọn hàng ] ──► [ Giỏ hàng ] ──► [ Chọn địa chỉ & Gói giao hàng GHN ]
                                                          │
          ┌───────────────────────────────────────────────┴───────────────────────────────────────────────┐
          ▼ (COD - Mặc định)                                                                              ▼ (VNPay Online)
[ Đặt hàng thành công ]                                                                         [ Chuyển sang Cổng VNPay ]
          │                                                                                               │
          │                                                                                 Quét VietQR / Thẻ ngân hàng
          │                                                                                               │
          │                                                                              [ Webhook IPN xác nhận SHA-512 ]
          │                                                                                               │
          └───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                          ▼
                                            [ Đơn hàng: ĐÃ XÁC NHẬN ]
                                                          │
                                            [ Tự động gửi Email thông báo ]
                                                          │
                                            [ Kho duyệt đơn & Bắn đơn GHN ]
                                                          │
                                            [ Bưu tá giao & Khách đồng kiểm ]
```

---

## Yêu cầu môi trường

* **Python:** Phiên bản 3.12 trở lên (kèm `pip` và `virtualenv`).
* **Docker & Docker Compose:** Docker Engine v24.0+ và Docker Compose v2.20+.
* **MySQL:** Phiên bản 8.0+ (sử dụng Native Password hoặc Caching SHA2 Password).
* **Domain & HTTPS (Cho Production):** Tên miền hợp lệ trỏ bản ghi DNS A về địa chỉ IP của máy chủ, mở cổng Firewall 80 (HTTP) và 443 (HTTPS).

---

## Cài đặt môi trường phát triển

### 1. Chạy với Python thuần (Local Dev)
```powershell
# 1. Di chuyển vào thư mục dự án
cd c:\WEB_TMDT\sportzone

# 2. Tạo và kích hoạt môi trường ảo
python -m venv .venv
.\.venv\Scripts\activate

# 3. Cài đặt các gói thư viện
pip install -r requirements.txt

# 4. Tạo file cấu hình môi trường từ mẫu
copy .env.example .env

# 5. Cập nhật cấu trúc database (mặc định dùng SQLite cục bộ)
flask db upgrade

# 6. Nạp dữ liệu mẫu ban đầu (sản phẩm, tài khoản thử nghiệm)
python scripts/seed_dev.py

# 7. Khởi chạy máy chủ phát triển
flask run
```
Truy cập: **http://127.0.0.1:5000**

### 2. Chạy với Docker Compose (Dev Container)
```bash
docker compose up --build -d
```
Truy cập: **http://localhost**

---

## Cấu hình biến môi trường

### Bảng biến môi trường cốt lõi

| Tên biến | Kiểu giá trị | Mặc định Dev | Mục đích |
|---|---|---|---|
| `FLASK_ENV` | `development` / `production` | `development` | Xác định cấu hình môi trường ứng dụng |
| `SECRET_KEY` | String (Bảo mật cao) | `dev-secret...` | Khóa mã hóa Cookie Session, CSRF Token |
| `DATABASE_URL` | URI kết nối | SQLite cục bộ | Chuỗi kết nối CSDL (MySQL 8 trên Production) |
| `MYSQL_PASSWORD` | String | `sportzone123` | Mật khẩu truy cập CSDL MySQL |
| `MAIL_SERVER` | Hostname | `smtp.gmail.com` | Địa chỉ máy chủ SMTP gửi thư tự động |
| `MAIL_PORT` | Integer | `587` | Cổng giao tiếp SMTP (587 TLS) |
| `MAIL_USERNAME` | Email | `...` | Tài khoản email gửi thư hệ thống |
| `MAIL_PASSWORD` | String (16 ký tự) | `...` | Mật khẩu ứng dụng (Google App Password) |
| `GHN_API_URL` | URL | Sandbox GHN | Cổng API kết nối Giao Hàng Nhanh |
| `GHN_API_TOKEN` | Token bí mật | Để trống (Chạy giả lập)| Mã ủy quyền kết nối bưu cục GHN |

### Quy tắc bảo mật
* File `.env` chứa thông tin nhạy cảm (mật khẩu CSDL, khóa bí mật, app password) **tuyệt đối không được commit lên GitHub**.
* Dự án cung cấp sẵn `.env.example` với đầy đủ chú thích để quản trị viên tham khảo và tự tạo file `.env` riêng biệt.

---

## Chạy kiểm thử

Toàn bộ hệ thống được bảo vệ bởi **399 kịch bản kiểm thử tự động** chạy độc lập trên cơ sở dữ liệu `SQLite in-memory`.

```powershell
cd c:\WEB_TMDT\sportzone

# Chạy toàn bộ 399 test cases:
.\.venv\Scripts\pytest tests/ -q

# Chạy test chi tiết từng ca kiểm thử:
.\.venv\Scripts\pytest tests/ -v

# Kiểm tra phân hệ cửa hàng & 4 trang chính sách pháp lý:
.\.venv\Scripts\pytest tests/test_shop.py -v

# Xuất báo cáo độ phủ mã nguồn (Code Coverage):
.\.venv\Scripts\pytest tests/ --cov=app --cov-report=term-missing
```

### Kiểm thử tải (Load Testing với Locust)
Kiểm thử chịu tải trực tiếp trên website thực tế `https://sportzone.id.vn`:
```powershell
# Chạy có giao diện web trực quan (mở http://localhost:8089):
.\.venv\Scripts\locust -f locustfile.py --host=https://sportzone.id.vn

# Chạy tự động dòng lệnh (Headless - 20 người dùng trong 30 giây):
.\.venv\Scripts\locust -f locustfile.py --headless -u 20 -r 5 --run-time 30s --host=https://sportzone.id.vn
```

---

## Triển khai production

Hệ thống đang hoạt động thực tế trên VPS Ubuntu 22.04 LTS tại địa chỉ IP `180.93.196.157`.

### 1. Cấu hình DNS Tên miền
* Bản ghi `@` (A record) ➔ `180.93.196.157`
* Bản ghi `www` (CNAME) ➔ `sportzone.id.vn`

### 2. Khởi chạy bằng Docker Compose Production
```bash
cd /opt/sportzone

# Khởi chạy toàn bộ 4 container:
docker compose -f docker-compose.prod.yml up -d --build

# Nạp migration CSDL MySQL:
docker compose -f docker-compose.prod.yml exec app flask db upgrade
```

### 3. Cấu hình & Gia hạn SSL Let's Encrypt
* Chứng chỉ SSL được quản lý bởi container `certbot`.
* Lệnh gia hạn chứng chỉ khi sắp hết hạn:
  ```bash
  docker compose -f docker-compose.prod.yml run --rm certbot renew
  docker compose -f docker-compose.prod.yml restart nginx
  ```

---

## Vận hành và giám sát

### Xem nhật ký & Quản lý Container
```bash
# Xem log ứng dụng thời gian thực:
docker compose -f docker-compose.prod.yml logs -f app

# Xem tình trạng tiêu thụ CPU, RAM của từng container:
docker stats

# Khởi động lại dịch vụ web:
docker compose -f docker-compose.prod.yml restart app nginx
```

### Kiểm tra sức khỏe hệ thống (Health Check)
* Endpoint `/health`: Trả về `{"status": "ok"}` khi Flask và kết nối MySQL sống. Nginx được cấu hình tắt access log cho endpoint này để bảo vệ dung lượng đĩa.
* MySQL Healthcheck: Chạy định kỳ `mysqladmin ping` mỗi 10 giây.
* Container tự phục hồi: Cấu hình `restart: unless-stopped` tự khởi động lại khi crash.

---

## Bảo mật

1. **Xác thực & Mã hóa:** Thuật toán `bcrypt` mã hóa mật khẩu; token khôi phục mật khẩu băm `SHA-256` thời hạn 30 phút.
2. **Bảo vệ Cookie & Session:** Bật cờ `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE = "Lax"` và `SESSION_COOKIE_SECURE = True` trên kết nối HTTPS.
3. **Chống brute-force (Rate Limiting):** Giới hạn per-IP (Đăng nhập: 10 lần/phút, Đăng ký: 20 lần/giờ, Quên mật khẩu: 10 lần/giờ). Tài khoản tự khóa tạm 15 phút sau 5 lần nhập sai.
4. **Bảo vệ danh tính (Prevent User Enumeration):** Thông báo quên mật khẩu trả về đồng nhất, ngăn chặn dò quét tài khoản.
5. **Security Headers (Nginx):** Cấu hình `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `HSTS max-age=31536000`.
6. **Cô lập CSDL:** Container MySQL 8 nằm trong mạng Docker nội bộ `internal`, hoàn toàn không mở cổng 3306 ra Internet.

---

## Hiệu năng và khả năng mở rộng

### Kết quả đo kiểm tải thực tế (Locust Benchmark Matrix trên Production)

| Mức tải người dùng | Tổng số Request | Tỉ lệ lỗi | Thông lượng (RPS) | Độ trễ TB (Avg) | Phân vị 90% (90th) |
|---|:---:|:---:|:---:|:---:|:---:|
| **20 Users** | 278 | **0.00%** | **9.53 req/s** | **104 ms** | **140 ms** |
| **100 Users** | 1,188 | **0.00%** | **40.20 req/s** | **378 ms** | **640 ms** |
| **200 Users** | 1,281 | **0.00%** | **43.26 req/s** | **2,266 ms** | **3,000 ms** |

### Giới hạn & Hướng mở rộng
* **Giới hạn hiện tại:** Cấu hình 1 worker Gunicorn duy nhất (nhằm bảo đảm an toàn cho luồng APScheduler trong app factory) đạt ngưỡng bão hòa ở mức **~43 req/s**.
* **Kế hoạch mở rộng (Scale-up):**
  1. Tách APScheduler ra container độc lập, nâng Gunicorn lên `(2 x Core CPU) + 1` workers.
  2. Bổ sung bộ nhớ đệm **Redis Cache** cho trang danh mục và trang chủ.
  3. Cân bằng tải mở rộng ngang (Horizontal Scaling) bằng nhiều container `app` phía sau Nginx.

---

## Tài khoản demo

*(Chỉ sử dụng trên môi trường thử nghiệm / Local Dev sau khi chạy `seed_dev.py`. Không áp dụng cho môi trường Production)*

| Tài khoản Email | Mật khẩu mặc định | Vai trò | Chức năng kiểm thử |
|---|---|---|---|
| `admin@sportzone.local` | `Admin123456` | Quản trị viên (`ADMIN`) | Quản lý hệ thống, phân quyền, sản phẩm, báo cáo |
| `staff@sportzone.local` | `Staff123456` | Nhân viên (`STAFF`) | Xử lý đơn hàng, nhập kho, duyệt đổi trả |
| `khach1@test.com` | `Khach123456` | Khách hàng (`CUSTOMER`) | Đặt hàng, theo dõi đơn, đổi trả, đánh giá |
| `khach2@test.com` | `Khach123456` | Khách hàng (`CUSTOMER`) | Kiểm thử tương tác nhiều người dùng |

---

## API hoặc route chính

* **Khách hàng:**
  * `GET /`: Trang chủ
  * `GET /products`, `GET /products/<slug>`: Danh sách & chi tiết sản phẩm
  * `GET /privacy-policy`: Chính sách bảo vệ dữ liệu cá nhân
  * `GET /terms`: Điều khoản mua bán & giao kết dịch vụ
  * `GET /returns-policy`: Chính sách đổi trả & hoàn tiền (07 ngày)
  * `GET /shipping-policy`: Chính sách vận chuyển & đồng kiểm GHN
  * `POST /account/cart/add`: Thêm sản phẩm vào giỏ
  * `GET /account/checkout`, `POST /account/checkout`: Đặt hàng
  * `GET /account/orders`, `GET /account/orders/<code>`: Xem đơn hàng
* **Nhân viên:**
  * `GET /staff/orders`: Quản lý danh sách đơn
  * `POST /staff/orders/<code>/ship-ghn`: Phát sinh vận đơn GHN tự động
  * `GET /staff/stock`: Thẻ kho xuất-nhập-tồn
  * `GET /staff/returns`: Xử lý yêu cầu đổi trả
* **Quản trị:**
  * `GET /admin/`: Thống kê tổng quan Dashboard
  * `GET /admin/reports`: Báo cáo doanh thu & sản phẩm bán chạy
  * `GET /admin/roles`, `POST /admin/roles`: Bảng phân quyền vai trò
  * `GET /admin/audit-logs`: Tra cứu nhật ký kiểm toán
* **Giám sát:**
  * `GET /health`: Kiểm tra sức khỏe hệ thống (Health Check)

---

## Hạn chế và hướng phát triển

1. **Thanh toán trực tuyến:** Đang tích hợp ở chế độ Sandbox / API Ready. Cần hoàn tất đăng ký pháp nhân doanh nghiệp để ký kết hợp đồng thương mại tiền thật với VNPay/MoMo.
2. **Dịch vụ vận chuyển GHN:** Hỗ trợ cơ chế Smart Simulation khi thiếu token bưu cục thật.
3. **Bộ nhớ đệm:** Chưa triển khai Redis; các tác vụ nền đang chạy trên tiến trình nội bộ APScheduler thay vì Celery/Redis Queue.
4. **Hạ tầng đơn cụm:** Hiện chạy trên 1 VPS duy nhất, chưa cấu hình Multi-server dự phòng thảm họa phần cứng.

---

## Sao lưu và khôi phục

### Kế hoạch sao lưu (RPO 24h, RTO < 30p)
* **Script tự động hóa:** [`scripts/backup.sh`](scripts/backup.sh) trích xuất CSDL MySQL bằng `mysqldump` không khóa bảng, nén định dạng `.sql.gz` và lưu trữ tại `/opt/sportzone/backups`.
* **Lịch trình Cron Job:** Tự động chạy lúc **02:00 sáng hàng ngày**:
  ```text
  0 2 * * * /bin/bash /opt/sportzone/scripts/backup.sh >/dev/null 2>&1
  ```
* **Chính sách xoay vòng:** Tự động xóa các bản sao lưu cũ hơn **7 ngày** để tối ưu hóa bộ nhớ VPS.

### Quy trình khôi phục (1-Click Recovery)
Khôi phục nguyên trạng CSDL từ bản sao lưu gần nhất khi gặp sự cố:
```bash
/bin/bash /opt/sportzone/scripts/restore.sh
```

---

## Khắc phục sự cố

* **Container không khởi động:** Kiểm tra file log bằng `docker compose logs app`. Đảm bảo file `.env` đã được cấu hình đầy đủ biến `SECRET_KEY` và `MYSQL_PASSWORD`.
* **Database không kết nối được:** Kiểm tra trạng thái container DB bằng `docker ps`. Đảm bảo container `db` đã đạt trạng thái `healthy` trước khi app khởi động.
* **Lỗi chứng chỉ SSL:** Kiểm tra nhật ký certbot bằng `docker compose logs certbot`. Đảm bảo cổng 80 và 443 trên máy chủ không bị tường lửa VPS chặn.
* **Không nhận được Email đặt lại mật khẩu:** Kiểm tra cấu hình `MAIL_USERNAME` và `MAIL_PASSWORD` (Mật khẩu ứng dụng 16 ký tự của Google) trong file `.env`.
* **Lỗi API GHN:** Kiểm tra kết nối mạng ngoài từ container app hoặc chuyển về chế độ Smart Simulation bằng cách bỏ trống `GHN_API_TOKEN`.

---

## Hướng dẫn build và cấu trúc release

* **Chi nhánh chính (Branch):** `main` — Chứa mã nguồn ổn định sẵn sàng triển khai môi trường Production.
* **Quy trình Release & Deploy:**
  1. Kiểm thử toàn bộ tính năng ở môi trường cục bộ: `pytest tests/ -q` (399/399 passed).
  2. Commit mã nguồn kèm thông điệp chuẩn mực: `git commit -m "feat/fix: ..."`
  3. Đẩy lên kho lưu trữ GitHub: `git push origin main`
  4. Cập nhật trên VPS:
     ```bash
     cd /opt/sportzone
     git pull origin main
     docker compose -f docker-compose.prod.yml restart app nginx
     ```

---

## Tác giả

* **Nhóm tác giả Đồ án Thương mại điện tử SportZone**
  * Thiết kế kiến trúc hệ thống, phát triển phân hệ Backend & API tích hợp 3PL.
  * Xây dựng giao diện Responsive, bộ lọc động và 4 trang chính sách pháp lý.
  * Triển khai hạ tầng VPS, Docker Compose, Nginx SSL, kịch bản sao lưu và kiểm thử hiệu năng.

---

## License

Dự án được phát triển phục vụ mục đích học thuật, nghiên cứu và đánh giá đồ án môn học Thương mại điện tử. Mọi quyền sở hữu trí tuệ và bản quyền mã nguồn thuộc về Nhóm tác giả SportZone &copy; 2026.
