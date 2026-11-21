# Campus Portal — hướng dẫn sử dụng

Website đăng ký sự kiện đại học: sinh viên xem sự kiện, đăng ký/hủy chỗ và nhận
biên nhận; ban tổ chức xuất bản sự kiện, theo dõi sức chứa, xem roster và tải CSV.
Dữ liệu mẫu là dữ liệu tổng hợp.

## 1. Chạy trên máy Windows

Yêu cầu Python 3.10 trở lên. Không cần cài thư viện Python ngoài.

1. Mở PowerShell tại thư mục dự án.
2. Chạy một trong các lệnh:

   ```powershell
   .\BAT-DAU.bat
   ```

   hoặc:

   ```powershell
   py -3 server.py
   ```

3. Mở <http://127.0.0.1:4173>.
4. Dừng máy chủ bằng `Ctrl+C`.

Trên Linux/macOS, chạy `python3 server.py`. Không mở trực tiếp `dist/index.html`:
giao diện cần máy chủ API. CSDL `portal.sqlite3` được tạo tự động trong lần chạy
đầu và còn nguyên sau khi khởi động lại.

## 2. Đăng nhập và thử chức năng

Chọn **Đăng nhập** rồi chọn tài khoản mẫu trong danh sách. Không cần mật khẩu.

- **Sinh viên:** `stu-10001` (Nguyễn Minh Anh) hoặc `stu-10002` (Trần Gia Huy).
- **Ban tổ chức:** `org-1` (CLB Công nghệ).
- **Quản trị viên:** `admin-1`.

### Sinh viên

1. Mở **Khám phá**, chọn sự kiện để xem chi tiết và số chỗ còn lại.
2. Chọn đăng ký, xác nhận; hệ thống trả mã booking và trang biên nhận.
3. Mở **Đăng ký của tôi** để xem lịch sử.
4. Chọn **Hủy đăng ký** để trả chỗ; đăng ký đã hủy vẫn được giữ trong lịch sử.

Trên CSDL mới, Cloud Lab có 20/20 chỗ; Hack Day đã hết chỗ. Mỗi sinh viên chỉ có
một đăng ký đang hoạt động cho mỗi sự kiện. Nếu mất phản hồi, hãy thử lại cùng
thao tác; request ID giúp tránh giữ chỗ hai lần.

### Ban tổ chức / Quản trị viên

1. Mở **Ban tổ chức**.
2. Chọn **Tạo sự kiện**, nhập tên, thời gian, sức chứa, chủ đề, hình thức và thông
   tin tùy chọn; chọn **Xuất bản**.
3. Sự kiện xuất hiện trong danh mục công khai. Chọn sự kiện trên dashboard để xem
   số đăng ký, số chỗ còn lại và roster.
4. Chọn **Tải danh sách CSV** để xuất toàn bộ đăng ký đang hoạt động.

Ban tổ chức chỉ quản lý sự kiện của mình; quản trị viên xem được mọi sự kiện.

## 3. Triển khai lên AWS (CloudFormation IaC)

Tài khoản AWS CLI cần được cấu hình trước (`aws configure`) với quyền tạo
CloudFormation, EC2/VPC, EBS, IAM role, S3, CloudWatch (và Cognito/RDS nếu bật
tùy chọn). Không chạy lệnh deploy trước khi quản trị viên xác nhận quyền và chi phí.

### Triển khai chế độ Demo (EC2 + EBS SQLite + CloudWatch)

```powershell
.\deploy\aws\deploy-aws.ps1 -Region ap-southeast-2
```

Script tự động lấy IPv4 công khai hiện tại (dạng `/32`, từ chối `0.0.0.0/0`),
đóng gói mã nguồn vào bucket S3 riêng tư mã hóa AES-256, và tạo stack gồm VPC,
2 subnet, EC2, EBS `gp3` mã hóa (`/var/lib/campus/portal.sqlite3`), CloudWatch
Alarms (`CPUUtilization`, `StatusCheckFailed`) và CloudWatch Dashboard.

### Triển khai kèm Amazon Cognito và/hoặc Amazon RDS PostgreSQL

Có thể truyền thông tin dịch vụ có sẵn hoặc yêu cầu CloudFormation tự tạo mới:

```powershell
.\deploy\aws\deploy-aws.ps1 -Region ap-southeast-2 -ProvisionCognito -ProvisionRds -DbMasterPassword "MatKhauManh>=8KyTu"
```

Xem chi tiết cấu hình trong [deploy/aws/campus-ec2.yaml](deploy/aws/campus-ec2.yaml),
[deploy/aws/deploy-aws.ps1](deploy/aws/deploy-aws.ps1) và hướng dẫn vận hành tại
[REPORT-C-D-E.md](REPORT-C-D-E.md).

### Xóa tài nguyên AWS

