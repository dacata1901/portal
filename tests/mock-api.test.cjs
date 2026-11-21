const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

function app() {
  const storage = new Map();
  const window = { crypto: { randomUUID }, localStorage: { getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, String(v)), removeItem: k => storage.delete(k) } };
  const context = vm.createContext({ window, setTimeout, clearTimeout });
  for (const file of ['data.js', 'api.js', 'utils.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, '../dist/js', file), 'utf8'), context, { filename: file });
  window.CAMPUS_CONFIG.mode = 'mock'; window.CAMPUS_CONFIG.mockDelay = 0;
  return { api: window.PortalApi, data: window.CAMPUS_DATA, utils: window.CampusUtils, storage };
}

test('bộ mẫu có 100 sinh viên, sự kiện 20 chỗ và sự kiện hết chỗ', async () => {
  const { api, data } = app();
  assert.equal(data.students.length, 100);
  const events = await api.listEvents();
  assert.equal(events.find(e => e.id === 'cloud-lab').remainingCapacity, 20);
  assert.equal(events.find(e => e.id === 'hack-day').remainingCapacity, 0);
});
test('thử lại cùng request ID lấy đúng booking, không trừ thêm chỗ', async () => {
  const { api } = app(); api.session.login('stu-10001');
  const first = await api.register('cloud-lab', 'request-1');
  for (let i = 0; i < 10; i++) {
    const again = await api.register('cloud-lab', 'request-1');
    assert.equal(again.booking.id, first.booking.id); assert.equal(again.replayed, true);
  }
  assert.equal((await api.listBookings()).length, 1);
  assert.equal((await api.getEvent('cloud-lab')).remainingCapacity, 19);
});
test('không tạo hai đăng ký hoạt động cho cùng sinh viên/sự kiện', async () => {
  const { api } = app(); api.session.login('stu-10001');
  await api.register('cloud-lab', 'r-1');
  await assert.rejects(() => api.register('cloud-lab', 'r-2'), err => err.code === 'ALREADY_REGISTERED');
  assert.equal((await api.getEvent('cloud-lab')).remainingCapacity, 19);
});
test('cùng khóa nhưng thao tác khác bị từ chối', async () => {
  const { api } = app(); api.session.login('stu-10001');
  await api.register('cloud-lab', 'r-1');
  await assert.rejects(() => api.register('ai-campus', 'r-1'), err => err.code === 'IDEMPOTENCY_CONFLICT');
});
test('hủy hai lần chỉ hoàn một chỗ, sinh viên khác đăng ký được', async () => {
  const { api } = app(); api.session.login('stu-10001');
  const { booking } = await api.register('cloud-lab', 'r-1');
  await api.cancel(booking.id, 'c-1'); await api.cancel(booking.id, 'c-2');
  assert.equal((await api.getEvent('cloud-lab')).remainingCapacity, 20);
  assert.equal((await api.listBookings())[0].status, 'cancelled');
  api.session.login('stu-10002'); await api.register('cloud-lab', 'r-2');
  assert.equal((await api.getEvent('cloud-lab')).remainingCapacity, 19);
});
test('mất phản hồi giả lập sau khi lưu: thử lại không tạo đăng ký thứ hai', async () => {
  const { api } = app(); api.session.login('stu-10001'); api.demo.setScenario('after-commit');
  await assert.rejects(() => api.register('cloud-lab', 'r-1'), err => err.code === 'NETWORK_ERROR');
  const result = await api.register('cloud-lab', 'r-1');
  assert.equal(result.replayed, true); assert.equal((await api.listBookings()).length, 1);
  assert.equal((await api.getEvent('cloud-lab')).remainingCapacity, 19);
});
test('hết chỗ thì từ chối, trạng thái vẫn nhất quán', async () => {
  const { api } = app(); api.session.login('stu-10001');
  await assert.rejects(() => api.register('hack-day', 'r-1'), err => err.code === 'EVENT_FULL');
  assert.equal((await api.listBookings()).length, 0);
});
test('quyền mẫu: sinh viên không xem roster, organizer chỉ xem sự kiện của mình', async () => {
  const { api } = app(); api.session.login('stu-10001');
  await assert.rejects(() => api.roster('cloud-lab'), err => err.status === 403);
  api.session.login('org-1'); assert.equal((await api.roster('cloud-lab')).length, 0);
  await assert.rejects(() => api.roster('career-kit'), err => err.status === 403);
  assert.equal((await api.organizerEvents()).length, 3);
});
test('ban tổ chức xuất bản sự kiện mới với sức chứa trống và thấy trong danh mục', async () => {
  const { api } = app(); api.session.login('org-1');
  const result = await api.createEvent({
    title: 'Sự kiện mới', startsAt: '2026-12-01T03:00:00.000Z', capacity: 25,
    category: 'Công nghệ', format: 'Workshop', venue: 'Phòng B.302', description: 'Thực hành'
  }, 'publish-1');
  assert.equal(result.event.remainingCapacity, 25);
  assert.ok((await api.listEvents()).some(event => event.id === result.event.id));
  assert.equal((await api.organizerEvents()).some(event => event.id === result.event.id), true);
});
test('không được hủy booking của người khác hoặc đọc lịch sử người khác', async () => {
  const { api } = app(); api.session.login('stu-10001');
  const { booking } = await api.register('cloud-lab', 'r-1'); api.session.login('stu-10002');
  assert.equal((await api.listBookings()).length, 0);
  await assert.rejects(() => api.cancel(booking.id, 'c-2'), err => err.status === 404);
});
test('phiên hết hạn được trả về 401 và xóa phiên mẫu', async () => {
  const { api } = app(); api.session.login('stu-10001'); api.demo.setScenario('expired');
  await assert.rejects(() => api.listBookings(), err => err.status === 401);
  assert.equal(api.session.getUser(), null);
});
test('CSV bảo vệ công thức, dấu ngoặc kép và có BOM tiếng Việt', () => {
  const { utils } = app();
  assert.equal(utils.csvCell('=SUM(A1:A2)'), '"\'=SUM(A1:A2)"');
  assert.equal(utils.csvCell('A "B"'), '"A ""B"""');
  const csv = utils.rosterCsv([{ studentId: '10001', name: 'Nguyễn Minh Anh', email: 'a@example.test', id: 'CP-123', createdAt: '2026-11-09' }]);
  assert.equal(csv.charCodeAt(0), 0xFEFF); assert.ok(csv.includes('Nguyễn Minh Anh')); assert.ok(csv.includes('\r\n'));
});
test('nội dung dữ liệu được escape trước khi đưa vào giao diện', () => {
  const { utils } = app();
  assert.equal(utils.escape('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
});
