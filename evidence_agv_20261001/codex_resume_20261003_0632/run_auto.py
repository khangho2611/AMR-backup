"""Explicit user-authorized ARM+AUTO; observation duration does not stop AUTO."""
import datetime,hashlib,json,pathlib,sys,time,urllib.request,urllib.error
root=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '/home/khangho/agv_codex_escape_20261003_0044')
assert str(root)=='/home/khangho/agv_codex_resume_20261003_0632'
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
     'boot':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
     'mode':'OPERATOR_CONTROL_CONTINUOUS','actions':[],'samples':[]}
assert out['boot']=='b61a8008-2552-4fce-b5dc-2985b6d6177a'
for line in (root/'sources.sha256').read_text().splitlines():
    expected,name=line.split(maxsplit=1)
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
def get(path):
    try:
        response=urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=3)
    except urllib.error.HTTPError as exc:response=exc
    return {'http':response.code,'data':json.load(response)}
before=get('/api/telemetry');out['before']=before
c=before['data']['control']
if not (before['http']==200 and c['preflight_ready'] and c['fault'] is None and not c['armed']):
    out['aborted']='PREFLIGHT_NOT_READY_NO_ARM'
    print(json.dumps(out));raise SystemExit(1)
assert c['latest_d0']['safety']=='DISARMED'
assert all(c['latest_d0'][k]==0 for k in ('l_tgt','r_tgt','l_rpm','r_rpm','l_pwm','r_pwm','v','w'))
arm=get('/api/cmd?val=ARM');out['actions'].append({'command':'ARM',**arm})
if arm['http']==200 and arm['data'].get('reason')=='ARM_CONFIRMED':
    auto=get('/api/auto?act=START');out['actions'].append({'command':'AUTO_START',**auto})
    if auto['http']!=200:
        out['actions'].append({'command':'STOP_AFTER_REJECTED_START',**get('/api/cmd?val=STOP')})
else:
    out['aborted']='ARM_NOT_CONFIRMED_NO_DRIVE'
started=time.monotonic()
while time.monotonic()-started<22:
    result=get('/api/telemetry');d=result['data'];control=d['control']
    sample={'elapsed':time.monotonic()-started,'auto':d['auto'],'status':d['status'],
            'control':control,'robot':d['robot'],'map':d['map_info'],'min_m':d['min_m']}
    out['samples'].append(sample)
    if control['fault'] is not None:
        out['fault']=control['fault'];break
    time.sleep(.1)
out['diagnostics']=get('/api/diagnostics')
out['after']=get('/api/telemetry')
print(json.dumps(out))
