(function () {
  'use strict';
  const students = Array.from({ length: 100 }, (_, i) => ({
    id: `stu-${10001 + i}`, studentId: String(10001 + i),
    name: ['Nguyễn Minh Anh', 'Trần Gia Huy', 'Lê Thảo Nguyên'][i] || `Sinh viên mẫu ${i + 1}`,
    email: `student${10001 + i}@example.test`, role: 'student'
  }));
  const users = [...students,
    { id: 'org-1', name: 'Ban tổ chức · CLB Công nghệ', email: 'organizer@example.test', role: 'organizer' },
    { id: 'admin-1', name: 'Quản trị viên mẫu', email: 'admin@example.test', role: 'administrator' }
  ];
  const events = [
    { id: 'cloud-lab', title: 'Cloud Computing: Từ ý tưởng đến ứng dụng', category: 'Công nghệ', format: 'Workshop', startsAt: '2026-11-14T08:30:00+07:00', endsAt: '2026-11-14T11:30:00+07:00', venue: 'Phòng thực hành B.302', capacity: 20, baseRegistered: 0, organizerId: 'org-1', organizer: 'CLB Công nghệ', theme: 'cloud', artwork: ['CLOUD', 'CONNECT.'], description: 'Đưa ứng dụng đầu tiên của bạn lên đám mây. Một buổi thực hành để hiểu cách dịch vụ cloud kết nối với nhau.', about: 'Bạn sẽ đi từ một ý tưởng nhỏ đến bản ứng dụng có thể truy cập trên trình duyệt, tìm hiểu vai trò của máy chủ, cơ sở dữ liệu và quá trình triển khai. Buổi học ưu tiên thực hành từng bước, phù hợp với sinh viên đang bắt đầu môn Điện toán đám mây.', agenda: ['08:30 · Làm quen với kiến trúc ứng dụng cloud', '09:15 · Thực hành triển khai ứng dụng mẫu', '10:30 · Thử nghiệm, chia sẻ và hỏi đáp'], note: 'Mang theo laptop và sạc. Có mặt trước giờ bắt đầu 10 phút.', speaker: 'Đội ngũ CLB Công nghệ' },
    { id: 'ai-campus', title: 'AI & Bạn: Học thông minh, làm sáng tạo', category: 'Công nghệ', format: 'Talkshow', startsAt: '2026-11-15T14:00:00+07:00', endsAt: '2026-11-15T16:00:00+07:00', venue: 'Hội trường A', capacity: 120, baseRegistered: 86, organizerId: 'org-1', organizer: 'CLB Công nghệ', theme: 'ai', artwork: ['MAKE', 'IT SMART.'], description: 'Gặp gỡ những góc nhìn mới về AI, việc học và những dự án sinh viên bạn có thể bắt đầu ngay.', about: 'Cùng khám phá các ví dụ ứng dụng AI vào việc học và sáng tạo sản phẩm. Diễn giả sẽ chia sẻ cách đặt vấn đề, kiểm chứng kết quả và xây dựng thói quen học tập chủ động.', agenda: ['14:00 · AI trong trải nghiệm học tập', '14:45 · Chia sẻ các dự án sinh viên', '15:30 · Hỏi đáp cùng khách mời'], note: 'Chuẩn bị một câu hỏi hoặc một ý tưởng bạn muốn thảo luận.', speaker: 'Khách mời từ cộng đồng công nghệ' },
    { id: 'career-kit', title: 'CV không chỉ là một tờ giấy', category: 'Kỹ năng', format: 'Workshop', startsAt: '2026-11-17T09:00:00+07:00', endsAt: '2026-11-17T11:00:00+07:00', venue: 'Không gian sáng tạo C.201', capacity: 60, baseRegistered: 42, organizerId: 'org-2', organizer: 'Trung tâm Hỗ trợ sinh viên', theme: 'career', artwork: ['YOUR', 'NEXT MOVE.'], description: 'Biến trải nghiệm học tập và hoạt động của bạn thành một câu chuyện nghề nghiệp rõ ràng.', about: 'Thực hành xây dựng cấu trúc CV, chọn trải nghiệm phù hợp và chuẩn bị phần giới thiệu bản thân. Bạn có thể mang bản CV hiện tại để tự rà soát trong buổi học.', agenda: ['09:00 · Cấu trúc một CV dễ đọc', '09:45 · Thực hành và góp ý', '10:30 · Hỏi đáp về cơ hội thực tập'], note: 'Mang theo laptop hoặc bản CV bạn đang sử dụng.', speaker: 'Đội ngũ Hỗ trợ nghề nghiệp' },
    { id: 'hack-day', title: 'Build Together: Một ngày, một sản phẩm', category: 'Công nghệ', format: 'Hackathon', startsAt: '2026-11-18T08:00:00+07:00', endsAt: '2026-11-18T17:00:00+07:00', venue: 'Innovation Hub · Tầng 2', capacity: 40, baseRegistered: 40, organizerId: 'org-1', organizer: 'CLB Công nghệ', theme: 'hack', artwork: ['BUILD', 'TOGETHER.'], description: 'Lập đội, chọn một vấn đề trong trường và cùng xây dựng giải pháp trong một ngày.', about: 'Một ngày làm sản phẩm với sự hỗ trợ của các anh chị hướng dẫn. Hoạt động khuyến khích thử nghiệm, chia sẻ và học từ đồng đội.', agenda: ['08:00 · Nhận chủ đề và lập đội', '09:00 · Xây dựng sản phẩm', '15:30 · Trình diễn và chia sẻ'], note: 'Sự kiện hiện đã hết chỗ. Bạn vẫn có thể xem thông tin chương trình.', speaker: 'Cộng đồng phát triển sản phẩm' },
    { id: 'open-mic', title: 'Sân khấu mở: Câu chuyện của chúng mình', category: 'Văn hóa', format: 'Giao lưu', startsAt: '2026-11-20T18:00:00+07:00', endsAt: '2026-11-20T20:30:00+07:00', venue: 'Sân trường · Khu A', capacity: 180, baseRegistered: 110, organizerId: 'org-2', organizer: 'CLB Văn nghệ', theme: 'music', artwork: ['FIND', 'YOUR VOICE.'], description: 'Một buổi tối dành cho âm nhạc, câu chuyện và những kết nối mới trong cộng đồng sinh viên.', about: 'Gặp gỡ những người bạn có cùng đam mê nghệ thuật, lắng nghe các tiết mục và chia sẻ câu chuyện sinh viên của bạn trong một không gian gần gũi.', agenda: ['18:00 · Đón khách', '18:30 · Âm nhạc và chia sẻ', '20:00 · Giao lưu cộng đồng'], note: 'Mang theo tinh thần cởi mở và một người bạn nếu bạn muốn.', speaker: 'CLB Văn nghệ và các nhóm sinh viên' },
    { id: 'green-campus', title: 'Một buổi sáng xanh hơn', category: 'Cộng đồng', format: 'Hoạt động', startsAt: '2026-11-22T07:30:00+07:00', endsAt: '2026-11-22T10:00:00+07:00', venue: 'Cổng chính · Khuôn viên trường', capacity: 100, baseRegistered: 67, organizerId: 'org-2', organizer: 'Đội Sinh viên tình nguyện', theme: 'green', artwork: ['SMALL ACTS.', 'BIG CHANGE.'], description: 'Cùng chăm sóc không gian chung và góp một hành động nhỏ cho một khuôn viên xanh hơn.', about: 'Tham gia hoạt động cộng đồng trong khuôn viên trường, tìm hiểu cách phân loại rác và cùng tạo nên một buổi sáng ý nghĩa với bạn bè.', agenda: ['07:30 · Tập trung và chia nhóm', '08:00 · Hoạt động theo khu vực', '09:30 · Tổng kết và chia sẻ'], note: 'Mặc trang phục thuận tiện, mang theo bình nước cá nhân.', speaker: 'Đội Sinh viên tình nguyện' }
  ];
  users.push({ id: 'org-2', name: 'Ban hoạt động sinh viên', email: 'organizer2@example.test', role: 'organizer' });
  window.CAMPUS_DATA = { students, users, events };
  const runtime = window.CAMPUS_RUNTIME_CONFIG || {};
  const cognito = runtime.authMode === 'cognito';
  window.CAMPUS_CONFIG = {
    mode: 'http',
    demoIdentity: !cognito,
    apiBaseUrl: '/api',
    getAccessToken: () => window.CampusAuth.getAccessToken(),
    signIn: () => window.CampusAuth.signIn(),
    mockDelay: 240
  };
  const demoStrip = typeof document === 'undefined' ? null : document.querySelector('.demo-strip');
  if (demoStrip && cognito) {
    demoStrip.hidden = true;
    demoStrip.style.display = 'none';
  }
}());
