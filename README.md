# Campus Event Portal — Hệ thống Đăng ký Sự kiện Đại học (AWS + Cloudflare Multi-Cloud)

**Campus Event Portal** là ứng dụng web quản lý và đăng ký sự kiện đại học chịu tải cao, chống đăng ký quá chỗ (race condition), hỗ trợ phân quyền chặt chẽ 3 vai trò, xác thực tài khoản an toàn và triển khai tự động theo mô hình **Multi-Cloud (Cloudflare Edge HTTPS + AWS Cloud)**.

> 🌐 **Truy cập bản Demo trực tuyến 24/7 (Cloudflare HTTPS + AWS EC2 — mở được từ mọi mạng Wi-Fi/4G):**
> - **Trang chủ ứng dụng:** https://musical-painted-realtors-administered.trycloudflare.com
> - **Kiểm tra trạng thái hệ thống (`/readyz`):** https://musical-painted-realtors-administered.trycloudflare.com/readyz
> - **API danh sách sự kiện (`/api/events`):** https://musical-painted-realtors-administered.trycloudflare.com/api/events
>
> *(Lưu ý: Đường link `http://127.0.0.1:4173/` ở Mục 5 bên dưới chỉ dùng khi bạn tự chạy máy chủ trên máy tính cá nhân bằng lệnh `py -3 server.py`.)*

---

## 1. Tính năng nổi bật

- **Giao diện hiện đại (Modern Indigo & Slate):** Thiết kế tối ưu tiếng Việt với bộ font **`Plus Jakarta Sans`** và **`Be Vietnam Pro`**, hỗ trợ đầy đủ cả máy tính lẫn điện thoại (`dist/theme-modern.css`).
- **Đăng ký & Đăng nhập tài khoản thật:**
  - Sinh viên tự đăng ký tài khoản bằng **Họ tên, Mã sinh viên, Email, Mật khẩu** (12–128 ký tự), băm mật khẩu an toàn bằng **`scrypt`**.
  - Phiên đăng nhập lưu bằng Cookie **`HttpOnly; SameSite=Strict`** (tự bật `Secure` qua HTTPS), bảo vệ **CSRF Token (`X-CSRF-Token`)**, kiểm tra `Origin` và giới hạn tốc độ (**Rate Limit**) chống dò mật khẩu.
  - Tự động khóa chế độ giả danh `X-Demo-User` khi truy cập từ ngoài Internet qua Proxy/Cloudflare.
- **Đăng ký / Hủy chỗ chuẩn giao dịch (Transactional & Idempotent):**
  - Xử lý an toàn **100 yêu cầu đồng thời tranh 20 chỗ** — chỉ đúng 20 sinh viên giữ chỗ thành công, 80 yêu cầu còn lại trả `409 EVENT_FULL`, tuyệt đối không âm chỗ hay tạo vé trùng.
  - Hỗ trợ **`Idempotency-Key`** giúp thử lại an toàn khi mất kết nối giữa chừng mà không bị trừ chỗ 2 lần.
- **Quản lý sự kiện cho Ban tổ chức & Quản trị viên:**
  - Tạo & xuất bản sự kiện mới, **chỉnh sửa thông tin/mô tả chi tiết sự kiện** đã xuất bản.
  - Theo dõi sức chứa theo thời gian thực, xem danh sách sinh viên tham gia (roster) và **xuất danh sách CSV** (có UTF-8 BOM hiển thị chuẩn tiếng Việt trong Excel, chống CSV formula injection, hỗ trợ lưu trữ cục bộ hoặc **Amazon S3**).
- **Giám sát, Telemetry & Sao lưu/Khôi phục:**
  - Cung cấp endpoint sức khỏe `/healthz`, sẵn sàng `/readyz`, gắn mã truy vết `X-Request-Id` và log cấu trúc JSON.
  - Sao lưu & khôi phục dữ liệu toàn vẹn có kiểm tra mã băm **`SHA-256`** và kiểm toán tự động (`audit`).

---

## 2. Kiến trúc hệ thống (Multi-Cloud: Cloudflare + AWS)

