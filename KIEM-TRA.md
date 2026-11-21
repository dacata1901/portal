# Kiểm tra phần A sau chỉnh nút và màu theo Meetup

## Cập nhật mới nhất: Fraunces và menu sắp xếp

1. npm.cmd test: 12/12 đạt, 0 lỗi. npm.cmd run check: đạt. Mã từ showDialog đến cuối app.js, các hàm request ID, data.js/api.js/utils.js/package/tests, ID HTML có sẵn và tập data-action được đối chiếu không đổi. Thêm helper và listener riêng cho menu, cùng các ID bổ sung của combobox/listbox; event-sort gốc giữ nguyên.
2. Chuột: chọn Số chỗ còn lại: nhiều nhất đưa Sân khấu mở lên đầu; chọn Ngày diễn ra: sớm nhất đưa Cloud Lab lên đầu. Giá trị select gốc và nhãn menu đồng bộ, menu đóng sau chọn.
3. Bàn phím: ArrowDown mở; Home/End di chuyển; Enter xác nhận; Escape đóng và giữ giá trị cũ; Tab xác nhận và chuyển focus ra ngoài. Bấm dòng hướng dẫn bên ngoài đóng menu. Lựa chọn seats giữ nguyên sau khi mở chi tiết rồi quay lại danh sách.
4. Fraunces tải thành công từ tài nguyên cục bộ, document.fonts.check với tiếng Việt trả true, trạng thái loaded. Đã xem dấu tiếng Việt trên tiêu đề, tên sự kiện và organizer. Nội dung/nút/bảng dùng font hệ thống, nền kem #dcd3ce và chữ #272a39.
5. Đo catalog và organizer ở 320, 360, 390, 768, 1024, 1440px: không tràn ngang. Dòng hướng dẫn hiện ở tất cả kích thước. Ô sắp xếp ở 320px hiển thị đầy đủ cả lựa chọn seats.
6. Đã xem menu mở ở laptop/điện thoại, catalog ở 320/390/1440, organizer ở 390/1440. Đăng nhập ban tổ chức, chuyển AI & Bạn, tìm 20001 ra 1/86; đã đăng xuất về khách. Không tạo hoặc hủy booking trong vòng này; logic tương ứng được kiểm tra tự động và đối chiếu không đổi.
7. Console không có cảnh báo/lỗi. Chạy cục bộ bằng npm.cmd start trên 127.0.0.1:4173, không xuất bản. Website đang mở ở khách, sắp xếp theo ngày, bộ lọc còn chỗ tắt.
8. Ảnh campus-sort-desktop.jpg/campus-sort-mobile.jpg minh họa popup mở; campus-fraunces-preview.jpg minh họa font mới. Đã cập nhật hai ảnh catalog, hai ảnh organizer, README/ASSETS và ZIP. Số đo có trong sort-font-check.json. Ảnh/canvas Kombai thuộc vòng thiết kế trước.


## Cập nhật mới nhất: màu chữ xanh than

- Lấy mẫu vùng chữ nhật trong ảnh: RGB 39, 42, 57, tương ứng #272a39. Nền ảnh và nền website đều RGB 220, 211, 206 (#dcd3ce).
- Trình duyệt xác nhận tiêu đề đầu trang, mô tả đầu trang, tiêu đề thẻ và mô tả sự kiện đều có màu tính toán RGB 39, 42, 57.
- Đã xem laptop 1440px và điện thoại 390px, không tràn ngang. Bộ lọc bật vẫn ra 5 sự kiện; chữ trên nút tối là RGB 255, 249, 242. Đã tắt bộ lọc về 6 sự kiện.
- npm.cmd test: 12/12 đạt, 0 lỗi. npm.cmd run check: đạt. Console không có cảnh báo/lỗi.
- Chỉ thay CSS và tài liệu; không đổi bố cục/kích thước, HTML, JavaScript, ID, data-action hoặc luồng đăng ký/hủy.
- Cập nhật campus-ink-preview.jpg, campus-desktop.jpg, campus-mobile.jpg và ZIP. Các ảnh organizer/Kombai khác là hồ sơ của những vòng thiết kế trước.


## Cập nhật mới nhất: bộ lọc còn chỗ

Chỉ sửa CSS của nhãn và checkbox, đồng bộ dạng bo tròn với bảng màu kem và nút đen. HTML/JavaScript/ID/data-action và luồng đăng ký/hủy giữ nguyên.

