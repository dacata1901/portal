# Phần C, D, E — Xác thực Cloud, Hạ tầng AWS IaC, Vận hành & Kiểm chứng Tải

## 1. Phần C — Xác thực Cognito & Hạ tầng AWS IaC

### 1.1 Xác thực Amazon Cognito (OAuth2 Authorization Code + PKCE)
- **Frontend (`dist/js/cognito-auth.js`, `dist/js/data.js`, `dist/js/api.js`):** Đọc cấu hình runtime từ `/runtime-config.js`. Khi `PORTAL_AUTH_MODE=cognito`, giao diện ẩn thanh chọn tài khoản demo, điều hướng đăng nhập qua Cognito Hosted UI (`code_challenge_method=S256`), lưu token trong `sessionStorage`, tự làm mới token bằng `refresh_token`, và gắn header `Authorization: Bearer <access_token>`.
- **Backend (`backend/auth.py`, `server.py`):** Xác minh chữ ký RS256 qua JWKS (`https://cognito-idp.<region>.amazonaws.com/<pool_id>/.well-known/jwks.json`), kiểm tra `token_use == "access"`, `client_id`, `iss`, `exp`, và đối chiếu `cognito:groups` (`Students`, `Organizers`, `Administrators`) với cột `role` trong CSDL. Chế độ `cognito` từ chối hoàn toàn header `X-Demo-User` (`401`).
- **Tương thích PostgreSQL (`backend/postgres.py`, `server.py`):** `server.py` tự động chuyển đổi placeholder (`%s` cho PostgreSQL, `?` cho SQLite) và đọc khóa cột `r['id']` tương thích `dict_row`.

### 1.2 Infrastructure as Code (`deploy/aws/campus-ec2.yaml`, `deploy/aws/deploy-aws.ps1`)
Mẫu CloudFormation hỗ trợ từ chế độ demo (EC2 + EBS mã hóa + SQLite) tới kiến trúc kết nối Managed Services trên AWS:
- **Mạng & Compute:** `PortalVpc` (`10.42.0.0/16`), hai subnet trên 2 Availability Zone (`PortalSubnet` `10.42.1.0/24`, `PortalSubnetB` `10.42.2.0/24`), `PortalInternetGateway`, `PortalSecurityGroup` (chỉ mở cổng `4173` cho `AllowedCidr`), `PortalInstance` (Ubuntu 24.04 LTS, IMDSv2 `HttpTokens: required`), `PortalDataVolume` (EBS `gp3` 8GB mã hóa).
- **Bootstrap & Bảo mật cấu hình:** `UserData` cài `python3-venv`, tạo `/opt/campus/.venv` từ `requirements.txt`, lưu biến môi trường (bao gồm `PORTAL_DATABASE_URL` với `NoEcho: true`) vào `/etc/campus-portal.env` (`chmod 600`), và chạy dịch vụ `campus-portal.service` qua `EnvironmentFile`.
- **Tùy chọn tự động tạo Cognito (`ProvisionCognito=true`):** Tạo `CampusUserPool`, `CampusUserPoolDomain`, `CampusUserPoolClient` (Authorization Code + PKCE, không client secret) và 3 nhóm `Students`, `Organizers`, `Administrators`.
- **Tùy chọn tự động tạo RDS PostgreSQL (`ProvisionRds=true`):** Tạo `PortalRdsSecurityGroup` (chỉ nhận TCP `5432` từ `PortalSecurityGroup`), `PortalDbSubnetGroup`, và `PortalPostgresInstance` (`db.t3.micro`, `gp3` 20GB mã hóa, `PubliclyAccessible: false`, `BackupRetentionPeriod: 7`), tự động nối chuỗi kết nối vào `PORTAL_DATABASE_URL`.

---

## 2. Phần D — Giám sát, CI/CD, Backup/Restore & Rollback

### 2.1 Giám sát CloudWatch (`deploy/aws/campus-ec2.yaml`)
- `PortalHighCpuAlarm`: Cảnh báo khi `AWS/EC2 CPUUtilization` trung bình > `80%` trong 2 chu kỳ 300s.
- `PortalStatusCheckAlarm`: Cảnh báo ngay khi `AWS/EC2 StatusCheckFailed >= 1` trong chu kỳ 60s.
- `PortalCloudWatchDashboard`: Dashboard `${AWS::StackName}-${AWS::Region}-dashboard` theo dõi `CPUUtilization`, `StatusCheckFailed`, `NetworkIn`, `NetworkOut`.