```text
Người dùng (Trình duyệt / Điện thoại qua Internet)
        │  HTTPS (SSL/TLS)
        ▼
Cloudflare Edge Network (Cloudflare Quick Tunnel — cloudflared)
        │  Kết nối mã hóa ra từ EC2 (không cần mở cổng 0.0.0.0/0 trên AWS)
        ▼
AWS Cloud (Region: ap-southeast-2 — CloudFormation Stack)
 ├── VPC + Subnets + Security Group + IAM Role (Least Privilege)
 ├── Amazon EC2 (Ubuntu 24.04 LTS + systemd: campus-portal & campus-tunnel)
 ├── Amazon EBS gp3 mã hóa (/var/lib/campus/portal.sqlite3 — SQLite WAL)
 ├── Amazon S3 Bucket riêng tư (mã hóa AES-256, lưu gói phát hành / CSV export)
 ├── AWS SSM Parameter Store (tự động cập nhật link HTTPS Cloudflare)
 ├── Amazon CloudWatch (Dashboard + 2 Alarms: CPU > 80% & StatusCheckFailed)
 └── Tùy chọn mở rộng tích hợp sẵn trong CloudFormation:
      ├── Amazon Cognito (User Pool, Hosted UI, nhóm Students/Organizers/Administrators)
      └── Amazon RDS PostgreSQL 16 (Private Subnet, mã hóa, backup 7 ngày)
```

---

## 3. Hệ thống phân quyền (RBAC)

Hệ thống phân quyền chặt chẽ ở cả tầng **API Backend** (`server.py`, `backend/auth.py`), **Cơ sở dữ liệu** và **AWS Cognito Groups**:

| Vai trò (`role`) | Nhóm AWS Cognito | Quyền được phép | Hành vi bị chặn (`401` / `403` / `404`) |
| :--- | :--- | :--- | :--- |
| **Sinh viên (`student`)** | `Students` | Xem danh mục sự kiện, đăng ký giữ chỗ, xem biên nhận & lịch sử của mình, tự hủy vé của mình. | Không tạo/sửa sự kiện; không xem roster hoặc xuất CSV; không hủy vé của người khác; không thể tự nâng quyền khi đăng ký tài khoản. |
| **Ban tổ chức (`organizer`)** | `Organizers` | Tạo sự kiện mới; sửa thông tin, xem roster và xuất CSV **chỉ cho sự kiện do mình làm chủ**. | Không sửa, xem roster hoặc xuất CSV sự kiện của Ban tổ chức khác. |
| **Quản trị viên (`administrator`)** | `Administrators` | Toàn quyền xem danh sách, chỉnh sửa, xuất CSV và quản lý tất cả sự kiện trên hệ thống. | — |

---

## 4. Cấu trúc thư mục dự án

```text
portal/
├── server.py                     # Máy chủ HTTP API (hỗ trợ SQLite & PostgreSQL, bảo mật CSRF/Proxy)
├── fixtures.json                 # Dữ liệu mẫu (100 sinh viên, 6 sự kiện, ban tổ chức & quản trị viên)
├── requirements.txt              # Thư viện Python (psycopg, PyJWT[crypto], boto3...)
├── package.json                  # Script khởi chạy & kiểm thử Frontend (Node.js)
├── BAT-DAU.bat                   # File bấm đúp chạy nhanh trên Windows
├── backend/
│   ├── 001_schema.sql            # Lược đồ cơ sở dữ liệu
│   ├── db.py                     # Bộ xử lý giao dịch SQLite (WAL, chống race condition)
│   ├── postgres.py               # Bộ xử lý giao dịch PostgreSQL / Amazon RDS (SELECT FOR UPDATE)
│   ├── auth.py                   # Xác thực AWS Cognito JWT (RS256/JWKS) & ánh xạ vai trò
│   ├── accounts.py               # Quản lý tài khoản, băm mật khẩu scrypt, phiên & rate limit
│   ├── account_validation.py     # Kiểm tra hợp lệ Email và CSRF Token
│   ├── event_updates.py          # Nghiệp vụ chỉnh sửa sự kiện có kiểm tra chủ sở hữu & idempotency
│   ├── storage.py                # Lưu trữ file xuất CSV (ổ đĩa cục bộ hoặc Amazon S3)
│   ├── backup.py                 # Sao lưu & khôi phục dữ liệu có kiểm tra SHA-256
│   ├── telemetry.py              # Log cấu trúc JSON, X-Request-Id & số liệu hệ thống
│   └── settings.py               # Đọc cấu hình môi trường & AWS Secrets Manager
├── dist/                         # Giao diện Web (HTML/CSS/JS thuần, không cần bước build phức tạp)
│   ├── index.html
│   ├── styles.css
│   ├── theme-modern.css          # Giao diện Modern Indigo & Slate + font tiếng Việt
│   └── js/                       # app.js, api.js, cognito-auth.js, data.js, utils.js
├── deploy/aws/
│   ├── campus-ec2.yaml           # Mẫu AWS CloudFormation IaC đầy đủ (EC2, EBS, CloudWatch, Tunnel, Cognito, RDS)
│   ├── deploy-aws.ps1            # Script PowerShell đóng gói và triển khai tự động 1 lệnh
│   └── backup-restore.ps1        # Script sao lưu cục bộ, chụp EBS Snapshot và Rollback CloudFormation
├── scripts/
│   ├── benchmark_e.py            # Công cụ Benchmark tải cao & tiêm lỗi mạng (Phần E)
│   ├── set_account_password.py   # Công cụ đặt mật khẩu an toàn cho tài khoản mẫu (org-1, admin-1)
│   └── start.cjs                 # Script khởi chạy server qua npm start
├── tests/                        # 42 bài test Python + 20 bài test Node.js
├── .github/workflows/ci-cd.yml   # Quy trình CI/CD tự động trên GitHub Actions
├── REPORT-B.md                   # Báo cáo kiểm toán & khắc phục lỗi (Phần B)
├── REPORT-C-D-E.md               # Báo cáo kiến trúc Cloud, vận hành & Benchmark (Phần C, D, E)
├── BENCHMARK-E-RESULTS.json      # Số liệu đo độ trễ p50/p95/p99 và kiểm toán Phần E
└── TEST-RESULTS.txt              # Tổng hợp kết quả kiểm thử tự động
```

