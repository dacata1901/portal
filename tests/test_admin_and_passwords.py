"""End-to-end HTTP tests for zero fake roster data, Admin CRUD (students/events/roster), and student password change."""
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
sys.path.insert(0, str(ROOT))
from backend import db

STU_PW = 'StudentPass-2026-Test'
ORG_PW = 'OrganizerPass-2026-Test'
ADM_PW = 'AdminPass-2026-Test'


class AdminAndPasswordHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / 'admin.sqlite3')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        env = dict(
            os.environ,
            PORTAL_AUTH_MODE='demo',
            PORTAL_DB=self.db_path,
            PORTAL_DATABASE_URL='',
            PORTAL_HOST='127.0.0.1',
            PORT=str(self.port),
            PYTHONDONTWRITEBYTECODE='1',
            PORTAL_ALLOW_REMOTE_DEMO='1',
            PORTAL_TRUST_LOCAL_PROXY='1',
            PORTAL_DISABLE_SIGNUP='1',
            PORTAL_OBJECT_DIR=str(Path(self.tmp.name) / 'objects'),
            PORTAL_LOG_FILE=str(Path(self.tmp.name) / 'log.jsonl'),
        )
        subprocess.run([sys.executable, str(ROOT / 'server.py'), 'seed'], env=env, check=True, stdout=subprocess.DEVNULL)
        for role, pw in (('student', STU_PW), ('organizer', ORG_PW), ('administrator', ADM_PW)):
            subprocess.run(
                [sys.executable, str(ROOT / 'scripts' / 'set_account_password.py'), '--role', role, '--db', self.db_path, '--password-env', 'INIT_PW'],
                env={**env, 'INIT_PW': pw},
                check=True,
                stdout=subprocess.DEVNULL,
            )
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'server.py')], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):
            try:
                if self.request('GET', '/healthz')[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.03)
        self.fail('server did not start')

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)
        self.tmp.cleanup()

    def public(self, extra=None):
        h = {
            'Host': 'campus-admin.trycloudflare.com',
            'Cf-Connecting-Ip': '198.51.100.9',
            'X-Forwarded-For': '198.51.100.9',
            'X-Forwarded-Proto': 'https',
            'Origin': 'https://campus-admin.trycloudflare.com',
        }
        h.update(extra or {})
        return h

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        h = self.public(headers)
        if data is not None:
            h['Content-Type'] = 'application/json'
        try:
            conn.request(method, path, body=None if data is None else json.dumps(data).encode(), headers=h)
            r = conn.getresponse()
            raw = r.read()
            return r.status, dict(r.getheaders()), (json.loads(raw) if raw and 'json' in r.getheader('Content-Type', '') else raw)
        finally:
            conn.close()

    def login(self, email, password):
        status, headers, body = self.request('POST', '/api/auth/login', {'email': email, 'password': password})
        self.assertEqual(status, 200, body)
        cookie = headers['Set-Cookie'].split(';')[0]
        return {'Cookie': cookie, 'X-CSRF-Token': body['csrfToken']}, body['user']

    def test_zero_fake_registrations_on_fresh_seed(self):
        status, _, events = self.request('GET', '/api/events')
        self.assertEqual(status, 200)
        self.assertTrue(len(events) >= 6)
        for ev in events:
            self.assertEqual(ev['registeredCount'], 0, ev['id'])
            self.assertEqual(ev['remainingCapacity'], ev['capacity'], ev['id'])
        admin_h, _ = self.login('admin@example.test', ADM_PW)
        status, _, students = self.request('GET', '/api/admin/students', headers=admin_h)
        self.assertEqual(status, 200)
        self.assertEqual(len(students), 100)
        self.assertFalse(any(s['id'].startswith('seed-') or 'Sinh viên giả' in s['name'] for s in students))

    def test_admin_student_crud_event_roster_and_event_delete(self):
        stu_h, _ = self.login('student10001@example.test', STU_PW)
        org_h, _ = self.login('organizer@example.test', ORG_PW)
        adm_h, _ = self.login('admin@example.test', ADM_PW)

        # RBAC: non-admins rejected
        self.assertEqual(self.request('GET', '/api/admin/students', headers=stu_h)[0], 403)
        self.assertEqual(self.request('GET', '/api/admin/students', headers=org_h)[0], 403)
        self.assertEqual(self.request('POST', '/api/admin/events/cloud-lab/delete', {}, headers=org_h)[0], 403)

        # Admin creates a new real student
        new_pw = 'RealStudentPass2026!'
        status, _, created = self.request(
            'POST',
            '/api/admin/students',
            {'name': 'Phạm Quốc Bảo', 'studentId': 'SV2026999', 'email': 'quocbao@campus.edu.vn', 'password': new_pw},
            headers=adm_h,
        )
        self.assertEqual(status, 201, created)
        uid = created['student']['id']
        # New student can log in immediately
        self.login('quocbao@campus.edu.vn', new_pw)

        # Admin updates student info and resets password
        reset_pw = 'ResetStudentPass2026!'
        status, _, updated = self.request(
            'POST',
            f'/api/admin/students/{uid}',
            {'name': 'Phạm Quốc Bảo (K22)', 'studentId': 'SV2026999', 'email': 'quocbao.k22@campus.edu.vn', 'password': reset_pw},
            headers=adm_h,
        )
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated['student']['name'], 'Phạm Quốc Bảo (K22)')
        self.assertEqual(self.request('POST', '/api/auth/login', {'email': 'quocbao.k22@campus.edu.vn', 'password': new_pw})[0], 401)
        self.login('quocbao.k22@campus.edu.vn', reset_pw)

        # Admin adds real student to cloud-lab -> remaining goes 20 -> 19
        status, _, added = self.request('POST', '/api/admin/events/cloud-lab/registrations', {'userId': uid}, headers=adm_h)
        self.assertEqual(status, 201, added)
        self.assertEqual(added['remainingCapacity'], 19)
        bid = added['booking']['id']

        # Admin removes student from cloud-lab -> remaining goes 19 -> 20
        status, _, removed = self.request('POST', f'/api/admin/registrations/{bid}/remove', {}, headers=adm_h)
        self.assertEqual(status, 200, removed)
        self.assertEqual(removed['remainingCapacity'], 20)

        # Add again then delete student -> slot automatically restored to 20 and audit clean
        self.assertEqual(self.request('POST', '/api/admin/events/cloud-lab/registrations', {'userId': uid}, headers=adm_h)[0], 201)
        self.assertEqual(self.request('GET', '/api/events/cloud-lab')[2]['remainingCapacity'], 19)
        status, _, deleted = self.request('POST', f'/api/admin/students/{uid}/delete', {}, headers=adm_h)
        self.assertEqual(status, 200, deleted)
        self.assertEqual(self.request('GET', '/api/events/cloud-lab')[2]['remainingCapacity'], 20)

        # Admin deletes an event (even with an active booking)
        self.assertEqual(self.request('POST', '/api/admin/events/career-kit/registrations', {'userId': 'stu-10001'}, headers=adm_h)[0], 201)
        status, _, ev_del = self.request('POST', '/api/admin/events/career-kit/delete', {}, headers=adm_h)
        self.assertEqual(status, 200, ev_del)
        self.assertEqual(self.request('GET', '/api/events/career-kit')[0], 404)

        audit_res = db.audit(self.db_path)
        self.assertTrue(audit_res['ok'])
        self.assertEqual(audit_res['foreignKeys'], [])

    def test_student_can_change_own_password(self):
        stu_h, _ = self.login('student10002@example.test', STU_PW)
        # Wrong current password -> 401
        status, _, _ = self.request(
            'POST',
            '/api/auth/change-password',
            {'currentPassword': 'wrong-password-12345', 'newPassword': 'BrandNewStudentPw2026!'},
            headers=stu_h,
        )
        self.assertEqual(status, 401)
        # Valid change -> 200 + fresh session cookie + old password stops working
        new_pw = 'BrandNewStudentPw2026!'
        status, headers, body = self.request(
            'POST',
            '/api/auth/change-password',
            {'currentPassword': STU_PW, 'newPassword': new_pw},
            headers=stu_h,
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body['changed'])
        self.assertIn('; Secure', headers['Set-Cookie'])
        self.assertEqual(self.request('POST', '/api/auth/login', {'email': 'student10002@example.test', 'password': STU_PW})[0], 401)
        self.login('student10002@example.test', new_pw)


if __name__ == '__main__':
    unittest.main()
