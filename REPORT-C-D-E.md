# Phần C, D, E — Xác thực Cloud, Hạ tầng AWS IaC, Vận hành, Thiết kế & Chi phí

## 1. Phần C — Xác thực Cloud, RBAC & Hạ tầng AWS IaC

### 1.1 Xác thực & Phân quyền (RBAC + Ownership)
- **Chế độ Local/Cloudflare Proxy (`PORTAL_AUTH_MODE=demo`, `PORTAL_DISABLE_SIGNUP=1`):**
  - Toàn bộ tài khoản sinh viên (`stu-10001`..`stu-10100`), Ban tổ chức (`org-1`, `org-2`) và Quản trị viên (`admin-1`) do nhà trường cấp sẵn trong CSDL; API `/api/auth/register` bị khóa (`403 SIGNUP_DISABLED`).
  - Mật khẩu băm một chiều bằng `scrypt` (`backend/accounts.py`). Phiên đăng nhập sử dụng Cookie `HttpOnly; SameSite=Strict; Secure` (qua Cloudflare HTTPS), kiểm tra `Origin`, `Sec-Fetch-Site`, mã `X-CSRF-Token` và Rate limit theo IP.
  - Khi đi qua Reverse Proxy (`Cf-Connecting-Ip` / `X-Forwarded-For`), máy chủ từ chối hoàn toàn header giả danh `X-Demo-User` (`401`) và chặn `/internal/telemetry` (`404`).
- **Chế độ Amazon Cognito (`PORTAL_AUTH_MODE=cognito`, tùy chọn Production):**
  - **Frontend (`dist/js/cognito-auth.js`):** Đọc cấu hình từ `/runtime-config.js`, điều hướng đăng nhập OAuth2 Authorization Code + PKCE (`S256`), gắn `Authorization: Bearer <access_token>`.
  - **Backend (`backend/auth.py`):** Xác minh chữ ký RS256 qua JWKS, kiểm tra `token_use == "access"`, `client_id`, `iss`, `exp`, và đối chiếu `cognito:groups` (`Students`, `Organizers`, `Administrators`) với cột `role` trong CSDL.
- **Tương thích PostgreSQL (`backend/postgres.py`, `server.py`):** `server.py` tự động chọn `%s` (PostgreSQL) hoặc `?` (SQLite) và đọc khóa cột `r['id']` tương thích `dict_row`.

### 1.2 Infrastructure as Code (`deploy/aws/campus-ec2.yaml`, `deploy/aws/deploy-aws.ps1`)
- **Mạng & Compute:** `PortalVpc` (`10.42.0.0/16`), hai subnet trên 2 Availability Zone (`PortalSubnet` `10.42.1.0/24`, `PortalSubnetB` `10.42.2.0/24`), `PortalInternetGateway`, `PortalSecurityGroup` (chỉ mở cổng `4173` cho `AllowedCidr`), `PortalInstance` (Ubuntu 24.04 LTS, `t3.micro`, IMDSv2 `HttpTokens: required`), `PortalDataVolume` (EBS `gp3` 8GB mã hóa tại `/var/lib/campus`).
- **Multi-Cloud Edge (`EnableCloudflareTunnel=true`):** Dịch vụ `campus-tunnel.service` (`cloudflared`) mở kết nối ra từ EC2 tới Cloudflare Edge Network để cấp HTTPS SSL/TLS công khai và ghi URL tự động vào AWS SSM Parameter `/campus-event-portal/tunnel-url`.
- **Bootstrap & Bảo mật cấu hình:** `UserData` cài `python3-venv`, lưu biến môi trường (với `NoEcho: true`) vào `/etc/campus-portal.env` (`chmod 600`), cấp mật khẩu an toàn qua biến môi trường (không ghi log), và chạy `campus-portal.service`.
- **Tùy chọn Managed Services:** Hỗ trợ `-ProvisionCognito` (User Pool + Hosted UI + 3 nhóm quyền) và `-ProvisionRds` (RDS PostgreSQL 16 `db.t3.micro`, `gp3` 20GB mã hóa, `PubliclyAccessible: false`, `BackupRetentionPeriod: 7`).

