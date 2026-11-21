const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

const user = { id: 'local-test-user', name: 'Nguyễn An Bình', studentId: 'SV20260001', email: 'binh@example.test', role: 'student' };
function client(handler) {
  const storage = new Map(), calls = [];
  const window = {
    CAMPUS_RUNTIME_CONFIG: { authMode: 'demo', localAccounts: true },
    CampusAuth: { enabled: false, getAccessToken: async () => null },
    crypto: { randomUUID },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key,value) => storage.set(key,String(value)), removeItem: key => storage.delete(key) }
  };
  const fetch = async (url, options) => {
    calls.push({url, ...options});
    const response = handler(url, options);
    return { ok: response.status < 400, status: response.status, headers: { get: () => 'application/json' }, json: async () => response.body };
  };
  const context = vm.createContext({ window, fetch, setTimeout, clearTimeout, AbortController });
  for (const file of ['data.js','api.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,'../dist/js',file),'utf8'), context);
  return { api: window.PortalApi, storage, calls };
}
test('khôi phục tài khoản bằng cookie và gửi CSRF, giữ request ID khi đăng ký', async () => {
  const {api,calls} = client((url) => ({status:200,body:url==='/api/auth/session'?{user,csrfToken:'csrf-test'}:{booking:{id:'CP-test'}}}));
  await api.session.restore();
  assert.equal(api.session.getUser().id, user.id);
  await api.register('cloud-lab','keep-request-id');
  const request = calls.at(-1);
  assert.equal(request.credentials, 'same-origin');
  assert.equal(request.headers['X-CSRF-Token'], 'csrf-test');
  assert.equal(request.headers['X-Demo-User'], undefined);
  assert.equal(request.headers['Idempotency-Key'], 'keep-request-id');
  assert.equal(JSON.parse(request.body).requestId,'keep-request-id');
});
test('tạo tài khoản không lưu mật khẩu hay session token vào localStorage', async () => {
  const {api,calls,storage} = client(() => ({status:201,body:{user,csrfToken:'csrf-test'}}));
  const result = await api.session.createAccount({name:user.name,studentId:user.studentId,email:user.email,password:'a-new-long-password'});
  assert.equal(result.id,user.id); assert.equal(calls[0].url,'/api/auth/register');
  assert.equal(storage.size,0);
  assert.equal(JSON.parse(calls[0].body).password,'a-new-long-password');
});
test('đăng xuất gọi server với CSRF và xóa tài khoản đang dùng', async () => {
  const {api,calls} = client(url => ({status:200,body:url==='/api/auth/session'?{user,csrfToken:'csrf-test'}:{user:null,csrfToken:null}}));
  await api.session.restore(); await api.session.signOut();
  assert.equal(calls.at(-1).url,'/api/auth/logout');
  assert.equal(calls.at(-1).headers['X-CSRF-Token'],'csrf-test');
  assert.equal(api.session.getUser(),null);
});
test('API trả 401 thì bỏ tài khoản hết phiên ở phía giao diện', async () => {
  const {api} = client(url => url==='/api/auth/session'?{status:200,body:{user,csrfToken:'csrf-test'}}:{status:401,body:{message:'Phiên hết hạn'}});
  await api.session.restore();
  await assert.rejects(()=>api.listBookings(), /Phiên hết hạn/);
  assert.equal(api.session.getUser(),null);
});
