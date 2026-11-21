(function () {
  'use strict';
  const api = window.PortalApi, config = window.CAMPUS_CONFIG, utils = window.CampusUtils;
  const $ = selector => document.querySelector(selector), esc = utils.escape;
  const main = $('#main'), dialog = $('#app-dialog');
  const view = { category: 'Tất cả', search: '', available: false, sort: 'date', bookingTab: 'all', rosterSearch: '', studentSearch: '' };
  let eventsCache = [], currentEvent = null, bookingCache = [], rosterCache = [], organizerCache = [], studentsCache = [], renderVersion = 0;
  let loginCallback = null, submitBusy = false, activeAction = null, publishRequestId = null;
  const pending = new Map();
  try { for (const [k, v] of Object.entries(JSON.parse(sessionStorage.getItem('campus-pending-v1') || '{}'))) pending.set(k, v); } catch { /* Dự phòng trong bộ nhớ. */ }
  const paths = {
    laptop: '<rect x="4" y="3" width="16" height="13" rx="2"/><path d="M2 20h20M8 20l1-4m6 0 1 4"/>',
    book: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15"/>',
    music: '<path d="M9 18V5l12-2v13M9 9l12-2"/><ellipse cx="6" cy="18" rx="3" ry="3"/><ellipse cx="18" cy="16" rx="3" ry="3"/>',
    leaf: '<path d="M20 3C8 2 3 8 5 15c2 7 14 6 15-12ZM4 21 15 10"/>',
    arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>', back: '<path d="m14 6-6 6 6 6"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18m-12 4h2m3 0h2"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', pin: '<path d="M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>', check: '<path d="m5 12 4 4L19 6"/>',
    users: '<circle cx="9" cy="8" r="3"/><path d="M3 21v-2a6 6 0 0 1 12 0v2m2-17a3 3 0 0 1 0 6m2 11v-2a6 6 0 0 0-3-5"/>',
    ticket: '<path d="M3 7h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4Zm12 0v3m0 4v5"/>',
    download: '<path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/>', close: '<path d="m6 6 12 12M6 18 18 6"/>',
    refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2"/>',
    shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
    chevron: '<path d="m8 10 4 4 4-4"/>', alert: '<path d="m12 3 10 18H2Z"/><path d="M12 9v4m0 4h.01"/>',
    logout: '<path d="M9 4H4v16h5m7-12 4 4-4 4m-6-4h10"/>'
  };
  const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.ticket}</svg>`;
  const fmt = (date, options) => new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', ...options }).format(new Date(date));
  const dateLabel = date => fmt(date, { day: '2-digit', month: '2-digit', year: 'numeric' });
  const timeLabel = date => fmt(date, { hour: '2-digit', minute: '2-digit', hour12: false });
  const initials = name => name.split(/[ ·]+/).filter(Boolean).slice(-2).map(s => s[0]).join('').toUpperCase();
  const user = () => api.session.getUser();
  const roleName = role => ({ student: 'Sinh viên', organizer: 'Ban tổ chức', administrator: 'Quản trị viên' }[role] || 'Khách');
  function requestId(action, entity) {
    const key = `${user()?.id}:${action}:${entity}`;
    if (!pending.has(key)) pending.set(key, api.newRequestId());
    persistPending(); return { key, id: pending.get(key) };
  }
  function persistPending() { try { sessionStorage.setItem('campus-pending-v1', JSON.stringify(Object.fromEntries(pending))); } catch { /* Dự phòng trong bộ nhớ. */ } }
  function clearPending(key) { pending.delete(key); persistPending(); }
  function toast(message, error = false) {
    const node = document.createElement('div'); node.className = `toast${error ? ' error' : ''}`; node.textContent = message;
    $('#toast-region').append(node); setTimeout(() => node.remove(), 5500);
  }
  function routeInfo() { return new URL(location.hash.slice(1) || '/events', 'https://campus.example'); }
  function go(path) { if (location.hash === '#' + path) renderRoute(); else location.hash = path; }
  function setMain(html, version) { if (version !== undefined && version !== renderVersion) return false; main.innerHTML = html; return true; }
  function emptyState(title, description, button = '', symbol = 'calendar') {
    return `<div class="state-box"><div class="state-symbol">${icon(symbol)}</div><h2>${esc(title)}</h2><p>${esc(description)}</p>${button}</div>`;
  }
  // Ảnh minh họa chụp thật: xem ASSETS.md. Không thay DTO hoặc adapter API.
  const eventImages = new Set(['cloud-lab', 'ai-campus', 'career-kit', 'hack-day', 'open-mic', 'green-campus']);
  function art(event, extra = '') {
    if (eventImages.has(event.id)) return `<figure class="event-art photo-art ${esc(event.theme)} ${extra}"><img src="./assets/events/${esc(event.id)}.jpg" alt="Ảnh minh họa cho ${esc(event.title)}" width="960" height="600" decoding="async"><span class="photo-format">${esc(event.format)}</span></figure>`;
    return `<div class="event-art ${esc(event.theme)} ${extra}" role="img" aria-label="Minh họa ${esc(event.title)}"><div class="art-kicker">CAMPUS / 2026</div><div class="art-title">${esc(event.title)}</div></div>`;
  }
  function header() {
    const current = user(), path = routeInfo().pathname;
    const links = [['/events', 'Khám phá']];
    if (!current || current.role !== 'administrator') links.push(['/bookings', 'Đăng ký của tôi']);
    if (current && current.role !== 'student') links.push(['/organizer', current.role === 'administrator' ? 'Quản lý sự kiện' : 'Ban tổ chức']);
    if (current && current.role === 'administrator') links.push(['/students', 'Quản lý sinh viên']);
    $('#main-nav').innerHTML = links.map(([href, label]) => `<a class="nav-link${path.startsWith(href) ? ' active' : ''}" href="#${href}"${path.startsWith(href) ? ' aria-current="page"' : ''}>${label}</a>`).join('');
    $('#account-area').innerHTML = current ? `<button class="account-button" type="button" data-action="account" aria-label="Tài khoản ${esc(current.name)}"><span class="avatar">${esc(initials(current.name))}</span><span class="account-name">${esc(current.name.split(' ').slice(-2).join(' '))}</span>${icon('chevron')}</button>` : '<div class="auth-header-actions"><button class="button primary small" type="button" data-action="login">Đăng nhập</button></div>';
    $('.site-header').classList.toggle('has-auth-actions', !current);
    $('#demo-tools').hidden = true;
  }
  // Biểu tượng SVG tự vẽ; cùng một ngôn ngữ hình ảnh trên mọi hệ điều hành.
  const categoryArtwork = {
    sparkle: '<path d="M34 8 42 25 58 32 41 40 33 57 25 40 8 32 25 24Z" fill="#d47b49"/><path d="m31 4 8 17 17 8-17 8-8 17-8-17-17-8 17-8Z" fill="#ffb986"/><path d="m31 7 4 15 14 7-15 3-3 16-4-15-14-4 14-5Z" fill="#ffd0a9"/><path d="m8 8 2 6 6 2-6 2-2 6-2-6-6-2 6-2Z" fill="#353039"/>',
    technology: '<g transform="rotate(-11 32 32)"><path d="M13 11h37v30H13Z" fill="#aa5a35"/><path d="M10 7h37v31H10Z" fill="#ffad77"/><path d="M15 12h27v20H15Z" fill="#41343c"/><path d="m22 18-5 5 5 4m13-9 5 5-5 4" stroke="#ffc99c" stroke-width="3" fill="none" stroke-linejoin="round"/><path d="m10 38-6 12 44 8 11-10-12-10Z" fill="#df794a"/><path d="m10 36-6 10 44 8 11-10-12-8Z" fill="#ffc094"/><path d="m15 40 28 4m-30 2 29 4" stroke="#e99060" stroke-width="2"/><path d="m26 48 9 2" stroke="#995734" stroke-width="2"/></g>',
    skills: '<g transform="rotate(9 32 32)"><path d="M9 22 34 9l24 14-24 14Z" fill="#6c4c9c"/><path d="M8 18 33 5l25 14-25 14Z" fill="#c8a3f4"/><path d="m16 28 17 8 17-8v12c-8 9-25 9-34 0Z" fill="#9d79d1"/><path d="m17 28 15 7v12c-6 0-12-2-15-6Z" fill="#b998ea"/><path d="m55 21 1 24" stroke="#5d4384" stroke-width="3"/><path d="m56 44-4 10h9Z" fill="#8460b4"/><path d="m20 18 14-8" stroke="#e6d2ff" stroke-width="3" stroke-linecap="round"/></g>',
    culture: '<g transform="rotate(10 32 32)"><path d="M26 10v33M51 5v34M26 14l25-5" stroke="#985532" stroke-width="7" stroke-linejoin="round"/><path d="M24 7v32M49 3v32M24 12l25-5" stroke="#ffb57d" stroke-width="6" stroke-linejoin="round"/><ellipse cx="17" cy="44" rx="10" ry="8" fill="#b76d47"/><ellipse cx="15" cy="40" rx="10" ry="8" fill="#ffc591"/><ellipse cx="43" cy="41" rx="10" ry="8" fill="#b76d47"/><ellipse cx="41" cy="37" rx="10" ry="8" fill="#ffa76f"/></g>',
    community: '<path d="M24 25C5 26 7 6 12 6c16 0 22 13 12 19Z" fill="#75c9a3"/><path d="M34 28c-9-17 6-28 21-23 1 17-8 26-21 23Z" fill="#43ac91"/><path d="M30 14v34m0-13L15 14m15 19L48 12" stroke="#236e5b" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M16 42h32l-5 18H21Z" fill="#33977e"/><path d="M16 40h32v7H16Z" fill="#91d3b7"/><path d="M21 48h6l2 10h-5Z" fill="#61b99b"/>',
    workshop: '<g transform="rotate(-10 32 32)"><rect x="12" y="6" width="35" height="49" rx="7" fill="#3b8b9a"/><rect x="8" y="3" width="35" height="49" rx="7" fill="#9ddade"/><path d="M18 16h17m-17 8h17m-17 8h10" stroke="#4d949c" stroke-width="3" stroke-linecap="round"/><path d="m43 20 10 4-12 30-10-4Z" fill="#edb972"/><path d="m53 24-4 9-10-4 4-9Z" fill="#e9839c"/><path d="m31 50 10 4-10 6Z" fill="#6b5b50"/></g>',
    talk: '<path d="M8 11h34a8 8 0 0 1 8 8v17a8 8 0 0 1-8 8H23L12 54V44a8 8 0 0 1-8-8V19a8 8 0 0 1 4-8Z" fill="#c85880"/><path d="M10 6h31a8 8 0 0 1 8 8v15a8 8 0 0 1-8 8H22L11 47V37a8 8 0 0 1-8-8V14a8 8 0 0 1 7-8Z" fill="#f6a4bf"/><circle cx="14" cy="21" r="3" fill="#a84b74"/><circle cx="26" cy="21" r="3" fill="#a84b74"/><circle cx="38" cy="21" r="3" fill="#a84b74"/><path d="M39 40h20v12H48l-6 6v-6h-3Z" fill="#fbc1d3"/>',
    hack: '<g transform="rotate(8 32 32)"><rect x="7" y="12" width="50" height="37" rx="10" fill="#75569d"/><rect x="5" y="7" width="50" height="37" rx="10" fill="#bea0e6"/><path d="m21 18-8 7 8 7m17-14 8 7-8 7m-8-16-4 18" stroke="#634484" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 50h32" stroke="#a080ca" stroke-width="5" stroke-linecap="round"/></g>',
    people: '<ellipse cx="23" cy="20" rx="10" ry="11" fill="#a986db"/><path d="M5 52c0-20 9-23 18-23 12 0 18 8 18 23Z" fill="#9e77d3"/><ellipse cx="43" cy="25" rx="9" ry="10" fill="#d3b6f4"/><path d="M29 55c0-18 7-22 15-22 10 0 16 9 16 22Z" fill="#c2a0e9"/><path d="M9 48c1-9 5-13 9-14" stroke="#c9aaf0" stroke-width="4" stroke-linecap="round"/>',
    activity: '<circle cx="32" cy="29" r="24" fill="#75c9b2"/><ellipse cx="29" cy="26" rx="22" ry="23" fill="#a4dec9"/><path d="M29 4c-13 13-13 32 0 45M30 4c13 13 13 32 0 45M7 25h44M29 4v45" stroke="#3f927b" stroke-width="3" fill="none"/><path d="M17 57h29" stroke="#3c806f" stroke-width="4" stroke-linecap="round"/>',
    heart: '<path d="M31 55 8 33C-6 14 16-3 31 13 45-4 69 13 55 33Z" fill="#c5527a"/><path d="M28 50 7 30C-5 13 16-2 29 12 44-2 64 13 51 30Z" fill="#f995b6"/><path d="M12 15c4-5 10-3 13 1" stroke="#ffc3d7" stroke-width="5" fill="none" stroke-linecap="round"/>'
  };
  const categoryIcons = {'Tất cả':'sparkle','Công nghệ':'technology','Kỹ năng':'skills','Văn hóa':'culture','Cộng đồng':'community','Workshop':'workshop','Talkshow':'talk','Hackathon':'hack','Giao lưu':'people','Hoạt động':'activity'};
  const categoryIcon = name => `<svg class="category-illustration" viewBox="0 0 64 64" aria-hidden="true" focusable="false">${categoryArtwork[categoryIcons[name] || name] || categoryArtwork.sparkle}</svg>`;
  function hero() {
    const cta = user() ? '<a class="button primary hero-cta" href="#/bookings">Xem đăng ký của tôi</a>' : '<button class="button primary hero-cta" type="button" data-action="login">Tham gia Campus</button>';
    return `<section class="hero meetup-hero"><div class="container hero-grid"><div class="hero-collage collage-left" aria-hidden="true"><figure class="hero-sticker sticker-study"><img src="./assets/events/cloud-lab.jpg" alt="" width="300" height="220"><figcaption>Cùng học điều mới</figcaption></figure><figure class="hero-sticker sticker-music"><img src="./assets/events/open-mic.jpg" alt="" width="300" height="220"><figcaption>Âm nhạc & bạn bè</figcaption></figure><span class="hero-scribble">♪</span></div><div class="hero-copy"><p class="hero-overline">CAMPUS · CỘNG ĐỒNG SINH VIÊN</p><h1>Cùng ${categoryIcon('people')} học điều mới.<br>Chung ${categoryIcon('sparkle')} một đam mê.<br>Thêm ${categoryIcon('heart')} nhiều bạn mới.</h1><p>Khám phá workshop, gặp người cùng sở thích và tham gia những hoạt động trong trường. Một sự kiện nhỏ, một trải nghiệm mới.</p>${cta}<span class="hero-helper">Lịch hoạt động tháng 11 · 2026</span></div><div class="hero-collage collage-right" aria-hidden="true"><figure class="hero-sticker sticker-friends"><img src="./assets/events/hack-day.jpg" alt="" width="300" height="220"><figcaption>Gặp người cùng đam mê</figcaption></figure><figure class="hero-sticker sticker-green"><img src="./assets/events/green-campus.jpg" alt="" width="300" height="220"><figcaption>Góp một chút xanh</figcaption></figure><span class="hero-scribble">✳</span></div></div></section>`;
  }
  function eventCard(event) {
    const availability = event.remainingCapacity === 0 ? '<span class="seat-tag full">Đã hết chỗ</span>' : `<span class="seat-tag${event.remainingCapacity <= 5 ? ' low' : ''}">Còn ${event.remainingCapacity}/${event.capacity} chỗ</span>`;
    return `<article class="event-card"><a class="event-image-link" href="#/events/${encodeURIComponent(event.id)}" tabindex="-1" aria-hidden="true">${art(event)}</a><div class="event-body"><div class="event-date">${icon('calendar')}${dateLabel(event.startsAt)} · ${timeLabel(event.startsAt)}</div><h3><a href="#/events/${encodeURIComponent(event.id)}">${esc(event.title)}</a></h3><div class="event-category">${esc(event.category)} · ${esc(event.format)}</div><p class="event-description">${esc(event.description)}</p><div class="event-meta"><span>${icon('pin')}${esc(event.venue)}</span><span>${icon('users')}${esc(event.organizer)}</span></div><div class="card-bottom">${availability}<a class="button secondary small" href="#/events/${encodeURIComponent(event.id)}" aria-label="Xem chi tiết: ${esc(event.title)}">Xem chi tiết ${icon('arrow')}</a></div></div></article>`;
  }
  async function renderCatalog(version) {
    setMain(`${hero()}<section class="container catalog-section"><div class="section-top"><div><h2>Khám phá sự kiện</h2><p>Các chương trình sắp diễn ra trong khuôn viên trường.</p></div><span class="section-count" id="results-count" aria-live="polite"></span></div><div class="search-row"><label class="search-input-wrap">${icon('search')}<span class="visually-hidden">Tìm sự kiện</span><input class="search-input" id="event-search" type="search" placeholder="Tìm sự kiện, chủ đề bạn quan tâm…" value="${esc(view.search)}" autocomplete="off"></label>${sortControl()}</div><div class="category-rail" role="group" aria-label="Chủ đề và hình thức sự kiện"><button class="category-scroll previous" type="button" data-category-scroll="previous" aria-label="Xem chủ đề trước" aria-controls="category-tabs" hidden>${icon('back')}</button><div class="chips category-tabs" id="category-tabs" tabindex="0" aria-label="Lọc theo chủ đề hoặc hình thức">${['Tất cả','Công nghệ','Kỹ năng','Văn hóa','Cộng đồng','Workshop','Talkshow','Hackathon','Giao lưu','Hoạt động'].map(category => `<button type="button" class="chip category-tab${category === view.category ? ' active' : ''}" aria-pressed="${category === view.category}" data-action="category" data-category="${esc(category)}"><span class="category-mark">${categoryIcon(category)}</span><span>${esc(category)}</span></button>`).join('')}</div><button class="category-scroll next" type="button" data-category-scroll="next" aria-label="Xem thêm chủ đề" aria-controls="category-tabs" hidden>${icon('arrow')}</button></div><div class="filter-row catalog-options"><span class="catalog-filter-label"><span>Chọn chủ đề hoặc hình thức bạn quan tâm</span></span><label class="check-label"><input id="available-only" type="checkbox"${view.available ? ' checked' : ''}> Chỉ hiện sự kiện còn chỗ</label></div><div id="event-results" aria-busy="true"><div class="event-grid" aria-label="Đang tải sự kiện">${Array.from({ length: 3 }, () => '<div class="skeleton" aria-hidden="true"></div>').join('')}</div><span class="visually-hidden" role="status">Đang tải danh sách sự kiện</span></div></section>`, version);
    $('#event-sort').value = view.sort;
    initSortControl();
    requestAnimationFrame(updateCategoryRail);
    try { const events = await api.listEvents(); if (version !== renderVersion) return; eventsCache = events; renderResults(); }
    catch (err) { if (version !== renderVersion) return; $('#event-results').setAttribute('aria-busy', 'false'); $('#event-results').innerHTML = emptyState('Chưa tải được sự kiện', err.message, '<button type="button" class="button primary" data-action="reload">Thử tải lại</button>', 'alert'); }
  }
  function renderResults() {
    const host = $('#event-results'); if (!host) return;
    const query = view.search.trim().toLocaleLowerCase('vi');
    const rows = eventsCache.filter(e => (view.category === 'Tất cả' || e.category === view.category || e.format === view.category) && (!view.available || e.remainingCapacity > 0) && (!query || `${e.title} ${e.category} ${e.description} ${e.venue}`.toLocaleLowerCase('vi').includes(query)));
    rows.sort(view.sort === 'seats' ? (a, b) => b.remainingCapacity - a.remainingCapacity : (a, b) => a.startsAt.localeCompare(b.startsAt));
    host.setAttribute('aria-busy', 'false'); $('#results-count').textContent = `${rows.length} sự kiện`;
    host.innerHTML = rows.length ? `<div class="event-grid">${rows.map(eventCard).join('')}</div>` : emptyState('Chưa tìm thấy sự kiện phù hợp', eventsCache.length ? 'Thử một từ khóa hoặc chủ đề khác để khám phá thêm.' : 'Danh sách hiện đang trống. Bạn có thể tải lại để kiểm tra.', `<button type="button" class="button secondary" data-action="${eventsCache.length ? 'clear-filters' : 'reload'}">${eventsCache.length ? 'Xóa bộ lọc' : 'Tải lại sự kiện'}</button>`, 'search');
  }
  async function renderDetail(id, version) {
    setMain('<div class="container page-shell"><div class="state-box"><span class="spinner" role="status" aria-label="Đang tải sự kiện"></span></div></div>', version);
    const event = await api.getEvent(id);
    let mine = [];
    if (user()?.role === 'student') { try { mine = await api.listBookings(); } catch (err) { if (err.status === 401) toast(err.message); else throw err; } }
    if (version !== renderVersion) return;
    currentEvent = event; bookingCache = mine; header();
    const active = mine.find(b => b.eventId === id && b.status === 'active');
    const button = active ? '<a class="button primary full" href="#/bookings">Xem đăng ký của tôi</a>' : event.remainingCapacity === 0 ? '<button class="button secondary full" type="button" disabled>Sự kiện đã hết chỗ</button>' : user() && user().role !== 'student' ? '<button class="button secondary full" type="button" data-action="login">Dùng tài khoản sinh viên</button>' : `<button class="button primary full" type="button" data-action="register" data-event="${esc(event.id)}">${user() ? 'Đăng ký tham gia' : 'Đăng nhập để đăng ký'} ${icon('arrow')}</button>`;
    setMain(`<div class="container page-shell"><a class="back-link" href="#/events">${icon('back')} Khám phá sự kiện</a><div class="detail-layout"><article><div class="detail-cover">${art(event)}</div><div class="detail-heading"><div class="event-category">${esc(event.category)} · ${esc(event.format)}</div><h1>${esc(event.title)}</h1><div class="organizer-line"><span class="organizer-emblem">${icon('users')}</span>Được tổ chức bởi <strong>${esc(event.organizer)}</strong></div></div><div class="detail-content"><section><h2>Về sự kiện</h2><p>${esc(event.about)}</p></section><section><h2>Lịch trình</h2><ul class="agenda">${event.agenda.map(item => `<li>${esc(item)}</li>`).join('')}</ul></section><section><h2>Thông tin cần biết</h2><p class="detail-note">${esc(event.note)}</p></section></div></article><aside class="booking-panel" aria-label="Thông tin đăng ký"><div class="panel-kicker">Trải nghiệm dành cho sinh viên</div><h2>Thông tin đăng ký</h2><div class="panel-meta"><div>${icon('calendar')}<div><strong>${dateLabel(event.startsAt)}</strong><span>${timeLabel(event.startsAt)} – ${timeLabel(event.endsAt)}</span></div></div><div>${icon('pin')}<div><strong>${esc(event.venue)}</strong><span>Trong khuôn viên trường</span></div></div><div>${icon('users')}<div><strong>${esc(event.speaker)}</strong><span>Cùng học và chia sẻ</span></div></div></div>${active ? '<div class="panel-state">✓ Bạn đã có một chỗ tại sự kiện này.</div>' : ''}<div class="capacity-heading"><span>Số chỗ còn lại</span><strong>${event.remainingCapacity}/${event.capacity}</strong></div><div class="capacity-track" role="progressbar" aria-label="Số chỗ đã đăng ký" aria-valuenow="${event.registeredCount}" aria-valuemin="0" aria-valuemax="${event.capacity}"><span style="width:${Math.min(100, event.registeredCount / event.capacity * 100)}%"></span></div><p class="capacity-note">${event.remainingCapacity ? 'Chỗ được xác nhận sau khi đăng ký thành công.' : 'Hiện chưa còn chỗ đăng ký.'}</p>${button}<p class="panel-footnote">${icon('shield')} Thông tin xác nhận có trong Đăng ký của tôi.</p></aside></div></div>`, version);
  }
  async function renderBookings(version) {
    if (!user()) { setMain(`<div class="container page-shell">${emptyState('Lịch hẹn của bạn bắt đầu ở đây', 'Đăng nhập để xem và quản lý các sự kiện bạn đã đăng ký.', '<button class="button primary" type="button" data-action="login">Đăng nhập</button>', 'ticket')}</div>`, version); return; }
    setMain('<div class="container page-shell"><div class="state-box"><span class="spinner" role="status" aria-label="Đang tải đăng ký"></span></div></div>', version);
    const bookings = await api.listBookings(), events = await api.listEvents();
    if (version !== renderVersion) return;
    bookingCache = bookings; eventsCache = events;
    const filtered = bookings.filter(b => view.bookingTab === 'all' || b.status === view.bookingTab);
    setMain(`<div class="container page-shell"><div class="page-intro"><div><div class="eyebrow">Lịch của bạn</div><h1 style="margin-top:14px">Đăng ký của tôi</h1><p>Xem xác nhận và quản lý các sự kiện bạn đã đăng ký.</p></div><a class="button secondary" href="#/events">Khám phá thêm ${icon('arrow')}</a></div><div class="chips" aria-label="Lọc đăng ký">${[['all', 'Tất cả'], ['active', 'Sắp tham gia'], ['cancelled', 'Đã hủy']].map(([value, label]) => `<button class="chip${view.bookingTab === value ? ' active' : ''}" type="button" data-action="booking-tab" data-value="${value}" aria-pressed="${view.bookingTab === value}">${label}${value === 'all' ? ` (${bookings.length})` : ''}</button>`).join('')}</div>${filtered.length ? `<div class="booking-list">${filtered.map(booking => {
      const event = events.find(e => e.id === booking.eventId); if (!event) return '';
      return `<article class="booking-row"><div class="date-square"><b>${fmt(event.startsAt, { day: '2-digit' })}</b><span>THÁNG ${fmt(event.startsAt, { month: '2-digit' })}</span></div><div class="booking-info"><span class="badge${booking.status === 'cancelled' ? ' cancelled' : ''}">${booking.status === 'active' ? 'Đã xác nhận' : 'Đã hủy'}</span><h3><a href="#/events/${esc(event.id)}">${esc(event.title)}</a></h3><p>${timeLabel(event.startsAt)} · ${esc(event.venue)}</p><span class="booking-code">${esc(booking.id)}</span></div><div class="booking-actions"><a class="button secondary small" href="#/receipt/${encodeURIComponent(booking.id)}">Xem xác nhận</a>${booking.status === 'active' ? `<button class="button danger small" type="button" data-action="cancel" data-booking="${esc(booking.id)}">Hủy đăng ký</button>` : ''}</div></article>`;
    }).join('')}</div>` : emptyState(view.bookingTab === 'cancelled' ? 'Chưa có đăng ký đã hủy' : 'Chưa có sự kiện trong danh sách', 'Tìm một sự kiện bạn yêu thích và giữ chỗ cho trải nghiệm tiếp theo.', '<a class="button primary" href="#/events">Khám phá sự kiện</a>', 'ticket')}</div>`, version);
  }
  async function renderReceipt(id, version) {
    if (!user()) { setMain(`<div class="container page-shell">${emptyState('Đăng nhập để xem xác nhận', 'Thông tin này chỉ hiển thị cho tài khoản đã đăng ký.', '<button class="button primary" type="button" data-action="login">Đăng nhập</button>', 'shield')}</div>`, version); return; }
    setMain('<div class="state-box"><span class="spinner" role="status" aria-label="Đang tải xác nhận"></span></div>', version);
    const bookings = await api.listBookings(), booking = bookings.find(b => b.id === id);
    if (!booking) throw new api.ApiError('Không tìm thấy xác nhận thuộc tài khoản này.', 404, 'BOOKING_NOT_FOUND');
    const event = await api.getEvent(booking.eventId); if (version !== renderVersion) return;
    const cancelled = booking.status === 'cancelled';
    setMain(`<section class="receipt-shell"><div class="success-symbol${cancelled ? ' cancelled' : ''}">${icon(cancelled ? 'close' : 'check')}</div><h1>${cancelled ? 'Đăng ký đã được hủy' : 'Bạn đã có một chỗ!'}</h1><p class="muted">${cancelled ? 'Số chỗ đã được cập nhật. Bạn luôn có thể khám phá một sự kiện khác.' : 'Hẹn gặp bạn tại sự kiện. Thông tin xác nhận đã có trong lịch của bạn.'}</p><div class="receipt-card"><div class="receipt-top"><div class="event-category">${esc(event.category)} · ${esc(event.format)}</div><h2>${esc(event.title)}</h2></div><dl class="receipt-grid"><div><dt>Mã đăng ký</dt><dd><strong>${esc(booking.id)}</strong></dd></div><div><dt>Trạng thái</dt><dd><span class="badge${cancelled ? ' cancelled' : ''}">${cancelled ? 'Đã hủy' : 'Đã xác nhận'}</span></dd></div><div><dt>Người tham gia</dt><dd>${esc(booking.name)} · ${esc(booking.studentId)}</dd></div><div><dt>Ngày và giờ</dt><dd>${dateLabel(event.startsAt)} · ${timeLabel(event.startsAt)}</dd></div><div><dt>Địa điểm</dt><dd>${esc(event.venue)}</dd></div><div><dt>${cancelled ? 'Thời điểm hủy' : 'Thời điểm đăng ký'}</dt><dd>${dateLabel(cancelled ? booking.cancelledAt : booking.createdAt)} · ${timeLabel(cancelled ? booking.cancelledAt : booking.createdAt)}</dd></div></dl><div class="receipt-bottom">${cancelled ? 'Bạn có thể đăng ký lại nếu sự kiện còn chỗ.' : 'Bạn có thể xem hoặc hủy đăng ký trong Đăng ký của tôi.'}</div></div><div class="action-row"><a class="button primary" href="#/bookings">Đăng ký của tôi</a><a class="button secondary" href="#/events">Khám phá thêm</a></div></section>`, version);
  }
  async function renderOrganizer(version) {
    if (!user()) { setMain(`<div class="container page-shell">${emptyState('Không gian của ban tổ chức', 'Đăng nhập bằng tài khoản ban tổ chức để quản lý danh sách.', '<button class="button primary" type="button" data-action="login">Đăng nhập</button>', 'users')}</div>`, version); return; }
    if (user().role === 'student') throw new api.ApiError('Trang này dành cho ban tổ chức. Bạn có thể quản lý đăng ký của mình ở mục Đăng ký của tôi.', 403, 'FORBIDDEN');
    setMain('<div class="container page-shell"><div class="state-box"><span class="spinner" role="status" aria-label="Đang tải bảng quản lý"></span></div></div>', version);
    const events = await api.organizerEvents(); if (version !== renderVersion) return; organizerCache = events;
    if (!events.length) { setMain(`<div class="container page-shell">${emptyState('Chưa có sự kiện được quản lý', 'Sự kiện của bạn sẽ xuất hiện ở đây khi được xuất bản.', '<button class="button primary" type="button" data-action="create-event">Tạo sự kiện</button>')}</div>`, version); return; }
    const requestedId = routeInfo().searchParams.get('event');
    const event = events.find(e => e.id === requestedId) || events[0]; currentEvent = event;
    const isAdmin = user().role === 'administrator';
    const roster = await api.roster(event.id); if (version !== renderVersion) return; rosterCache = roster;
    setMain(`<div class="container page-shell organizer-page"><div class="page-intro"><div><div class="eyebrow">${isAdmin ? 'Không gian quản trị viên' : 'Không gian ban tổ chức'}</div><h1 style="margin-top:14px">Quản lý sự kiện</h1><p>Theo dõi sức chứa, quản lý sự kiện và danh sách sinh viên tham gia thực tế.</p></div><span class="badge">${esc(roleName(user().role))}</span><div class="toolbar-actions">${isAdmin ? '<a class="button secondary small" href="#/students">Quản lý sinh viên</a>' : ''}<button type="button" class="button primary small" data-action="create-event">Tạo sự kiện</button></div></div><section class="organizer-summary"><div class="summary-art">${art(event)}</div><div class="summary-copy"><div class="event-category">${esc(event.category)} · ${esc(event.format)}</div><h2>${esc(event.title)}</h2><p>${icon('calendar')}${dateLabel(event.startsAt)} · ${timeLabel(event.startsAt)}<span>·</span>${esc(event.venue)}</p><div class="toolbar-actions" style="margin-top:12px"><button type="button" class="button secondary small" data-action="edit-event">Chỉnh sửa sự kiện</button>${isAdmin ? '<button type="button" class="button danger small" data-action="delete-event">Xóa sự kiện</button>' : ''}</div><div class="dashboard-selector"><label for="organizer-event">Sự kiện đang xem</label><select id="organizer-event" class="select-input">${events.map(e => `<option value="${esc(e.id)}"${e.id === event.id ? ' selected' : ''}>${esc(e.title)}</option>`).join('')}</select></div></div></section><div class="stats-grid"><div class="stat-card"><span>Đã đăng ký</span><strong>${roster.length}</strong><small>Sinh viên có đăng ký hoạt động</small></div><div class="stat-card"><span>Chỗ còn lại</span><strong>${event.remainingCapacity}</strong><small>Trên tổng ${event.capacity} chỗ</small></div><div class="stat-card"><span>Tỷ lệ đăng ký</span><strong>${Math.round(roster.length / event.capacity * 100)}%</strong><small>Đăng ký đang hoạt động / sức chứa</small><div class="capacity-track" role="progressbar" aria-label="Tỷ lệ đăng ký" aria-valuenow="${roster.length}" aria-valuemin="0" aria-valuemax="${event.capacity}"><span style="width:${Math.min(100, roster.length / event.capacity * 100)}%"></span></div></div></div><section class="dashboard-panel"><div class="dashboard-toolbar"><div><h2>Danh sách tham gia</h2><p>${esc(event.title)}</p></div><div class="toolbar-actions">${isAdmin ? '<button type="button" class="button secondary small" data-action="add-to-event">+ Thêm sinh viên</button>' : ''}<button type="button" class="button primary small" data-action="export-csv">${icon('download')} Tải danh sách CSV</button></div></div><div class="roster-tools"><label class="search-input-wrap">${icon('search')}<span class="visually-hidden">Tìm sinh viên</span><input id="roster-search" class="search-input" type="search" placeholder="Tìm họ tên hoặc mã sinh viên…" value="${esc(view.rosterSearch)}"></label><span id="roster-count" class="roster-count" aria-live="polite"></span></div><div class="table-wrap"><table><caption class="visually-hidden">Sinh viên đã đăng ký sự kiện</caption><thead><tr><th scope="col">Sinh viên</th><th scope="col">Mã sinh viên</th><th scope="col">Mã đăng ký</th><th scope="col">Trạng thái</th>${isAdmin ? '<th scope="col">Thao tác</th>' : ''}</tr></thead><tbody id="roster-rows"></tbody></table></div><div class="table-footnote">CSV bao gồm toàn bộ đăng ký đang hoạt động của sự kiện được chọn.</div></section></div>`, version);
    renderRosterRows();
  }
  function renderRosterRows() {
    const query = view.rosterSearch.trim().toLocaleLowerCase('vi');
    const isAdmin = user()?.role === 'administrator';
    const rows = rosterCache.filter(row => `${row.name} ${row.studentId} ${row.email}`.toLocaleLowerCase('vi').includes(query));
    if (!$('#roster-rows')) return;
    $('#roster-count').textContent = `${rows.length}/${rosterCache.length} sinh viên`;
    $('#roster-rows').innerHTML = rows.length ? rows.map(row => `<tr><td><div class="student-cell"><span class="avatar">${esc(initials(row.name))}</span><div><strong>${esc(row.name)}</strong><small>${esc(row.email)}</small></div></div></td><td data-label="Mã sinh viên">${esc(row.studentId)}</td><td data-label="Mã đăng ký"><span class="booking-code">${esc(row.id)}</span></td><td data-label="Trạng thái"><span class="badge">Đã xác nhận</span></td>${isAdmin ? `<td data-label="Thao tác"><button type="button" class="button danger small" data-action="remove-from-event" data-booking="${esc(row.id)}">Gỡ khỏi sự kiện</button></td>` : ''}</tr>`).join('') : `<tr><td colspan="${isAdmin ? 5 : 4}" class="empty-table">Chưa có sinh viên nào đăng ký sự kiện này.</td></tr>`;
  }
  async function renderStudents(version) {
    if (!user()) { setMain(`<div class="container page-shell">${emptyState('Quản lý sinh viên', 'Đăng nhập bằng tài khoản quản trị viên để quản lý danh sách sinh viên.', '<button class="button primary" type="button" data-action="login">Đăng nhập</button>', 'users')}</div>`, version); return; }
    if (user().role !== 'administrator') throw new api.ApiError('Chỉ quản trị viên mới có quyền quản lý danh sách sinh viên.', 403, 'FORBIDDEN');
    setMain('<div class="container page-shell"><div class="state-box"><span class="spinner" role="status" aria-label="Đang tải danh sách sinh viên"></span></div></div>', version);
    const students = await api.admin.listStudents(); if (version !== renderVersion) return; studentsCache = students;
    const totalActive = students.reduce((sum, s) => sum + (Number(s.activeBookings) || 0), 0);
    setMain(`<div class="container page-shell organizer-page"><div class="page-intro"><div><div class="eyebrow">Không gian quản trị viên</div><h1 style="margin-top:14px">Quản lý sinh viên</h1><p>Thêm mới, chỉnh sửa thông tin, cấp lại mật khẩu hoặc xóa tài khoản sinh viên của nhà trường.</p></div><div class="toolbar-actions"><a class="button secondary small" href="#/organizer">Quản lý sự kiện</a><button type="button" class="button primary small" data-action="create-student">+ Thêm sinh viên</button></div></div><div class="stats-grid"><div class="stat-card"><span>Tổng số sinh viên</span><strong>${students.length}</strong><small>Tài khoản sinh viên đang hoạt động</small></div><div class="stat-card"><span>Tổng lượt tham gia</span><strong>${totalActive}</strong><small>Đăng ký sự kiện đang hoạt động</small></div><div class="stat-card"><span>Phạm vi quản trị</span><strong>RBAC</strong><small>Chỉ quản trị viên được phép thay đổi</small></div></div><section class="dashboard-panel"><div class="dashboard-toolbar"><div><h2>Danh sách sinh viên</h2><p>Chỉ sinh viên được quản trị viên tạo hoặc cấp sẵn mới có thể đăng nhập và tham gia sự kiện.</p></div><button type="button" class="button primary small" data-action="create-student">+ Thêm sinh viên</button></div><div class="roster-tools"><label class="search-input-wrap">${icon('search')}<span class="visually-hidden">Tìm sinh viên</span><input id="student-search" class="search-input" type="search" placeholder="Tìm họ tên, mã sinh viên hoặc email…" value="${esc(view.studentSearch)}"></label><span id="student-count" class="roster-count" aria-live="polite"></span></div><div class="table-wrap"><table><caption class="visually-hidden">Danh sách tài khoản sinh viên</caption><thead><tr><th scope="col">Sinh viên</th><th scope="col">Mã sinh viên</th><th scope="col">Sự kiện tham gia</th><th scope="col">Thao tác</th></tr></thead><tbody id="student-rows"></tbody></table></div></section></div>`, version);
    renderStudentRows();
  }
  function renderStudentRows() {
    const query = view.studentSearch.trim().toLocaleLowerCase('vi');
    const rows = studentsCache.filter(row => `${row.name} ${row.studentId} ${row.email}`.toLocaleLowerCase('vi').includes(query));
    if (!$('#student-rows')) return;
    $('#student-count').textContent = `${rows.length}/${studentsCache.length} sinh viên`;
    $('#student-rows').innerHTML = rows.length ? rows.map(row => `<tr><td><div class="student-cell"><span class="avatar">${esc(initials(row.name))}</span><div><strong>${esc(row.name)}</strong><small>${esc(row.email)}</small></div></div></td><td data-label="Mã sinh viên">${esc(row.studentId)}</td><td data-label="Sự kiện tham gia"><span class="badge">${row.activeBookings || 0} sự kiện</span></td><td data-label="Thao tác"><div class="row-actions"><button type="button" class="button secondary small" data-action="edit-student" data-student="${esc(row.id)}">Sửa</button><button type="button" class="button danger small" data-action="delete-student" data-student="${esc(row.id)}">Xóa</button></div></td></tr>`).join('') : '<tr><td colspan="4" class="empty-table">Không tìm thấy sinh viên phù hợp.</td></tr>';
  }
  function updateCategoryRail() {
    const strip = $('#category-tabs'); if (!strip) return;
    const rail = strip.closest('.category-rail'), max = strip.scrollWidth - strip.clientWidth;
    rail.querySelector('.previous').hidden = strip.scrollLeft < 4;
    rail.querySelector('.next').hidden = max < 4 || strip.scrollLeft > max - 4;
  }
  document.addEventListener('click', event => {
    const control = event.target.closest('[data-category-scroll]');
    if (!control) return;
    const strip = $('#category-tabs'); if (!strip) return;
    const direction = control.dataset.categoryScroll === 'next' ? 1 : -1;
    strip.scrollBy({ left: direction * Math.max(180, strip.clientWidth * .7), behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  });
  document.addEventListener('scroll', event => { if (event.target.id === 'category-tabs') updateCategoryRail(); }, true);
  window.addEventListener('resize', updateCategoryRail);
  function sortControl() {
    const choices = [['date', 'Ngày diễn ra: sớm nhất'], ['seats', 'Số chỗ còn lại: nhiều nhất']];
    const arrows = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4v16m-4-4 4 4 4-4M16 20V4m-4 4 4-4 4 4"/></svg>';
    return `<div class="sort-control" data-sort-control><label class="visually-hidden" id="event-sort-label" for="event-sort">Sắp xếp sự kiện</label><select class="select-input" id="event-sort">${choices.map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select><button type="button" class="sort-trigger" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-controls="event-sort-menu" aria-labelledby="event-sort-label event-sort-current" hidden>${arrows}<span id="event-sort-current" data-sort-current></span>${icon('chevron')}</button><div class="sort-menu" id="event-sort-menu" role="listbox" aria-labelledby="event-sort-label" hidden>${choices.map(([value, label]) => `<button type="button" class="sort-option" id="event-sort-option-${value}" role="option" aria-selected="${view.sort === value}" tabindex="-1" data-sort-value="${value}"><span>${label}</span><span class="sort-selected-dot" aria-hidden="true"></span></button>`).join('')}</div></div>`;
  }
  function syncSortControl() {
    const root = $('[data-sort-control]'); if (!root) return;
    const select = root.querySelector('#event-sort');
    root.querySelector('[data-sort-current]').textContent = select.selectedOptions[0].textContent;
    root.querySelectorAll('[data-sort-value]').forEach(option => option.setAttribute('aria-selected', String(option.dataset.sortValue === select.value)));
  }
  function initSortControl() {
    const root = $('[data-sort-control]'); if (!root) return;
    syncSortControl();
    root.querySelector('#event-sort').hidden = true;
    root.querySelector('.sort-trigger').hidden = false;
    root.classList.add('is-enhanced');
  }
  function setSortActive(index) {
    const root = $('[data-sort-control]'); if (!root) return;
    const options = [...root.querySelectorAll('[data-sort-value]')];
    index = (index + options.length) % options.length;
    root.dataset.activeIndex = String(index);
    options.forEach((option, i) => option.classList.toggle('is-active', i === index));
    root.querySelector('.sort-trigger').setAttribute('aria-activedescendant', options[index].id);
  }
  function closeSortControl() {
    const root = $('[data-sort-control]'); if (!root) return;
    root.querySelector('.sort-trigger').setAttribute('aria-expanded', 'false');
    root.querySelector('.sort-trigger').removeAttribute('aria-activedescendant');
    root.querySelector('.sort-menu').hidden = true;
    delete root.dataset.placement;
  }
  function openSortControl(index) {
    const root = $('[data-sort-control]'); if (!root) return;
    const trigger = root.querySelector('.sort-trigger'), menu = root.querySelector('.sort-menu');
    trigger.setAttribute('aria-expanded', 'true'); menu.hidden = false;
    const options = [...root.querySelectorAll('[data-sort-value]')];
    setSortActive(index ?? options.findIndex(option => option.dataset.sortValue === root.querySelector('#event-sort').value));
    const rect = trigger.getBoundingClientRect();
    root.dataset.placement = window.innerHeight - rect.bottom < menu.offsetHeight + 12 && rect.top > menu.offsetHeight + 12 ? 'above' : 'below';
  }
  function commitSortControl(value, restoreFocus = true) {
    const root = $('[data-sort-control]'); if (!root) return;
    const select = root.querySelector('#event-sort');
    if (![...select.options].some(option => option.value === value)) return;
    select.value = value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    syncSortControl(); closeSortControl();
    if (restoreFocus) root.querySelector('.sort-trigger').focus({ preventScroll: true });
  }
  document.addEventListener('click', event => {
    const root = $('[data-sort-control]'); if (!root) return;
    const choice = event.target.closest('[data-sort-value]');
    if (choice && root.contains(choice)) { commitSortControl(choice.dataset.sortValue); return; }
    const trigger = event.target.closest('.sort-trigger');
    if (trigger && root.contains(trigger)) {
      if (trigger.getAttribute('aria-expanded') === 'true') closeSortControl(); else openSortControl();
    } else if (!root.contains(event.target)) closeSortControl();
  });
  document.addEventListener('keydown', event => {
    const trigger = event.target.closest('.sort-trigger'); if (!trigger) return;
    const root = trigger.closest('[data-sort-control]'), open = trigger.getAttribute('aria-expanded') === 'true';
    const options = [...root.querySelectorAll('[data-sort-value]')], active = Number(root.dataset.activeIndex || 0);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) openSortControl(); else setSortActive(active + (event.key === 'ArrowDown' ? 1 : -1));
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault(); const index = event.key === 'Home' ? 0 : options.length - 1;
      if (!open) openSortControl(index); else setSortActive(index);
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault(); if (!open) openSortControl(); else commitSortControl(options[active].dataset.sortValue);
    } else if (event.key === 'Escape' && open) {
      event.preventDefault(); closeSortControl();
    } else if (event.key === 'Tab' && open) commitSortControl(options[active].dataset.sortValue, false);
  });
  window.addEventListener('resize', closeSortControl);
  window.addEventListener('hashchange', closeSortControl);

  function showDialog(title, html) {
    dialog.innerHTML = `<div class="dialog-head"><h2 id="dialog-title">${esc(title)}</h2><button class="icon-button" type="button" data-action="close-dialog" aria-label="Đóng">${icon('close')}</button></div><div class="dialog-body">${html}</div>`;
    dialog.dataset.busy = 'false'; if (!dialog.open) dialog.showModal();
  }
  function openLogin(callback = null) {
    loginCallback = callback;
    if (config.mode !== 'mock' && !config.demoIdentity) { showDialog('Đăng nhập', '<p>Tiếp tục với dịch vụ đăng nhập của nhà trường.</p><button class="button primary full" type="button" data-action="real-login">Tiếp tục đăng nhập</button>'); return; }
    if (!config.localAccounts) { showDialog('Đăng nhập', '<p>Chức năng đăng nhập chưa sẵn sàng. Vui lòng liên hệ ban quản trị.</p>'); return; }
    showDialog('Chào mừng bạn trở lại', `<p>Đăng nhập bằng tài khoản nhà trường cấp để giữ chỗ và quản lý các sự kiện bạn tham gia.</p><form id="account-login-form" class="account-form"><label class="field" for="login-email">Email<input id="login-email" name="email" type="email" autocomplete="username" maxlength="254" required></label><label class="field" for="login-password">Mật khẩu<input id="login-password" name="password" type="password" autocomplete="current-password" maxlength="128" required></label><div id="account-form-error" role="alert" aria-live="polite"></div><button class="button primary full" type="submit">Đăng nhập</button></form><p class="auth-switch">Sử dụng tài khoản sinh viên hoặc cán bộ do nhà trường cấp.</p>`);
  }
  function openSignup(callback = null) {
    loginCallback = callback;
    showDialog('Tài khoản nhà trường', '<p>Tài khoản sinh viên và cán bộ do nhà trường cấp. Vui lòng đăng nhập bằng tài khoản đã được cấp.</p><button class="button primary full" type="button" data-action="account-login">Đến đăng nhập</button>');
  }
  async function submitAccountForm(form) {
    if (submitBusy || !form.reportValidity()) return;
    const signup = form.id === 'account-signup-form', error = $('#account-form-error');
    error.innerHTML = '';
    if (signup && $('#signup-password').value !== $('#signup-confirm').value) {
      error.innerHTML = '<p class="dialog-error">Hai mật khẩu chưa khớp. Vui lòng kiểm tra lại.</p>';
      $('#signup-confirm').focus(); return;
    }
    const button = form.querySelector('button[type="submit"]'), previous = button.textContent;
    submitBusy = true; dialog.dataset.busy = 'true';
    dialog.querySelectorAll('input,button,summary').forEach(control => { control.disabled = true; });
    button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Đang xử lý…';
    try {
      if (signup) await api.session.createAccount({name:$('#signup-name').value,studentId:$('#signup-student').value,email:$('#signup-email').value,password:$('#signup-password').value});
      else await api.session.passwordLogin($('#login-email').value,$('#login-password').value);
      form.querySelectorAll('input[type="password"]').forEach(input => { input.value = ''; });
      dialog.close(); header();
      toast(signup ? 'Tạo tài khoản thành công. Chào mừng bạn đến Campus!' : 'Bạn đã đăng nhập.');
      const callback = loginCallback; loginCallback = null;
      if (callback) await callback(); else await renderRoute();
    } catch (err) {
      if (dialog.open && error.isConnected) error.innerHTML = `<p class="dialog-error">${esc(err.message)}</p>`;
    } finally {
      submitBusy = false; dialog.dataset.busy = 'false';
      dialog.querySelectorAll('input,button,summary').forEach(control => { control.disabled = false; });
      if (button.isConnected) button.textContent = previous;
    }
  }
  function openAccount() {
    const current = user(); if (!current) return openLogin();
    showDialog('Tài khoản của bạn', `<p><strong>${esc(current.name)}</strong><br>${esc(roleName(current.role))}${current.studentId ? ` · MSSV: ${esc(current.studentId)}` : ''}<br>${esc(current.email)}</p><div class="demo-options">${config.localAccounts && config.mode === 'http' ? '<button class="button secondary" type="button" data-action="change-password">Đổi mật khẩu</button>' : ''}${config.mode === 'mock' ? '<button class="button secondary" type="button" data-action="login">Đổi tài khoản mẫu</button>' : ''}<button class="button secondary" type="button" data-action="logout">${icon('logout')} Đăng xuất</button></div>`);
  }
  function openChangePassword() {
    if (!user()) return openLogin();
    showDialog('Đổi mật khẩu', `<p>Nhập mật khẩu hiện tại và đặt mật khẩu mới (tối thiểu 12 ký tự).</p><form id="change-password-form" class="account-form"><label class="field" for="cp-current">Mật khẩu hiện tại<input id="cp-current" name="currentPassword" type="password" autocomplete="current-password" maxlength="128" required></label><label class="field" for="cp-new">Mật khẩu mới<input id="cp-new" name="newPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required><small>Từ 12 đến 128 ký tự.</small></label><label class="field" for="cp-confirm">Nhập lại mật khẩu mới<input id="cp-confirm" name="confirm" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><div id="account-form-error" role="alert" aria-live="polite"></div><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">Hủy</button><button class="button primary" type="submit">Lưu mật khẩu mới</button></div></form>`);
  }
  async function submitChangePassword(form) {
    if (submitBusy || !form.reportValidity()) return;
    const error = $('#account-form-error'); error.innerHTML = '';
    if ($('#cp-new').value !== $('#cp-confirm').value) {
      error.innerHTML = '<p class="dialog-error">Mật khẩu mới nhập lại chưa khớp.</p>';
      $('#cp-confirm').focus(); return;
    }
    const button = form.querySelector('button[type="submit"]'), previous = button.textContent;
    submitBusy = true; dialog.dataset.busy = 'true';
    dialog.querySelectorAll('input,button').forEach(control => { control.disabled = true; });
    button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Đang lưu…';
    try {
      await api.session.changePassword($('#cp-current').value, $('#cp-new').value);
      form.querySelectorAll('input[type="password"]').forEach(input => { input.value = ''; });
      dialog.close(); toast('Đã đổi mật khẩu thành công.');
    } catch (err) {
      if (dialog.open && error.isConnected) error.innerHTML = `<p class="dialog-error">${esc(err.message)}</p>`;
    } finally {
      submitBusy = false; dialog.dataset.busy = 'false';
      dialog.querySelectorAll('input,button').forEach(control => { control.disabled = false; });
      if (button.isConnected) button.textContent = previous;
    }
  }
  function openStudentForm(studentId = null) {
    const existing = studentId ? studentsCache.find(s => s.id === studentId) : null;
    showDialog(existing ? 'Chỉnh sửa sinh viên' : 'Thêm sinh viên mới', `<p>${existing ? 'Cập nhật thông tin sinh viên. Có thể để trống ô mật khẩu nếu không muốn đổi.' : 'Tạo tài khoản sinh viên mới do nhà trường cấp.'}</p><form id="admin-student-form" class="account-form"${existing ? ` data-student-id="${esc(existing.id)}"` : ''}><label class="field" for="stu-name">Họ và tên<input id="stu-name" name="name" minlength="2" maxlength="100" value="${esc(existing?.name || '')}" required></label><label class="field" for="stu-code">Mã sinh viên<input id="stu-code" name="studentId" minlength="3" maxlength="32" pattern="[A-Za-z0-9][A-Za-z0-9._-]{2,31}" value="${esc(existing?.studentId || '')}" required></label><label class="field" for="stu-email">Email<input id="stu-email" name="email" type="email" maxlength="254" value="${esc(existing?.email || '')}" required></label><label class="field" for="stu-password">${existing ? 'Mật khẩu mới (tùy chọn)' : 'Mật khẩu khởi tạo'}<input id="stu-password" name="password" type="password" minlength="12" maxlength="128" autocomplete="new-password"${existing ? '' : ' required'}><small>${existing ? 'Để trống nếu giữ nguyên mật khẩu hiện tại (tối thiểu 12 ký tự nếu đặt lại).' : 'Từ 12 đến 128 ký tự.'}</small></label><div id="account-form-error" role="alert" aria-live="polite"></div><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">Hủy</button><button class="button primary" type="submit">${existing ? 'Lưu thay đổi' : 'Thêm sinh viên'}</button></div></form>`);
  }
  async function submitStudentForm(form) {
    if (submitBusy || !form.reportValidity()) return;
    const error = $('#account-form-error'); error.innerHTML = '';
    const studentId = form.dataset.studentId || null;
    const payload = { name: $('#stu-name').value.trim(), studentId: $('#stu-code').value.trim(), email: $('#stu-email').value.trim() };
    const pw = $('#stu-password').value;
    if (pw || !studentId) payload.password = pw;
    const button = form.querySelector('button[type="submit"]'), previous = button.textContent;
    submitBusy = true; dialog.dataset.busy = 'true';
    dialog.querySelectorAll('input,button').forEach(control => { control.disabled = true; });
    button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Đang lưu…';
    try {
      if (studentId) await api.admin.updateStudent(studentId, payload);
      else await api.admin.createStudent(payload);
      dialog.close();
      toast(studentId ? 'Đã cập nhật thông tin sinh viên.' : 'Đã thêm sinh viên mới.');
      await renderRoute();
    } catch (err) {
      if (dialog.open && error.isConnected) error.innerHTML = `<p class="dialog-error">${esc(err.message)}</p>`;
    } finally {
      submitBusy = false; dialog.dataset.busy = 'false';
      dialog.querySelectorAll('input,button').forEach(control => { control.disabled = false; });
      if (button.isConnected) button.textContent = previous;
    }
  }
  function openDeleteStudent(studentId) {
    const stu = studentsCache.find(s => s.id === studentId); if (!stu) return;
    showDialog('Xóa sinh viên?', `<p>Bạn có chắc muốn xóa tài khoản <strong>${esc(stu.name)}</strong> (${esc(stu.studentId)})? Toàn bộ lượt đăng ký sự kiện của sinh viên này cũng sẽ bị xóa và tự động hoàn lại chỗ trống.</p><div id="account-form-error" role="alert"></div><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">Giữ lại</button><button type="button" class="button danger" data-action="confirm-delete-student" data-student="${esc(stu.id)}">Xác nhận xóa</button></div>`);
  }
  function openDeleteEvent() {
    if (!currentEvent) return;
    showDialog('Xóa sự kiện?', `<p>Bạn có chắc muốn xóa vĩnh viễn sự kiện <strong>${esc(currentEvent.title)}</strong> cùng toàn bộ danh sách đăng ký của sự kiện này?</p><div id="account-form-error" role="alert"></div><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">Giữ sự kiện</button><button type="button" class="button danger" data-action="confirm-delete-event" data-event="${esc(currentEvent.id)}">Xác nhận xóa</button></div>`);
  }
  async function openAddToEvent() {
    if (!currentEvent) return;
    showDialog('Thêm sinh viên vào sự kiện', '<div class="state-box" style="min-height:140px"><span class="spinner" role="status" aria-label="Đang tải danh sách sinh viên"></span></div>');
    try {
      const allStudents = await api.admin.listStudents();
      const activeIds = new Set(rosterCache.map(r => r.userId));
      const available = allStudents.filter(s => !activeIds.has(s.id));
      if (!available.length) {
        showDialog('Thêm sinh viên vào sự kiện', '<p>Tất cả sinh viên trong hệ thống đều đã đăng ký sự kiện này hoặc chưa có sinh viên nào.</p><div class="dialog-actions"><a class="button primary" href="#/students" data-action="close-dialog">Quản lý sinh viên</a></div>');
        return;
      }
      showDialog('Thêm sinh viên vào sự kiện', `<p>Chọn một sinh viên đã tạo trong hệ thống để ghi danh vào <strong>${esc(currentEvent.title)}</strong> (còn ${currentEvent.remainingCapacity} chỗ).</p><form id="admin-add-to-event-form" class="account-form"><label class="field" for="add-student-filter">Lọc nhanh sinh viên<input id="add-student-filter" type="search" placeholder="Nhập tên hoặc MSSV…"></label><label class="field" for="add-student-select">Chọn sinh viên<select id="add-student-select" class="select-input" required>${available.map(s => `<option value="${esc(s.id)}">${esc(s.studentId)} · ${esc(s.name)} (${esc(s.email)})</option>`).join('')}</select></label><div id="account-form-error" role="alert"></div><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">Hủy</button><button type="submit" class="button primary">Thêm vào sự kiện</button></div></form>`);
      dialog._availableStudents = available;
    } catch (err) {
      showDialog('Không tải được danh sách sinh viên', `<p class="dialog-error">${esc(err.message)}</p>`);
    }
  }
  async function submitAddToEvent(form) {
    if (submitBusy || !currentEvent) return;
    const select = $('#add-student-select'), error = $('#account-form-error'); error.innerHTML = '';
    if (!select || !select.value) { error.innerHTML = '<p class="dialog-error">Vui lòng chọn sinh viên.</p>'; return; }
    const button = form.querySelector('button[type="submit"]'), previous = button.textContent;
    submitBusy = true; dialog.dataset.busy = 'true';
    dialog.querySelectorAll('input,select,button').forEach(control => { control.disabled = true; });
    button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Đang thêm…';
    try {
      await api.admin.addStudentToEvent(currentEvent.id, select.value);
      dialog.close(); toast('Đã thêm sinh viên vào sự kiện.');
      await renderRoute();
    } catch (err) {
      if (dialog.open && error.isConnected) error.innerHTML = `<p class="dialog-error">${esc(err.message)}</p>`;
    } finally {
      submitBusy = false; dialog.dataset.busy = 'false';
      dialog.querySelectorAll('input,select,button').forEach(control => { control.disabled = false; });
      if (button.isConnected) button.textContent = previous;
    }
  }
  function openRemoveFromEvent(bookingId) {
    const row = rosterCache.find(r => r.id === bookingId); if (!row) return;
    showDialog('Gỡ sinh viên khỏi sự kiện?', `<p>Hủy suất tham gia của <strong>${esc(row.name)}</strong> (${esc(row.studentId)}) khỏi sự kiện này và hoàn lại 1 chỗ trống?</p><div id="account-form-error" role="alert"></div><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">Giữ lại</button><button type="button" class="button danger" data-action="confirm-remove-from-event" data-booking="${esc(row.id)}">Xác nhận gỡ</button></div>`);
  }
  function openPublishEvent() {
    publishRequestId = api.newRequestId();
    showDialog('Xuất bản sự kiện', `<p>Sự kiện sẽ xuất hiện ngay trong danh mục và có thể nhận đăng ký.</p><div id="publish-error"></div><form id="publish-event-form"><label class="field" for="publish-title">Tên sự kiện<input id="publish-title" name="title" maxlength="140" required></label><label class="field" for="publish-start">Ngày và giờ bắt đầu<input id="publish-start" name="startsAt" type="datetime-local" required></label><label class="field" for="publish-capacity">Sức chứa<input id="publish-capacity" name="capacity" type="number" min="1" max="100000" value="20" required></label><label class="field" for="publish-category">Chủ đề<select id="publish-category" name="category" class="select-input"><option>Công nghệ</option><option>Kỹ năng</option><option>Văn hóa</option><option>Cộng đồng</option></select></label><label class="field" for="publish-format">Hình thức<select id="publish-format" name="format" class="select-input"><option>Workshop</option><option>Talkshow</option><option>Hackathon</option><option>Giao lưu</option><option>Hoạt động</option></select></label><label class="field" for="publish-venue">Địa điểm<input id="publish-venue" name="venue" maxlength="160" placeholder="Ví dụ: Phòng B.302"></label><label class="field" for="publish-description">Mô tả<textarea id="publish-description" name="description" maxlength="400" rows="3"></textarea></label><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">Để sau</button><button type="button" class="button primary" data-action="publish-event" id="publish-submit">Xuất bản</button></div></form>`);
  }
  function openEditEvent() {
    if (!currentEvent) return;
    openPublishEvent();
    const form = $('#publish-event-form'), event = currentEvent;
    form.dataset.eventId = event.id;
    $('#dialog-title').textContent = 'Chỉnh sửa sự kiện';
    dialog.querySelector('p').textContent = 'Mô tả ngắn xuất hiện trong danh mục; nội dung chi tiết xuất hiện tại trang sự kiện. Sức chứa phải đủ cho các đăng ký đang hoạt động.';
    const date = new Date(event.startsAt); date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    const values = { title: event.title, start: date.toISOString().slice(0, 16), capacity: event.capacity, category: event.category, format: event.format, venue: event.venue, description: event.description };
    for (const [name, value] of Object.entries(values)) $(`#publish-${name}`).value = value;
    const description = $('#publish-description');
    description.parentElement.firstChild.textContent = 'Mô tả ngắn (danh mục)';
    description.parentElement.insertAdjacentHTML('afterend', '<label class="field" for="publish-about">Nội dung chi tiết (trang sự kiện)<textarea id="publish-about" name="about" maxlength="10000" rows="6" aria-describedby="publish-about-help"></textarea><small id="publish-about-help">Nếu hai phần đang giống nhau, nội dung chi tiết sẽ theo mô tả ngắn cho đến khi bạn chỉnh sửa riêng.</small></label>');
    $('#publish-about').value = event.about || '';
    form.dataset.linkedDescription = String(event.about === event.description || (event.about === '' && event.description === 'Thông tin chi tiết sẽ được ban tổ chức cập nhật.'));
    $('#publish-submit').textContent = 'Lưu thay đổi';
  }
  async function publishEvent() {
    const form = $('#publish-event-form');
    if (submitBusy || !form.reportValidity()) return;
    const data = {
      title: $('#publish-title').value.trim(),
      startsAt: new Date($('#publish-start').value).toISOString(),
      capacity: Number($('#publish-capacity').value),
      category: $('#publish-category').value,
      format: $('#publish-format').value,
      venue: $('#publish-venue').value.trim(),
      description: $('#publish-description').value.trim()
    };
    if (form.dataset.eventId) data.about = $('#publish-about').value.trim();
    const button = $('#publish-submit');
    submitBusy = true; dialog.dataset.busy = 'true';
    dialog.querySelectorAll('button').forEach(control => { control.disabled = true; });
    button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Đang xuất bản…';
    $('#publish-error').innerHTML = '';
    try {
      const result = form.dataset.eventId ? await api.updateEvent(form.dataset.eventId, data, publishRequestId) : await api.createEvent(data, publishRequestId);
      dialog.close(); publishRequestId = null;
      toast(form.dataset.eventId ? 'Đã cập nhật sự kiện.' : 'Sự kiện đã được xuất bản.');
      go(`/organizer?event=${encodeURIComponent(result.event.id)}`);
    } catch (err) {
      $('#publish-error').innerHTML = `<p class="dialog-error" role="alert">${esc(err.message)}${err.status === 0 ? ' Hãy thử lại mà không thay đổi nội dung để tránh tạo sự kiện trùng.' : ''}</p>`;
      dialog.querySelectorAll('button').forEach(control => { control.disabled = false; });
      if (err.status === 0) {
        form.querySelectorAll('input,select,textarea').forEach(control => { control.disabled = true; });
        button.textContent = 'Thử lại cùng nội dung';
      } else {
        publishRequestId = api.newRequestId();
        button.textContent = 'Thử lại';
      }
    } finally { submitBusy = false; dialog.dataset.busy = 'false'; }
  }
  async function openRegister(eventId) {
    const event = currentEvent?.id === eventId ? currentEvent : await api.getEvent(eventId);
    if (!user()) return openLogin(() => openRegister(eventId));
    if (user().role !== 'student') return openLogin(() => openRegister(eventId));
    activeAction = { type: 'register', event, request: requestId('register', eventId) };
    showDialog('Xác nhận tham gia', `<p>Kiểm tra thông tin trước khi giữ chỗ cho sự kiện.</p><div class="dialog-event"><h3>${esc(event.title)}</h3><p>${icon('calendar')}${dateLabel(event.startsAt)} · ${timeLabel(event.startsAt)}</p><p>${icon('pin')}${esc(event.venue)}</p></div><p class="dialog-person">Người tham gia: <strong>${esc(user().name)}</strong><br>Mã sinh viên: ${esc(user().studentId)}</p><div id="action-error"></div><div class="dialog-actions"><button type="button" class="button secondary" data-action="close-dialog">Để sau</button><button type="button" class="button primary" data-action="submit-registration" id="submit-action">Xác nhận đăng ký</button></div>`);
  }
  function openCancel(bookingId) {
    const booking = bookingCache.find(b => b.id === bookingId), event = eventsCache.find(e => e.id === booking?.eventId);
    if (!booking || !event) { toast('Vui lòng tải lại danh sách đăng ký.', true); return; }
    activeAction = { type: 'cancel', booking, event, request: requestId('cancel', bookingId) };
    showDialog('Hủy đăng ký sự kiện?', `<p>Chỗ của bạn sẽ được trả lại để sinh viên khác có thể đăng ký.</p><div class="dialog-event"><h3>${esc(event.title)}</h3><p>${icon('calendar')}${dateLabel(event.startsAt)} · ${timeLabel(event.startsAt)}</p></div><div id="action-error"></div><div class="dialog-actions"><button class="button secondary" type="button" data-action="close-dialog">Giữ đăng ký</button><button class="button danger" type="button" data-action="submit-cancellation" id="submit-action">Xác nhận hủy</button></div>`);
  }
  async function submitAction() {
    if (submitBusy || !activeAction) return;
    const action = activeAction, button = $('#submit-action'); submitBusy = true; dialog.dataset.busy = 'true';
    dialog.querySelectorAll('button').forEach(b => { b.disabled = true; });
    button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Đang xử lý…'; $('#action-error').innerHTML = '';
    try {
      const result = action.type === 'register' ? await api.register(action.event.id, action.request.id) : await api.cancel(action.booking.id, action.request.id);
      clearPending(action.request.key); activeAction = null; dialog.close();
      toast(action.type === 'cancel' ? 'Đã hủy đăng ký và cập nhật chỗ.' : result.replayed ? 'Đã tìm thấy xác nhận đăng ký của bạn.' : 'Đăng ký thành công. Hẹn gặp bạn tại sự kiện!');
      go(`/receipt/${encodeURIComponent(result.booking.id)}`);
    } catch (err) {
      if (err.status === 401) { dialog.close(); toast(err.message, true); openLogin(); header(); }
      else {
        $('#action-error').innerHTML = `<p class="dialog-error" role="alert">${esc(err.message)}</p>`;
        dialog.querySelectorAll('button').forEach(b => { b.disabled = false; });
        button.textContent = err.status === 0 ? 'Thử lại' : action.type === 'register' ? 'Thử đăng ký lại' : 'Thử hủy lại';
        if (err.code === 'ALREADY_REGISTERED' || err.code === 'EVENT_FULL') {
          clearPending(action.request.key); button.dataset.action = err.code === 'ALREADY_REGISTERED' ? 'show-bookings' : 'reload-detail'; button.textContent = err.code === 'ALREADY_REGISTERED' ? 'Xem đăng ký của tôi' : 'Cập nhật số chỗ';
        }
      }
    } finally { submitBusy = false; dialog.dataset.busy = 'false'; }
  }
  function openDemo() {
    showDialog('Tùy chọn bản mẫu', `<p>Thử các trạng thái để kiểm tra giao diện phần A. Dữ liệu và tài khoản đều là giả lập.</p><label class="field" for="demo-scenario">Tình huống hiển thị<select class="select-input" id="demo-scenario">${[['normal', 'Bình thường'], ['error', 'Lỗi tải danh sách'], ['empty', 'Danh sách trống'], ['loading', 'Đang tải'], ['after-commit', 'Mất phản hồi sau đăng ký → thử lại'], ['expired', 'Phiên đăng nhập hết hạn ở lần gọi tiếp theo']].map(([v, label]) => `<option value="${v}"${api.demo.getScenario() === v ? ' selected' : ''}>${label}</option>`).join('')}</select></label><button class="button primary full" type="button" data-action="apply-scenario">Áp dụng tình huống</button><hr class="demo-divider"><div class="demo-options"><button class="button secondary" type="button" data-action="login">Đổi tài khoản mẫu</button><button class="button danger" type="button" data-action="ask-reset">Đặt lại dữ liệu bản mẫu</button></div><p class="demo-caption" style="margin-top:18px">Bản mẫu chạy trong một trình duyệt. Kiểm thử đồng thời 100 yêu cầu và xác thực thật thuộc phần backend/cloud, chưa được chứng minh ở đây.</p>`);
  }
  async function exportCsv() {
    const eventId = currentEvent?.id; if (!eventId) return;
    const result = await api.exportRoster(eventId);
    const blob = new Blob([result.csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = `campus-${eventId}-roster.csv`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000); toast(`Đã xuất danh sách ${result.count} sinh viên.`);
  }
  async function renderRoute() {
    const version = ++renderVersion; if (dialog.open && !submitBusy) dialog.close();
    $('#main-nav').classList.remove('open'); $('#menu-toggle').setAttribute('aria-expanded', 'false'); header();
    const path = routeInfo().pathname;
    document.title = path.startsWith('/students') ? 'Quản lý sinh viên — Campus' : path.startsWith('/organizer') ? 'Quản lý sự kiện — Campus' : path === '/bookings' ? 'Đăng ký của tôi — Campus' : 'Campus — Sự kiện đại học';
    try {
      if (path === '/events' || path === '/') await renderCatalog(version);
      else if (/^\/events\/[^/]+$/.test(path)) await renderDetail(decodeURIComponent(path.split('/')[2]), version);
      else if (path === '/bookings') await renderBookings(version);
      else if (/^\/receipt\/[^/]+$/.test(path)) await renderReceipt(decodeURIComponent(path.split('/')[2]), version);
      else if (path === '/organizer') await renderOrganizer(version);
      else if (path === '/students') await renderStudents(version);
      else throw new api.ApiError('Đường dẫn này chưa có trong bản mẫu.', 404, 'NOT_FOUND');
    } catch (err) {
      if (version !== renderVersion) return; header();
      setMain(`<div class="container page-shell">${emptyState(err.status === 401 ? 'Đăng nhập để tiếp tục' : err.status === 403 ? 'Bạn chưa có quyền truy cập' : err.status === 404 ? 'Không tìm thấy nội dung' : 'Có chút gián đoạn', err.message || 'Vui lòng thử lại sau.', err.status === 401 ? '<button class="button primary" type="button" data-action="login">Đăng nhập</button>' : '<a class="button secondary" href="#/events">Về trang sự kiện</a>', err.status === 403 ? 'shield' : 'alert')}</div>`, version);
    }
  }
  document.addEventListener('click', async event => {
    const link = event.target.closest('.skip-link'); if (link) { event.preventDefault(); main.focus(); return; }
    const target = event.target.closest('[data-action]'); if (!target || target.disabled) return;
    const action = target.dataset.action;
    try {
      if (action === 'login') openLogin();
      else if (action === 'signup') openSignup();
      else if (action === 'account-signup') openSignup(loginCallback);
      else if (action === 'account-login') openLogin(loginCallback);
      else if (action === 'account') openAccount();
      else if (action === 'change-password') openChangePassword();
      else if (action === 'close-dialog') { if (!submitBusy) dialog.close(); }
      else if (action === 'choose-user') { await api.session.signOut(); api.session.login(target.dataset.user); dialog.close(); const callback = loginCallback; loginCallback = null; header(); if (callback) await callback(); else renderRoute(); }
      else if (action === 'logout') { await api.session.signOut(); dialog.close(); toast('Bạn đã đăng xuất.'); renderRoute(); }
      else if (action === 'real-login') await api.session.signIn();
      else if (action === 'create-event') openPublishEvent();
      else if (action === 'edit-event') openEditEvent();
      else if (action === 'delete-event') openDeleteEvent();
      else if (action === 'confirm-delete-event') { await api.admin.deleteEvent(target.dataset.event); dialog.close(); toast('Đã xóa sự kiện.'); go('/organizer'); }
      else if (action === 'add-to-event') await openAddToEvent();
      else if (action === 'remove-from-event') openRemoveFromEvent(target.dataset.booking);
      else if (action === 'confirm-remove-from-event') { await api.admin.removeRegistration(target.dataset.booking); dialog.close(); toast('Đã gỡ sinh viên khỏi sự kiện và hoàn lại 1 chỗ.'); await renderRoute(); }
      else if (action === 'create-student') openStudentForm();
      else if (action === 'edit-student') openStudentForm(target.dataset.student);
      else if (action === 'delete-student') openDeleteStudent(target.dataset.student);
      else if (action === 'confirm-delete-student') { await api.admin.deleteStudent(target.dataset.student); dialog.close(); toast('Đã xóa tài khoản sinh viên.'); await renderRoute(); }
      else if (action === 'publish-event') await publishEvent();
      else if (action === 'category') { view.category = target.dataset.category; document.querySelectorAll('[data-action="category"]').forEach(button => { const active = button.dataset.category === view.category; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); }); renderResults(); }
      else if (action === 'clear-filters') { Object.assign(view, { category: 'Tất cả', search: '', available: false }); renderRoute(); }
      else if (action === 'reload') { if (config.mode === 'mock') api.demo.setScenario('normal'); renderRoute(); }
      else if (action === 'register') await openRegister(target.dataset.event);
      else if (action === 'cancel') openCancel(target.dataset.booking);
      else if (action === 'submit-registration' || action === 'submit-cancellation') await submitAction();
      else if (action === 'booking-tab') { view.bookingTab = target.dataset.value; renderRoute(); }
      else if (action === 'export-csv') await exportCsv();
      else if (action === 'show-bookings') { dialog.close(); go('/bookings'); }
      else if (action === 'reload-detail') { dialog.close(); renderRoute(); }
      else if (action === 'apply-scenario') { const scenario = $('#demo-scenario').value; api.demo.setScenario(scenario); dialog.close(); toast('Đã áp dụng tình huống bản mẫu.'); if (scenario === 'expired') renderRoute(); else go('/events'); }
      else if (action === 'ask-reset') showDialog('Đặt lại bản mẫu?', '<p>Xóa các đăng ký mẫu và tài khoản đang chọn trong trình duyệt này. Dữ liệu của ứng dụng khác không bị ảnh hưởng.</p><div class="dialog-actions"><button class="button secondary" type="button" data-action="close-dialog">Giữ dữ liệu</button><button class="button danger" type="button" data-action="reset-demo">Đặt lại dữ liệu</button></div>');
      else if (action === 'reset-demo') { api.demo.reset(); pending.clear(); persistPending(); view.bookingTab = 'all'; dialog.close(); toast('Đã đặt lại dữ liệu bản mẫu.'); go('/events'); }
    } catch (err) { toast(err.message || 'Chưa hoàn tất thao tác. Vui lòng thử lại.', true); }
  });
  document.addEventListener('submit', event => {
    if (['account-signup-form','account-login-form'].includes(event.target.id)) { event.preventDefault(); submitAccountForm(event.target); }
    else if (event.target.id === 'change-password-form') { event.preventDefault(); submitChangePassword(event.target); }
    else if (event.target.id === 'admin-student-form') { event.preventDefault(); submitStudentForm(event.target); }
    else if (event.target.id === 'admin-add-to-event-form') { event.preventDefault(); submitAddToEvent(event.target); }
  });
  document.addEventListener('input', event => {
    if (event.target.id === 'event-search') { view.search = event.target.value; renderResults(); }
    else if (event.target.id === 'roster-search') { view.rosterSearch = event.target.value; renderRosterRows(); }
    else if (event.target.id === 'student-search') { view.studentSearch = event.target.value; renderStudentRows(); }
    else if (event.target.id === 'add-student-filter' && dialog._availableStudents) {
      const q = event.target.value.trim().toLocaleLowerCase('vi');
      const matches = dialog._availableStudents.filter(s => `${s.studentId} ${s.name} ${s.email}`.toLocaleLowerCase('vi').includes(q));
      $('#add-student-select').innerHTML = matches.length ? matches.map(s => `<option value="${esc(s.id)}">${esc(s.studentId)} · ${esc(s.name)} (${esc(s.email)})</option>`).join('') : '<option value="">Không tìm thấy sinh viên phù hợp</option>';
    }
    else if (event.target.id === 'publish-description' && $('#publish-event-form').dataset.linkedDescription === 'true') $('#publish-about').value = event.target.value;
    else if (event.target.id === 'publish-about') $('#publish-event-form').dataset.linkedDescription = 'false';
  });
  document.addEventListener('change', event => {
    if (event.target.id === 'event-sort') { view.sort = event.target.value; renderResults(); }
    else if (event.target.id === 'available-only') { view.available = event.target.checked; renderResults(); }
    else if (event.target.id === 'organizer-event') { view.rosterSearch = ''; go(`/organizer?event=${encodeURIComponent(event.target.value)}`); }
  });
  $('#menu-toggle').addEventListener('click', () => { const open = $('#main-nav').classList.toggle('open'); $('#menu-toggle').setAttribute('aria-expanded', String(open)); });
  $('#demo-tools').addEventListener('click', openDemo);
  dialog.addEventListener('cancel', event => { if (submitBusy) event.preventDefault(); });
  dialog.addEventListener('click', event => { if (event.target !== dialog || submitBusy) return; const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); });
  let authReady = false;
  window.addEventListener('hashchange', () => { if (!authReady) return; window.scrollTo(0, 0); renderRoute(); main.focus({ preventScroll: true }); });
  window.addEventListener('storage', event => { if (event.key?.startsWith('campus-demo-') && !dialog.open) renderRoute(); });
  window.CampusAuth.ready.then(() => api.session.restore()).then(() => {
    authReady = true;
    if (!location.hash || location.hash === '#main') location.hash = '/events'; else renderRoute();
  }).catch(() => {
    authReady = true;
    main.textContent = 'Không thể khởi tạo đăng nhập. Hãy tải lại trang hoặc liên hệ quản trị viên.';
  });
}());