---

## 5. Hướng dẫn chạy trên máy cá nhân (Local)

### Yêu cầu môi trường
- **Python 3.10 trở lên** (bắt buộc).
- **Node.js 20 trở lên** (nếu dùng lệnh `npm.cmd start` và chạy test Frontend).

### Bước 1: Khởi động máy chủ
Mở PowerShell tại thư mục dự án và chạy **một trong các cách sau**:

```powershell
# Cách 1: Chạy trực tiếp bằng Python
py -3 server.py

# Cách 2: Chạy qua npm
npm.cmd start

# Cách 3: Bấm đúp file khởi chạy nhanh trên Windows
.\BAT-DAU.bat
```

*(Trên Linux/macOS dùng lệnh `python3 server.py`. Không mở trực tiếp file `dist/index.html` vì giao diện cần gọi API từ máy chủ.)*

Truy cập trình duyệt tại: **http://127.0.0.1:4173/** — nhấn `Ctrl + C` để dừng máy chủ.

### Bước 2: Sử dụng & Đặt mật khẩu tài khoản quản trị trên máy
- **Sinh viên:** Bấm nút **Đăng ký** ở góc phải màn hình để tạo tài khoản sinh viên mới bằng MSSV, Email và Mật khẩu (tối thiểu 12 ký tự), sau đó đăng ký sự kiện, xem biên nhận và hủy chỗ.
- **Ban tổ chức / Quản trị viên:** Để đăng nhập bằng tài khoản mẫu có sẵn (`org-1` hoặc `admin-1`), chạy lệnh đặt mật khẩu:

```powershell
py -3 scripts/set_account_password.py org-1
py -3 scripts/set_account_password.py admin-1
```

Sau đó đăng nhập trên web bằng Email tương ứng trong dữ liệu mẫu:
- Ban tổ chức (`org-1`): `organizer@example.test`
- Quản trị viên (`admin-1`): `admin@example.test`

---

## 6. Hướng dẫn triển khai lên AWS + Cloudflare HTTPS

### Điều kiện chuẩn bị
1. Đã cài đặt **AWS CLI** và cấu hình thông tin xác thực bằng `aws configure` (tài khoản IAM có quyền CloudFormation, EC2/VPC, EBS, IAM, S3, SSM, CloudWatch).
2. Không cần mua tên miền riêng nếu dùng **Cloudflare Quick Tunnel** (mặc định được bật sẵn trong mẫu CloudFormation).

### Triển khai tự động 1 lệnh (EC2 + Encrypted EBS + CloudWatch + Cloudflare HTTPS)

```powershell
.\deploy\aws\deploy-aws.ps1 `
  -Region ap-southeast-2 `
  -OrganizerPassword "MatKhauBanToChuc>=12KyTu" `
  -AdminPassword "MatKhauQuanTriVien>=12KyTu"
```

Script sẽ tự động thực hiện toàn bộ quy trình:
1. Tự nhận diện IPv4 công cộng của bạn (khóa Security Group ở mức `/32`, từ chối `0.0.0.0/0`).
2. Đóng gói mã nguồn vào một **Amazon S3 Bucket riêng tư** (bật mã hóa `AES256`, chặn truy cập công khai).
3. Dựng stack CloudFormation `campus-event-portal` gồm **VPC, EC2, EBS `gp3` mã hóa, CloudWatch Dashboard & Alarms, dịch vụ `cloudflared` (Cloudflare HTTPS Tunnel)**.
4. Khởi tạo cơ sở dữ liệu, đặt mật khẩu cho `org-1` / `admin-1` an toàn (không ghi ra log) và in ra đường link công khai **`https://...trycloudflare.com`**.