Stack và EBS sẽ bị xóa cùng dữ liệu khi xóa stack. Bucket S3 do script tạo nằm
ngoài stack, cần xóa riêng. Thay region, stack name và bucket bằng giá trị lúc
triển khai:

```powershell
aws cloudformation delete-stack --stack-name campus-event-portal --region ap-southeast-2
aws cloudformation wait stack-delete-complete --stack-name campus-event-portal --region ap-southeast-2
aws s3 rm s3://TEN-BUCKET-DA-IN --recursive --region ap-southeast-2
aws s3 rb s3://TEN-BUCKET-DA-IN --region ap-southeast-2
```

AWS có thể tính phí EC2, EBS, S3 và truyền dữ liệu. Kiểm tra giá và dừng/xóa tài
nguyên khi không còn dùng.

## 4. Kiểm thử và dữ liệu mẫu

Chạy tại thư mục dự án:

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m unittest discover -s tests -p "test_*.py" -v
py -3 scripts/benchmark_e.py
npm.cmd test
npm.cmd run check
```

Test kiểm tra 100 yêu cầu đồng thời tranh 20 chỗ, idempotency, hủy đồng thời,
quyền, xuất bản sự kiện, retry sau khi mất phản hồi, xác minh Cognito JWT,
backup/restore và mẫu CloudFormation. Kết quả gần nhất được ghi trong
[TEST-RESULTS.txt](TEST-RESULTS.txt), [FRONTEND-TEST-RESULTS.txt](FRONTEND-TEST-RESULTS.txt),
[BENCHMARK-E-RESULTS.json](BENCHMARK-E-RESULTS.json) và [REPORT-C-D-E.md](REPORT-C-D-E.md).

Lệnh quản trị, sao lưu và phục hồi CSDL:

```powershell
py -3 server.py migrate
py -3 server.py seed
py -3 server.py audit
py -3 server.py backup --file campus-backup.json
py -3 server.py restore --file campus-backup.json
.\deploy\aws\backup-restore.ps1 -Action local-backup -BackupFile campus-backup.json
.\deploy\aws\backup-restore.ps1 -Action ebs-snapshot -Region ap-southeast-2
```

`seed` có thể chạy lặp lại và không xóa lịch sử đăng ký. Dữ liệu tham chiếu cùng
kết quả mong đợi nằm trong [REFERENCE.md](REFERENCE.md).

## 5. Cấu hình PostgreSQL và Cognito (dịch vụ AWS cần được tạo riêng)

Backend có adapter PostgreSQL và xác minh Cognito access token. Cần tạo sẵn
PostgreSQL và Cognito User Pool/App Client có Hosted UI domain, bật Authorization
Code + PKCE, và cấu hình callback/sign-out URL đúng với URL ứng dụng. Cognito
username phải khớp ID trong dữ liệu (ví dụ `stu-10001`, `org-1`, `admin-1`) và
gán đúng group `Students`, `Organizers` hoặc `Administrators`.

Cài dependency và chạy server bằng biến môi trường (không đưa DSN/mật khẩu vào mã
nguồn hoặc git):

```powershell
py -3 -m pip install -r requirements.txt
$env:PORTAL_DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
$env:PORTAL_AUTH_MODE = "cognito"
$env:COGNITO_REGION = "ap-southeast-2"
$env:COGNITO_USER_POOL_ID = "REGION_POOL_ID"
$env:COGNITO_CLIENT_ID = "APP_CLIENT_ID"
$env:COGNITO_DOMAIN = "https://YOUR_DOMAIN.auth.ap-southeast-2.amazoncognito.com"
$env:COGNITO_REDIRECT_URI = "https://YOUR_APP_URL/"
$env:COGNITO_LOGOUT_URI = "https://YOUR_APP_URL/"
py -3 server.py
```

Server tự migrate/seed khi khởi động. Khi cấu hình Cognito, API không chấp nhận
`X-Demo-User`; request được xác thực bằng access token và đối chiếu group với
vai trò trong cơ sở dữ liệu. `PORTAL_AUTH_MODE` mặc định là `demo` chỉ để chạy
cục bộ, tuyệt đối không mở chế độ này ra Internet.

**Trạng thái:** Đã hoàn thiện mã nguồn xác thực Cognito, adapter PostgreSQL,
tính năng backup/restore kiểm tra checksum, CI/CD GitHub Actions, CloudFormation
IaC (EC2, EBS, VPC, tùy chọn Cognito & RDS PostgreSQL, CloudWatch Alarms &
Dashboard), và benchmark HTTP Phần E (`BENCHMARK-E-RESULTS.json`). Tài khoản AWS
trên máy chưa cấu hình credential (`aws configure`) nên chưa tạo tài nguyên thật
trên AWS và chưa chạy kiểm thử live với HTTPS/RDS ngoài.
