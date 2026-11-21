import sqlite3, json, uuid, hashlib
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parent.parent
DatabaseError=sqlite3.Error
OperationalError=sqlite3.OperationalError

class ObservedConnection(sqlite3.Connection):
    def close(self):
        if not getattr(self,'_observed_closed',False):
            self._observed_closed=True
            from backend.telemetry import connection_delta
            connection_delta(-1)
        super().close()

def connect(path):
    c=sqlite3.connect(path, timeout=15, isolation_level=None,factory=ObservedConnection)
    from backend.telemetry import connection_delta
    connection_delta(1)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=15000')
    return c

def migrate(path):
    c=connect(path)
    try:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript((ROOT/'backend/001_schema.sql').read_text(encoding='utf-8'))
    finally: c.close()

def seed(path):
    d=json.loads((ROOT/'fixtures.json').read_text(encoding='utf-8'))
    c=connect(path)
    try:
        c.execute('BEGIN IMMEDIATE')
        for u in d['users']:
            c.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?,?)',(u['id'],u.get('studentId'),u['name'],u['email'],u['role']))
        for e in d['events']:
            c.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)',(e['id'],e['title'],e['startsAt'],e['capacity'],json.dumps(e)))
        c.commit()
    except: c.rollback(); raise
    finally: c.close()

def event(c,id):
    e=c.execute('SELECT * FROM events WHERE id=?',(id,)).fetchone()
    if not e: return None
    n=c.execute("SELECT COUNT(*) FROM registrations WHERE event_id=? AND status='active'",(id,)).fetchone()[0]
    return dict(json.loads(e['metadata']),title=e['name'],startsAt=e['starts_at'],capacity=e['capacity'],registeredCount=n,remainingCapacity=e['capacity']-n)

def booking(c,id):
    b=c.execute('SELECT r.*,u.student_id,u.name,u.email FROM registrations r JOIN users u ON u.id=r.user_id WHERE r.id=?',(id,)).fetchone()
    return None if not b else dict(id=b['id'],eventId=b['event_id'],userId=b['user_id'],studentId=b['student_id'],name=b['name'],email=b['email'],status=b['status'],createdAt=b['created_at'],cancelledAt=b['cancelled_at'])

