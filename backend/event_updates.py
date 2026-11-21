"""Shared event-edit rules; storage adapters retain their transaction semantics."""
import hashlib,json
from datetime import datetime

def validate(payload):
    if not isinstance(payload,dict):raise ValueError('Dữ liệu sự kiện không hợp lệ.')
    fields={k:payload.get(k) for k in ('title','startsAt','capacity','category','format','venue','description')}
    for name,limit in [('title',140),('venue',160),('description',400)]:
        if not isinstance(fields[name],str) or len(fields[name].strip())>limit or name=='title' and not fields[name].strip():raise ValueError('Tên, địa điểm hoặc mô tả không hợp lệ.')
        fields[name]=fields[name].strip()
    if 'about' in payload:
        if not isinstance(payload['about'],str) or len(payload['about'].strip())>10000:raise ValueError('Nội dung chi tiết không được vượt quá 10000 ký tự.')
        fields['about']=payload['about'].strip()
    if type(fields['capacity']) is not int or not 1<=fields['capacity']<=100000:raise ValueError('Sức chứa phải từ 1 đến 100000.')
    if fields['category'] not in ('Công nghệ','Kỹ năng','Văn hóa','Cộng đồng') or fields['format'] not in ('Workshop','Talkshow','Hackathon','Giao lưu','Hoạt động'):raise ValueError('Chủ đề hoặc hình thức không hợp lệ.')
    if not isinstance(fields['startsAt'],str) or len(fields['startsAt'])>64:raise ValueError('Thời gian không hợp lệ.')
    try:
        parsed=datetime.fromisoformat(fields['startsAt'].replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError()
        fields['startsAt']=parsed.isoformat()
    except ValueError:raise ValueError('Thời gian cần có múi giờ ISO-8601.') from None
    return fields

def update_event(database,target,user,event_id,key,payload,is_postgres=False):
    if not isinstance(key,str) or not 1<=len(key)<=128:return 400,dict(code='INVALID_REQUEST_ID',message='Request ID không hợp lệ'),False
    fp=hashlib.sha256(json.dumps([event_id,payload],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    p='%s' if is_postgres else '?';c=database.connect(target)
    try:
        c.execute('BEGIN' if is_postgres else 'BEGIN IMMEDIATE')
        if is_postgres:database._lock_request(c,user,'update-event',key)
        u=c.execute(f'SELECT role FROM users WHERE id={p}',(user,)).fetchone()
        if not u:c.rollback();return 401,dict(message='Vui lòng đăng nhập'),False
        old=c.execute(f'SELECT fingerprint,http_status,response FROM idempotency_records WHERE user_id={p} AND operation={p} AND request_id={p}',(user,'update-event',key)).fetchone()
        if old:
            c.commit()
            if old['fingerprint']!=fp:return 409,dict(code='IDEMPOTENCY_CONFLICT',message='Khóa đã dùng cho nội dung khác'),False
            return old['http_status'],json.loads(old['response']),True
        row=c.execute(f'SELECT id FROM events WHERE id={p}'+(' FOR UPDATE' if is_postgres else ''),(event_id,)).fetchone()
        e=database.event(c,event_id) if row else None
        status=200
        if not e:status,result=404,dict(code='EVENT_NOT_FOUND',message='Không tìm thấy sự kiện')
        elif not (u['role']=='administrator' or u['role']=='organizer' and e['organizerId']==user):status,result=403,dict(code='FORBIDDEN',message='Bạn không quản lý sự kiện này')
        else:
            try:fields=validate(payload)
            except ValueError as error:status,result=400,dict(code='INVALID_EVENT',message=str(error))
            if status==200 and fields['capacity']<e['registeredCount']:
                status,result=409,dict(code='CAPACITY_BELOW_ACTIVE',message='Sức chứa không được nhỏ hơn số đăng ký đang hoạt động')
            if status==200:
                # Older clients expose one description field. Keep their linked
                # detail copy in sync while preserving independently written text.
                linked_copy=e.get('about','')==e.get('description','') or (e.get('about','')=='' and e.get('description')=='Thông tin chi tiết sẽ được ban tổ chức cập nhật.')
                if 'about' not in fields and linked_copy:
                    fields['about']=fields['description']
                metadata=dict(e,**fields)
                for name in ('registeredCount','remainingCapacity'):metadata.pop(name,None)
                if datetime.fromisoformat(metadata['endsAt'].replace('Z','+00:00'))<datetime.fromisoformat(fields['startsAt']):metadata['endsAt']=fields['startsAt']
                c.execute(f'UPDATE events SET name={p},starts_at={p},capacity={p},metadata={p} WHERE id={p}',(fields['title'],fields['startsAt'],fields['capacity'],json.dumps(metadata,ensure_ascii=False),event_id))
                result=dict(event=database.event(c,event_id),requestId=key,replayed=False)
        c.execute(f'INSERT INTO idempotency_records VALUES({p},{p},{p},{p},{p},{p})',(user,'update-event',key,fp,status,json.dumps(result,ensure_ascii=False)))
        c.commit();return status,result,False
    except Exception:c.rollback();raise
    finally:c.close()
