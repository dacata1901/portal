const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

function client(mode = 'mock') {
  const storage = new Map(), calls = [];
  const window = { crypto: { randomUUID }, localStorage: {
    getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, String(v)), removeItem: k => storage.delete(k)
  }, CampusAuth: { getAccessToken: async () => null } };
  const context = vm.createContext({ window, setTimeout, clearTimeout, AbortController, fetch: async (url, options) => {
    calls.push({ url, ...options });
    return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => ({ event: JSON.parse(options.body) }) };
  } });
  for (const file of ['data.js', 'api.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, '../dist/js', file), 'utf8'), context);
  window.CAMPUS_CONFIG.mode = mode; window.CAMPUS_CONFIG.mockDelay = 0;
  window.PortalApi.session.login('org-1');
  return { api: window.PortalApi, calls };
}
const create = { title: 'Sự kiện mới', startsAt: '2026-12-01T03:00:00Z', capacity: 25,
  category: 'Công nghệ', format: 'Workshop', venue: 'Phòng B.302', description: 'Nội dung A' };
const fields = event => Object.fromEntries(['title', 'startsAt', 'capacity', 'category', 'format', 'venue', 'description'].map(k => [k, event[k]]));

test('mock: created A → edit B synchronizes detail and replays the saved result', async () => {
  const { api } = client();
  const { event } = await api.createEvent(create, 'create-copy');
  const payload = { ...fields(event), description: 'Nội dung B' };
  const first = await api.updateEvent(event.id, payload, 'edit-copy');
  assert.equal(first.event.description, 'Nội dung B'); assert.equal(first.event.about, 'Nội dung B');
  const again = await api.updateEvent(event.id, payload, 'edit-copy');
  assert.equal(again.replayed, true); assert.equal(again.event.about, first.event.about);
  await assert.rejects(() => api.updateEvent(event.id, { ...payload, about: 'Khác' }, 'edit-copy'), err => err.code === 'IDEMPOTENCY_CONFLICT');
  assert.equal((await api.getEvent(event.id)).about, 'Nội dung B');
});

test('mock: seeded rich copy survives a summary change and supports its own edit', async () => {
  const { api } = client(), event = await api.getEvent('cloud-lab');
  const summary = await api.updateEvent(event.id, { ...fields(event), description: 'Mô tả ngắn mới' }, 'seed-summary');
  assert.equal(summary.event.about, event.about);
  const payload = { ...fields(summary.event), about: 'Chi tiết riêng. '.repeat(80) };
  const edited = await api.updateEvent(event.id, payload, 'seed-details');
  assert.equal(edited.event.about, payload.about.trim());
  assert.equal(edited.event.description, 'Mô tả ngắn mới');
  assert.deepEqual(edited.event.agenda, event.agenda);
  await assert.rejects(() => api.updateEvent(event.id, { ...payload, about: null }, 'bad-about'), err => err.code === 'INVALID_EVENT');
  assert.equal((await api.getEvent(event.id)).about, payload.about.trim());
});

test('HTTP adapter sends separate detail copy and preserves the existing route and request ID', async () => {
  const { api, calls } = client('http');
  const payload = { ...create, about: 'Nội dung chi tiết riêng' };
  await api.updateEvent('event-copy', payload, 'http-copy');
  const call = calls.at(-1), body = JSON.parse(call.body);
  assert.equal(call.url, '/api/organizer/events/event-copy'); assert.equal(call.method, 'POST');
  assert.equal(call.headers['Idempotency-Key'], 'http-copy'); assert.equal(body.requestId, 'http-copy');
  assert.equal(body.description, 'Nội dung A'); assert.equal(body.about, payload.about);
});
