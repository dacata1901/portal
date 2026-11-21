# Nguồn ảnh thật và quá trình sử dụng

Ngày chọn ảnh: 09/11/2026. Ảnh dùng để minh họa chủ đề trong frontend giả lập; không khẳng định người trong ảnh tham gia hoặc bảo trợ cho Campus.

Tất cả ảnh dưới đây là ảnh chụp từ Pexels, không phải ảnh sinh người bằng AI. Giấy phép: https://www.pexels.com/license/ (đã kiểm tra khi chọn: cho phép dùng miễn phí trên website và chỉnh ảnh). Không mua/nâng gói. Nguồn và tác giả được ghi để tiện thay thế, dù Pexels không bắt buộc ghi công.

Các ảnh đã được nhập vào tài khoản Canva qua connector, mở và tải xuống qua trình duyệt. Khi Canva chỉ trả ảnh xem trước nhỏ, dùng bản 1.600px từ chính URL nguồn gốc đã nhập để bảo đảm độ nét. Tối ưu JPEG, bỏ metadata, giữ màu tự nhiên; cắt hiển thị bằng object-fit/object-position trong CSS. Không ghép người, đổi khuôn mặt, làm đẹp da hoặc tái tạo bằng AI.

| Tệp trong dist/assets/events | Tác giả | Trang nguồn | Media Canva |
|---|---|---|---|
| cloud-lab.jpg | Thirdman | [Pexels](https://www.pexels.com/photo/a-group-of-people-sitting-on-the-chair-while-communicating-on-laptop-5256691/) | [MAHaa1hCBJg](https://www.canva.com/M/MAHaa1hCBJg) |
| ai-campus.jpg | This And No Internet 25 | [Pexels](https://www.pexels.com/photo/professional-conference-with-audience-listening-to-speaker-35335992/) | [MAHaa1ecEnY](https://www.canva.com/M/MAHaa1ecEnY) |
| career-kit.jpg | Arina Krasnikova | [Pexels](https://www.pexels.com/photo/a-woman-writing-on-the-paper-in-front-of-the-laptop-on-the-glass-table-7005389/) | [MAHaa7_jR4Y](https://www.canva.com/M/MAHaa7_jR4Y) |
| hack-day.jpg | George Pak | [Pexels](https://www.pexels.com/photo/three-young-people-studying-together-outdoors-with-laptops-7972948/) | [MAHaa4TDf-A](https://www.canva.com/M/MAHaa4TDf-A) |
| open-mic.jpg | Justinas Stanislovaitis | [Pexels](https://www.pexels.com/photo/man-playing-an-electric-guitar-while-singing-on-stage-9298954/) | [MAHaa2iSxoc](https://www.canva.com/M/MAHaa2iSxoc) |
| green-campus.jpg | Anna Shvets | [Pexels](https://www.pexels.com/photo/people-planting-plant-together-5029923/) | [MAHaa1UQVWg](https://www.canva.com/M/MAHaa1UQVWg) |

## Những bản thử không dùng trong website

Bản ảnh AI thử đầu tiên MAHaavPRw_4 và bộ poster Canva DAHaaloGAkc được tạo trước yêu cầu ưu tiên ảnh chụp thật. Hai bản này không được dùng trong dist. Bộ poster vẫn có thể xem tại https://canva.link/2gn97fs4bbyvtnn nhưng không phải nguồn của 6 ảnh đang hiển thị.

## Tham khảo thiết kế

Người dùng chọn Meetup (https://www.meetup.com/find/) trong 4 website tham khảo. Áp dụng cách phân cấp tiêu đề/ảnh/thời gian, bộ lọc chủ đề và khoảng cách; giữ nhận diện Campus riêng.

Kombai canvas riêng tư cnv_79ba993abb5f, 4 màn hình của cùng một hướng thiết kế. Không chạy Taste hoặc tạo thêm hướng mẫu vì đây là chỉnh theo mẫu đã chọn. Bản website dùng ảnh cục bộ; canvas dùng URL ảnh Pexels công khai để render tham khảo.

Video tham khảo do người dùng cung cấp: https://youtu.be/gRYqlDwkWTM . Áp dụng quy trình tham khảo mẫu → chỉnh từng vùng → đưa thiết kế vào mã. Chưa lấy được transcript đầy đủ, không xác nhận đã áp dụng toàn bộ nội dung video.

## Cập nhật nút và biểu tượng theo ảnh Meetup

Tham khảo thêm trang chủ https://www.meetup.com/ ngày 09/11/2026 và ba ảnh người dùng gửi. Áp dụng nút đen bo tròn có bóng trong nhẹ, thanh chủ đề ngang có biểu tượng màu và gạch dưới. Các SVG trong categoryArtwork của app.js được vẽ riêng; không sao chép file biểu tượng, logo hoặc CSS tải từ Meetup. Ảnh ghép trang đầu tái sử dụng bốn JPEG thật của sáu sự kiện đã có. Không phát sinh ảnh AI hay tài nguyên trả phí trong lần chỉnh này.

## Phông Fraunces

Nguồn chính thức: [Fraunces trên Google Fonts](https://fonts.google.com/specimen/Fraunces), [CSS bộ ký tự](https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400..700&display=swap), [giấy phép OFL trong kho Google Fonts](https://github.com/google/fonts/blob/main/ofl/fraunces/OFL.txt).

Copyright 2018 The Fraunces Project Authors. SIL Open Font License 1.1, bản giấy phép đi kèm dist/assets/fonts/OFL.txt. Dùng ba WOFF2 chính thức của phiên bản v38 cho vietnamese, latin-ext và latin; tổng 146.392 byte, trọng lượng 400–700, trục optical size 9–144. CSS tham chiếu tệp cục bộ, không dùng CDN khi xem trang. Không mua hoặc nâng gói. Dùng Fraunces cho các tiêu đề; font hệ thống cho nội dung và điều khiển.
