# Campus — Phần A: Giao diện cổng đăng ký sự kiện

Bản cải tiến giao diện ngày 09/11/2026, tiếp tục trực tiếp trên phần A đã có. Tham khảo bố cục Meetup do người dùng chọn; đã dựng 4 màn hình laptop/điện thoại trên canvas Kombai và nhập/xuất bộ ảnh chụp thật qua Canva. HTML/CSS/JS thuần, không thêm framework, thư viện chạy ngoài hoặc tài nguyên trả phí. Chỉ chạy cục bộ; toàn bộ danh tính, sự kiện và đăng ký là giả lập.

## Bắt đầu nhanh

### Cách 1 — Xem ngay, không cài thêm

Mở thư mục `dist`, nhấp đúp `index.html`. Bản mẫu không dùng JavaScript modules nên có thể xem bằng đường dẫn file. Nếu trình duyệt hạn chế lưu dữ liệu khi mở file trực tiếp, dùng cách 2.

### Cách 2 — Khuyến nghị khi làm bài với VS Code

1. Mở toàn bộ thư mục này bằng **File → Open Folder** trong VS Code.
2. Mở **Terminal → New Terminal**.
3. Kiểm tra `node --version`. Cần Node.js 20 trở lên; nếu chưa có, cài bản LTS từ https://nodejs.org/ rồi mở lại VS Code.
4. Chạy `npm start` (PowerShell chặn `npm.ps1` thì dùng `npm.cmd start`). Không cần `npm install`.
5. Mở **http://127.0.0.1:4173**. Giữ terminal đang chạy; nhấn Ctrl+C để dừng.

Trên Windows cũng có thể nhấp đúp `BAT-DAU.bat` khi đã có Node.js. Server chỉ lắng nghe trên máy của bạn, không tự xuất bản website.

## Những phần đã có

- Danh sách sự kiện, tìm kiếm, lọc chủ đề/còn chỗ và sắp xếp.
- Chi tiết sự kiện, lịch trình, thời gian, địa điểm, số chỗ còn lại.
- Đăng nhập bằng tài khoản mẫu, xác nhận đăng ký và mã đặt chỗ.
- Lịch sử, hủy đăng ký và xác nhận sau hủy.
- Trang ban tổ chức: chọn sự kiện thuộc quyền, bảng sức chứa, tìm sinh viên, tải CSV tiếng Việt.
- Trạng thái đang tải, trống, lỗi mạng, hết chỗ, đã đăng ký, sai quyền và hết phiên.
- Tình huống mất phản hồi sau khi lưu: bấm **Thử lại**, giao diện dùng lại request ID của thao tác đang chờ.

## Bấm thử theo thứ tự

1. Ở **Khám phá**, mở sự kiện **Cloud Computing: Từ ý tưởng đến ứng dụng** (ban đầu 20/20 chỗ).
2. Bấm **Đăng nhập để đăng ký**, chọn **Nguyễn Minh Anh**. Mọi danh tính trong bản mẫu đều giả lập.
3. Xác nhận đăng ký → nhận mã `CP-...` → xem **Đăng ký của tôi**. Số chỗ còn lại là 19.
4. Hủy đăng ký → lịch sử chuyển sang **Đã hủy** → số chỗ trở về 20.
5. Nhấn tài khoản ở góc phải → **Đổi tài khoản mẫu** → **Ban tổ chức · CLB Công nghệ**.
6. Mở **Ban tổ chức**, chọn sự kiện, thử tìm sinh viên và tải CSV. CSV xuất toàn bộ đăng ký hoạt động của sự kiện được chọn, không chỉ các hàng đang lọc.
7. Bấm **Tùy chọn trải nghiệm** trên thanh đầu trang để thử lỗi tải, danh sách trống, đang tải, phiên hết hạn hoặc mất phản hồi sau đăng ký.

Để kiểm tra mất phản hồi: dùng tài khoản sinh viên, bật tình huống đó, đăng ký một sự kiện chưa đăng ký; lần đầu hiện lỗi và nút **Thử lại**, lần sau trả về booking đã lưu. Sau đó xem lịch sử: chỉ có một đăng ký cho thao tác này.