---

## 2. Phần D — Giám sát, CI/CD, Backup/Restore & Rollback

### 2.1 Giám sát CloudWatch & Telemetry (`deploy/aws/campus-ec2.yaml`, `backend/telemetry.py`)
- **Dashboard:** `${AWS::StackName}-${AWS::Region}-dashboard` theo dõi `CPUUtilization`, `StatusCheckFailed`, `NetworkIn`, `NetworkOut`.
- **Telemetry ứng dụng (`/internal/telemetry` + structured JSON logs):** Ghi nhận `X-Request-Id` xuyên suốt request/response/log (không ghi mật khẩu/cookie/signed URL), thu thập `booking latency p95`, `capacity conflicts`, `duplicate replays` và `database connection count`.

#### Bảng Cảnh báo vận hành (Actionable Alerts)

| Tên cảnh báo / Chỉ số | Điều kiện kích hoạt (Threshold) | Cửa sổ đánh giá (Window) | Độ trễ dự kiến (Delay) | Hành động khắc phục đầu tiên (First Recovery Action) |
| :--- | :--- | :--- | :--- | :--- |
| **`PortalHighCpuAlarm`** (`AWS/EC2 CPUUtilization`) | `Average > 80%` | 2 chu kỳ liên tiếp × 300s (10 phút) | ~10–11 phút | Kiểm tra log burst/rate-limit trên EC2, xem xét nâng `InstanceType` lên `t3.small` hoặc tách DB sang RDS. |
| **`PortalStatusCheckAlarm`** (`AWS/EC2 StatusCheckFailed`) | `Maximum >= 1` | 1 chu kỳ × 60s | ~1–2 phút | Kiểm tra EC2 Console / `systemctl status campus-portal`, reboot instance hoặc chạy `cfn-rollback` / khôi phục từ EBS Snapshot. |
| **Telemetry ứng dụng** (`p95`, `conflicts`, `replays`, `DB connections`) | `p95 > 1000ms` hoặc `5xx > 1%` hoặc DB connection gần ngưỡng | Mẫu cửa sổ trượt theo request (`/internal/telemetry`) | Tức thời trên log JSON / probe `/readyz` | Kiểm tra khóa giao dịch/tắc nghẽn DB, xác nhận `/readyz` trả `200`, kiểm tra tỷ lệ `Idempotency-Replayed: true` từ retry của client. |

### 2.2 Sao lưu, Phục hồi & Rollback (`backend/backup.py`, `deploy/aws/backup-restore.ps1`)
- **`create_backup`:** Sao lưu nhất quán (`sqlite3.Connection.backup()` hoặc `REPEATABLE READ READ ONLY` trên PostgreSQL), xuất toàn bộ dữ liệu + `audit()` + mã toàn vẹn `sha256`.
- **`restore_backup`:** Xác minh `sha256` trước khi ghi, nạp nguyên tử trong 1 giao dịch và chạy lại `audit()`.
- **`deploy/aws/backup-restore.ps1`:** Hỗ trợ `local-backup`, `local-restore`, `ebs-snapshot` (chụp EBS từ `DataVolumeId`), và `cfn-rollback` (`rollback-stack` / dọn stack lỗi).

### 2.3 CI/CD Pipeline (`.github/workflows/ci-cd.yml`)
Tự động chạy trên `push` (`main`/`master`) và `pull_request`:
1. Chạy `npm test` (20 tests) và `npm run check`.
2. Chạy `python -m unittest discover -s tests -p "test_*.py" -v` (46 tests).
3. Chạy `python scripts/benchmark_e.py` và lưu artifact `BENCHMARK-E-RESULTS.json`.

---

## 3. Phần E — Kiểm chứng Tải HTTP, Tiêm lỗi & Audit

Kết quả chạy thực tế qua HTTP server (`scripts/benchmark_e.py`, `ENABLE_FAULTS=1`, bộ mẫu `100` sinh viên, `6` sự kiện không có dữ liệu giả, thời lượng tải đồng thời `ThreadPoolExecutor(32)` không warmup), lưu chi tiết tại [BENCHMARK-E-RESULTS.json](BENCHMARK-E-RESULTS.json):

