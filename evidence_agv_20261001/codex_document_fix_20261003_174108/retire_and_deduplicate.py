"""One deployment, exact boot/controller; STOP only, no ARM or drive."""
import json,os,pathlib,signal,subprocess,tarfile,time,urllib.request,urllib.error
out=pathlib.Path('/home/khangho/agv_codex_document_20261003_174108')
old=pathlib.Path('/home/khangho/agv_codex_reader_20261003_0652')
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='4269f3dd-12c6-4330-9753-7cafc283ba5d'
p=pathlib.Path('/proc/52139')
assert pathlib.Path(os.readlink(p/'cwd'))==old
assert (p/'cmdline').read_bytes().split(b'\0')[:5]==[b'python3',b'-B',b'-u',b'agv_unified_brain.py',b'--operator-control']
assert not (out/'retirement.json').exists()
report={}
with tarfile.open(out/'previous_test_backup.tar','x') as archive:
 for name in ['agv_unified_brain.py','agv_command_session.py','agv_navigation.py','agv_command_journal.py','agv_preflight_static_collector.py','index_cyberpunk.html','slam_scan_fix.yaml','logs']:
  if (old/name).exists():archive.add(old/name,arcname=name)
def get(path):
 try:r=urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=3)
 except urllib.error.HTTPError as e:r=e
 return {'http':r.status,'data':json.load(r)}
report['map_before']=get('/api/map_full')
report['stop']=get('/api/cmd?val=STOP')
deadline=time.monotonic()+4
while time.monotonic()<deadline:
 t=get('/api/telemetry')['data'];h=t['control'];d=h['latest_d0']
 if (h['stop_confirmed'] and h['stop_write_ok'] and h['d0_age_s']<.25 and
     d['safety']=='DISARMED' and all(d[k]==0 for k in ['l_tgt','r_tgt','l_pwm','r_pwm','l_rpm','r_rpm','v','w'])):break
 time.sleep(.05)
else:raise RuntimeError('STOP NOT CONFIRMED; no retirement')
report['stopped']=h
os.kill(52139,signal.SIGTERM)
for _ in range(60):
 if not p.exists() or '\nState:\tZ' in (p/'status').read_text():break
 time.sleep(.1)
else:raise RuntimeError('controller did not retire; no forced kill')
assert subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True).returncode==1
# Keep the latest mapper/TF pair. Only duplicates in this exact deployment
# with the same frames/config are selected, never a global pkill ros2.
keep={52113,52122,52120,52244}
targets={}
for proc in pathlib.Path('/proc').iterdir():
 if not proc.name.isdigit() or int(proc.name) in keep:continue
 try:
  args=(proc/'cmdline').read_bytes().split(b'\0');pid=int(proc.name)
  if pathlib.Path(os.readlink(proc/'cwd'))!=old:continue
  tf=(b'static_transform_publisher' in args or args[0]==b'/opt/ros/jazzy/lib/tf2_ros/static_transform_publisher') and b'base_footprint' in args and b'laser' in args
  slam=(b'slam_toolbox' in args or args[0]==b'/opt/ros/jazzy/lib/slam_toolbox/async_slam_toolbox_node') and any(b'slam_scan_fix.yaml' in a for a in args)
  if tf or slam:targets[pid]=args
 except (OSError,IndexError):pass
report['retired_duplicates']=list(targets)
for pid,args in targets.items():
 proc=pathlib.Path('/proc')/str(pid)
 try:
  if (proc/'cmdline').read_bytes().split(b'\0')==args:os.kill(pid,signal.SIGINT)
 except ProcessLookupError:pass
time.sleep(2)
alive=[]
for pid,args in targets.items():
 try:
  if (pathlib.Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')==args:alive.append(pid)
 except OSError:pass
report['duplicates_still_alive']=alive
(out/'retirement.json').write_text(json.dumps(report,indent=2))
assert not alive,alive
print(json.dumps({k:v for k,v in report.items() if k!='map_before'}))