**Đặt lại dữ liệu bản mẫu** chỉ xóa dữ liệu có tiền tố `campus-demo-` của ứng dụng này. Các đăng ký giả lập được lưu trong localStorage theo trình duyệt/origin; đường dẫn file và localhost có dữ liệu riêng.

## Cấu trúc dễ sửa

```
dist/index.html     Khung trang
dist/styles.css     Toàn bộ màu, chữ, bố cục và responsive
dist/js/data.js     Dữ liệu mẫu + cấu hình kết nối
dist/js/api.js      Lớp dữ liệu: mock / HTTP
dist/js/utils.js    Escape HTML, xuất CSV
dist/js/app.js      Màn hình, điều hướng, tương tác
dist/assets/events  6 ảnh chụp thật dùng cục bộ
ASSETS.md           Nguồn, tác giả, giấy phép và mã Canva
server.mjs         Server tĩnh chỉ trên máy cục bộ
tests/             Kiểm tra logic mẫu và CSV
```

## Thiết kế đã áp dụng

- Mẫu tham khảo chính: https://www.meetup.com/find/ (chỉ tham khảo cách bố cục, không sao chép thương hiệu, mã hoặc ảnh Meetup).
- Kombai: canvas riêng tư **Campus · Cải tiến giao diện phần A**. Bốn màn hình: **Sinh viên · Khám phá · Laptop**, **Sinh viên · Khám phá · Điện thoại**, **Ban tổ chức · Laptop**, **Ban tổ chức · Điện thoại**. Chỉnh bố cục trước, sau đó vùng ảnh; đã render và xem ảnh kiểm tra.
- Chỉnh tiếp theo ảnh Meetup người dùng cung cấp: nút đen bo tròn hoàn toàn, chuyển sắc và bóng trong nhẹ; chữ than, nền kem theo ảnh người dùng, điểm nhấn hồng/tím/cam. Đầu trang dùng ảnh thật trên các mảng màu mềm. Thanh chủ đề có SVG màu, nhãn tiếng Việt, gạch dưới mục đang chọn và nút cuộn tròn khi thiếu chiều rộng.
- Ban tổ chức có tóm tắt sự kiện và sức chứa; trên điện thoại, mỗi sinh viên được trình bày thành một hàng thẻ, không phải vuốt ngang để đọc mã/trạng thái.
- Sáu ảnh chụp thật Pexels miễn phí đã được nhập vào Canva và xuất/đối chiếu. Dùng bản JPEG 1.600px tối ưu cục bộ; không cần gọi CDN khi mở website. Khung hình do CSS xử lý; không sinh lại người/khuôn mặt bằng AI.
- Ảnh chỉ minh họa chủ đề, không phải ảnh của sự kiện hoặc người tham gia trong dữ liệu mẫu. Xem **ASSETS.md** để biết tác giả, nguồn, giấy phép và mã media Canva.
- Giữ nguyên các ID HTML có sẵn, tập data-action, route, adapter API, mã request ID và mọi hàm xử lý đăng nhập/đăng ký/hủy. Thêm ID category-tabs và thuộc tính data-category-scroll cho thanh cuộn mới. data.js, api.js, utils.js, package.json và 12 kiểm tra logic không thay đổi.

### Lần chỉnh nút và màu theo Meetup, 09/11/2026

Thanh chủ đề gồm 10 mục lấy từ chủ đề/hình thức của 6 sự kiện hiện có; không thêm dữ liệu sự kiện. Bộ lọc dùng category hoặc format tương ứng. Tham khảo trực tiếp https://www.meetup.com/ và ba ảnh do người dùng gửi. Bộ SVG được vẽ riêng, không tải hoặc sao chép tài nguyên biểu tượng/nhãn hiệu của Meetup. Tất cả nội dung giao diện vẫn bằng tiếng Việt.

