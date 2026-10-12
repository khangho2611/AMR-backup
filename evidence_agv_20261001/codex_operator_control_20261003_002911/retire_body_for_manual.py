"""One confirmed STOP and bounded retirement of verified controller/SLAM."""
import json,os,pathlib,signal,subprocess,time,urllib.request
root=pathlib.Path('/home/khangho/agv_codex_body_20261003_0106')
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='6c0476e0-29bf-4510-a153-b7708dcbbec7'
pid=int((root/'runtime/brain.pid').read_text());proc=pathlib.Path(f'/proc/{pid}')
assert pid==11643 and (proc/'cwd').resolve()==root
assert b'--operator-control' in (proc/'cmdline').read_bytes()
def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/'+path,timeout=3))
out={'before':get('telemetry'),'map':get('map_full'),'diagnostics':get('diagnostics')}
out['stop']=get('cmd?val=STOP')
for _ in range(20):
    out['after_stop']=get('telemetry');c=out['after_stop']['control'];d=c['latest_d0']
    if c['stop_confirmed'] and c['stop_write_ok'] and c['d0_age_s']<=.25 and d['safety']=='DISARMED' and all(d[k]==0 for k in ('l_tgt','r_tgt','l_rpm','r_rpm','l_pwm','r_pwm','v','w')):break
    time.sleep(.1)
else:raise RuntimeError('STOP_NOT_CONFIRMED_DO_NOT_RESTART')
os.kill(pid,signal.SIGTERM)
for _ in range(40):
    if not proc.exists() or (proc/'stat').read_text().split()[2]=='Z':break
    time.sleep(.1)
owner=subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True)
assert owner.returncode==1 and not owner.stdout.strip(),'MCU owner not released'
out['retired_controller']=pid
# A new MCU OPEN resets odometry. Start a new SLAM epoch rather than feeding
# that discontinuity into the previous map. Keep the LiDAR/static TF running.
old=pathlib.Path('/home/khangho/agv_codex_operator_20261003_002911/runtime')
launch=int((old/'slam.pid').read_text());launch_proc=pathlib.Path(f'/proc/{launch}')
assert b'online_async_launch.py' in (launch_proc/'cmdline').read_bytes()
assert b'slam_toolbox' in (launch_proc/'cmdline').read_bytes()
os.kill(launch,signal.SIGINT)
for _ in range(100):
    child=pathlib.Path('/proc/2107')
    child_dead=not child.exists() or (child/'stat').read_text().split()[2]=='Z'
    launch_dead=not launch_proc.exists() or (launch_proc/'stat').read_text().split()[2]=='Z'
    if child_dead and launch_dead:break
    time.sleep(.1)
else:raise RuntimeError('OLD_SLAM_NOT_RETIRED_NO_NEW_START')
out['retired_slam_launch']=launch;out['retired_slam_node']=2107
print(json.dumps(out))
