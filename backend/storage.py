"""Private CSV objects. Authorization is enforced at the API, never by a public URL."""
import csv
import hashlib
import io
import os
from pathlib import Path
import re
import time
import uuid


class ObjectUnavailable(Exception): pass


def object_key(event_id, object_id):
    if not re.fullmatch('[0-9a-f]{32}',object_id): raise ObjectUnavailable()
    return 'exports/'+hashlib.sha256(event_id.encode()).hexdigest()+'/'+object_id+'.csv'


def roster_csv(rows):
    out=io.StringIO(newline=''); out.write('\ufeff')
    writer=csv.writer(out,quoting=csv.QUOTE_ALL)
    def safe(value):
        value=str(value or '')
        return "'"+value if re.match(r'^\s*[=+@-]',value) else value
    writer.writerow(['Mã sinh viên','Họ tên','Email','Mã đăng ký','Trạng thái','Thời điểm đăng ký'])
    for r in rows:writer.writerow([safe(r.get(k)) for k in ('studentId','name','email','id')]+['Đã đăng ký',safe(r.get('createdAt'))])
    return out.getvalue().encode('utf-8')


class LocalPrivateObjects:
    def __init__(self,root):self.root=Path(root).resolve()
    def put(self,key,data):
        target=self.root/key
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as out:out.write(data)
        target.chmod(0o600)
    def get(self,key):
        target=(self.root/key).resolve()
        try:
            if not target.is_relative_to(self.root) or time.time()-target.stat().st_mtime>86400:raise ObjectUnavailable()
            return target.read_bytes()
        except OSError:raise ObjectUnavailable() from None


class S3PrivateObjects:
    def __init__(self,bucket,client=None):
        if client is None:
            import boto3
            client=boto3.client('s3')
        self.bucket,self.client=bucket,client
    def put(self,key,data):
        try:self.client.put_object(Bucket=self.bucket,Key=key,Body=data,ContentType='text/csv; charset=utf-8',ServerSideEncryption='AES256')
        except Exception:raise ObjectUnavailable() from None
    def get(self,key):
        try:
            result=self.client.get_object(Bucket=self.bucket,Key=key)
            if time.time()-result['LastModified'].timestamp()>86400:raise ObjectUnavailable()
            with result['Body'] as body:return body.read()
        except Exception:raise ObjectUnavailable() from None


def configured_store(root):
    bucket=os.environ.get('PORTAL_EXPORT_BUCKET')
    if bucket:return S3PrivateObjects(bucket)
    if os.environ.get('PORTAL_ENV')=='production':raise ObjectUnavailable()
    return LocalPrivateObjects(os.environ.get('PORTAL_OBJECT_DIR',str(root/'.runtime/private-objects')))


def create_export(store,event_id,rows):
    object_id=uuid.uuid4().hex
    store.put(object_key(event_id,object_id),roster_csv(rows))
    return object_id