### Lấy lại đường link Cloudflare HTTPS bất kỳ lúc nào

```powershell
aws ssm get-parameter --name /campus-event-portal/tunnel-url --region ap-southeast-2 --query Parameter.Value --output text
```

### Triển khai nâng cao kèm Amazon Cognito và/hoặc Amazon RDS PostgreSQL 16

```powershell
.\deploy\aws\deploy-aws.ps1 `
  -Region ap-southeast-2 `
  -ProvisionCognito `
  -ProvisionRds `
  -DbMasterPassword "MatKhauRDSManh2026!"
```

### Xóa toàn bộ tài nguyên AWS sau khi demo xong (tránh phát sinh chi phí)

```powershell
aws cloudformation delete-stack --stack-name campus-event-portal --region ap-southeast-2
aws cloudformation wait stack-delete-complete --stack-name campus-event-portal --region ap-southeast-2
aws ssm delete-parameter --name /campus-event-portal/tunnel-url --region ap-southeast-2
aws s3 rb s3://TEN-BUCKET-S3-CUA-BAN --force --region ap-southeast-2
```

---

## 7. Quản trị, Sao lưu, Khôi phục & Rollback

```powershell
# Khởi tạo / nạp dữ liệu mẫu / kiểm toán toàn vẹn dữ liệu
py -3 server.py migrate
py -3 server.py seed
py -3 server.py audit

# Sao lưu & khôi phục dữ liệu có kiểm tra chữ ký SHA-256
py -3 server.py backup --file campus-backup.json
py -3 server.py restore --file campus-backup.json

# Tiện ích vận hành AWS (sao lưu, chụp EBS Snapshot, Rollback CloudFormation)
.\deploy\aws\backup-restore.ps1 -Action local-backup -BackupFile campus-backup.json
.\deploy\aws\backup-restore.ps1 -Action local-restore -BackupFile campus-backup.json
.\deploy\aws\backup-restore.ps1 -Action ebs-snapshot -Region ap-southeast-2
.\deploy\aws\backup-restore.ps1 -Action cfn-rollback -Region ap-southeast-2
```

---

## 8. Kiểm thử tự động, CI/CD & Benchmark tải cao

Cài đặt thư viện phụ thuộc và chạy toàn bộ bộ kiểm thử:

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m unittest discover -s tests -p "test_*.py" -v
npm.cmd test
npm.cmd run check
py -3 scripts/benchmark_e.py
```

### Kết quả kiểm thử đã xác minh
- **Backend, Bảo mật, Proxy, Tài khoản & AWS IaC:** **42/42 tests PASS** (`OK`).
- **Frontend & Client Adapter:** **20/20 tests PASS** (`0 fail`) + kiểm tra cú pháp sạch lỗi.
- **Benchmark Phần E (`BENCHMARK-E-RESULTS.json`):**
  - **E1 (100 yêu cầu HTTP đồng thời tranh 20 chỗ):** Đúng `20` HTTP `201`, `80` HTTP `409 EVENT_FULL`, `0` lỗi `5xx` (`p50 = 111.376 ms`, `p95 = 609.107 ms`, `p99 = 773.499 ms`).
  - **E2 (Tiêm lỗi mất phản hồi sau commit `X-Drop-After-Commit` + 10 lần thử lại):** `10/10` trả `201` với `Idempotency-Replayed: true`, không trừ thêm chỗ.
  - **E3 (20 hủy đồng thời + kiểm tra xung đột khóa):** `20/20` trả `200`, xung đột khóa trả `409 IDEMPOTENCY_CONFLICT`, `auditBefore` & `auditAfter` đều `ok = true`.
- **CI/CD:** Tự động chạy kiểm thử và benchmark trên **GitHub Actions** tại [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml) mỗi khi đẩy mã lên nhánh `main`.

---

## 9. Tài liệu báo cáo đính kèm

- [REPORT-B.md](REPORT-B.md) — Báo cáo kiểm toán lỗi hệ thống, tranh chấp dữ liệu và cách khắc phục (Phần B).
- [REPORT-C-D-E.md](REPORT-C-D-E.md) — Báo cáo kiến trúc Cloud, bảo mật, vận hành Backup/Restore/Rollback và phân tích Benchmark (Phần C, D, E).
- [TEST-RESULTS.txt](TEST-RESULTS.txt) & [FRONTEND-TEST-RESULTS.txt](FRONTEND-TEST-RESULTS.txt) — Nhật ký kết quả kiểm thử tự động.
- [REFERENCE.md](REFERENCE.md) & [KIEM-TRA.md](KIEM-TRA.md) — Dữ liệu tham chiếu và kịch bản kiểm tra chức năng.