def mutate(path,user,operation,target,key,payload,fail_before_commit=False):
    if not isinstance(key,str) or not 1<=len(key)<=128: return 400,dict(code='INVALID_REQUEST_ID',message='Request ID phải dài 1–128 ký tự'),False
    fp=hashlib.sha256(json.dumps([target,payload],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    c=connect(path)
    try:
        c.execute('BEGIN IMMEDIATE')
        u=c.execute('SELECT * FROM users WHERE id=?',(user,)).fetchone()
        if not u: c.rollback(); return 401,dict(code='UNAUTHENTICATED',message='Tài khoản mẫu không hợp lệ'),False
        old=c.execute('SELECT * FROM idempotency_records WHERE user_id=? AND operation=? AND request_id=?',(user,operation,key)).fetchone()
        if old:
            c.commit()
            if old['fingerprint']!=fp: return 409,dict(code='IDEMPOTENCY_CONFLICT',message='Khóa đã dùng cho nội dung khác'),False
            return old['http_status'],json.loads(old['response']),True
        status=200; result=None
        def error(s,code,msg): return s,dict(code=code,message=msg,requestId=key)
        if u['role']!='student': status,result=error(403,'STUDENT_REQUIRED','Chỉ sinh viên được đăng ký/hủy')
        elif operation=='register':
            e=event(c,target)
            if not e: status,result=error(404,'EVENT_NOT_FOUND','Không tìm thấy sự kiện')
            elif c.execute("SELECT 1 FROM registrations WHERE user_id=? AND event_id=? AND status='active'",(user,target)).fetchone(): status,result=error(409,'ALREADY_REGISTERED','Bạn đã đăng ký sự kiện')
            elif e['remainingCapacity']<=0: status,result=error(409,'EVENT_FULL','Sự kiện hết chỗ')
            else:
                bid='CP-'+uuid.uuid4().hex
                c.execute('INSERT INTO registrations VALUES(?,?,?,?,?,NULL)',(bid,user,target,'active',datetime.now(timezone.utc).isoformat()))
                status=201
        else:
            b=booking(c,target)
            if not b or b['userId']!=user: status,result=error(404,'BOOKING_NOT_FOUND','Không tìm thấy đăng ký của bạn')
            else:
                bid=target
                c.execute("UPDATE registrations SET status='cancelled',cancelled_at=? WHERE id=? AND status='active'",(datetime.now(timezone.utc).isoformat(),bid))
        if result is None:
            b=booking(c,bid)
            result=dict(booking=b,remainingCapacity=event(c,b['eventId'])['remainingCapacity'],requestId=key,replayed=False)
        c.execute('INSERT INTO idempotency_records VALUES(?,?,?,?,?,?)',(user,operation,key,fp,status,json.dumps(result)))
        if fail_before_commit: raise RuntimeError('Injected failure before commit')
        c.commit()
        return status,result,False
    except: c.rollback(); raise
    finally: c.close()

def publish_event(path,user,key,payload):
    if not isinstance(key,str) or not 1<=len(key)<=128:
        return 400,dict(code='INVALID_REQUEST_ID',message='Request ID phải dài 1–128 ký tự'),False
    if not isinstance(payload,dict):
        return 400,dict(code='INVALID_PAYLOAD',message='Dữ liệu sự kiện không hợp lệ'),False
    fp=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    c=connect(path)
    try:
        c.execute('BEGIN IMMEDIATE')
        u=c.execute('SELECT * FROM users WHERE id=?',(user,)).fetchone()
        if not u:
            c.rollback()
            return 401,dict(code='UNAUTHENTICATED',message='Vui lòng đăng nhập'),False
        old=c.execute('SELECT * FROM idempotency_records WHERE user_id=? AND operation=? AND request_id=?',(user,'publish',key)).fetchone()
        if old:
            c.commit()
            if old['fingerprint']!=fp:
                return 409,dict(code='IDEMPOTENCY_CONFLICT',message='Khóa đã dùng cho nội dung khác'),False
            return old['http_status'],json.loads(old['response']),True

        status=201
        result=None
        if u['role'] not in ('organizer','administrator'):
            status=403
            result=dict(code='ORGANIZER_REQUIRED',message='Chỉ ban tổ chức được xuất bản sự kiện',requestId=key)
        else:
            title=payload.get('title')
            starts_at=payload.get('startsAt')
            capacity=payload.get('capacity')
            venue=payload.get('venue','')
            category=payload.get('category','Công nghệ')
            format=payload.get('format','Workshop')
            description=payload.get('description','')
            if not isinstance(title,str) or not title.strip() or len(title.strip())>140:
                status=400
                result=dict(code='INVALID_TITLE',message='Tên sự kiện phải có từ 1 đến 140 ký tự',requestId=key)
            elif not isinstance(starts_at,str) or len(starts_at)>64:
                status=400
                result=dict(code='INVALID_START_TIME',message='Thời gian bắt đầu không hợp lệ',requestId=key)
            else:
                try:
                    parsed=datetime.fromisoformat(starts_at.replace('Z','+00:00'))
                    if parsed.tzinfo is None: raise ValueError()
                    starts_at=parsed.isoformat()
                except ValueError:
                    status=400
                    result=dict(code='INVALID_START_TIME',message='Thời gian bắt đầu phải có múi giờ ISO-8601',requestId=key)
            if status==201 and (type(capacity) is not int or not 1<=capacity<=100000):
                status=400
                result=dict(code='INVALID_CAPACITY',message='Sức chứa phải từ 1 đến 100000 chỗ',requestId=key)
            if status==201 and (not isinstance(venue,str) or len(venue.strip())>160):
                status=400
                result=dict(code='INVALID_VENUE',message='Địa điểm không được vượt quá 160 ký tự',requestId=key)
            if status==201 and category not in ('Công nghệ','Kỹ năng','Văn hóa','Cộng đồng'):
                status=400
                result=dict(code='INVALID_CATEGORY',message='Chủ đề sự kiện không hợp lệ',requestId=key)
            if status==201 and format not in ('Workshop','Talkshow','Hackathon','Giao lưu','Hoạt động'):
                status=400
                result=dict(code='INVALID_FORMAT',message='Hình thức sự kiện không hợp lệ',requestId=key)
            if status==201 and (not isinstance(description,str) or len(description.strip())>400):
                status=400
                result=dict(code='INVALID_DESCRIPTION',message='Mô tả không được vượt quá 400 ký tự',requestId=key)
            if status==201:
                event_id='event-'+uuid.uuid4().hex[:16]
                metadata=dict(
                    id=event_id,title=title.strip(),category=category,format=format,
                    startsAt=starts_at,endsAt=starts_at,venue=venue.strip() or 'Sẽ được ban tổ chức cập nhật',
                    capacity=capacity,baseRegistered=0,organizerId=user,organizer=u['name'],
                    theme='cloud',artwork=['CAMPUS','EVENT.'],
                    description=description.strip() or 'Thông tin chi tiết sẽ được ban tổ chức cập nhật.',
                    about=description.strip(),agenda=[],note='Thông tin do ban tổ chức cập nhật.',
                    speaker=u['name']
                )
                c.execute('INSERT INTO events VALUES(?,?,?,?,?)',(event_id,title.strip(),starts_at,capacity,json.dumps(metadata,ensure_ascii=False)))
                result=dict(event=event(c,event_id),requestId=key,replayed=False)

        c.execute('INSERT INTO idempotency_records VALUES(?,?,?,?,?,?)',(user,'publish',key,fp,status,json.dumps(result,ensure_ascii=False)))
        c.commit()
        return status,result,False
    except:
        c.rollback()
        raise
    finally: c.close()

def audit(path):
    c=connect(path)
    try:
        rows=c.execute("SELECT e.id,e.capacity,COUNT(r.id) active,e.capacity-COUNT(r.id) remaining FROM events e LEFT JOIN registrations r ON r.event_id=e.id AND r.status='active' GROUP BY e.id").fetchall()
        duplicates=c.execute("SELECT user_id,event_id,COUNT(*) n FROM registrations WHERE status='active' GROUP BY user_id,event_id HAVING COUNT(*)>1").fetchall()
        return dict(ok=not duplicates and all(0<=r['remaining']<=r['capacity'] for r in rows),events=[dict(r) for r in rows],duplicates=[dict(r) for r in duplicates],foreignKeys=[tuple(r) for r in c.execute('PRAGMA foreign_key_check')])
    finally: c.close()