- npm.cmd test: 12/12 đạt, 0 lỗi; npm.cmd run check: đạt.
- Trình duyệt: bật bộ lọc ra 5 sự kiện; phím Space tắt bộ lọc và khôi phục 6. Vòng focus bàn phím hiển thị trên toàn nhãn.
- Kiểm tra 320/390/768/1440px: không tràn ngang; điều khiển rộng khoảng 217px trên điện thoại và 232px trên máy tính.
- Đã xem cả hai trạng thái trên laptop và trạng thái bật ở điện thoại 320px; console không có cảnh báo/lỗi. Đã trả trang về trạng thái khách, bộ lọc tắt.
- Ảnh mới: campus-availability-off.jpg, campus-availability-on.jpg, campus-availability-mobile.jpg. Đã cập nhật campus-desktop.jpg, campus-mobile.jpg, campus-cream-preview.jpg và ZIP.


## Kết quả mới nhất: nền kem và chữ lớn

- Đổi nền chính sang #dcd3ce theo mẫu màu người dùng; tăng chữ ở cả hai vai trò. Chỉ sửa styles.css và tài liệu.
- npm.cmd test: 12/12 đạt, 0 lỗi; npm.cmd run check: đạt.
- Đối chiếu hợp đồng gốc: dữ liệu, API, utils, bộ test, package, hàm xử lý thao tác, request ID, ID HTML và tập data-action giữ nguyên.
- Đo catalog và organizer ở 320, 360, 390, 768, 1024, 1440px: không tràn ngang. Đã xem hình ở laptop 1440px, điện thoại 390px và catalog 320px; chỉnh header 320px để vẫn một hàng.
- Đăng nhập ban tổ chức, chuyển AI & Bạn, lọc MSSV 20001: 1/86; bảng và bộ chọn sự kiện hiển thị đúng với chữ lớn. Đã đăng xuất về khách; không tạo hay hủy đăng ký trong vòng CSS này.
- Đã xem thẻ sự kiện trên điện thoại: tiêu đề 24px, mô tả 16px, danh mục 14px. Tiêu đề đầu trang 31px ở 390px, 52px ở 1440px; nền tính toán RGB 220, 211, 206.
- Console không có cảnh báo hoặc lỗi JavaScript. Tiếp tục chạy localhost bằng npm.cmd start, không xuất bản.
- Đã lưu ảnh website mới và đóng gói lại ZIP. responsive-cream.json là số đo của vòng này. Canvas/ảnh Kombai ở phần dưới là bản Meetup trước khi đổi màu kem, không được coi là ảnh của vòng này.

## Hồ sơ vòng Meetup trước

Ngày 09/11/2026. Windows, Node.js 26, Chromium. Chạy cục bộ bằng npm.cmd start tại http://127.0.0.1:4173. Không xuất bản.

## Kiểm tra tự động trên mã cuối

- npm.cmd test: 12/12 đạt, 0 lỗi.
- npm.cmd run check: đạt.
- Đối chiếu SHA-256: data.js, api.js, utils.js, package.json và tests/mock-api.test.cjs không đổi so với baseline.
- Toàn bộ mã từ showDialog đến cuối app.js giữ nguyên; các hàm requestId/persistPending/clearPending không đổi. Tập data-action và toàn bộ ID HTML có sẵn giữ nguyên. Bổ sung category-tabs và data-category-scroll để cuộn thanh chủ đề.
- Giữ 6 sự kiện, 100 sinh viên giả, adapter API và các route. Cloud Lab vẫn có 20 chỗ.

## Đã thử trong trình duyệt ở vòng Meetup trước

