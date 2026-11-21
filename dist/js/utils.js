(function () {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function csvCell(value) {
    let text = String(value ?? '');
    // Chặn công thức khi CSV được mở bằng phần mềm bảng tính.
    if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }
  function rosterCsv(rows) {
    const records = [['Mã sinh viên', 'Họ tên', 'Email', 'Mã đăng ký', 'Trạng thái', 'Thời điểm đăng ký'], ...rows.map(row => [row.studentId, row.name, row.email, row.id, 'Đã đăng ký', row.createdAt])];
    return '\uFEFF' + records.map(record => record.map(csvCell).join(',')).join('\r\n');
  }
  window.CampusUtils = { escape, csvCell, rosterCsv };
}());
