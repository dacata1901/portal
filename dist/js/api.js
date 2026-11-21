(function () {
  'use strict';
  const config = window.CAMPUS_CONFIG;
  const fixtures = window.CAMPUS_DATA;
  const STATE_KEY = 'campus-demo-state-v1';
  const USER_KEY = 'campus-demo-user-v1';
  let memoryState = null;
  let memoryUser = null;
  let localUser = null, csrfToken = null;
  config.localAccounts = Boolean(window.CAMPUS_RUNTIME_CONFIG?.localAccounts);
  let createdEvents = [];
  let scenario = 'normal';
  let didDropResponse = false;
  const clone = value => JSON.parse(JSON.stringify(value));
  const uid = () => window.crypto?.randomUUID?.() || `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const wait = () => new Promise(resolve => setTimeout(resolve, Number(config.mockDelay) || 0));
  class ApiError extends Error {
    constructor(message, status = 0, code = 'NETWORK_ERROR') { super(message); this.name = 'ApiError'; this.status = status; this.code = code; }
  }
  function readState() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(STATE_KEY));
      if (parsed && Array.isArray(parsed.bookings) && parsed.requests && typeof parsed.requests === 'object') return parsed;
    } catch { /* Trình duyệt có thể chặn lưu trữ khi mở file trực tiếp. */ }
    return memoryState || { bookings: [], requests: {} };
  }
  function writeState(state) {
    memoryState = clone(state);
    try { window.localStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch { /* Dùng bộ nhớ cho phiên hiện tại. */ }
  }
  function getUser() {
    if (window.CampusAuth?.enabled) {
      const id = window.CampusAuth.username();
      return fixtures.users.find(user => user.id === id) || null;
    }
    if (localUser) return clone(localUser);
    let id = memoryUser;
    try { id = window.localStorage.getItem(USER_KEY) || id; } catch { /* Bộ nhớ dự phòng. */ }
    return fixtures.users.find(user => user.id === id) || null;
  }
  function requireUser() {
    if (scenario === 'expired') { session.logout(); scenario = 'normal'; throw new ApiError('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', 401, 'SESSION_EXPIRED'); }
    const user = getUser();
    if (!user) throw new ApiError('Vui lòng đăng nhập để tiếp tục.', 401, 'UNAUTHENTICATED');
    return user;
  }
  function eventById(id) {
    const event = [...fixtures.events, ...createdEvents].find(item => item.id === id);
    if (!event) throw new ApiError('Không tìm thấy sự kiện này.', 404, 'EVENT_NOT_FOUND');
    return event;
  }
  function withCapacity(event, state = readState()) {
    const active = state.bookings.filter(b => b.eventId === event.id && b.status === 'active').length;
    return { ...clone(event), remainingCapacity: Math.max(0, event.capacity - event.baseRegistered - active), registeredCount: event.baseRegistered + active };
  }
  function authorizeOrganizer(event, user) {
    if (user.role !== 'administrator' && !(user.role === 'organizer' && event.organizerId === user.id)) throw new ApiError('Bạn không có quyền xem danh sách của sự kiện này.', 403, 'FORBIDDEN');
  }
  function replay(state, requestId, fingerprint) {
    if (!requestId) throw new ApiError('Thiếu mã yêu cầu. Vui lòng tải lại trang và thử lại.', 400, 'MISSING_REQUEST_ID');
    const record = state.requests[requestId];
    if (!record) return null;
    if (record.fingerprint !== fingerprint) throw new ApiError('Mã yêu cầu đã được dùng cho một thao tác khác.', 409, 'IDEMPOTENCY_CONFLICT');
    return { ...clone(record.result), replayed: true, requestId };
  }
  async function http(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const token = await config.getAccessToken();
      const headers = { Accept: 'application/json', ...options.headers };
      if (config.demoIdentity && !localUser && getUser()) headers['X-Demo-User'] = getUser().id;
      if (options.body) headers['Content-Type'] = 'application/json';
      if (csrfToken && options.method && options.method !== 'GET') headers['X-CSRF-Token'] = csrfToken;
      if (token) headers.Authorization = `Bearer ${token}`;
      if (options.requestId) { headers['Idempotency-Key'] = options.requestId; headers['X-Request-Id'] = options.requestId; }
      const base = config.apiBaseUrl.replace(/\/$/, '');
      const response = await fetch(base + path, { method: options.method || 'GET', credentials: 'same-origin', headers, body: options.body ? JSON.stringify(options.body) : undefined, signal: controller.signal });
      const body = response.headers.get('content-type')?.includes('json') ? await response.json() : options.text ? await response.text() : null;
      if (response.status === 401 && localUser) { localUser = null; csrfToken = null; }
      if (!response.ok) throw new ApiError(body?.message || 'Không thể hoàn tất yêu cầu. Vui lòng thử lại.', response.status, body?.code || 'API_ERROR');
      return body;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Chưa nhận được phản hồi. Kết quả có thể đã được lưu; hãy thử lại cùng thao tác.', 0, 'NETWORK_ERROR');
    } finally { clearTimeout(timeout); }
  }
  const session = {
    getUser,
    async restore() {
      if (!config.localAccounts || config.mode !== 'http') return;
      const result = await http('/auth/session');
      localUser = result.user; csrfToken = result.csrfToken;
      if (localUser) { memoryUser = null; try { window.localStorage.removeItem(USER_KEY); } catch {} }
    },
    async createAccount(data) {
      if (!config.localAccounts || config.mode !== 'http') throw new ApiError('Chức năng đăng ký tài khoản chưa được bật ở môi trường này.', 403, 'LOCAL_ACCOUNTS_DISABLED');
      const result = await http('/auth/register', { method: 'POST', body: data });
      this.logout(); localUser = result.user; csrfToken = result.csrfToken;
      return clone(localUser);
    },
    async passwordLogin(email, password) {
      if (!config.localAccounts || config.mode !== 'http') throw new ApiError('Hãy dùng dịch vụ đăng nhập của nhà trường.', 403, 'LOCAL_ACCOUNTS_DISABLED');
      const result = await http('/auth/login', { method: 'POST', body: { email, password } });
      this.logout(); localUser = result.user; csrfToken = result.csrfToken;
      return clone(localUser);
    },
    async changePassword(currentPassword, newPassword) {
      if (!config.localAccounts || config.mode !== 'http') throw new ApiError('Chức năng đổi mật khẩu không khả dụng ở chế độ này.', 403, 'LOCAL_ACCOUNTS_DISABLED');
      const result = await http('/auth/change-password', { method: 'POST', body: { currentPassword, newPassword } });
      localUser = result.user; csrfToken = result.csrfToken;
      return result;
    },
    login(id) {
      if (window.CampusAuth?.enabled) throw new ApiError('Hãy đăng nhập bằng tài khoản trường.', 403, 'COGNITO_LOGIN_REQUIRED');
      const user = fixtures.users.find(item => item.id === id);
      if (!user) throw new ApiError('Không tìm thấy tài khoản mẫu.', 404);
      memoryUser = id;
      try { window.localStorage.setItem(USER_KEY, id); } catch { /* Bộ nhớ dự phòng. */ }
      return clone(user);
    },
    logout() { localUser = null; csrfToken = null; memoryUser = null; try { window.localStorage.removeItem(USER_KEY); } catch { /* Bộ nhớ dự phòng. */ } if (config.mode === 'http') config.currentUser = null; },
    async signOut() {
      if (window.CampusAuth?.enabled) return window.CampusAuth.signOut();
      if (config.localAccounts && config.mode === 'http') await http('/auth/logout', { method: 'POST', body: {} });
      this.logout();
    },
    async signIn() { if (typeof config.signIn === 'function') return config.signIn(); throw new ApiError('Nhóm chưa cấu hình luồng đăng nhập thật.', 501, 'AUTH_NOT_CONFIGURED'); }
  };
  const api = {
    ApiError, session, newRequestId: uid,
    async exportRoster(eventId) {
      if (config.mode !== 'http') { const rows = await this.roster(eventId); return { csv: window.CampusUtils.rosterCsv(rows), count: rows.length }; }
      const path = `/organizer/events/${encodeURIComponent(eventId)}/exports`;
      const result = await http(path, { method: 'POST', body: {} });
      return { csv: await http(`${path}/${result.objectId}`, { text: true }), count: result.count };
    },
    async listEvents() {
      if (config.mode === 'http') return http('/events');
      await wait();
      if (scenario === 'loading') return new Promise(() => {});
      if (scenario === 'error') throw new ApiError('Chưa tải được danh sách sự kiện. Kiểm tra kết nối và thử lại.', 503, 'UNAVAILABLE');
      if (scenario === 'empty') return [];
      return [...fixtures.events, ...createdEvents].map(event => withCapacity(event));
    },
    async getEvent(id) { if (config.mode === 'http') return http(`/events/${encodeURIComponent(id)}`); await wait(); return withCapacity(eventById(id)); },
    async listBookings() {
      if (config.mode === 'http') return http('/me/registrations');
      await wait(); const user = requireUser();
      return clone(readState().bookings.filter(b => b.userId === user.id).sort((a, b) => b.createdAt.localeCompare(a.createdAt)));
    },
    async register(eventId, requestId) {
      if (config.mode === 'http') return http(`/events/${encodeURIComponent(eventId)}/registrations`, { method: 'POST', requestId, body: { requestId } });
      await wait(); const user = requireUser();
      if (user.role !== 'student') throw new ApiError('Hãy dùng tài khoản sinh viên để đăng ký sự kiện.', 403, 'STUDENT_REQUIRED');
      const event = eventById(eventId), state = readState();
      const fingerprint = `register:${user.id}:${eventId}`;
      const previous = replay(state, requestId, fingerprint); if (previous) return previous;
      if (state.bookings.some(b => b.userId === user.id && b.eventId === eventId && b.status === 'active')) throw new ApiError('Bạn đã đăng ký sự kiện này. Xem thông tin trong Đăng ký của tôi.', 409, 'ALREADY_REGISTERED');
      if (withCapacity(event, state).remainingCapacity <= 0) throw new ApiError('Sự kiện vừa hết chỗ. Bạn có thể khám phá sự kiện khác.', 409, 'EVENT_FULL');
      const booking = { id: `CP-${uid().replace(/-/g, '').slice(0, 10).toUpperCase()}`, eventId, userId: user.id, studentId: user.studentId, name: user.name, email: user.email, status: 'active', createdAt: new Date().toISOString(), cancelledAt: null };
      state.bookings.push(booking);
      const result = { booking: clone(booking), remainingCapacity: withCapacity(event, state).remainingCapacity, requestId, replayed: false };
      state.requests[requestId] = { fingerprint, result: clone(result) }; writeState(state);
      if (scenario === 'after-commit' && !didDropResponse) { didDropResponse = true; throw new ApiError('Kết nối bị ngắt trước khi nhận xác nhận. Bấm Thử lại để tìm kết quả đăng ký của bạn.', 0, 'NETWORK_ERROR'); }
      return result;
    },
    async cancel(bookingId, requestId) {
      if (config.mode === 'http') return http(`/registrations/${encodeURIComponent(bookingId)}/cancel`, { method: 'POST', requestId, body: { requestId } });
      await wait(); const user = requireUser(), state = readState();
      const fingerprint = `cancel:${user.id}:${bookingId}`, previous = replay(state, requestId, fingerprint); if (previous) return previous;
      const booking = state.bookings.find(b => b.id === bookingId && b.userId === user.id);
      if (!booking) throw new ApiError('Không tìm thấy đăng ký của bạn.', 404, 'BOOKING_NOT_FOUND');
      if (booking.status === 'active') { booking.status = 'cancelled'; booking.cancelledAt = new Date().toISOString(); }
      const result = { booking: clone(booking), remainingCapacity: withCapacity(eventById(booking.eventId), state).remainingCapacity, requestId, replayed: false };
      state.requests[requestId] = { fingerprint, result: clone(result) }; writeState(state); return result;
    },
    async createEvent(data, requestId) {
      if (config.mode === 'http') return http('/organizer/events', { method: 'POST', requestId, body: { ...data, requestId } });
      await wait(); const creator = requireUser();
      if (!['organizer', 'administrator'].includes(creator.role)) throw new ApiError('Chỉ ban tổ chức được xuất bản sự kiện.', 403, 'ORGANIZER_REQUIRED');
      const event = {
        id: `event-${uid().replace(/-/g, '').slice(0, 16)}`, ...clone(data), endsAt: data.startsAt,
        baseRegistered: 0, organizerId: creator.id, organizer: creator.name, theme: 'cloud',
        artwork: ['CAMPUS', 'EVENT.'], about: data.description, agenda: [],
        note: 'Thông tin do ban tổ chức cập nhật.', speaker: creator.name
      };
      createdEvents.push(event);
      return { event: withCapacity(event), requestId, replayed: false };
    },
    async updateEvent(eventId, data, requestId) {
      if (config.mode === 'http') return http(`/organizer/events/${encodeURIComponent(eventId)}`, { method: 'POST', requestId, body: { ...data, requestId } });
      await wait();
      const creator = requireUser(), event = eventById(eventId); authorizeOrganizer(event, creator);
      const state = readState(), fingerprint = `update-event:${creator.id}:${eventId}:${JSON.stringify(data)}`;
      const previous = replay(state, requestId, fingerprint); if (previous) return previous;
      if (data.capacity < withCapacity(event).registeredCount) throw new ApiError('Sức chứa không được nhỏ hơn số đăng ký đang hoạt động.', 409, 'CAPACITY_BELOW_ACTIVE');
      if (typeof data.description !== 'string' || data.description.trim().length > 400 || ('about' in data && (typeof data.about !== 'string' || data.about.trim().length > 10000))) throw new ApiError('Mô tả hoặc nội dung chi tiết không hợp lệ.', 400, 'INVALID_EVENT');
      const fields = { ...clone(data), description: data.description.trim() };
      if ('about' in fields) fields.about = fields.about.trim();
      else if (event.about === event.description) fields.about = fields.description;
      Object.assign(event, fields);
      if (new Date(event.endsAt) < new Date(event.startsAt)) event.endsAt = event.startsAt;
      const result = { event: withCapacity(event), requestId, replayed: false };
      state.requests[requestId] = { fingerprint, result: clone(result) }; writeState(state);
      return result;
    },
    async roster(eventId) {
      if (config.mode === 'http') return http(`/organizer/events/${encodeURIComponent(eventId)}/roster`);
      await wait(); const user = requireUser(), event = eventById(eventId); authorizeOrganizer(event, user);
      const seeded = Array.from({ length: event.baseRegistered }, (_, i) => ({ id: `SEED-${eventId}-${i + 1}`, eventId, userId: `seed-${i + 1}`, studentId: String(20001 + i), name: `Sinh viên mẫu ${i + 1}`, email: `student${20001 + i}@example.test`, status: 'active', createdAt: '2026-11-09T01:00:00.000Z' }));
      return [...seeded, ...clone(readState().bookings.filter(b => b.eventId === eventId && b.status === 'active'))];
    },
    async organizerEvents() { const events = await this.listEvents(); const user = requireUser(); if (!['organizer', 'administrator'].includes(user.role)) throw new ApiError('Bạn không có quyền truy cập trang này.', 403, 'FORBIDDEN'); return events.filter(e => user.role === 'administrator' || e.organizerId === user.id); },
    admin: {
      listStudents: () => http('/admin/students'),
      createStudent: data => http('/admin/students', { method: 'POST', body: data }),
      updateStudent: (id, data) => http(`/admin/students/${encodeURIComponent(id)}`, { method: 'POST', body: data }),
      deleteStudent: id => http(`/admin/students/${encodeURIComponent(id)}/delete`, { method: 'POST', body: {} }),
      deleteEvent: id => http(`/admin/events/${encodeURIComponent(id)}/delete`, { method: 'POST', body: {} }),
      addStudentToEvent: (eventId, userId) => http(`/admin/events/${encodeURIComponent(eventId)}/registrations`, { method: 'POST', body: { userId } }),
      removeRegistration: bookingId => http(`/admin/registrations/${encodeURIComponent(bookingId)}/remove`, { method: 'POST', body: {} })
    },
    demo: {
      getScenario: () => scenario,
      setScenario(value) { scenario = value; didDropResponse = false; },
      users: () => clone([fixtures.students[0], fixtures.students[1], ...fixtures.users.filter(u => u.role !== 'student')]),
      reset() { memoryState = null; createdEvents = []; session.logout(); scenario = 'normal'; didDropResponse = false; try { window.localStorage.removeItem(STATE_KEY); } catch { /* Bộ nhớ dự phòng. */ } },
      inspect: () => clone(readState())
    }
  };
  window.PortalApi = api;
}());
