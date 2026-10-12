"""Read-only observation of the active AUTO owner; sends no commands."""
import datetime,json,pathlib,time,urllib.request
root=pathlib.Path('/home/khangho/agv_codex_body_20261003_0106')
pid=int((root/'runtime/brain.pid').read_text())
assert pathlib.Path(f'/proc/{pid}/cwd').resolve()==root
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='6c0476e0-29bf-4510-a153-b7708dcbbec7'
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pid':pid,'samples':[]}
start=time.monotonic()
while time.monotonic()-start<12:
    with urllib.request.urlopen('http://127.0.0.1:8080/api/telemetry',timeout=3) as response:
        d=json.load(response)
    out['samples'].append({'elapsed':time.monotonic()-start,'auto':d['auto'],
                           'status':d['status'],'robot':d['robot'],'map':d['map_info'],
                           'control':d['control'],'min_m':d['min_m']})
    time.sleep(.15)
with urllib.request.urlopen('http://127.0.0.1:8080/api/diagnostics',timeout=3) as response:
    out['diagnostics']=json.load(response)
print(json.dumps(out))
