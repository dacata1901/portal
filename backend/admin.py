"""Administrator management helpers for university students, events, and event rosters."""
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone

from backend.account_validation import normalize_email
from backend.accounts import AccountError, AccountStore, password_hash


def _begin(conn, p):
    conn.execute('BEGIN IMMEDIATE' if p == '?' else 'BEGIN')


def _validate_student_fields(payload, require_password=True):
    if not isinstance(payload, dict):
        raise AccountError(400, 'INVALID_ACCOUNT', 'Thông tin sinh viên không hợp lệ.')
    allowed = {'name', 'studentId', 'email', 'password'}
    if not set(payload).issubset(allowed) or not {'name', 'studentId', 'email'}.issubset(payload):
        raise AccountError(400, 'INVALID_ACCOUNT', 'Vui lòng nhập đầy đủ họ tên, mã sinh viên và email.')
    for key in ('name', 'studentId', 'email'):
        if not isinstance(payload[key], str):
            raise AccountError(400, 'INVALID_ACCOUNT', 'Thông tin sinh viên không hợp lệ.')
    name = ' '.join(unicodedata.normalize('NFKC', payload['name']).split())
    student_id = unicodedata.normalize('NFKC', payload['studentId']).strip().upper()
    email = payload['email'].strip().lower()
    if not 2 <= len(name) <= 100 or any(unicodedata.category(c).startswith('C') for c in name):
        raise AccountError(400, 'INVALID_NAME', 'Họ tên cần có từ 2 đến 100 ký tự.')
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{2,31}', student_id):
        raise AccountError(400, 'INVALID_STUDENT_ID', 'Mã sinh viên cần có 3–32 ký tự: chữ, số, dấu chấm, gạch ngang hoặc gạch dưới.')
    try:
        email = normalize_email(email)
    except ValueError as error:
        raise AccountError(400, 'INVALID_EMAIL', str(error)) from error
    password = payload.get('password', '')
    if password is None:
        password = ''
    if not isinstance(password, str):
        raise AccountError(400, 'INVALID_PASSWORD', 'Mật khẩu không hợp lệ.')
    if require_password or password:
        if not 12 <= len(password) <= 128 or not password.strip():
            raise AccountError(400, 'INVALID_PASSWORD', 'Mật khẩu cần có từ 12 đến 128 ký tự.')
    return name, student_id, email, password


