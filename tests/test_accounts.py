import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import db
from backend.accounts import AccountError, AccountStore, password_matches
from backend.backup import create_backup, restore_backup

PASSWORD = 'campus-test-password-2026'


def profile(index=1):
    return dict(name='Nguyễn An Bình', studentId=f'SV2026{index:04}', email=f'account{index}@example.test', password=PASSWORD)


class AccountStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = str(Path(self.tmp.name) / 'account.sqlite3')
        db.migrate(self.target); db.seed(self.target)
        self.store = AccountStore(db, self.target); self.store.migrate()

    def tearDown(self):
        self.tmp.cleanup()

    def test_student_only_and_password_hash(self):
        user = self.store.register(profile())
        self.assertEqual(user['role'], 'student')
        self.assertTrue(user['id'].startswith('local-'))
        with closing(db.connect(self.target)) as conn:
            encoded = conn.execute('SELECT password_hash FROM account_credentials').fetchone()['password_hash']
        self.assertNotIn(PASSWORD, encoded)
        self.assertTrue(password_matches(PASSWORD, encoded))
        with self.assertRaises(AccountError): self.store.register({**profile(2), 'role': 'administrator'})

    def test_validation_and_existing_seed_cannot_be_claimed(self):
        for field, value in [('name', ''), ('studentId', '../bad'), ('email', 'not-an-email'), ('password', 'short')]:
            with self.subTest(field=field), self.assertRaises(AccountError):
                self.store.register({**profile(), field: value})
        with self.assertRaises(AccountError) as error:
            self.store.register({**profile(), 'studentId': '10001'})
        self.assertEqual(error.exception.status, 409)

    def test_invalid_domain_labels_and_local_email_parts_are_rejected(self):
        for email in ('audit@example.-test.com','audit@one..example.test','audit@-example.test',
                      'audit@example-.test','.audit@example.test','a..b@example.test',
                      'audit@'+'a'*64+'.test'):
            with self.subTest(email=email), self.assertRaises(AccountError) as error:
                self.store.register({**profile(), 'email': email})
            self.assertEqual(error.exception.code, 'INVALID_EMAIL')
        user = self.store.register({**profile(), 'email': 'audit+student@sub.example.test'})
        self.assertEqual(user['email'], 'audit+student@sub.example.test')

    def test_concurrent_duplicates_do_not_create_orphan_users(self):
        def attempt(_):
            try: return self.store.register(profile())['id']
            except AccountError as error: return error.status
        with ThreadPoolExecutor(4) as executor:
            results = list(executor.map(attempt, range(4)))
        self.assertEqual(sum(isinstance(r, str) for r in results), 1)
        self.assertEqual(results.count(409), 3)
        with closing(db.connect(self.target)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users WHERE id LIKE 'local-%'").fetchone()[0], 1)
        for data in [{**profile(2), 'email': profile()['email'].upper()}, {**profile(2), 'studentId': profile()['studentId'].lower()}]:
            with self.assertRaises(AccountError): self.store.register(data)

    def test_sessions_survive_store_restart_and_are_revoked(self):
        user = self.store.register(profile())
        token, csrf = self.store.create_session(user['id'])
        again = AccountStore(db, self.target)
        self.assertEqual(again.session(token)['user'], user)
        self.assertEqual(again.session(token)['csrfToken'], csrf)
        with closing(db.connect(self.target)) as conn:
            self.assertEqual(conn.execute('SELECT token_hash FROM account_sessions').fetchone()[0], hashlib.sha256(token.encode()).hexdigest())
        again.revoke(token)
        self.assertIsNone(self.store.session(token))

    def test_backup_keeps_passwords_but_not_sessions_and_reads_legacy(self):
        user = self.store.register(profile()); token, _ = self.store.create_session(user['id'])
        path = Path(self.tmp.name) / 'backup.json'
        create_backup(self.target, path)
        bundle = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(len(bundle['tables']['account_credentials']), 1)
        self.assertNotIn('account_sessions', bundle['tables'])
        self.store.register(profile(2))
        restore_backup(self.target, path)
        self.assertEqual(self.store.login(dict(email=profile()['email'], password=PASSWORD)), user)
        self.assertIsNone(self.store.session(token))
        # Original v1 bundles did not contain this optional extension.
        del bundle['tables']['account_credentials']
        bundle['sha256'] = hashlib.sha256(json.dumps(bundle['tables'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        path.write_text(json.dumps(bundle), encoding='utf-8')
        restore_backup(self.target, path)
        with self.assertRaises(AccountError): self.store.login(dict(email=profile()['email'], password=PASSWORD))

    def test_rate_limit_is_shared_between_store_instances(self):
        for _ in range(5): self.store.rate_limit('test-address', 'register')
        with self.assertRaises(AccountError) as error: AccountStore(db, self.target).rate_limit('test-address', 'register')
        self.assertEqual(error.exception.status, 429)

    def test_remote_http_does_not_enable_password_accounts(self):
        from server import Handler
        remote = SimpleNamespace(client_address=('203.0.113.10', 40000), headers={'Host': 'localhost:4173'})
        local = SimpleNamespace(client_address=('127.0.0.1', 40000), headers={'Host': '127.0.0.1:4173'})
        with patch.dict(os.environ, {'PORTAL_AUTH_MODE': 'demo', 'PORTAL_SECURE_COOKIES': ''}):
            self.assertFalse(Handler.local_accounts_enabled(remote))
            self.assertTrue(Handler.local_accounts_enabled(local))
        with patch.dict(os.environ, {'PORTAL_AUTH_MODE': 'demo', 'PORTAL_SECURE_COOKIES': '1'}):
            self.assertFalse(Handler.local_accounts_enabled(remote))
            self.assertIn('; Secure', Handler.session_cookie(remote, 'test-cookie'))


class AccountHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.target = str(Path(self.tmp.name) / 'http.sqlite3')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.origin = f'http://127.0.0.1:{self.port}'
        self.start()

    def start(self, mode='demo'):
        env = dict(os.environ, PORTAL_AUTH_MODE=mode, PORTAL_DB=self.target, PORTAL_DATABASE_URL='', PORTAL_HOST='127.0.0.1', PORT=str(self.port), PYTHONDONTWRITEBYTECODE='1', PORTAL_SECURE_COOKIES='')
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'server.py')], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(150):
            try:
                if self.request('GET', '/healthz')[0] == 200: return
            except OSError: pass
            time.sleep(.03)
        self.proc.terminate(); self.proc.wait(); self.fail('Account test server did not start')

    def tearDown(self):
        self.proc.terminate(); self.proc.wait(timeout=10); self.tmp.cleanup()

    def request(self, method, path, data=None, cookie=None, csrf=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        h = {'Origin': self.origin}
        if data is not None: h['Content-Type'] = 'application/json'
        if cookie: h['Cookie'] = cookie
        if csrf: h['X-CSRF-Token'] = csrf
        h.update(headers or {})
        try:
            connection.request(method, path, body=None if data is None else json.dumps(data).encode(), headers=h)
            response = connection.getresponse(); raw = response.read()
            return response.status, dict(response.getheaders()), json.loads(raw)
        finally: connection.close()

    def signup(self):
        status, headers, body = self.request('POST', '/api/auth/register', profile())
        self.assertEqual(status, 201, body)
        return headers['Set-Cookie'].split(';')[0], body['csrfToken'], body['user'], headers

    def test_cookie_login_logout_and_session_after_server_restart(self):
        cookie, csrf, user, headers = self.signup()
        for flag in ('HttpOnly', 'SameSite=Strict', 'Path=/api'): self.assertIn(flag, headers['Set-Cookie'])
        self.assertEqual(self.request('GET', '/api/auth/session', cookie=cookie)[2]['user'], user)
        self.proc.terminate(); self.proc.wait(); self.start()
        self.assertEqual(self.request('GET', '/api/auth/session', cookie=cookie)[2]['user'], user)
        self.assertEqual(self.request('POST', '/api/auth/logout', {}, cookie=cookie, csrf='wrong')[0], 403)
        self.assertEqual(self.request('POST', '/api/auth/logout', {}, cookie=cookie, csrf=csrf)[0], 200)
        self.assertEqual(self.request('GET', '/api/me/registrations', cookie=cookie)[0], 401)
        self.assertEqual(self.request('POST', '/api/auth/login', dict(email=profile()['email'], password='wrong'))[0], 401)
        status, _, result = self.request('POST', '/api/auth/login', dict(email=profile()['email'].upper(), password=PASSWORD))
        self.assertEqual(status, 200); self.assertEqual(result['user'], user)

    def test_real_booking_cancel_and_cannot_spoof_new_user_or_become_organizer(self):
        cookie, csrf, user, _ = self.signup()
        path = '/api/events/cloud-lab/registrations'
        headers = {'Idempotency-Key': 'new-user-register', 'X-Demo-User': 'admin-1'}
        data = {'requestId': 'new-user-register'}
        self.assertEqual(self.request('POST', path, data, cookie=cookie, headers=headers)[0], 403)
        status, _, booked = self.request('POST', path, data, cookie=cookie, csrf=csrf, headers=headers)
        self.assertEqual(status, 201); self.assertEqual(booked['booking']['userId'], user['id'])
        again = self.request('POST', path, data, cookie=cookie, csrf=csrf, headers=headers)
        self.assertEqual(again[2]['booking']['id'], booked['booking']['id'])
        self.assertEqual(self.request('GET', '/api/me/registrations', cookie=cookie)[2][0]['id'], booked['booking']['id'])
        self.assertEqual(self.request('GET', '/api/me/registrations', headers={'X-Demo-User': user['id']})[0], 401)
        self.assertEqual(self.request('POST', '/api/organizer/events', {'requestId': 'no-admin'}, cookie=cookie, csrf=csrf, headers={'Idempotency-Key': 'no-admin'})[0], 403)
        cancel = '/api/registrations/' + booked['booking']['id'] + '/cancel'
        for key in ('cancel-1', 'cancel-2'):
            result = self.request('POST', cancel, {'requestId': key}, cookie=cookie, csrf=csrf, headers={'Idempotency-Key': key})
            self.assertEqual(result[0], 200); self.assertEqual(result[2]['remainingCapacity'], 20)
        self.assertEqual(self.request('GET', '/api/me/registrations', headers={'X-Demo-User': 'stu-10001'})[0], 200)

    def test_cross_origin_validation_and_expired_cookie(self):
        self.assertEqual(self.request('POST', '/api/auth/register', profile(), headers={'Origin': 'https://other.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/auth/register', {**profile(), 'role': 'administrator'})[0], 400)
        cookie, csrf, _, _ = self.signup()
        self.assertEqual(self.request('POST', '/api/auth/logout', {}, cookie=cookie, csrf=csrf, headers={'Origin': 'https://other.example'})[0], 403)
        with closing(db.connect(self.target)) as conn: conn.execute('UPDATE account_sessions SET expires_at=0')
        self.assertEqual(self.request('GET', '/api/me/registrations', cookie=cookie)[0], 401)
        status, headers, result = self.request('GET', '/api/auth/session', cookie=cookie)
        self.assertEqual(status, 200); self.assertIsNone(result['user']); self.assertIn('Max-Age=0', headers['Set-Cookie'])

    def test_malformed_csrf_returns_json_without_disconnecting_or_revoking_session(self):
        for email in ('audit@example.-test.com','audit@one..example.test'):
            status, _, body = self.request('POST','/api/auth/register',{**profile(2),'email':email})
            self.assertEqual(status,400); self.assertEqual(body['code'],'INVALID_EMAIL')
        cookie, csrf, _, _ = self.signup()
        for bad in ('é', 'bad', 'x'*300, '\x80'):
            with self.subTest(token=repr(bad)):
                status, headers, body = self.request('POST','/api/auth/logout',{},cookie=cookie,csrf=bad)
                self.assertEqual(status,403)
                self.assertEqual(body['code'],'INVALID_CSRF')
                self.assertIn('application/json',headers['Content-Type'])
        status, _, body = self.request('POST','/api/events/cloud-lab/registrations',{'requestId':'bad-csrf'},
                                       cookie=cookie,csrf='é',headers={'Idempotency-Key':'bad-csrf'})
        self.assertEqual(status,403); self.assertEqual(body['code'],'INVALID_CSRF')
        self.assertIsNotNone(self.request('GET','/api/auth/session',cookie=cookie)[2]['user'])
        self.assertEqual(self.request('POST','/api/auth/logout',{},cookie=cookie,csrf=csrf)[0],200)

    def test_cognito_mode_keeps_local_signup_disabled(self):
        self.proc.terminate(); self.proc.wait(); self.start('cognito')
        self.assertEqual(self.request('POST', '/api/auth/register', profile())[0], 403)
        self.assertEqual(self.request('GET', '/api/me/registrations', headers={'X-Demo-User': 'stu-10001'})[0], 401)


if __name__ == '__main__': unittest.main()