| Workload | Kịch bản kiểm thử | Kết quả đạt được | Độ trễ đo được (ms) |
| :--- | :--- | :--- | :--- |
| **E1** | 100 request HTTP đồng thời (`32` workers) tranh 20 chỗ `cloud-lab` | `20` HTTP `201`, `80` HTTP `409 EVENT_FULL`, `0` lỗi `5xx`; `cloud-lab` còn `0/20` chỗ | `min=45.825`, `mean=247.106`, `p50=195.433`, `p95=740.879`, `p99=965.99`, `max=1036.924` |
| **E2** | Tiêm lỗi `X-Drop-After-Commit: 1` (`RemoteDisconnected`) trên `ai-campus` + 10 lần HTTP retry cùng `requestId` | 10/10 HTTP `201`, `Idempotency-Replayed: true`, cùng 1 `bookingId`, `remainingCapacity=119` | `min=14.472`, `mean=24.799`, `p50=25.226`, `p95=35.367`, `p99=38.77`, `max=39.621` |
| **E3** | 20 request HTTP hủy đồng thời + dùng lại khóa E2 sang `career-kit` | 20/20 HTTP `200`, `ai-campus` về `120/120`; xung đột khóa trả `409 IDEMPOTENCY_CONFLICT` (`25.843ms`) | Hủy đồng thời: `p50=117.275`, `p95=198.33`, `p99=198.84`, `max=198.967` |

- **Audit trước và sau tải:** `auditBefore.ok == true`, `auditAfter.ok == true`, `duplicates == []`, `foreignKeys == []`, toàn bộ sự kiện thỏa mãn `0 <= remaining <= capacity`.

---

## 4. Quyết định Thiết kế cần Bảo vệ (Design Decisions to Defend)

1. **Compute & Persistence Model (EC2 + Encrypted EBS SQLite WAL vs. ECS Fargate + ALB + RDS PostgreSQL):**
   - **Lựa chọn hiện tại:** Triển khai `1` EC2 (`t3.micro`) + SQLite chế độ `WAL` trên ổ EBS `gp3` mã hóa, đứng sau Cloudflare Quick Tunnel (HTTPS). Lý do: tối ưu chi phí cho đồ án (tận dụng AWS Free Tier, không tốn phí NAT Gateway / ALB ~\$16–20/tháng) mà vẫn đảm bảo độ trễ giao dịch thấp (< 5ms nội bộ) và cô lập mạng không cần mở cổng `0.0.0.0/0` trên AWS.
   - **Phương án thay thế đã tích hợp sẵn:** CloudFormation (`ProvisionRds=true`, `ProvisionCognito=true`) và `backend/postgres.py` cho phép chuyển sang **Amazon RDS PostgreSQL 16** (khóa dòng `SELECT ... FOR UPDATE`) hoặc chạy sau **ALB + ECS/Auto Scaling** khi lưu lượng vượt khả năng 1 node.
2. **Tác động khi mở rộng ngang (Horizontal Scaling) lên Session, Cache & DB Connections:**
   - **Sessions:** Phiên đăng nhập (`account_sessions`) và Rate-limit (`account_rate_limits`) được lưu trực tiếp trong CSDL (không lưu trong RAM của tiến trình Python), nên vẫn đồng bộ nếu mở rộng nhiều worker/instance khi dùng chung PostgreSQL.
   - **Cache & State:** Không cache số chỗ còn lại ở tầng bộ nhớ ứng dụng; mọi truy vấn và cập nhật sức chứa đều đọc/ghi trực tiếp tại **Nguồn chân lý duy nhất (Authoritative Source of State)** là CSDL (SQLite/PostgreSQL với trigger + unique index).
   - **DB Connections:** `backend/postgres.py` giới hạn ngân sách kết nối (`PORTAL_DB_MAX_CONNECTIONS=12`) để tránh cạn kết nối trên `db.t3.micro` khi mở rộng; khi scale nhiều instance cần thêm PgBouncer/RDS Proxy hoặc nâng tier RDS.
