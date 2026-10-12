import json
import os
import pathlib
import signal
import time
import urllib.request

root=pathlib.Path('/home/khangho/agv_codex_20261002_1915')
def read(path):
    with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=3) as r:return json.load(r)
before=read('/api/telemetry')
assert not before['control']['trial_used'],'Operator already consumed trial; no automatic replacement'
response=read('/api/cmd?val=STOP')
after=read('/api/telemetry')
assert after['control']['stop_confirmed'] and not after['control']['armed']
assert after['control']['d0_age_s']<=.25
out=root/'runtime_trial'/('retire_'+str(time.time_ns())+'.json')
out.write_text(json.dumps({'before':before,'stop':response,'after':after}),encoding='utf8')
pid=int((root/'runtime_trial/brain.pid').read_text())
assert pathlib.Path(f'/proc/{pid}/cwd').resolve()==root
os.kill(pid,signal.SIGTERM)
limit=time.monotonic()+4
while pathlib.Path(f'/proc/{pid}').exists() and time.monotonic()<limit:time.sleep(.1)
assert not pathlib.Path(f'/proc/{pid}').exists(),'Controller still alive; do not replace'
print('UNUSED_TRIAL_RETIRED_WITH_CONFIRMED_STOP',out)
