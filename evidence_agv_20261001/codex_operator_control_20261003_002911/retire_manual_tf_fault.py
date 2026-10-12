import json,os,pathlib,signal,subprocess,time,urllib.request
root=pathlib.Path('/home/khangho/agv_codex_manual_cruise_20261003_011949')
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='6c0476e0-29bf-4510-a153-b7708dcbbec7'
pid=int((root/'runtime/brain.pid').read_text());p=pathlib.Path(f'/proc/{pid}')
assert pid==27620 and (p/'cwd').resolve()==root
def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/'+path,timeout=3))
out={'before':get('telemetry'),'map':get('map_full'),'diagnostics':get('diagnostics')}
c=out['before']['control'];d=c['latest_d0']
assert not c['armed'] and not out['before']['auto'] and c['d0_age_s']<=.25
assert d['safety']=='DISARMED' and all(d[k]==0 for k in ('l_tgt','r_tgt','l_rpm','r_rpm','l_pwm','r_pwm','v','w'))
assert c['stop_confirmed'] and c['stop_write_ok']
os.kill(pid,signal.SIGTERM)
for _ in range(40):
    if not p.exists() or (p/'stat').read_text().split()[2]=='Z':break
    time.sleep(.1)
owner=subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True)
assert owner.returncode==1 and not owner.stdout.strip()
out['retired_pid']=pid;out['owner_released']=True
print(json.dumps(out))
