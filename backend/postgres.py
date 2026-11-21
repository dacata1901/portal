"""PostgreSQL persistence for the hosted deployment."""
import hashlib
import json
import uuid
import os
import threading
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

DatabaseError = psycopg.Error
OperationalError = psycopg.OperationalError

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        student_id TEXT UNIQUE,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('student','organizer','administrator'))
    )""",
    """CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        starts_at TEXT NOT NULL,
        capacity INTEGER NOT NULL CHECK (capacity >= 0),
        metadata TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS registrations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id),
        event_id TEXT NOT NULL REFERENCES events(id),
        status TEXT NOT NULL CHECK (status IN ('active','cancelled')),
        created_at TEXT NOT NULL,
        cancelled_at TEXT
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS one_active
        ON registrations(user_id,event_id) WHERE status='active'""",
    """CREATE TABLE IF NOT EXISTS idempotency_records (
        user_id TEXT NOT NULL REFERENCES users(id),
        operation TEXT NOT NULL,
        request_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        http_status INTEGER NOT NULL,
        response TEXT NOT NULL,
        PRIMARY KEY(user_id,operation,request_id)
    )""",
    """CREATE OR REPLACE FUNCTION campus_check_registration_capacity()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE event_capacity INTEGER;
        BEGIN
            IF NEW.status = 'active' THEN
                SELECT capacity INTO event_capacity FROM events
                WHERE id = NEW.event_id FOR UPDATE;
                IF event_capacity IS NULL OR
                    (SELECT COUNT(*) FROM registrations
                     WHERE event_id = NEW.event_id AND status = 'active'
                       AND id IS DISTINCT FROM NEW.id) >= event_capacity THEN
                    RAISE EXCEPTION 'capacity exceeded'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END
        $$""",
    """DROP TRIGGER IF EXISTS capacity_insert ON registrations""",
    """CREATE TRIGGER capacity_insert
        BEFORE INSERT ON registrations FOR EACH ROW
        EXECUTE FUNCTION campus_check_registration_capacity()""",
    """DROP TRIGGER IF EXISTS capacity_update ON registrations""",
    """CREATE TRIGGER capacity_update
        BEFORE UPDATE OF status,event_id ON registrations FOR EACH ROW
        EXECUTE FUNCTION campus_check_registration_capacity()""",
    """CREATE OR REPLACE FUNCTION campus_check_capacity_reduction()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.capacity < (SELECT COUNT(*) FROM registrations
                               WHERE event_id = OLD.id AND status = 'active') THEN
                RAISE EXCEPTION 'capacity below registrations'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$""",
    """DROP TRIGGER IF EXISTS capacity_reduce ON events""",
    """CREATE TRIGGER capacity_reduce
        BEFORE UPDATE OF capacity ON events FOR EACH ROW
        EXECUTE FUNCTION campus_check_capacity_reduction()""",
)


_slots=threading.BoundedSemaphore(int(os.environ.get('PORTAL_DB_MAX_CONNECTIONS','12')))

class LimitedConnection(psycopg.Connection):
    def close(self):
        if not getattr(self,'_slot_released',False):
            self._slot_released=True
            try:super().close()
            finally:_slots.release()

def connect(dsn):
    if not _slots.acquire(timeout=20):raise OperationalError('Database concurrency limit reached')
    try:
        return LimitedConnection.connect(dsn,row_factory=dict_row,autocommit=True,connect_timeout=5,
                                         options='-c statement_timeout=15000 -c lock_timeout=10000')
    except Exception:
        _slots.release();raise


def migrate(dsn):
    with connect(dsn) as c:
        with c.transaction():
            c.execute("SELECT pg_advisory_xact_lock(7403921)")
            for statement in SCHEMA:
                c.execute(statement)


def seed(dsn):
    from backend.db import ROOT

    data = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))
    with connect(dsn) as c:
        c.execute("BEGIN")
        try:
            for user in data["users"]:
                c.execute(
                    """INSERT INTO users VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING""",
                    (user["id"], user.get("studentId"), user["name"], user["email"], user["role"]),
                )
            for item in data["events"]:
                c.execute(
                    """INSERT INTO events VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING""",
                    (item["id"], item["title"], item["startsAt"], item["capacity"],
                     json.dumps(item, ensure_ascii=False)),
                )
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise


def event(c, event_id):
    # One statement means capacity and occupancy share the same MVCC snapshot,
    # including when callers use READ COMMITTED and another transaction edits
    # the capacity while a student books the newly available place.
    row = c.execute(
        """SELECT e.*,
           (SELECT COUNT(*) FROM registrations r
            WHERE r.event_id=e.id AND r.status='active') AS active_count
           FROM events e WHERE e.id=%s""", (event_id,)
    ).fetchone()
    if not row:
        return None
    count = row['active_count']
    return dict(json.loads(row["metadata"]), title=row["name"], startsAt=row["starts_at"],
                capacity=row["capacity"], registeredCount=count,
                remainingCapacity=row["capacity"] - count)


def booking(c, booking_id):
    row = c.execute(
        """SELECT r.*,u.student_id,u.name,u.email FROM registrations r
           JOIN users u ON u.id=r.user_id WHERE r.id=%s""",
        (booking_id,),
    ).fetchone()
    if not row:
        return None
    return dict(id=row["id"], eventId=row["event_id"], userId=row["user_id"],
                studentId=row["student_id"], name=row["name"], email=row["email"],
                status=row["status"], createdAt=row["created_at"],
                cancelledAt=row["cancelled_at"])


def _lock_request(c, user_id, operation, request_id):
    # PostgreSQL text cannot contain NUL. JSON also prevents ambiguous scopes.
    scope = json.dumps([user_id,operation,request_id],separators=(',',':'))
    c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (scope,))


def _existing_request(c, user_id, operation, key, fingerprint):
    old = c.execute(
        """SELECT fingerprint,http_status,response FROM idempotency_records
           WHERE user_id=%s AND operation=%s AND request_id=%s""",
        (user_id, operation, key),
    ).fetchone()
    if not old:
        return None
    if old["fingerprint"] != fingerprint:
        return 409, dict(code="IDEMPOTENCY_CONFLICT",
                         message="Khóa đã dùng cho nội dung khác"), False
    return old["http_status"], json.loads(old["response"]), True


def _save_request(c, user_id, operation, key, fingerprint, status, result):
    c.execute(
        """INSERT INTO idempotency_records
           (user_id,operation,request_id,fingerprint,http_status,response)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (user_id, operation, key, fingerprint, status,
         json.dumps(result, ensure_ascii=False)),
    )


