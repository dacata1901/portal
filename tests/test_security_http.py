"""Real HTTP + real RSA signatures; provider JWKS retrieval is a test double only."""
import importlib.util,json,os,tempfile,threading,time,unittest,urllib.request,urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from backend import db
ROOT=Path(__file__).resolve().parents[1]

class HttpSecurity(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.path=str(Path(cls.tmp.name)/'test.sqlite3');db.migrate(cls.path);db.seed(cls.path)
  cls.env=patch.dict(os.environ,{'PORTAL_ENV':'development','PORTAL_DB':cls.path,'PORTAL_AUTH_MODE':'cognito','COGNITO_REGION':'ap-southeast-2','COGNITO_USER_POOL_ID':'ap-southeast-2_test','COGNITO_CLIENT_ID':'test-client','PORTAL_OBJECT_DIR':str(Path(cls.tmp.name)/'objects'),'PORTAL_LOG_FILE':str(Path(cls.tmp.name)/'requests.jsonl')})
  cls.env.start()
  cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  client=SimpleNamespace(get_signing_key_from_jwt=lambda token:SimpleNamespace(key=cls.key.public_key()))
  cls.jwks=patch('backend.auth._jwks',{});cls.jwks.start()
  cls.client=patch('jwt.PyJWKClient',return_value=client);cls.client.start()
  spec=importlib.util.spec_from_file_location('http_security_server',ROOT/'server.py');cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
  cls.server=cls.module.ThreadingHTTPServer(('127.0.0.1',0),cls.module.Handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
  cls.base=f'http://127.0.0.1:{cls.server.server_port}'
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.client.stop();cls.jwks.stop();cls.env.stop();cls.tmp.cleanup()
 def token(self,user='stu-10001',groups=None,**changes):
  claims=dict(iss='https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_test',exp=int(time.time())+300,token_use='access',client_id='test-client',username=user)
  claims['cognito:groups']=groups or ['Students'];claims.update(changes)
  return jwt.encode(claims,self.key,algorithm='RS256')
 def call(self,path,token=None,payload=None,key=None,headers=None):
  headers=dict(headers or {})
  if token:headers['Authorization']='Bearer '+token
  if key:headers['Idempotency-Key']=key
  if payload is not None:headers['Content-Type']='application/json'
  req=urllib.request.Request(self.base+path,data=None if payload is None else json.dumps(payload).encode(),headers=headers)
  try:r=urllib.request.urlopen(req,timeout=10)
  except urllib.error.HTTPError as error:r=error
  with r:
   raw=r.read();return r.status,json.loads(raw) if 'json' in r.headers.get('Content-Type','') else raw,r.headers
 def test_invalid_tokens_rejected_through_http(self):
  changes=[{'iss':'https://wrong.example/'},{'client_id':'other-client'},{'exp':int(time.time())-120},{'token_use':'id'},{'aud':'https://other-api.example'},{'cognito:groups':'Students'}]
  for change in changes:
   with self.subTest(change=change):self.assertEqual(self.call('/api/me/registrations',self.token(**change))[0],401)
  forged=jwt.encode(dict(iss='x',exp=int(time.time())+500,token_use='access',client_id='test-client'),rsa.generate_private_key(public_exponent=65537,key_size=2048),algorithm='RS256')
  self.assertEqual(self.call('/api/me/registrations',forged)[0],401)
  self.assertEqual(self.call('/api/me/registrations',headers={'X-Demo-User':'stu-10001'})[0],401)
 def test_history_ownership_and_role_checks(self):
  token=self.token();path='/api/events/cloud-lab/registrations'
  status,body,headers=self.call(path,token,{'requestId':'security-own'},'security-own');self.assertEqual(status,201)
  self.assertEqual(headers['X-Request-Id'],'security-own');bid=body['booking']['id']
  self.assertEqual(self.call('/api/me/registrations',token)[1][0]['id'],bid)
  self.assertEqual(self.call('/api/me/registrations',self.token('stu-10002'))[1],[])
  self.assertEqual(self.call(f'/api/registrations/{bid}/cancel',self.token('stu-10002'),{'requestId':'steal'},'steal')[0],404)
  self.assertEqual(self.call('/api/organizer/events/cloud-lab/roster',token)[0],403)
  self.assertEqual(self.call('/api/organizer/events/cloud-lab/roster',self.token('org-1',['Students']))[0],403)
  self.assertEqual(self.call('/api/organizer/events/cloud-lab/roster',self.token('admin-1',['Administrators']))[0],200)
 def test_event_edits_validate_owner_capacity_and_durable_replay(self):
  org=self.token('org-1',['Organizers']);path='/api/organizer/events/ai-campus'
  event=self.call('/api/events/ai-campus')[1]
  payload={k:event[k] for k in ('title','startsAt','capacity','category','format','venue','description')}
  payload.update(capacity=130,requestId='edit-ok')
  status,body,_=self.call(path,org,payload,'edit-ok');self.assertEqual(status,200);self.assertEqual(body['event']['capacity'],130)
  self.assertEqual(self.call(path,org,payload,'edit-ok')[1],body)
  self.assertEqual(self.call(path,org,{**payload,'capacity':131},'edit-ok')[0],409)
  self.assertEqual(self.call(path,org,{**payload,'capacity':85,'requestId':'edit-low'},'edit-low')[0],409)
  self.assertEqual(self.call(path,self.token('org-2',['Organizers']),{**payload,'requestId':'edit-other'},'edit-other')[0],403)
  self.assertEqual(self.call(path,self.token(),{**payload,'requestId':'edit-student'},'edit-student')[0],403)
  c=db.connect(self.path)
  try:self.assertEqual(c.execute("SELECT capacity FROM events WHERE id='ai-campus'").fetchone()['capacity'],130)
  finally:c.close()
 def test_private_csv_is_authenticated_and_ownership_scoped(self):
  org=self.token('org-1',['Organizers']);prefix='/api/organizer/events/cloud-lab/exports'
  status,created,_=self.call(prefix,org,{})
  self.assertEqual(status,201);path=prefix+'/'+created['objectId']
  status,csv,_=self.call(path,org);self.assertEqual(status,200);self.assertTrue(csv.startswith(b'\xef\xbb\xbf'))
  self.assertEqual(self.call(path)[0],401)
  self.assertEqual(self.call(path,self.token())[0],403)
  self.assertEqual(self.call(path,self.token('org-2',['Organizers']))[0],403)
  self.assertEqual(self.call(path,self.token('admin-1',['Administrators']))[0],200)
 def test_cloud_rejects_local_account_routes_and_metrics(self):
  self.assertEqual(self.call('/api/auth/register',payload={})[0],403)
  self.assertEqual(self.call('/internal/telemetry',headers={'Host':'campus.example.test'})[0],404)