def _student_row(conn, user_id, p='?'):
    row = conn.execute(
        f"SELECT u.id, u.student_id, u.name, u.email, u.role, "
        f"(SELECT COUNT(*) FROM registrations r WHERE r.user_id=u.id AND r.status='active') AS active_bookings "
        f"FROM users u WHERE u.id={p} AND u.role='student'",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    return dict(
        id=row['id'],
        studentId=row['student_id'],
        name=row['name'],
        email=row['email'],
        role=row['role'],
        activeBookings=row['active_bookings'],
    )


def list_students(database, target, p='?'):
    conn = database.connect(target)
    try:
        rows = conn.execute(
            "SELECT u.id, u.student_id, u.name, u.email, u.role, "
            "(SELECT COUNT(*) FROM registrations r WHERE r.user_id=u.id AND r.status='active') AS active_bookings "
            "FROM users u WHERE u.role='student' ORDER BY u.student_id, u.id"
        ).fetchall()
        return [
            dict(
                id=r['id'],
                studentId=r['student_id'],
                name=r['name'],
                email=r['email'],
                role=r['role'],
                activeBookings=r['active_bookings'],
            )
            for r in rows
        ]
    finally:
        conn.close()


def create_student(database, target, payload, p='?'):
    name, student_id, email, password = _validate_student_fields(payload, require_password=True)
    AccountStore(database, target, p).migrate()
    encoded = password_hash(password)
    conn = database.connect(target)
    try:
        _begin(conn, p)
        if p != '?':
            conn.execute('SELECT pg_advisory_xact_lock(67461020)')
        dup = conn.execute(
            f'SELECT id FROM users WHERE LOWER(email)={p} OR UPPER(student_id)={p}',
            (email, student_id),
        ).fetchone()
        if dup:
            raise AccountError(409, 'ACCOUNT_EXISTS', 'Email hoặc mã sinh viên đã tồn tại trong hệ thống.')
        user_id = 'local-' + uuid.uuid4().hex
        conn.execute(
            f'INSERT INTO users(id,student_id,name,email,role) VALUES({p},{p},{p},{p},{p})',
            (user_id, student_id, name, email, 'student'),
        )
        conn.execute(
            f'INSERT INTO account_credentials(user_id,email_key,student_key,password_hash,created_at) VALUES({p},{p},{p},{p},{p})',
            (user_id, email, student_id, encoded, int(time.time())),
        )
        conn.commit()
        return dict(id=user_id, studentId=student_id, name=name, email=email, role='student', activeBookings=0)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_student(database, target, user_id, payload, p='?'):
    name, student_id, email, password = _validate_student_fields(payload, require_password=False)
    AccountStore(database, target, p).migrate()
    encoded = password_hash(password) if password else None
    conn = database.connect(target)
    try:
        _begin(conn, p)
        if p != '?':
            conn.execute('SELECT pg_advisory_xact_lock(67461020)')
        existing = conn.execute(f"SELECT id FROM users WHERE id={p} AND role='student'", (user_id,)).fetchone()
        if not existing:
            raise AccountError(404, 'STUDENT_NOT_FOUND', 'Không tìm thấy sinh viên cần chỉnh sửa.')
        dup = conn.execute(
            f'SELECT id FROM users WHERE id<>{p} AND (LOWER(email)={p} OR UPPER(student_id)={p})',
            (user_id, email, student_id),
        ).fetchone()
        if dup:
            raise AccountError(409, 'ACCOUNT_EXISTS', 'Email hoặc mã sinh viên đã thuộc về tài khoản khác.')
        conn.execute(
            f'UPDATE users SET student_id={p}, name={p}, email={p} WHERE id={p}',
            (student_id, name, email, user_id),
        )
        cred = conn.execute(f'SELECT user_id FROM account_credentials WHERE user_id={p}', (user_id,)).fetchone()
        if cred:
            if encoded:
                conn.execute(
                    f'UPDATE account_credentials SET email_key={p}, student_key={p}, password_hash={p} WHERE user_id={p}',
                    (email, student_id, encoded, user_id),
                )
                conn.execute(f'DELETE FROM account_sessions WHERE user_id={p}', (user_id,))
            else:
                conn.execute(
                    f'UPDATE account_credentials SET email_key={p}, student_key={p} WHERE user_id={p}',
                    (email, student_id, user_id),
                )
        elif encoded:
            conn.execute(
                f'INSERT INTO account_credentials(user_id,email_key,student_key,password_hash,created_at) VALUES({p},{p},{p},{p},{p})',
                (user_id, email, student_id, encoded, int(time.time())),
            )
        updated = _student_row(conn, user_id, p)
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_student(database, target, user_id, p='?'):
    AccountStore(database, target, p).migrate()
    conn = database.connect(target)
    try:
        _begin(conn, p)
        existing = conn.execute(f"SELECT id FROM users WHERE id={p} AND role='student'", (user_id,)).fetchone()
        if not existing:
            raise AccountError(404, 'STUDENT_NOT_FOUND', 'Không tìm thấy sinh viên cần xóa.')
        conn.execute(f'DELETE FROM registrations WHERE user_id={p}', (user_id,))
        conn.execute(f'DELETE FROM idempotency_records WHERE user_id={p}', (user_id,))
        conn.execute(f'DELETE FROM account_sessions WHERE user_id={p}', (user_id,))
        conn.execute(f'DELETE FROM account_credentials WHERE user_id={p}', (user_id,))
        conn.execute(f'DELETE FROM users WHERE id={p}', (user_id,))
        conn.commit()
        return dict(deleted=True, userId=user_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_event(database, target, event_id, p='?'):
    conn = database.connect(target)
    try:
        _begin(conn, p)
        existing = conn.execute(f'SELECT id FROM events WHERE id={p}', (event_id,)).fetchone()
        if not existing:
            raise AccountError(404, 'EVENT_NOT_FOUND', 'Không tìm thấy sự kiện cần xóa.')
        conn.execute(f'DELETE FROM registrations WHERE event_id={p}', (event_id,))
        conn.execute(f'DELETE FROM events WHERE id={p}', (event_id,))
        conn.commit()
        return dict(deleted=True, eventId=event_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_student_to_event(database, target, event_id, user_id, p='?'):
    if not isinstance(user_id, str) or not user_id.strip():
        raise AccountError(400, 'INVALID_STUDENT', 'Vui lòng chọn sinh viên cần thêm vào sự kiện.')
    conn = database.connect(target)
    try:
        _begin(conn, p)
        e = database.event(conn, event_id)
        if not e:
            raise AccountError(404, 'EVENT_NOT_FOUND', 'Không tìm thấy sự kiện.')
        stu = conn.execute(f"SELECT id FROM users WHERE id={p} AND role='student'", (user_id,)).fetchone()
        if not stu:
            raise AccountError(404, 'STUDENT_NOT_FOUND', 'Không tìm thấy tài khoản sinh viên.')
        active = conn.execute(
            f"SELECT id FROM registrations WHERE user_id={p} AND event_id={p} AND status='active'",
            (user_id, event_id),
        ).fetchone()
        if active:
            raise AccountError(409, 'ALREADY_REGISTERED', 'Sinh viên này đã có mặt trong danh sách sự kiện.')
        if e['remainingCapacity'] <= 0:
            raise AccountError(409, 'EVENT_FULL', 'Sự kiện đã hết chỗ trống.')
        bid = 'CP-' + uuid.uuid4().hex
        conn.execute(
            f"INSERT INTO registrations(id,user_id,event_id,status,created_at,cancelled_at) VALUES({p},{p},{p},'active',{p},NULL)",
            (bid, user_id, event_id, datetime.now(timezone.utc).isoformat()),
        )
        booking_obj = database.booking(conn, bid)
        remaining = database.event(conn, event_id)['remainingCapacity']
        conn.commit()
        return dict(booking=booking_obj, remainingCapacity=remaining)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def remove_registration(database, target, booking_id, p='?'):
    conn = database.connect(target)
    try:
        _begin(conn, p)
        b = database.booking(conn, booking_id)
        if not b:
            raise AccountError(404, 'BOOKING_NOT_FOUND', 'Không tìm thấy đăng ký cần hủy.')
        conn.execute(
            f"UPDATE registrations SET status='cancelled', cancelled_at={p} WHERE id={p} AND status='active'",
            (datetime.now(timezone.utc).isoformat(), booking_id),
        )
        updated = database.booking(conn, booking_id)
        remaining = database.event(conn, b['eventId'])['remainingCapacity']
        conn.commit()
        return dict(booking=updated, remainingCapacity=remaining)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
