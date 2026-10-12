import ast,datetime,difflib,hashlib,json,pathlib,re,shutil,subprocess
evidence=pathlib.Path(__file__).resolve().parent
root=evidence.parents[1]
log=(evidence/'speed_manual_final_python.log').read_text(encoding='utf-8-sig')
assert re.search(r'Ran 90 tests in 17\.809s',log) and log.rstrip().endswith('OK')
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
remote='/home/khangho/agv_codex_manual_cruise_'+stamp
bundle=evidence/'bundle_manual_cruise';bundle.mkdir(exist_ok=False)
files=['agv_unified_brain.py','agv_command_session.py','agv_navigation.py',
       'agv_command_journal.py','agv_preflight_static_collector.py','index_cyberpunk.html']
hashes={}
for name in files:
    content=(root/name).read_bytes();hashes[name]=hashlib.sha256(content).hexdigest()
    if name.endswith('.py'):ast.parse(content,filename=name)
    shutil.copy2(root/name,bundle/name)
    before=(evidence/'bundle_body'/name).read_text(encoding='utf8').splitlines(True)
    after=content.decode('utf8').splitlines(True)
    (evidence/(name+'.manual_cruise.diff')).write_text(''.join(difflib.unified_diff(before,after,
        fromfile='body/'+name,tofile='manual_cruise/'+name)),encoding='utf8')
shutil.copy2(evidence/'bundle_body/slam_scan_fix.yaml',bundle/'slam_scan_fix.yaml')
hashes['slam_scan_fix.yaml']=hashlib.sha256((bundle/'slam_scan_fix.yaml').read_bytes()).hexdigest()
js=re.search(r'<script>([\s\S]*?)</script>',(bundle/'index_cyberpunk.html').read_text(encoding='utf8')).group(1)
js_path=evidence/'dashboard_manual_cruise.js';js_path.write_text(js,encoding='utf8')
results=[]
for cmd in (['node','--check',str(js_path)],['node',str(root/'tests/test_agv_pid_ui.cjs')]):
    r=subprocess.run(cmd,cwd=root,capture_output=True,text=True)
    results.append({'command':cmd,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    assert r.returncode==0
after={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
assert all(after[name]==hashes[name] for name in files)
(bundle/'sources.sha256').write_text(''.join(f'{h}  {name}\n' for name,h in hashes.items()),encoding='ascii')
(evidence/'manual_cruise_verification.json').write_text(json.dumps({'remote':remote,'hashes':hashes,
    'hash_after':after,'hash_stable':True,'python':{'count':90,'seconds':17.809,'exit':0,
    'log':'speed_manual_final_python.log'},'js':results,'limitations':'Offline proof, not physical cruise/coverage acceptance.'},indent=2),encoding='utf8')
script='''#!/usr/bin/env bash
set -eo pipefail
cd REMOTE
test ! -e started_once
test "$(cat /proc/sys/kernel/random/boot_id)" = 6c0476e0-29bf-4510-a153-b7708dcbbec7
test "$(readlink -f /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0)" = /dev/ttyUSB0
if fuser /dev/ttyUSB0 >/dev/null 2>&1; then echo PORT_BUSY_NO_START; exit 1; fi
if ss -H -ltn 'sport = :8080' | grep -q .; then echo HTTP_BUSY_NO_START; exit 1; fi
test -d /proc/2073
test ! -d /proc/2107
sha256sum -c sources.sha256
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
python3 -B -c 'import agv_unified_brain,serial,rclpy,tf2_ros'
mkdir runtime
date -Is > started_once
nohup ros2 launch slam_toolbox online_async_launch.py slam_params_file:=REMOTE/slam_scan_fix.yaml use_sim_time:=false >runtime/slam.log 2>&1 < /dev/null &
printf '%s\\n' "$!" >runtime/slam.pid
sleep 1
AGV_BODY_RADIUS_M=0.20 AGV_BODY_BOUNDS_M=-0.16,-0.12,0.10,0.12 nohup python3 -B -u agv_unified_brain.py --operator-control >runtime/brain.log 2>&1 < /dev/null &
printf '%s\\n' "$!" >runtime/brain.pid
printf 'MANUAL_CRUISE_STARTED_DISARMED; PID=%s\\n' "$(cat runtime/brain.pid)"
'''.replace('REMOTE',remote)
(evidence/'start_manual_cruise.sh').write_text(script,encoding='utf8',newline='\n')
print(json.dumps({'remote':remote,'hashes':hashes}))