1. Khách thấy 6 sự kiện; ảnh JPEG cục bộ tải đủ. Nút Tham gia Campus mở đúng hộp đăng nhập mẫu.
2. Thanh chủ đề có 10 mục: Tất cả, Công nghệ, Kỹ năng, Văn hóa, Cộng đồng, Workshop, Talkshow, Hackathon, Giao lưu, Hoạt động. Biểu tượng SVG màu, nhãn tiếng Việt và gạch dưới trạng thái đang chọn.
3. Công nghệ ra 3, Workshop ra 2; Talkshow/Hackathon/Giao lưu/Hoạt động mỗi mục ra 1; Tất cả khôi phục 6. Lọc thêm theo format của dữ liệu hiện có, không thêm sự kiện giả mới.
4. Ở 390px, nút Xem thêm chủ đề cuộn sang phải và nút Xem chủ đề trước xuất hiện. Chọn Workshop khi thanh đã cuộn trả đúng 2 sự kiện và đánh dấu mục đang chọn.
5. Đăng nhập Nguyễn Minh Anh, mở Cloud Lab, xác nhận đăng ký thành công, nhận CP-828D5A7E8F; mở Đăng ký của tôi, xác nhận hủy thành công. Sau hủy, dashboard Cloud Lab có 0 đăng ký và 20/20 chỗ.
6. Đổi sang ban tổ chức, chuyển sang AI & Bạn, tìm MSSV 20001 ra 1/86; tải CSV vẫn chứa toàn bộ 86 sinh viên đang hoạt động, cùng hàng tiêu đề và BOM UTF-8.
7. Catalog và organizer được đo ở 320, 360, 390, 768, 1024, 1440px: không tràn ngang toàn trang. Catalog một cột trên điện thoại, hai cột ở 768, ba cột ở 1024/1440. Danh mục cuộn riêng khi không đủ chỗ; bảng sinh viên chuyển thành thẻ trên điện thoại.
8. Đã xem trực tiếp bố cục catalog ở 320/390/1024/1440 và organizer ở 390/1440. Tinh chỉnh cỡ chữ tiêu đề ở 320px để giữ ba dòng rõ ràng. Nút chính đen bo tròn, các màu hồng/tím/cam nhất quán giữa hai vai trò.
9. Console của tab kiểm tra mới không có cảnh báo/lỗi JavaScript.
10. Đã đặt lại dữ liệu kiểm tra: trở về khách, Cloud Lab còn 20/20 chỗ.

Những kiểm tra rộng hơn của vòng trước (retry mất phản hồi, quyền mẫu, trạng thái lỗi/trống/đang tải, tìm kiếm/sắp xếp, sự kiện hết chỗ) đã đạt. Mã xử lý tương ứng được đối chiếu không đổi trong lần chỉnh này; không tuyên bố đã chạy lại tất cả thao tác đó trong trình duyệt.

## Thiết kế và ảnh

- Cập nhật cùng canvas Kombai riêng tư Campus · Cải tiến giao diện phần A: hai màn hình sinh viên và hai màn hình ban tổ chức, laptop/điện thoại. Không tạo thêm hướng mẫu hoặc chạy Taste.
- Đã render và xem đủ mọi tile: sinh viên laptop v4, sinh viên điện thoại v3, ban tổ chức laptop/điện thoại v3. Cả bốn báo screenshotState ok. Ảnh organizer trên canvas trình bày năm hàng đầu trong tổng 86 để xem bố cục; website thật hiển thị/lọc toàn bộ danh sách.
- Phần nhúng canvas trong chat từng báo agent.kombai.com từ chối kết nối. Đây là lỗi hiển thị chưa được xác nhận đã sửa; không ảnh hưởng bản lưu CLI hoặc website localhost.
- Tham khảo trang chủ Meetup và ảnh người dùng gửi; bộ SVG màu tự vẽ, không dùng logo/ảnh biểu tượng tải từ Meetup.
- Giữ sáu ảnh chụp thật Pexels đã nhập Canva. Không dùng ảnh người sinh bằng AI trong dist. Xem ASSETS.md để biết nguồn, giấy phép và media Canva. Không mua hay nâng gói.
- Chưa có transcript đầy đủ của video tham khảo; không tuyên bố đã kiểm chứng toàn bộ video.

Ảnh mới: campus-desktop.jpg, campus-mobile.jpg, campus-meetup-preview.jpg, campus-category-mobile.jpg, campus-organizer-desktop.jpg, campus-organizer-mobile.jpg. Hai ảnh organizer dùng sự kiện AI & Bạn và bộ lọc 20001, vì vậy chỉ hiển thị 1/86. Các ảnh trước có hậu tố before là baseline; các ảnh thao tác khác là bằng chứng của vòng kiểm tra trước.

## Giới hạn

Đây vẫn là HTML/CSS/JS thuần và dữ liệu mock trên trình duyệt. Chưa có backend/OIDC/cloud thật. LocalStorage không bảo đảm giao dịch giữa nhiều máy/tab. Xác thực và quyền thật tại API, giao dịch CSDL, 100 yêu cầu đồng thời, p95, giám sát, CI/CD, IaC và rollback cần được tích hợp và nghiệm thu ở phần B/C/D/E.
