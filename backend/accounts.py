"""Local student accounts; Cognito remains the external identity provider."""
import hashlib
import hmac
import re
import secrets
import time
import unicodedata
import uuid
from backend.account_validation import normalize_email

SESSION_SECONDS = 8 * 60 * 60
PASSWORD_ITERATIONS = 600_000
COOKIE_NAME = 'campus_local_session'


class AccountError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), PASSWORD_ITERATIONS)
    return f'pbkdf2-sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}'


def password_matches(password, encoded):
    try:
        algorithm, iterations, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2-sha256' or int(iterations) != PASSWORD_ITERATIONS:
            return False
        calculated = password_hash(password, salt).split('$')[-1]
        return hmac.compare_digest(calculated, expected)
    except (ValueError, TypeError):
        return False


_DUMMY_PASSWORD_HASH = password_hash('unused-account-password', '00' * 16)


def public_user(row):
    return dict(id=row['id'], studentId=row['student_id'], name=row['name'], email=row['email'], role=row['role'])


class AccountStore:
    def __init__(self, database, target, placeholder='?'):
        self.database, self.target, self.p = database, target, placeholder

    def begin(self, conn):
        conn.execute('BEGIN IMMEDIATE' if self.p == '?' else 'BEGIN')

    def migrate(self):
        conn = self.database.connect(self.target)
        try:
            self.begin(conn)
            for sql in (
                '''CREATE TABLE IF NOT EXISTS account_credentials (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    email_key TEXT NOT NULL UNIQUE, student_key TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL, created_at BIGINT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS account_sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL, expires_at BIGINT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS account_rate_limits (
                    scope TEXT PRIMARY KEY, attempts INTEGER NOT NULL, resets_at BIGINT NOT NULL)''',
            ):
                conn.execute(sql)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rate_limit(self, address, action):
        """Shared DB counters; independent of the event registration endpoints."""
        now = int(time.time())
        limit, window = (5, 600) if action == 'register' else (20, 300)
        scope = hashlib.sha256(f'{action}:{address}'.encode()).hexdigest()
        conn = self.database.connect(self.target)
        try:
            self.begin(conn)
            conn.execute(f'DELETE FROM account_rate_limits WHERE resets_at<={self.p}', (now,))
            # UPSERT serializes the same scope on PostgreSQL and SQLite.
            row = conn.execute(
                f'INSERT INTO account_rate_limits(scope,attempts,resets_at) VALUES({self.p},1,{self.p}) '
                'ON CONFLICT(scope) DO UPDATE SET attempts=account_rate_limits.attempts+1 RETURNING attempts',
                (scope, now + window),
            ).fetchone()
            conn.commit()
            if row['attempts'] > limit:
                raise AccountError(429, 'TOO_MANY_ATTEMPTS', 'Bạn đã thử nhiều lần. Vui lòng chờ vài phút rồi thử lại.')
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def register(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'name', 'studentId', 'email', 'password'}:
            raise AccountError(400, 'INVALID_ACCOUNT', 'Vui lòng nhập đầy đủ thông tin tài khoản sinh viên.')
        if not all(isinstance(payload[key], str) for key in payload):
            raise AccountError(400, 'INVALID_ACCOUNT', 'Thông tin tài khoản không hợp lệ.')
        name = ' '.join(unicodedata.normalize('NFKC', payload['name']).split())
        student = unicodedata.normalize('NFKC', payload['studentId']).strip().upper()
        email = payload['email'].strip().lower()
        password = payload['password']
        if not 2 <= len(name) <= 100 or any(unicodedata.category(c).startswith('C') for c in name):
            raise AccountError(400, 'INVALID_NAME', 'Họ tên cần có từ 2 đến 100 ký tự.')
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{2,31}', student):
            raise AccountError(400, 'INVALID_STUDENT_ID', 'Mã sinh viên cần có 3–32 ký tự: chữ, số, dấu chấm, gạch ngang hoặc gạch dưới.')
        try:
            email = normalize_email(email)
        except ValueError as error:
            raise AccountError(400, 'INVALID_EMAIL', str(error)) from error
        if not 12 <= len(password) <= 128 or not password.strip():
            raise AccountError(400, 'INVALID_PASSWORD', 'Mật khẩu cần có từ 12 đến 128 ký tự.')
        encoded = password_hash(password)
        conn = self.database.connect(self.target)
        try:
            self.begin(conn)
            if self.p != '?':
                conn.execute('SELECT pg_advisory_xact_lock(67461020)')
            if conn.execute(f'SELECT id FROM users WHERE LOWER(email)={self.p} OR UPPER(student_id)={self.p}', (email, student)).fetchone():
                raise AccountError(409, 'ACCOUNT_EXISTS', 'Email hoặc mã sinh viên đã được sử dụng. Hãy đăng nhập bằng tài khoản hiện có.')
            user_id = 'local-' + uuid.uuid4().hex
            conn.execute(f'INSERT INTO users(id,student_id,name,email,role) VALUES({self.p},{self.p},{self.p},{self.p},{self.p})',
                         (user_id, student, name, email, 'student'))
            conn.execute(f'INSERT INTO account_credentials VALUES({self.p},{self.p},{self.p},{self.p},{self.p})',
                         (user_id, email, student, encoded, int(time.time())))
            conn.commit()
            return dict(id=user_id, studentId=student, name=name, email=email, role='student')
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def login(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'email', 'password'}:
            raise AccountError(400, 'INVALID_LOGIN', 'Vui lòng nhập email và mật khẩu.')
        email, password = payload['email'], payload['password']
        if not isinstance(email, str) or not isinstance(password, str) or len(email) > 254 or len(password) > 128:
            raise AccountError(400, 'INVALID_LOGIN', 'Email hoặc mật khẩu không hợp lệ.')
        conn = self.database.connect(self.target)
        try:
            row = conn.execute(f'SELECT u.*,a.password_hash FROM account_credentials a JOIN users u ON u.id=a.user_id WHERE a.email_key={self.p}',
                               (email.strip().lower(),)).fetchone()
        finally:
            conn.close()
        # Apply the same KDF work when the email does not exist.
        encoded = row['password_hash'] if row else _DUMMY_PASSWORD_HASH
        valid = password_matches(password, encoded)
        if not row or not valid:
            raise AccountError(401, 'INVALID_CREDENTIALS', 'Email hoặc mật khẩu chưa đúng.')
        return public_user(row)

    def create_session(self, user_id):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        conn = self.database.connect(self.target)
        try:
            self.begin(conn)
            conn.execute(f'DELETE FROM account_sessions WHERE expires_at<={self.p}', (now,))
            conn.execute(f'INSERT INTO account_sessions VALUES({self.p},{self.p},{self.p},{self.p})',
                         (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, now + SESSION_SECONDS))
            conn.commit()
            return token, csrf
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def session(self, token):
        if not isinstance(token, str) or not 20 <= len(token) <= 128:
            return None
        conn = self.database.connect(self.target)
        try:
            row = conn.execute(
                f'SELECT u.*,s.csrf_token FROM account_sessions s JOIN users u ON u.id=s.user_id '
                f'WHERE s.token_hash={self.p} AND s.expires_at>{self.p}',
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time())),
            ).fetchone()
            return None if not row else dict(user=public_user(row), csrfToken=row['csrf_token'])
        finally:
            conn.close()

    def revoke(self, token):
        if not token:
            return
        conn = self.database.connect(self.target)
        try:
            conn.execute(f'DELETE FROM account_sessions WHERE token_hash={self.p}', (hashlib.sha256(token.encode()).hexdigest(),))
            conn.commit()
        finally:
            conn.close()