Bốn màn hình trên canvas Kombai cũ được đồng bộ, không tạo canvas hay hướng mẫu mới. Phần nhúng canvas trong chat từng báo agent.kombai.com từ chối kết nối; bản lưu và ảnh render qua CLI được kiểm tra riêng, không coi lỗi nhúng là đã sửa. Canva tiếp tục là nguồn quản lý sáu media ảnh thật đã nhập; lần chỉnh nút/màu này không sinh thêm ảnh và không mua/nâng gói.

## Cập nhật nền kem và chữ lớn, 09/11/2026

Nền chính dùng đúng màu lấy từ ảnh người dùng: #dcd3ce (RGB 220, 211, 206). Các ô nhập và bảng dùng màu kem sáng hơn để phân biệt. Tăng tiêu đề chính lên 52px ở laptop; tiêu đề thẻ sự kiện 24px, mô tả 16px, nhãn danh mục 14–15px. Cỡ chữ được điều chỉnh theo màn hình; đầu trang vẫn gọn một hàng ở 320px. Đồng bộ giao diện sinh viên, chi tiết, xác nhận, hộp thoại và ban tổ chức.

Lần này chỉ sửa CSS và tài liệu; không đổi HTML, JavaScript, ID, data-action hoặc luồng đăng ký/hủy. Ảnh bản mới: campus-cream-preview.jpg, campus-desktop.jpg, campus-mobile.jpg và hai ảnh campus-organizer-*.jpg. Bốn ảnh Kombai đã lưu thuộc vòng Meetup trước khi đổi nền kem.

## Chỉnh tiếp từng vùng

Ưu tiên sửa dist/styles.css và các mẫu HTML trong dist/js/app.js. Không đổi ID, data-action, route hoặc các hàm API. Các ảnh nằm ở dist/assets/events/, gắn theo ID của 6 sự kiện hiện tại; sự kiện khác vẫn có phần minh họa dự phòng.

Sau khi chỉnh, chạy npm.cmd test, npm.cmd run check rồi thử đăng ký/hủy và nút tải CSV. Không đưa API key vào frontend. Canva/Kombai chỉ phục vụ thiết kế; không phải backend hay nơi xuất bản website.

## Nối với phần B/C

Hiện `CAMPUS_CONFIG.mode` là `mock`. Chưa tích hợp API hay OIDC thật. Người làm B/C cần thống nhất DTO, lỗi và phương thức xác thực trước khi chuyển `mode` sang `http` trong `dist/js/data.js`.

- `apiBaseUrl`: gốc API, ví dụ đường dẫn cùng origin `/api`.
- `getAccessToken`: hàm lấy access token từ SDK OIDC do nhóm chọn. Không dùng tên người hoặc bộ chọn tài khoản mẫu để xác thực thật.
- `currentUser`: thông tin người dùng đã được xác minh từ phiên thật.
- `signIn`: hàm bắt đầu luồng đăng nhập OIDC.

Lớp HTTP có timeout và truyền Bearer token. Các thao tác thay đổi dữ liệu truyền cùng request ID trong `Idempotency-Key`, `X-Request-Id` và body. Giữ cùng ID khi kết quả chưa xác định do lỗi mạng; đây là hợp đồng đề xuất để nhóm thống nhất, không phải API đã có sẵn.

| Hàm | Endpoint đề xuất | Dữ liệu trả về |
| --- | --- | --- |
| `listEvents` | `GET /events` | Mảng Event |
| `getEvent` | `GET /events/:id` | Event |
| `listBookings` | `GET /me/registrations` | Mảng Registration của người đang đăng nhập |
| `register` | `POST /events/:id/registrations` | `{ booking, remainingCapacity, requestId, replayed }` |
| `cancel` | `POST /registrations/:id/cancel` | Cùng cấu trúc phản hồi đăng ký |
| `roster` | `GET /organizer/events/:id/roster` | Mảng Registration đang hoạt động, đã kiểm tra quyền |

Event cần các trường hiện dùng trong `data.js`, đặc biệt `remainingCapacity`/`registeredCount` lấy từ máy chủ thật. Registration gồm `id`, `eventId`, `userId`, `studentId`, `name`, `email`, `status` (`active`/`cancelled`), `createdAt`, `cancelledAt`. Chuẩn hóa phản hồi lỗi thành `{ message, code }` cùng HTTP status tương ứng (401/403/404/409...). Điều chỉnh adapter nếu nhóm dùng tên trường/endpoint khác.

