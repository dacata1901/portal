"""Event copy stays consistent without replacing independently authored details."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from backend import db
from backend.event_updates import update_event

ROOT = Path(__file__).resolve().parents[1]
EDIT_FIELDS = ('title', 'startsAt', 'capacity', 'category', 'format', 'venue', 'description')


class EventDescriptionUpdates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'events.sqlite3')
        db.migrate(self.path)
        db.seed(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, event_id):
        c = db.connect(self.path)
        try:
            return db.event(c, event_id)
        finally:
            c.close()

    def create(self):
        payload = dict(title='Sự kiện kiểm tra', startsAt='2026-12-01T10:00:00+07:00',
                       capacity=25, description='Nội dung A')
        status, result, _ = db.publish_event(self.path, 'org-1', 'create-copy', payload)
        self.assertEqual(status, 201)
        return result['event']

    def edit(self, event, key, **changes):
        payload = {k: event[k] for k in EDIT_FIELDS}
        payload.update(changes)
        return update_event(db, self.path, 'org-1', event['id'], key, payload), payload

    def test_created_description_updates_linked_detail_and_durable_replay(self):
        event = self.create()
        self.assertEqual(event['about'], 'Nội dung A')
        (status, first, replayed), payload = self.edit(event, 'edit-copy', description='Nội dung B')
        self.assertEqual(status, 200)
        self.assertFalse(replayed)
        saved = self.read(event['id'])
        self.assertEqual((saved['description'], saved['about']), ('Nội dung B', 'Nội dung B'))
        status, again, replayed = update_event(db, self.path, 'org-1', event['id'], 'edit-copy', payload)
        self.assertEqual(status, 200)
        self.assertTrue(replayed)
        self.assertEqual(again, first)
        conflict = update_event(db, self.path, 'org-1', event['id'], 'edit-copy', {**payload, 'about': 'Khác'})
        self.assertEqual(conflict[0], 409)
        self.assertEqual(self.read(event['id'])['about'], 'Nội dung B')

    def test_seeded_details_survive_summary_edit_and_are_separately_editable(self):
        event = self.read('cloud-lab')
        self.assertNotEqual(event['description'], event['about'])
        (status, result, _), _ = self.edit(event, 'seed-summary', description='Mô tả ngắn mới')
        self.assertEqual(status, 200)
        self.assertEqual(result['event']['about'], event['about'])
        details = 'Thông tin chi tiết mới.\n' + 'Thực hành cùng nhóm. ' * 80
        (status, result, _), payload = self.edit(result['event'], 'seed-details', about=details)
        self.assertEqual(status, 200)
        self.assertEqual(result['event']['description'], 'Mô tả ngắn mới')
        self.assertEqual(result['event']['about'], details.strip())
        self.assertEqual(result['event']['agenda'], event['agenda'])
        self.assertEqual(result['event']['note'], event['note'])
        self.assertEqual(update_event(db, self.path, 'org-1', event['id'], 'seed-details', payload)[1], result)
        self.assertEqual(self.read(event['id'])['about'], details.strip())

    def test_created_without_description_links_its_empty_details_on_first_edit(self):
        payload = dict(title='Sự kiện chưa có mô tả', startsAt='2026-12-01T10:00:00+07:00', capacity=25)
        status, result, _ = db.publish_event(self.path, 'org-1', 'create-empty-copy', payload)
        self.assertEqual(status, 201)
        self.assertEqual(result['event']['about'], '')
        (status, result, _), _ = self.edit(result['event'], 'edit-empty-copy', description='Mô tả được bổ sung')
        self.assertEqual(status, 200)
        self.assertEqual(result['event']['about'], 'Mô tả được bổ sung')

    def test_explicit_details_override_linked_copy_and_validate_before_saving(self):
        event = self.create()
        (status, result, _), _ = self.edit(event, 'explicit-copy', description='Mô tả B', about='Chi tiết riêng')
        self.assertEqual(status, 200)
        self.assertEqual(result['event']['about'], 'Chi tiết riêng')
        for i, invalid in enumerate([None, [], 'x' * 10001]):
            (status, result, _), _ = self.edit(event, f'invalid-about-{i}', about=invalid)
            self.assertEqual(status, 400)
            self.assertEqual(result['code'], 'INVALID_EVENT')
            self.assertEqual(self.read(event['id'])['about'], 'Chi tiết riêng')
        (status, result, _), _ = self.edit(self.read(event['id']), 'clear-about', about='')
        self.assertEqual(status, 200)
        self.assertEqual(result['event']['about'], '')

    def test_http_round_trip_supports_detailed_vietnamese_copy_and_replay(self):
        env = dict(PORTAL_ENV='development', PORTAL_DB=self.path, PORTAL_AUTH_MODE='demo',
                   PORTAL_LOG_FILE=str(Path(self.tmp.name) / 'requests.jsonl'))
        with patch.dict(os.environ, env):
            spec = importlib.util.spec_from_file_location('event_copy_http_server', ROOT / 'server.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            server = module.ThreadingHTTPServer(('127.0.0.1', 0), module.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                event = self.create()
                payload = {k: event[k] for k in EDIT_FIELDS}
                payload.update(description='Mô tả B', about='Hướng dẫn thực hành. ' * 200, requestId='http-copy')
                raw = json.dumps(payload, ensure_ascii=False).encode()
                self.assertGreater(len(raw), 4096)
                url = f'http://127.0.0.1:{server.server_port}/api/organizer/events/{event["id"]}'
                headers = {'Content-Type': 'application/json', 'X-Demo-User': 'org-1', 'Idempotency-Key': 'http-copy'}
                def request():
                    return urllib.request.urlopen(urllib.request.Request(url, data=raw, headers=headers), timeout=5)
                with request() as response:
                    self.assertEqual(response.status, 200)
                    first = json.load(response)
                    self.assertEqual(first['event']['about'], payload['about'].strip())
                with request() as response:
                    self.assertEqual(response.headers['Idempotency-Replayed'], 'true')
                    self.assertEqual(json.load(response), first)
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/events/{event["id"]}') as response:
                    saved = json.load(response)
                self.assertEqual(saved['description'], 'Mô tả B')
                self.assertEqual(saved['about'], payload['about'].strip())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
