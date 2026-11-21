"""Local classroom backend. Demo identity is NOT production authentication."""
import os,json,re,socket,argparse,hmac,ipaddress,time
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from urllib.parse import urlsplit,unquote
from contextlib import closing
from backend.db import ROOT
from backend.auth import AuthenticationError,identity_from_headers,identity_matches_role
from backend.accounts import AccountStore,AccountError,COOKIE_NAME,SESSION_SECONDS
from backend.account_validation import valid_csrf
from backend.settings import database_target,auto_migrate
from backend import telemetry
from backend.storage import configured_store,create_export,object_key,ObjectUnavailable
from backend.event_updates import update_event
DB=database_target(ROOT)
IS_POSTGRES=DB.startswith(('postgresql://','postgres://'))
if IS_POSTGRES:
    from backend import postgres as database
    P='%s'
else:
    from backend import db as database
    P='?'
migrate,seed,connect,event,booking,mutate,publish_event,audit=(
    database.migrate,database.seed,database.connect,database.event,database.booking,
    database.mutate,database.publish_event,database.audit
)
accounts=AccountStore(database,DB,P)

def begin_read(c):
    # A roster/export must not select active IDs from one state and then read
    # cancelled bookings from another committed state halfway through a response.
    c.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY' if IS_POSTGRES else 'BEGIN')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT/'dist'),**kw)
    def log_message(self,*args): pass  # Structured, redacted logging is emitted by dispatch.
    def send_response(self,code,message=None):
        self.response_status=code
        super().send_response(code,message)
    def end_headers(self):
        self.send_header('X-Request-Id',getattr(self,'rid',''))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','same-origin')
        super().end_headers()
    def dispatch(self,handler):
        self.rid=telemetry.request_id(self.headers); self.response_status=0
        self.response_replayed=False; self.response_code=None; self.response_dropped=False
        started=time.perf_counter()
        try: handler()
        except AccountError as exc: self.reply(exc.status,dict(code=exc.code,message=str(exc)))
        except database.DatabaseError: self.reply(503,dict(code='RETRY_SAME_KEY',message='Chưa thể kết nối CSDL; thử lại cùng request ID'))
        except (BrokenPipeError,ConnectionResetError): pass
        finally:
            path=unquote(urlsplit(self.path).path)
            if path.startswith(('/api/','/healthz','/readyz','/internal/')):
                telemetry.record(self.command,path,self.response_status,(time.perf_counter()-started)*1000,self.rid,
                                 self.response_replayed,self.response_code,self.response_dropped)
    def do_GET(self): self.dispatch(self.get_request)
    def do_POST(self): self.dispatch(self.post_request)
    def loopback_request(self):
        # Traffic relayed by a reverse proxy (Cloudflare adds Cf-Connecting-Ip) is never "this machine".
        if self.headers.get('Cf-Connecting-Ip') or self.headers.get('X-Forwarded-For'): return False
        try:
            host=urlsplit('//'+self.headers.get('Host','')).hostname
            return ipaddress.ip_address(self.client_address[0]).is_loopback and host in ('localhost','127.0.0.1','::1')
        except ValueError: return False
    def reply(self,status,data,replayed=False,cookie=None):
        self.response_replayed=replayed
        self.response_code=data.get('code') if isinstance(data,dict) else None
        raw=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.send_header('Idempotency-Replayed',str(replayed).lower())
        if cookie is not None: self.send_header('Set-Cookie',cookie)
        self.end_headers(); self.wfile.write(raw)
    def local_accounts_enabled(self):
        if os.environ.get('PORTAL_AUTH_MODE','demo').lower()!='demo': return False
        if os.environ.get('PORTAL_ALLOW_REMOTE_DEMO')=='1': return True
        return Handler.loopback_request(self)
    def cookie_token(self):
        jar=SimpleCookie()
        try: jar.load(self.headers.get('Cookie',''))
        except CookieError: return None
        return jar[COOKIE_NAME].value if COOKIE_NAME in jar else None
    def request_scheme(self):
        # Only a reverse proxy on this host (cloudflared) may declare the public scheme.
        if os.environ.get('PORTAL_SECURE_COOKIES')=='1': return 'https'
        try: proxied=ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError: proxied=False
        if proxied and os.environ.get('PORTAL_TRUST_LOCAL_PROXY')=='1' and self.headers.get('X-Forwarded-Proto','').lower()=='https': return 'https'
        return 'http'
    def session_cookie(self,token=''):
        secure='; Secure' if Handler.request_scheme(self)=='https' else ''
        return f'{COOKIE_NAME}={token}; Path=/api; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS if token else 0}{secure}'
    def check_account_origin(self):
        scheme=Handler.request_scheme(self)
        if self.headers.get('Origin')!=f'{scheme}://{self.headers.get("Host","")}' or self.headers.get('Sec-Fetch-Site')=='cross-site':
            raise AccountError(403,'INVALID_ORIGIN','Yêu cầu không xuất phát từ trang Campus hiện tại.')
    def request_identity(self):
        if os.environ.get('PORTAL_AUTH_MODE','demo').lower()!='demo': return identity_from_headers(self.headers)
        token=self.cookie_token()
        if token:
            active=accounts.session(token) if self.local_accounts_enabled() else None
            if not active: raise AuthenticationError('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
            if self.command=='POST':
                self.check_account_origin()
                if not valid_csrf(active['csrfToken'],self.headers.get('X-CSRF-Token','')):
                    raise AccountError(403,'INVALID_CSRF','Phiên bảo vệ không hợp lệ. Hãy tải lại trang rồi thử lại.')
            return dict(user_id=active['user']['id'],groups=None)
        identity=identity_from_headers(self.headers)
        # X-Demo-User is a spoofable classroom shortcut: honour it only on this machine.
        if identity['user_id'] and os.environ.get('PORTAL_ALLOW_REMOTE_DEMO')=='1' and not self.loopback_request():
            raise AuthenticationError('Vui lòng đăng nhập bằng email và mật khẩu.')
        if identity['user_id'].startswith('local-'):
            raise AuthenticationError('Tài khoản này cần đăng nhập bằng email và mật khẩu.')
        return identity
    def export_request(self,event_id,object_id=None):
        try:identity=self.request_identity()
        except AuthenticationError as exc:return self.reply(401,dict(message=str(exc)))
        with closing(connect(DB)) as c:
            begin_read(c)
            try:
                u=c.execute(f'SELECT role FROM users WHERE id={P}',(identity['user_id'],)).fetchone()
                e=event(c,event_id)
                if not u or not identity_matches_role(identity,u['role']):return self.reply(403,dict(message='Không có quyền'))
                if not e or not (u['role']=='administrator' or u['role']=='organizer' and e['organizerId']==identity['user_id']):return self.reply(403,dict(message='Không có quyền'))
                store=configured_store(ROOT)
                if object_id:
                    data=store.get(object_key(event_id,object_id))
                    self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8')
                    self.send_header('Content-Disposition','attachment; filename="campus-roster.csv"')
                    self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
                    self.end_headers();self.wfile.write(data);return
                rows=[booking(c,r['id']) for r in c.execute(f"SELECT id FROM registrations WHERE event_id={P} AND status='active' ORDER BY id",(event_id,))]
                oid=create_export(store,event_id,rows)
                return self.reply(201,dict(objectId=oid,count=len(rows),expiresInSeconds=86400))
            except ObjectUnavailable:return self.reply(503,dict(message='Chưa tải được bản xuất hoặc bản xuất đã hết hạn.'))
            finally:c.rollback()
    def account_request(self,path):
        if not self.local_accounts_enabled():
            return self.reply(403,dict(code='LOCAL_ACCOUNTS_DISABLED',message='Đăng ký bằng mật khẩu hiện chỉ khả dụng trên máy cục bộ. Tài khoản trường được quản lý qua dịch vụ danh tính của trường.'))
        try:
            self.check_account_origin()
            if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
                raise AccountError(415,'JSON_REQUIRED','Yêu cầu cần dùng nội dung JSON.')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096: raise AccountError(400,'INVALID_BODY','Thông tin tài khoản không hợp lệ.')
            payload=json.loads(self.rfile.read(size))
            if path=='/api/auth/logout':
                token=self.cookie_token()
                active=accounts.session(token)
                if active and not valid_csrf(active['csrfToken'],self.headers.get('X-CSRF-Token','')):
                    raise AccountError(403,'INVALID_CSRF','Phiên bảo vệ không hợp lệ. Hãy tải lại trang rồi thử lại.')
                accounts.revoke(token)
                return self.reply(200,dict(user=None,csrfToken=None),cookie=self.session_cookie())
            action='register' if path=='/api/auth/register' else 'login'
            accounts.rate_limit(self.client_address[0],action)
            user=accounts.register(payload) if action=='register' else accounts.login(payload)
            accounts.revoke(self.cookie_token())
            token,csrf=accounts.create_session(user['id'])
            return self.reply(201 if action=='register' else 200,dict(user=user,csrfToken=csrf),cookie=self.session_cookie(token))
        except AccountError as exc: return self.reply(exc.status,dict(code=exc.code,message=str(exc)))
        except (ValueError,UnicodeError): return self.reply(400,dict(code='INVALID_BODY',message='Thông tin tài khoản không hợp lệ.'))
        except database.DatabaseError:
            self.log_error('Account request failed; database error')
            return self.reply(503,dict(code='ACCOUNT_UNAVAILABLE',message='Chưa thể xử lý tài khoản. Vui lòng thử lại.'))
    def script(self,data):
        raw=('window.CAMPUS_RUNTIME_CONFIG='+json.dumps(data,ensure_ascii=True)+';').encode()
        self.send_response(200); self.send_header('Content-Type','application/javascript; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def get_request(self):
        p=unquote(urlsplit(self.path).path)
        export=re.fullmatch('/api/organizer/events/([^/]+)/exports/([0-9a-f]{32})',p)
        if export:return self.export_request(export[1],export[2])
        if p=='/internal/telemetry':
            return self.reply(200,telemetry.snapshot()) if self.loopback_request() else self.reply(404,dict(message='Không tìm thấy'))
        if p=='/runtime-config.js':
            mode=os.environ.get('PORTAL_AUTH_MODE','demo').lower()
            return self.script({
                'authMode':mode,
                'localAccounts':self.local_accounts_enabled(),
                'region':os.environ.get('COGNITO_REGION',''),
                'userPoolId':os.environ.get('COGNITO_USER_POOL_ID',''),
                'clientId':os.environ.get('COGNITO_CLIENT_ID',''),
                'domain':os.environ.get('COGNITO_DOMAIN',''),
                'redirectUri':os.environ.get('COGNITO_REDIRECT_URI',''),
                'logoutUri':os.environ.get('COGNITO_LOGOUT_URI','')
            })
        if p=='/api/auth/session':
            active=accounts.session(self.cookie_token()) if self.local_accounts_enabled() else None
            return self.reply(200,active or dict(user=None,csrfToken=None),cookie=None if active else self.session_cookie())
        if p in ('/healthz','/readyz'):
            c=None
            try:
                c=connect(DB)
                c.execute('SELECT 1')
                if p=='/readyz':
                    c.execute('SELECT id FROM events LIMIT 1'); c.execute('SELECT request_id FROM idempotency_records LIMIT 1')
                return self.reply(200,dict(status='ok',appVersion=telemetry.VERSION) if p=='/readyz' else dict(status='ok'))
            except database.DatabaseError:
                return self.reply(503,dict(status='unavailable'))
            finally:
                if c: c.close()
        if not p.startswith('/api/'): return super().do_GET()
        # Session lookup can use the same limited PostgreSQL connection budget.
        # Complete it before holding the response's read transaction.
        identity=None
        if p!='/api/events' and not p.startswith('/api/events/'):
            try: identity=self.request_identity()
            except AuthenticationError as exc: return self.reply(401,dict(message=str(exc)))
        c=connect(DB)
        try:
            begin_read(c)
            if p=='/api/events': return self.reply(200,[event(c,r['id']) for r in c.execute('SELECT id FROM events')])
            if p.startswith('/api/events/'):
                e=event(c,p.split('/')[-1]); return self.reply(200 if e else 404,e or dict(message='Không tìm thấy sự kiện'))
            user=identity['user_id']
            u=c.execute(f'SELECT * FROM users WHERE id={P}',(user,)).fetchone()
            if not u: return self.reply(401,dict(message='Vui lòng đăng nhập'))
            if not identity_matches_role(identity,u['role']): return self.reply(403,dict(message='Nhóm tài khoản không khớp quyền hệ thống'))
            if p=='/api/me/registrations': return self.reply(200,[booking(c,r['id']) for r in c.execute(f'SELECT id FROM registrations WHERE user_id={P} ORDER BY created_at DESC',(user,))])
            m=re.fullmatch('/api/organizer/events/([^/]+)/roster',p)
            if m:
                e=event(c,m[1])
                if not e: return self.reply(404,dict(message='Không tìm thấy sự kiện'))
                if not (u['role']=='administrator' or u['role']=='organizer' and e['organizerId']==user): return self.reply(403,dict(message='Không có quyền'))
                return self.reply(200,[booking(c,r['id']) for r in c.execute(f"SELECT id FROM registrations WHERE event_id={P} AND status='active'",(m[1],))])
            self.reply(404,dict(message='Không tìm thấy API'))
        finally: c.rollback(); c.close()
    def post_request(self):
        p=unquote(urlsplit(self.path).path)
        export=re.fullmatch('/api/organizer/events/([^/]+)/exports',p)
        if export:return self.export_request(export[1])
        if p in ('/api/auth/register','/api/auth/login','/api/auth/logout'): return self.account_request(p)
        m=re.fullmatch('/api/events/([^/]+)/registrations',p); n=re.fullmatch('/api/registrations/([^/]+)/cancel',p); q=p=='/api/organizer/events'; edit=re.fullmatch('/api/organizer/events/([^/]+)',p)
        if not (m or n or q or edit): return self.reply(404,dict(message='Không tìm thấy API'))
        try:
            try: identity=self.request_identity()
            except AuthenticationError as exc: return self.reply(401,dict(message=str(exc)))
            if identity.get('groups') is not None:
                allowed={'Organizers','Administrators'} if q or edit else {'Students'}
                if not allowed.intersection(identity['groups']): return self.reply(403,dict(message='Không có quyền'))
            user=identity['user_id']
            c=connect(DB)
            try:u=c.execute(f'SELECT role FROM users WHERE id={P}',(user,)).fetchone()
            finally:c.close()
            if not u:return self.reply(401,dict(message='Vui lòng đăng nhập'))
            if not identity_matches_role(identity,u['role']):return self.reply(403,dict(message='Nhóm tài khoản không khớp quyền hệ thống'))
            size=int(self.headers.get('Content-Length','0'))
            limit=65536 if edit else 4096
            if not 0<size<=limit: return self.reply(400,dict(message='Kích thước nội dung không hợp lệ'))
            payload=json.loads(self.rfile.read(size))
            key=self.headers.get('Idempotency-Key')
            if not isinstance(payload,dict) or payload.get('requestId')!=key: return self.reply(400,dict(message='requestId phải khớp Idempotency-Key'))
            if edit:
                status,result,replayed=update_event(database,DB,user,edit[1],key,payload,IS_POSTGRES)
            elif q:
                status,result,replayed=publish_event(DB,user,key,payload)
            else:
                status,result,replayed=mutate(DB,user,'register' if m else 'cancel',(m or n)[1],key,payload)
            if os.environ.get('ENABLE_FAULTS')=='1' and self.loopback_request() and self.headers.get('X-Drop-After-Commit')=='1' and not replayed and 200<=status<300:
                self.response_dropped=True
                self.close_connection=True
                self.connection.shutdown(socket.SHUT_RDWR); self.connection.close(); return
            self.reply(status,result,replayed)
        except AccountError as exc: self.reply(exc.status,dict(code=exc.code,message=str(exc)))
        except (ValueError,UnicodeError): self.reply(400,dict(message='JSON không hợp lệ'))
        except database.OperationalError: self.reply(503,dict(code='RETRY_SAME_KEY',message='CSDL đang bận; thử lại cùng request ID'))
        except database.DatabaseError:
            self.log_error('Request failed; transaction rolled back if uncommitted')
            self.reply(500,dict(message='Lỗi máy chủ; thử lại cùng request ID'))
if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('command',nargs='?',default='serve',choices=['serve','migrate','seed','audit','backup','restore']); parser.add_argument('--file',default='campus-backup.json'); args=parser.parse_args()
    if args.command=='audit':
        result=audit(DB); print(json.dumps(result,ensure_ascii=False,indent=2)); raise SystemExit(0 if result['ok'] and not result['foreignKeys'] else 1)
    if args.command=='backup':
        from backend.backup import create_backup
        result=create_backup(DB,args.file); print(json.dumps(result,ensure_ascii=False,indent=2)); raise SystemExit(0)
    if args.command=='restore':
        from backend.backup import restore_backup
        result=restore_backup(DB,args.file); print(json.dumps(result,ensure_ascii=False,indent=2)); raise SystemExit(0 if result['ok'] and not result['foreignKeys'] else 1)
    port=int(os.environ.get('PORT',4173)); host=os.environ.get('PORTAL_HOST','127.0.0.1')
    if args.command=='serve' and os.environ.get('PORTAL_AUTH_MODE','demo').lower()=='demo' and host not in ('127.0.0.1','::1','localhost') and os.environ.get('PORTAL_ALLOW_REMOTE_DEMO')!='1':
        raise SystemExit('Chế độ tài khoản cục bộ chỉ được bind loopback.')
    if args.command in ('migrate','seed') or auto_migrate(): migrate(DB)
    if args.command=='migrate': raise SystemExit()
    if args.command=='seed' or auto_migrate(): seed(DB)
    if args.command=='seed': raise SystemExit()
    if os.environ.get('PORTAL_AUTH_MODE','demo').lower()=='demo': accounts.migrate()
    class Server(ThreadingHTTPServer):
        request_queue_size=256
        daemon_threads=True
    stop=telemetry.start_sampler(database,DB,IS_POSTGRES)
    telemetry.emit(dict(event='startup',host=host,port=port,database='postgresql' if IS_POSTGRES else 'sqlite'))
    try:
        with Server((host,port),Handler) as http: http.serve_forever()
    except KeyboardInterrupt: pass
    finally: stop.set()