def mutate(dsn, user_id, operation, target, key, payload, fail_before_commit=False):
    if not isinstance(key, str) or not 1 <= len(key) <= 128:
        return 400, dict(code="INVALID_REQUEST_ID", message="Request ID phải dài 1–128 ký tự"), False
    fingerprint = hashlib.sha256(
        json.dumps([target, payload], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with connect(dsn) as c:
        c.execute("BEGIN")
        try:
            _lock_request(c, user_id, operation, key)
            user = c.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
            if not user:
                c.execute("ROLLBACK")
                return 401, dict(code="UNAUTHENTICATED", message="Tài khoản mẫu không hợp lệ"), False
            existing = _existing_request(c, user_id, operation, key, fingerprint)
            if existing:
                c.execute("COMMIT")
                return existing
            status, result, booking_id = 200, None, None
            if user["role"] != "student":
                status, result = 403, dict(code="STUDENT_REQUIRED", message="Chỉ sinh viên được đăng ký/hủy")
            elif operation == "register":
                locked = c.execute("SELECT id FROM events WHERE id=%s FOR UPDATE", (target,)).fetchone()
                current = event(c, target) if locked else None
                if not current:
                    status, result = 404, dict(code="EVENT_NOT_FOUND", message="Không tìm thấy sự kiện")
                elif c.execute(
                    """SELECT 1 FROM registrations WHERE user_id=%s AND event_id=%s
                       AND status='active'""", (user_id, target)
                ).fetchone():
                    status, result = 409, dict(code="ALREADY_REGISTERED", message="Bạn đã đăng ký sự kiện")
                elif current["remainingCapacity"] <= 0:
                    status, result = 409, dict(code="EVENT_FULL", message="Sự kiện hết chỗ")
                else:
                    booking_id = "CP-" + uuid.uuid4().hex
                    c.execute(
                        """INSERT INTO registrations
                           (id,user_id,event_id,status,created_at,cancelled_at)
                           VALUES (%s,%s,%s,'active',%s,NULL)""",
                        (booking_id, user_id, target, datetime.now(timezone.utc).isoformat()),
                    )
                    status = 201
            else:
                current_booking = c.execute(
                    "SELECT id,user_id,event_id,status FROM registrations WHERE id=%s FOR UPDATE",
                    (target,),
                ).fetchone()
                if not current_booking or current_booking["user_id"] != user_id:
                    status, result = 404, dict(code="BOOKING_NOT_FOUND", message="Không tìm thấy đăng ký của bạn")
                else:
                    booking_id = target
                    c.execute(
                        """UPDATE registrations SET status='cancelled',cancelled_at=%s
                           WHERE id=%s AND status='active'""",
                        (datetime.now(timezone.utc).isoformat(), booking_id),
                    )
            if result is None:
                receipt = booking(c, booking_id)
                result = dict(booking=receipt, remainingCapacity=event(c, receipt["eventId"])["remainingCapacity"],
                              requestId=key, replayed=False)
            _save_request(c, user_id, operation, key, fingerprint, status, result)
            if fail_before_commit:
                raise RuntimeError("Injected failure before commit")
            c.execute("COMMIT")
            return status, result, False
        except Exception:
            if not c.closed:
                c.execute("ROLLBACK")
            raise


def publish_event(dsn, user_id, key, payload):
    if not isinstance(key, str) or not 1 <= len(key) <= 128:
        return 400, dict(code="INVALID_REQUEST_ID", message="Request ID phải dài 1–128 ký tự"), False
    if not isinstance(payload, dict):
        return 400, dict(code="INVALID_PAYLOAD", message="Dữ liệu sự kiện không hợp lệ"), False
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with connect(dsn) as c:
        c.execute("BEGIN")
        try:
            _lock_request(c, user_id, "publish", key)
            user = c.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
            if not user:
                c.execute("ROLLBACK")
                return 401, dict(code="UNAUTHENTICATED", message="Vui lòng đăng nhập"), False
            existing = _existing_request(c, user_id, "publish", key, fingerprint)
            if existing:
                c.execute("COMMIT")
                return existing
            status, result = 201, None
            if user["role"] not in ("organizer", "administrator"):
                status, result = 403, dict(code="ORGANIZER_REQUIRED", message="Chỉ ban tổ chức được xuất bản sự kiện", requestId=key)
            else:
                title = payload.get("title")
                starts_at = payload.get("startsAt")
                capacity = payload.get("capacity")
                venue = payload.get("venue", "")
                category = payload.get("category", "Công nghệ")
                format_name = payload.get("format", "Workshop")
                description = payload.get("description", "")
                if not isinstance(title, str) or not title.strip() or len(title.strip()) > 140:
                    status, result = 400, dict(code="INVALID_TITLE", message="Tên sự kiện phải có từ 1 đến 140 ký tự", requestId=key)
                else:
                    try:
                        parsed = datetime.fromisoformat(starts_at.replace("Z", "+00:00")) if isinstance(starts_at, str) else None
                        if parsed is None or parsed.tzinfo is None:
                            raise ValueError()
                        starts_at = parsed.isoformat()
                    except ValueError:
                        status, result = 400, dict(code="INVALID_START_TIME", message="Thời gian bắt đầu phải có múi giờ ISO-8601", requestId=key)
                if status == 201 and (type(capacity) is not int or not 1 <= capacity <= 100000):
                    status, result = 400, dict(code="INVALID_CAPACITY", message="Sức chứa phải từ 1 đến 100000 chỗ", requestId=key)
                if status == 201 and (not isinstance(venue, str) or len(venue.strip()) > 160):
                    status, result = 400, dict(code="INVALID_VENUE", message="Địa điểm không được vượt quá 160 ký tự", requestId=key)
                if status == 201 and category not in ("Công nghệ", "Kỹ năng", "Văn hóa", "Cộng đồng"):
                    status, result = 400, dict(code="INVALID_CATEGORY", message="Chủ đề sự kiện không hợp lệ", requestId=key)
                if status == 201 and format_name not in ("Workshop", "Talkshow", "Hackathon", "Giao lưu", "Hoạt động"):
                    status, result = 400, dict(code="INVALID_FORMAT", message="Hình thức sự kiện không hợp lệ", requestId=key)
                if status == 201 and (not isinstance(description, str) or len(description.strip()) > 400):
                    status, result = 400, dict(code="INVALID_DESCRIPTION", message="Mô tả không được vượt quá 400 ký tự", requestId=key)
                if status == 201:
                    event_id = "event-" + uuid.uuid4().hex[:16]
                    metadata = dict(
                        id=event_id, title=title.strip(), category=category, format=format_name,
                        startsAt=starts_at, endsAt=starts_at, venue=venue.strip() or "Sẽ được ban tổ chức cập nhật",
                        capacity=capacity, baseRegistered=0, organizerId=user_id, organizer=user["name"],
                        theme="cloud", artwork=["CAMPUS", "EVENT."],
                        description=description.strip() or "Thông tin chi tiết sẽ được ban tổ chức cập nhật.",
                        about=description.strip(), agenda=[], note="Thông tin do ban tổ chức cập nhật.",
                        speaker=user["name"],
                    )
                    c.execute(
                        "INSERT INTO events VALUES (%s,%s,%s,%s,%s)",
                        (event_id, title.strip(), starts_at, capacity, json.dumps(metadata, ensure_ascii=False)),
                    )
                    result = dict(event=event(c, event_id), requestId=key, replayed=False)
            _save_request(c, user_id, "publish", key, fingerprint, status, result)
            c.execute("COMMIT")
            return status, result, False
        except Exception:
            if not c.closed:
                c.execute("ROLLBACK")
            raise


def audit(dsn):
    with connect(dsn) as c:
        rows = c.execute(
            """SELECT e.id,e.capacity,COUNT(r.id) FILTER (WHERE r.status='active') AS active,
               e.capacity-COUNT(r.id) FILTER (WHERE r.status='active') AS remaining
               FROM events e LEFT JOIN registrations r ON r.event_id=e.id
               GROUP BY e.id"""
        ).fetchall()
        duplicates = c.execute(
            """SELECT user_id,event_id,COUNT(*) AS n FROM registrations
               WHERE status='active' GROUP BY user_id,event_id HAVING COUNT(*)>1"""
        ).fetchall()
        return dict(ok=not duplicates and all(0 <= row["remaining"] <= row["capacity"] for row in rows),
                    events=rows, duplicates=duplicates, foreignKeys=[])
