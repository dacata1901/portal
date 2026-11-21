import unittest,tempfile,os,sys,json,subprocess,socket,time,urllib.request,urllib.error,sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import *
class Correctness(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=str(Path(self.tmp.name)/'test.db');migrate(self.db);seed(self.db)
 def tearDown(self):self.tmp.cleanup()
 def reg(self,i,key=None,target='cloud-lab',**kw):
  key=key or f'key-{i}';return mutate(self.db,f'stu-{10001+i}','register',target,key,{'requestId':key},**kw)
 def check(self):
  a=audit(self.db);self.assertTrue(a['ok']);self.assertEqual(a['foreignKeys'],[]);return next(e for e in a['events'] if e['id']=='cloud-lab')
 def test_100_concurrent_20_seats(self):
  with ThreadPoolExecutor(40) as ex:r=list(ex.map(self.reg,range(100)))
  self.assertEqual(sum(x[0]==201 for x in r),20);self.assertEqual(sum(x[0]==409 for x in r),80);self.assertEqual(self.check()['remaining'],0)
 def test_same_key_concurrent_conflict(self):
  with ThreadPoolExecutor(20) as ex:r=list(ex.map(lambda _:self.reg(0),range(20)))
  self.assertTrue(all(x[:2]==r[0][:2] for x in r));self.assertEqual(sum(not x[2] for x in r),1);self.assertEqual(self.reg(0,target='ai-campus')[0],409);self.assertEqual(self.check()['active'],1)
 def test_different_keys_same_student(self):
  with ThreadPoolExecutor(20) as ex:r=list(ex.map(lambda i:self.reg(0,str(i)),range(20)))
  self.assertEqual(sum(x[0]==201 for x in r),1);self.assertEqual(self.check()['active'],1)
 def test_cancel_concurrent(self):
  b=self.reg(0)[1]['booking']['id']
  def cancel(i):return mutate(self.db,'stu-10001','cancel',b,str(i),{'requestId':str(i)})
  with ThreadPoolExecutor(20) as ex:r=list(ex.map(cancel,range(20)))
  self.assertTrue(all(x[0]==200 for x in r));self.assertEqual(self.check()['remaining'],20);self.assertEqual(cancel(0)[:2],r[0][:2]);self.assertEqual(self.reg(0,'new')[0],201);self.assertEqual(self.check()['remaining'],19)
 def test_rollback_seed(self):
  with self.assertRaises(RuntimeError):self.reg(0,fail_before_commit=True)
  self.assertEqual(self.check()['active'],0);self.assertEqual(self.reg(0)[0],201);migrate(self.db);seed(self.db);seed(self.db);self.assertEqual(self.check()['active'],1)
 def test_constraints_ownership(self):
  b=self.reg(0)[1]['booking']['id'];c=connect(self.db)
  try:
   with self.assertRaises(sqlite3.IntegrityError):c.execute("UPDATE events SET capacity=0 WHERE id='cloud-lab'")
   with self.assertRaises(sqlite3.IntegrityError):c.execute("INSERT INTO registrations VALUES('bad','stu-10001','cloud-lab','active','now',NULL)")
  finally:c.close()
  self.assertEqual(mutate(self.db,'stu-10002','cancel',b,'x',{'requestId':'x'})[0],404);self.check()
 def test_organizer_publish_persists_and_replays(self):
  payload={'requestId':'publish-1','title':'Hội thảo sinh viên','startsAt':'2026-12-01T10:00:00+07:00','capacity':25,'category':'Công nghệ','format':'Workshop','venue':'Phòng B.302','description':'Thực hành cloud'}
  status,result,replayed=publish_event(self.db,'org-1','publish-1',payload)
  self.assertEqual(status,201);self.assertFalse(replayed)
  self.assertEqual(result['event']['remainingCapacity'],25)
  self.assertEqual(result['event']['organizerId'],'org-1')
  status,again,replayed=publish_event(self.db,'org-1','publish-1',payload)
  self.assertEqual(status,201);self.assertTrue(replayed);self.assertEqual(again,result)
  self.assertEqual(publish_event(self.db,'org-1','publish-1',{**payload,'capacity':30})[0],409)
  self.assertEqual(publish_event(self.db,'stu-10001','student-publish',payload)[0],403)
  self.assertEqual(publish_event(self.db,'org-1','invalid-publish',{**payload,'capacity':0})[0],400)
  c=connect(self.db)
  try:self.assertEqual(c.execute("SELECT COUNT(*) FROM events WHERE name='Hội thảo sinh viên'").fetchone()[0],1)
  finally:c.close()
  self.check()
 def test_http_drop_commit_restart_replay(self):
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  env=dict(os.environ,PORTAL_DB=self.db,PORT=str(port),ENABLE_FAULTS='1')
  def start():
   p=subprocess.Popen([sys.executable,str(ROOT/'server.py')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   for _ in range(100):
    try:urllib.request.urlopen(f'http://127.0.0.1:{port}/api/events',timeout=.2).close();return p
    except OSError:time.sleep(.03)
   p.kill();p.wait();self.fail('Startup failed')
  def request(drop=False):
   h={'Content-Type':'application/json','Idempotency-Key':'drop','X-Demo-User':'stu-10001'}
   if drop:h['X-Drop-After-Commit']='1'
   return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/api/events/cloud-lab/registrations',data=b'{"requestId":"drop"}',headers=h),timeout=20)
  def publish(payload):
   body=json.dumps(payload,ensure_ascii=False).encode()
   headers={'Content-Type':'application/json','Idempotency-Key':payload['requestId'],'X-Demo-User':'org-1'}
   return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/api/organizer/events',data=body,headers=headers),timeout=20)
  p=start()
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',timeout=5) as response:
    self.assertEqual(response.status,200);self.assertEqual(json.load(response),{'status':'ok'})
   event_payload={'requestId':'publish-http','title':'Sự kiện qua HTTP','startsAt':'2026-12-01T10:00:00+07:00','capacity':10}
   with publish(event_payload) as response:
    event_result=json.load(response);self.assertEqual(response.status,201);self.assertEqual(event_result['event']['remainingCapacity'],10)
   with publish(event_payload) as response:
    self.assertEqual(json.load(response),event_result);self.assertEqual(response.headers['Idempotency-Replayed'],'true')
   with self.assertRaises(urllib.error.HTTPError) as conflict:publish({**event_payload,'capacity':11})
   self.assertEqual(conflict.exception.code,409);conflict.exception.close()
   with self.assertRaises(Exception):request(True)
   self.assertEqual(self.check()['active'],1)
  finally:p.terminate();p.wait()
  p=start()
  try:
   with request() as response:body=json.load(response);self.assertEqual(response.headers['Idempotency-Replayed'],'true')
   for _ in range(10):
    with request() as response:self.assertEqual(json.load(response),body)
   self.assertEqual(self.check()['active'],1)
  finally:p.terminate();p.wait()
 def test_cognito_mode_rejects_spoofed_demo_identity(self):
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  env=dict(os.environ,PORTAL_DB=self.db,PORT=str(port),PORTAL_AUTH_MODE='cognito')
  p=subprocess.Popen([sys.executable,str(ROOT/'server.py')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   for _ in range(100):
    try:
     urllib.request.urlopen(f'http://127.0.0.1:{port}/api/events',timeout=.2).close()
     break
    except OSError:time.sleep(.03)
   request=urllib.request.Request(
    f'http://127.0.0.1:{port}/api/me/registrations',
    headers={'X-Demo-User':'stu-10001'}
   )
   with self.assertRaises(urllib.error.HTTPError) as response:
    urllib.request.urlopen(request,timeout=5)
   self.assertEqual(response.exception.code,401)
   response.exception.close()
  finally:p.terminate();p.wait()
 def test_backup_and_restore_preserves_state_and_passes_audit(self):
  from backend.backup import create_backup,restore_backup
  backup_file=Path(self.tmp.name)/'portal-backup.json'
  status,reg_res,_=self.reg(0,key='bkp-key-1')
  self.assertEqual(status,201)
  summary=create_backup(self.db,str(backup_file))
  self.assertTrue(summary['audit']['ok'])
  self.assertEqual(summary['counts']['registrations'],next(c for c in [summary['counts']['registrations']] if c>0))
  # Mutate DB after backup (register second student and publish an event)
  self.assertEqual(self.reg(1,key='after-bkp-2')[0],201)
  self.assertEqual(self.check()['remaining'],18)
  # Tampered checksum must be rejected
  tampered=Path(self.tmp.name)/'tampered.json'
  data=json.loads(backup_file.read_text(encoding='utf-8'))
  data['sha256']='0'*64
  tampered.write_text(json.dumps(data),encoding='utf-8')
  with self.assertRaises(ValueError):restore_backup(self.db,str(tampered))
  # Restore from clean backup and verify state matches point-in-time snapshot
  restored_audit=restore_backup(self.db,str(backup_file))
  self.assertTrue(restored_audit['ok'])
  self.assertEqual(restored_audit['foreignKeys'],[])
  self.assertEqual(self.check()['remaining'],19)
  # Idempotency record from before backup is also preserved
  replay_status,replay_res,replayed=self.reg(0,key='bkp-key-1')
  self.assertEqual(replay_status,201)
  self.assertTrue(replayed)
  self.assertEqual(replay_res['booking']['id'],reg_res['booking']['id'])
