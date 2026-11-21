"""Bounded local observations and low-cardinality CloudWatch EMF events."""
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid

_lock = threading.RLock()
_counts = {'CapacityConflicts':0,'DuplicateReplays':0,'HttpResponsesDropped':0,'InfrastructureErrors':0}
_latencies = deque(maxlen=20000)
_drops = deque(maxlen=10000)
_connections = 0
_alarm = None


def source_version():
    if os.environ.get('APP_VERSION'): return os.environ['APP_VERSION'][:128]
    root=Path(__file__).resolve().parents[1]; h=hashlib.sha256()
    files=[root/'server.py',root/'requirements.txt',root/'fixtures.json']
    files += list((root/'backend').glob('*.py')) + [p for p in (root/'dist').rglob('*') if p.suffix in ('.js','.css','.html')]
    for p in sorted(files):
        if p.is_file(): h.update(p.relative_to(root).as_posix().encode());h.update(p.read_bytes())
    return 'local-'+h.hexdigest()[:24]


VERSION = source_version()


def request_id(headers):
    value=headers.get('Idempotency-Key') or headers.get('X-Request-Id') or ''
    return value if re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',value) else str(uuid.uuid4())


def route_name(path):
    if re.fullmatch(r'/api/events/[^/]+/registrations',path): return '/api/events/:id/registrations'
    if re.fullmatch(r'/api/registrations/[^/]+/cancel',path): return '/api/registrations/:id/cancel'
    if re.fullmatch(r'/api/organizer/events/[^/]+/roster',path): return '/api/organizer/events/:id/roster'
    if re.fullmatch(r'/api/events/[^/]+',path): return '/api/events/:id'
    allowed={'/api/events','/api/me/registrations','/api/organizer/events','/api/auth/login','/api/auth/logout','/api/auth/register','/api/auth/session','/healthz','/readyz','/internal/telemetry'}
    return path if path in allowed else '/other'


def emit(event, metrics=None):
    event=dict(event, timestamp=datetime.now(timezone.utc).isoformat(), appVersion=VERSION,
               Service='campus',Stage=os.environ.get('CAMPUS_STAGE','local'))
    if metrics:
        event.update(metrics)
        event['_aws']={'Timestamp':int(time.time()*1000),'CloudWatchMetrics':[{
            'Namespace':'Campus/Portal','Dimensions':[['Service','Stage']],
            'Metrics':[{'Name':name,'Unit':'Milliseconds' if name=='BookingLatency' else 'Count'} for name in metrics]}]}
    with _lock:
        stream = os.environ.get('PORTAL_LOG_FILE')
        line=json.dumps(event,ensure_ascii=True,separators=(',',':'))+'\n'
        if stream:
            with open(stream,'a',encoding='utf-8') as target: target.write(line)
        else:
            sys.stdout.write(line);sys.stdout.flush()


def connection_delta(delta):
    global _connections
    with _lock: _connections=max(0,_connections+delta)


def record(method,path,status,elapsed_ms,rid,replayed=False,code=None,dropped=False):
    route=route_name(path); metrics={}
    with _lock:
        if method=='POST' and route=='/api/events/:id/registrations':
            _latencies.append((time.time(),elapsed_ms));metrics['BookingLatency']=round(elapsed_ms,3)
        for name,condition in [('CapacityConflicts',code=='EVENT_FULL'),('DuplicateReplays',replayed),('HttpResponsesDropped',dropped),('InfrastructureErrors',status>=500)]:
            if condition:
                _counts[name]+=1;metrics[name]=1
        if dropped: _drops.append(time.time())
    # Deliberately omit request body, query, cookies, Authorization and private fields.
    emit(dict(event='http_request',requestId=rid,method=method,route=route,status=status,
              durationMs=round(elapsed_ms,3),replayed=bool(replayed),responseDropped=bool(dropped)),metrics)


def percentile(values,pct=95):
    values=sorted(values)
    if not values:return 0.0
    rank=(len(values)-1)*pct/100;lo=math.floor(rank);hi=math.ceil(rank)
    return round(values[lo]+(values[hi]-values[lo])*(rank-lo),3)


def evaluate_alert(now=None):
    global _alarm
    now=time.time() if now is None else now
    with _lock:
        while _drops and _drops[0]<now-60:_drops.popleft()
        if _drops and (not _alarm or _alarm['state']=='OK'):
            _alarm={'state':'ALARM','condition':'HttpResponsesDropped sum >= 1','windowSeconds':60,
                    'evaluationSeconds':float(os.environ.get('PORTAL_METRICS_INTERVAL','15')),
                    'firstFaultAt':_drops[0],'evaluatedAt':now,'measuredDelaySeconds':round(now-_drops[0],3),
                    'firstRecoveryAction':'Retry the committed booking with the same request ID; inspect DB audit before any compensation.'}
            emit(dict(event='fault_alert',**_alarm))
        if not _drops and _alarm and _alarm['state']=='ALARM':_alarm=dict(_alarm,state='OK',recoveredAt=now)
        return dict(_alarm) if _alarm else {'state':'OK'}


def snapshot():
    with _lock:
        values=[v for ts,v in _latencies if ts>=time.time()-300]
        return dict(appVersion=VERSION,counters=dict(_counts),bookingLatency={'windowSeconds':300,'count':len(values),'p95Ms':percentile(values)},
                    sqliteOpenConnections=_connections,alert=dict(_alarm) if _alarm else {'state':'OK'})


def start_sampler(database,target,is_postgres=False):
    stop=threading.Event()
    def run():
        while not stop.wait(float(os.environ.get('PORTAL_METRICS_INTERVAL','15'))):
            try:
                if is_postgres:
                    conn=database.connect(target)
                    try: count=conn.execute('SELECT numbackends FROM pg_stat_database WHERE datname=current_database()').fetchone()['numbackends']
                    finally:conn.close()
                else:
                    with _lock:count=_connections
                emit({'event':'db_connections'}, {'DatabaseConnections':int(count)})
                evaluate_alert()
            except Exception:
                emit({'event':'telemetry_sample_unavailable'})
    thread=threading.Thread(target=run,name='campus-metrics',daemon=True);thread.start()
    return stop
