# Bộ tham chiếu có kết quả biết trước
Dùng DB mới; seed hai lần phải cho cùng trạng thái.

| Sự kiện | Sức chứa | Active ban đầu | Chỗ trống |
|---|---:|---:|---:|
| cloud-lab | 20 | 0 | 20 |
| ai-campus | 120 | 86 | 34 |
| career-kit | 60 | 42 | 18 |
| hack-day | 40 | 40 | 0 |
| open-mic | 180 | 110 | 70 |
| green-campus | 100 | 67 | 33 |

100 sinh viên tải: stu-10001 đến stu-10100. Các đăng ký có sẵn dùng sinh viên giả
riêng, để 100 sinh viên tải không bị trùng với người đã đăng ký ban đầu.

Chuỗi tuần tự: stu-10001 register cloud-lab khóa R1 => 201, active=1, remaining=19.
Replay R1 10 lần => cùng booking và HTTP status, active=1, remaining=19.
Cùng R1 đổi target ai-campus => 409, không thêm đăng ký.
Hủy booking khóa C1 => 200, active=0, remaining=20.
Hủy lại khóa C2 => 200, active=0, remaining=20.
Đăng ký lại khóa R2 => 201, booking mới, active=1, remaining=19.
R1 replay sau hủy vẫn là receipt cũ; GET lịch sử phản ánh trạng thái hiện tại.

Tải trên DB mới: 100 sinh viên khác nhau đăng ký cloud-lab => 20 mã 201,
80 mã 409 EVENT_FULL; active=20, remaining=0. Sinh viên thắng không cố định.
