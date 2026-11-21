"""Public exposure through a local reverse proxy (Cloudflare Tunnel) must not enable spoofable demo identities."""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'campus-proxy-password-2026'


class PublicProxyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        env = dict(os.environ, PORTAL_AUTH_MODE='demo', PORTAL_DB=str(Path(self.tmp.name) / 'proxy.sqlite3'),
                   PORTAL_DATABASE_URL='', PORTAL_HOST='127.0.0.1', PORT=str(self.port), PYTHONDONTWRITEBYTECODE='1',
                   PORTAL_SECURE_COOKIES='', PORTAL_ALLOW_REMOTE_DEMO='1', PORTAL_TRUST_LOCAL_PROXY='1',
                   PORTAL_OBJECT_DIR=str(Path(self.tmp.name) / 'objects'), PORTAL_LOG_FILE=str(Path(self.tmp.name) / 'log.jsonl'))
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'server.py')], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):
            try:
                if self.request('GET', '/healthz')[0] == 200: return
            except OSError: pass
            time.sleep(.03)
        self.fail('server did not start')

    def tearDown(self):
        self.proc.terminate(); self.proc.wait(timeout=10); self.tmp.cleanup()

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        h = dict(headers or {})
        if data is not None: h['Content-Type'] = 'application/json'
        try:
            conn.request(method, path, body=None if data is None else json.dumps(data).encode(), headers=h)
            r = conn.getresponse(); raw = r.read()
            return r.status, dict(r.getheaders()), (json.loads(raw) if raw and 'json' in r.getheader('Content-Type', '') else raw)
        finally: conn.close()

    def public(self, extra=None):
        h = {'Host': 'campus-demo.trycloudflare.com', 'Cf-Connecting-Ip': '198.51.100.7',
             'X-Forwarded-For': '198.51.100.7', 'X-Forwarded-Proto': 'https', 'Origin': 'https://campus-demo.trycloudflare.com'}
        h.update(extra or {}); return h

    def test_spoofed_demo_identity_rejected_through_proxy(self):
        self.assertEqual(self.request('GET', '/api/me/registrations', headers=self.public({'X-Demo-User': 'admin-1'}))[0], 401)
        self.assertEqual(self.request('GET', '/api/organizer/events/cloud-lab/roster', headers=self.public({'X-Demo-User': 'admin-1'}))[0], 401)
        # Even a forged localhost Host header is not trusted once the request carries proxy headers.
        self.assertEqual(self.request('GET', '/api/me/registrations', headers=self.public({'Host': '127.0.0.1', 'X-Demo-User': 'admin-1'}))[0], 401)
        self.assertEqual(self.request('GET', '/internal/telemetry', headers=self.public({'Host': '127.0.0.1'}))[0], 404)
        # Direct local development still works.
        self.assertEqual(self.request('GET', '/api/me/registrations', headers={'Host': '127.0.0.1', 'X-Demo-User': 'stu-10001'})[0], 200)

    def test_https_signup_through_proxy_sets_secure_cookie(self):
        profile = dict(name='Trần Proxy', studentId='SVPROXY01', email='proxy@example.test', password=PASSWORD)
        status, headers, body = self.request('POST', '/api/auth/register', profile, headers=self.public())
        self.assertEqual(status, 201, body)
        self.assertIn('; Secure', headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';')[0]
        status, _, booked = self.request('POST', '/api/events/cloud-lab/registrations', {'requestId': 'proxy-1'},
                                         headers=self.public({'Cookie': cookie, 'X-CSRF-Token': body['csrfToken'], 'Idempotency-Key': 'proxy-1'}))
        self.assertEqual(status, 201, booked)
        # A spoofed X-Forwarded-Proto from a non-proxy origin mismatch is still rejected.
        self.assertEqual(self.request('POST', '/api/auth/register', {**profile, 'email': 'x@example.test', 'studentId': 'SVPROXY02'},
                                      headers=self.public({'Origin': 'https://evil.example'}))[0], 403)


class UniversityIssuedAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / 'issued.sqlite3')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        env = dict(os.environ, PORTAL_AUTH_MODE='demo', PORTAL_DB=self.db_path, PORTAL_DATABASE_URL='',
                   PORTAL_HOST='127.0.0.1', PORT=str(self.port), PYTHONDONTWRITEBYTECODE='1',
                   PORTAL_ALLOW_REMOTE_DEMO='1', PORTAL_TRUST_LOCAL_PROXY='1', PORTAL_DISABLE_SIGNUP='1',
                   PORTAL_OBJECT_DIR=str(Path(self.tmp.name) / 'objects'), PORTAL_LOG_FILE=str(Path(self.tmp.name) / 'log.jsonl'))
        subprocess.run([sys.executable, str(ROOT / 'server.py'), 'seed'], env=env, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'set_account_password.py'), '--role', 'student', '--db', self.db_path, '--password-env', 'TEST_STU_PW'],
                       env={**env, 'TEST_STU_PW': PASSWORD}, check=True, stdout=subprocess.DEVNULL)
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'server.py')], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):
            try:
                if self.request('GET', '/healthz')[0] == 200: return
            except OSError: pass
            time.sleep(.03)
        self.fail('server did not start')

    def tearDown(self):
        self.proc.terminate(); self.proc.wait(timeout=10); self.tmp.cleanup()

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        h = dict(headers or {})
        if data is not None: h['Content-Type'] = 'application/json'
        try:
            conn.request(method, path, body=None if data is None else json.dumps(data).encode(), headers=h)
            r = conn.getresponse(); raw = r.read()
            return r.status, dict(r.getheaders()), (json.loads(raw) if raw and 'json' in r.getheader('Content-Type', '') else raw)
        finally: conn.close()

    def public(self, extra=None):
        h = {'Host': 'campus-demo.trycloudflare.com', 'Cf-Connecting-Ip': '198.51.100.7',
             'X-Forwarded-For': '198.51.100.7', 'X-Forwarded-Proto': 'https', 'Origin': 'https://campus-demo.trycloudflare.com'}
        h.update(extra or {}); return h

    def test_signup_disabled_and_university_student_can_login(self):
        profile = dict(name='Trần Tự Đăng Ký', studentId='SVSELF01', email='self@example.test', password=PASSWORD)
        status, _, body = self.request('POST', '/api/auth/register', profile, headers=self.public())
        self.assertEqual(status, 403)
        self.assertEqual(body['code'], 'SIGNUP_DISABLED')
        status, headers, body = self.request('POST', '/api/auth/login', {'email': 'student10001@example.test', 'password': PASSWORD}, headers=self.public())
        self.assertEqual(status, 200, body)
        self.assertEqual(body['user']['id'], 'stu-10001')
        self.assertEqual(body['user']['role'], 'student')
        self.assertIn('; Secure', headers['Set-Cookie'])


if __name__ == '__main__': unittest.main()
