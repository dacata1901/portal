# Phần B — Mô hình dữ liệu và tính đúng đắn

## B1. Bốn thực thể
users lưu id, student_id duy nhất, tên, email giả và vai trò.
events lưu id, tên, starts_at, capacity không âm và metadata trình bày.
registrations liên kết users với events, có active/cancelled và thời điểm tạo/hủy.
idempotency_records lưu khóa, fingerprint, mã HTTP và toàn bộ JSON kết quả đã commit.
Quan hệ: user 1–N registration; event 1–N registration; user 1–N idempotency record.
Chỉ mục unique có điều kiện (user_id,event_id) WHERE status='active' cho phép
đăng ký lại sau hủy nhưng không cho hai đăng ký hoạt động.

## B2. Giao dịch
Mỗi request dùng kết nối riêng và BEGIN IMMEDIATE trước mọi kiểm tra ghi.
SQLite tuần tự hóa các writer ở mức DB; request tiếp theo đợi tối đa 15 giây.
Trong khóa, kiểm tra người dùng, khóa yêu cầu, đăng ký đang hoạt động và sức chứa.
Tạo đăng ký rồi ghi kết quả idempotency, commit cả hai cùng lúc. Exception trước
commit rollback tất cả. Trigger kiểm tra sức chứa khi insert/update đăng ký và
khi giảm capacity, bổ sung bảo vệ nếu có thao tác SQL bỏ qua API.

Không lưu bộ đếm chỗ trống riêng. remaining = capacity − COUNT(active). Vì vậy
không có cập nhật cộng chỗ bị lặp. Hủy chỉ UPDATE WHERE status='active'; lần hủy
sau vẫn trả trạng thái cancelled. Dữ liệu đăng ký đã hủy được giữ để tra cứu.

## B3. Idempotency và retry
Phạm vi: (user_id, operation, request_id). operation gồm register, cancel và
publish. Fingerprint SHA-256 của JSON chuẩn hóa gồm target + payload cho đăng ký/
hủy, hoặc payload cho xuất bản sự kiện. Khóa phải
1–128 ký tự; requestId trong body phải khớp Idempotency-Key trong header.
Cùng khóa/nội dung: trả nguyên HTTP status và JSON đã commit. Header
Idempotency-Replayed=true phân biệt replay mà không thay đổi JSON cũ.
Cùng khóa/nội dung khác: 409 IDEMPOTENCY_CONFLICT. Request trùng đồng thời đợi
khóa ghi; sau commit sẽ thấy bản ghi kết quả. Nếu writer rollback, request kế
có thể thực hiện. Lỗi nghiệp vụ như EVENT_FULL cũng được lưu, do đó muốn thử
đăng ký mới sau khi có chỗ phải dùng khóa mới.

Mất kết nối/503: retry cùng khóa và cùng payload, có backoff và jitter. Người dùng
bấm thử lại trong giao diện để giữ request ID; không tạo khóa mới để dò kết quả.
Kết quả replay là receipt lịch sử: remainingCapacity trong receipt có thể cũ.
GET /events hoặc GET /events/:id đọc trạng thái hiện tại từ DB trong read transaction.
Không dùng localStorage làm nguồn đăng ký; localStorage chỉ giữ lựa chọn tài khoản demo.
Chưa đặt TTL cho idempotency record để giữ replay xuyên suốt bản demo.

## API
GET /api/events; GET /api/events/:id; GET /api/me/registrations;
GET /api/organizer/events/:id/roster.
POST /api/events/:id/registrations; POST /api/registrations/:id/cancel.
POST /api/organizer/events nhận title, startsAt ISO-8601 có múi giờ, capacity,
category, format, venue, description và requestId; chỉ organizer/administrator
được xuất bản. Trả 201 với event và số chỗ trống; cùng request ID/payload trả lại
receipt, dùng lại khóa với nội dung khác trả 409.
POST có body {"requestId":"demo-request-001"}, header Idempotency-Key cùng giá trị
và X-Demo-User: stu-10001. Thành công đăng ký trả 201, hủy trả 200;
409 cho hết chỗ/đăng ký trùng/xung đột khóa, 404 cho đối tượng không tồn tại hoặc
không thuộc người hủy, 401/403 cho danh tính/vai trò, 400 cho request không hợp lệ.

## B4. Kiểm chứng và phối hợp E
Bộ test kiểm tra: ban tổ chức xuất bản và replay sự kiện; 100 yêu cầu tranh 20 chỗ; trùng khóa đồng thời; khác khóa cùng
sinh viên; hủy đồng thời và đăng ký lại; rollback; migration/seed lặp; ràng buộc
SQL và quyền hủy; mất phản hồi thật qua HTTP, restart, rồi replay 10 lần.
Các bài đồng thời chính gọi tầng giao dịch qua nhiều kết nối SQLite; không phải
bài đo thông lượng HTTP hay chứng nhận cloud. Test fault đi qua server HTTP thật.

E chạy tải/lỗi trên cùng DB, lưu input request ID, thời gian, raw HTTP output và
chạy audit trước/sau. Điều kiện: active <= capacity, remaining trong [0,capacity],
không duplicate active và foreign_key_check rỗng. audit dùng cho trạng thái sau tải;
đợi workload kết thúc trước khi ghi ảnh chụp số liệu. Không tuyên bố đã phối hợp E
khi chưa có kết quả chạy của thành viên đó.

Fault drill thủ công: đặt ENABLE_FAULTS=1 khi chạy server; POST thêm
X-Drop-After-Commit: 1. Server commit rồi đóng kết nối trước response. Gửi lại cùng
khóa sẽ nhận receipt cũ (kể cả header drop vẫn còn). Không bật fault ở môi trường thật.

## B5. Kết luận phạm vi
DB là nguồn trạng thái chuẩn. Giao dịch cùng unique index và trigger bảo vệ các
bất biến; retry không làm lặp tác dụng đã commit. Đã có cấu hình AWS EC2 + EBS
mã hóa và hướng dẫn triển khai trong deploy/aws; chưa triển khai lên tài khoản AWS.
Đây là demo một máy, chưa có OIDC/HTTPS/HA, dashboard cloud hoặc benchmark E.