3. **An toàn thử lại (Retry Safety) & Khả dụng khi xảy ra lỗi (`Drop-After-Commit`):**
   - Mỗi yêu cầu đột biến gửi kèm `Idempotency-Key` khớp `requestId` trong body; kết quả HTTP và `fingerprint` (SHA-256 của target + payload) được commit **trong cùng một giao dịch** với thay đổi sức chứa.
   - Khi mạng bị ngắt sau lúc commit (`X-Drop-After-Commit: 1`), bản ghi đã lưu an toàn trong CSDL; lần thử lại với cùng `requestId` phát hiện bản ghi có sẵn và trả về đúng `bookingId` cũ (`Idempotency-Replayed: true`), còn toàn bộ các route đọc (`/events`, `/readyz`, `/api/me/registrations`) và các sinh viên khác vẫn hoạt động bình thường không bị gián đoạn.

---

## 5. Ước tính Chi phí Hàng tháng theo Tải (Monthly Cost Estimate)

- **Vùng triển khai:** `ap-southeast-2` (Sydney).
- **Giả định tải lớp học / demo:** Chạy 24/7 (`730 giờ/tháng`), ~100 sinh viên + 6 sự kiện, ~10.000 HTTP requests/tháng, truyền tải dữ liệu ra ngoài (egress) < 2 GB/tháng, 1 EBS Snapshot sao lưu (~2 GB thay đổi).

| Dịch vụ AWS / Cloud | Cấu hình & Bậc dịch vụ (Tier) | Định mức sử dụng / tháng | Chi phí trong Free Tier (12 tháng đầu) | Chi phí sau Free Tier (Ước tính/tháng) |
| :--- | :--- | :--- | :---: | :---: |
| **Amazon EC2** | `t3.micro` (2 vCPU, 1 GB RAM), Ubuntu 24.04 | 730 giờ (chạy 24/7) | **\$0.00** *(750h/tháng Free Tier)* | ~\$9.64 |
| **Amazon EBS** | `gp3` mã hóa (`10 GB` root + `8 GB` data = `18 GB`) + `1` Snapshot | 18 GB/tháng + ~2 GB snapshot | **\$0.00** *(30 GB EBS + 1 GB snapshot Free Tier)* | ~\$1.73 |
| **Amazon S3** | Standard, Private + AES-256 (chứa release ZIP & CSV export) | < 10 MB lưu trữ, < 1.000 PUT/GET | **\$0.00** *(5 GB Free Tier)* | < \$0.05 |
| **CloudWatch & SSM** | 1 Dashboard, 2 Standard Alarms, 1 Standard SSM Parameter | Trong hạn mức cơ bản | **\$0.00** *(10 alarms & 3 dashboards Free Tier)* | \$0.00 – \$0.20 |
| **Data Transfer (Egress)** | Lưu lượng ra Internet qua Tunnel | < 2 GB/tháng | **\$0.00** *(100 GB/tháng Free Tier)* | ~\$0.11 |
| **Cloudflare Quick Tunnel** | `cloudflared` Edge HTTPS SSL/TLS | Không giới hạn demo | **\$0.00** | **\$0.00** |
| **Tổng cộng (Cấu hình đang chạy)** | **EC2 + EBS + S3 + CloudWatch + Cloudflare** | **730 giờ/tháng** | **~\$0.00 / tháng** | **~\$11.53 – \$12.00 / tháng** |
| *(Tùy chọn mở rộng)* **RDS PostgreSQL** | `db.t3.micro` Single-AZ, `20 GB gp3`, backup 7 ngày | Bật khi cần nhiều instance | \$0.00 *(nếu đủ 750h RDS Free Tier)* | ~\$16.50 / tháng |

> ⚠️ **Lưu ý chi phí & Dọn dẹp:** Budget alert chỉ là cảnh báo, không tự ngắt dịch vụ. Sau khi hoàn tất demo/chấm bài, chạy các lệnh xóa stack CloudFormation, SSM Parameter và S3 Bucket trong [README.md](README.md) rồi kiểm tra lại EC2/EBS/S3 trên AWS Console để xác nhận không còn tài nguyên tính phí.