### 2.2 Sao lưu, Phục hồi & Rollback (`backend/backup.py`, `deploy/aws/backup-restore.ps1`)
- **`backend/backup.py` & `server.py backup|restore`:**
  - `create_backup`: Sao lưu nhất quán (dùng `sqlite3.Connection.backup()` cho SQLite hoặc giao dịch `REPEATABLE READ READ ONLY` cho PostgreSQL), xuất toàn bộ 4 bảng (`users`, `events`, `registrations`, `idempotency_records`), snapshot `audit()` và mã kiểm tra toàn vẹn `sha256`.
  - `restore_backup`: Xác minh `sha256` trước khi ghi, nạp nguyên tử trong một giao dịch theo đúng thứ tự khóa ngoại và trigger, sau đó chạy lại `audit()` để xác nhận bất biến dữ liệu.
- **`deploy/aws/backup-restore.ps1`:** Hỗ trợ `local-backup`, `local-restore`, `ebs-snapshot` (tạo snapshot EBS từ `DataVolumeId` của stack), và `cfn-rollback` (tự động `rollback-stack` khi `UPDATE_FAILED` hoặc dọn stack khi `CREATE_FAILED`).

### 2.3 CI/CD Pipeline (`.github/workflows/ci-cd.yml`)
Tự động chạy trên `push` (`main`/`master`) và `pull_request`:
1. Cài đặt Node.js 22 và Python 3.12 cùng dependencies.
2. Chạy `npm test` và `npm run check`.
3. Chạy `python -m unittest discover -s tests -p "test_*.py" -v`.
4. Chạy `python scripts/benchmark_e.py` và lưu artifact `BENCHMARK-E-RESULTS.json`.

---

## 3. Phần E — Kiểm chứng Tải HTTP, Tiêm lỗi & Audit

Kết quả chạy thực tế qua HTTP server (`scripts/benchmark_e.py` trên SQLite với `ENABLE_FAULTS=1`), lưu chi tiết tại [BENCHMARK-E-RESULTS.json](BENCHMARK-E-RESULTS.json):

| Workload | Kịch bản kiểm thử | Kết quả đạt được | Độ trễ (ms) |
|---|---|---|---|
| **E1** | 100 request HTTP đồng thời (`ThreadPoolExecutor(32)`) tranh 20 chỗ `cloud-lab` | `20` HTTP `201`, `80` HTTP `409 EVENT_FULL`; `cloud-lab` còn `0/20` chỗ | `min=18.001`, `p50=111.376`, `p95=609.107`, `p99=773.499`, `max=873.877` |
| **E2** | Tiêm lỗi `X-Drop-After-Commit: 1` (`RemoteDisconnected`) trên `ai-campus` + 10 lần HTTP retry cùng `requestId` | 10/10 HTTP `201`, `Idempotency-Replayed: true`, cùng 1 `bookingId`, `remainingCapacity=33` | `min=4.836`, `p50=18.632`, `p95=26.665`, `p99=27.559`, `max=27.782` |
| **E3** | 20 request HTTP hủy đồng thời + dùng lại khóa E2 sang `career-kit` | 20/20 HTTP `200`, `ai-campus` về `34`; xung đột khóa trả `409 IDEMPOTENCY_CONFLICT` (`11.96ms`) | Hủy đồng thời: `p50=85.362`, `p95=192.352`, `p99=209.694`, `max=214.029` |

- **Audit trước và sau tải:** `auditBefore.ok == true`, `auditAfter.ok == true`, `duplicates == []`, `foreignKeys == []`, toàn bộ sự kiện thỏa mãn `0 <= remaining <= capacity`.
- **Giới hạn ghi nhận:** Benchmark chạy trên máy cục bộ qua SQLite; chưa triển khai trực tiếp stack lên tài khoản AWS do máy chưa cấu hình credential (`aws configure`) và chưa chạy kiểm thử tích hợp trực tiếp trên instance RDS PostgreSQL thật.