Quyền tại API, tính đúng đắn của giao dịch, idempotency bền vững và khả năng giữ chỗ khi 100 yêu cầu đồng thời phải do backend thực thi. Kiểm tra vai trò/ẩn nút trong frontend chỉ phục vụ trải nghiệm.

## Kiểm tra và giới hạn

- `npm test`: kiểm tra các hành vi giả lập, retry, hủy lặp, quyền mẫu, escape và CSV.
- `npm run check`: kiểm tra cú pháp JavaScript.
- Bộ dữ liệu có 100 sinh viên giả và một sự kiện 20 chỗ. Đây không phải kết quả bài tải 100 yêu cầu lên cloud.
- LocalStorage không phải CSDL và không bảo đảm giao dịch/concurrency giữa nhiều tab hoặc nhiều máy. Tài khoản mẫu không phải xác thực bảo mật.
- Các trạng thái lỗi/metric ở đây là giả lập giao diện; chưa có giám sát cloud, p95 thực tế, CI/CD, IaC hoặc rollback của phần D/E.
- Phần A chỉ được nghiệm thu đầy đủ sau khi nối API/đăng nhập thật, kiểm thử với backend và triển khai cùng nhóm.

## Cập nhật bộ lọc còn chỗ, 09/11/2026

Ô Chỉ hiện sự kiện còn chỗ dùng dạng nút bo tròn, nền kem sáng khi tắt và màu đen khi bật; checkbox góc bo, chữ cùng phông với trang. Giữ input checkbox thật, ID available-only và toàn bộ mã lọc. Có vòng focus khi dùng bàn phím và giao diện checkbox hệ thống trong chế độ forced colors.

## Màu chữ theo ảnh người dùng, 09/11/2026

Màu chữ chính là #272a39 (RGB 39, 42, 57), lấy trực tiếp từ hình chữ nhật xanh than trong ảnh tham khảo. Dùng cho tiêu đề, nội dung, điều hướng và nhãn chính; chữ phụ dùng sắc xanh xám #535666. Nền kem #dcd3ce giữ nguyên. Chữ trên nút tối vẫn sáng để dễ đọc; các trạng thái còn chỗ/lỗi và nhận diện Campus giữ màu chức năng. Chỉ thay CSS, không đổi HTML hoặc JavaScript.

## Fraunces, menu sắp xếp và hướng dẫn nổi bật, 09/11/2026

- Tiêu đề và tên sự kiện dùng Fraunces 500, có đầy đủ tiếng Việt. Nội dung, nút và bảng vẫn dùng phông hệ thống để dễ đọc. Ba bộ ký tự WOFF2 được lưu tại dist/assets/fonts/ cùng OFL.txt; website không gọi Google Fonts khi mở. Máy chủ cục bộ bổ sung kiểu font/woff2.
- Ô sắp xếp dùng khung bo tròn và menu nổi: nền kem sáng, dòng đang chọn màu tím và dấu chấm. Chỉ giữ hai lựa chọn cũ. Có hỗ trợ phím mũi tên, Home/End, Enter/Space, Escape, Tab và bấm ra ngoài; menu tự mở lên trên nếu dưới không đủ chỗ.
- Giữ select#event-sort gốc làm nguồn giá trị và dự phòng trước khi nâng cấp giao diện. Menu mới phát sự kiện change vào select này, sử dụng nguyên mã sắp xếp cũ; không đổi hợp đồng data-action, API, route, request ID hay đăng ký/hủy.
- Dòng Chọn chủ đề hoặc hình thức bạn quan tâm nằm trong ô tím nhạt có biểu tượng và viền nhấn, hiện cả trên điện thoại.
- Ảnh mới: campus-fraunces-preview.jpg, campus-sort-desktop.jpg, campus-sort-mobile.jpg, campus-desktop.jpg, campus-mobile.jpg, hai ảnh organizer. Bản Kombai đã lưu trước đó chưa phản ánh lần thử font và menu mới này.
