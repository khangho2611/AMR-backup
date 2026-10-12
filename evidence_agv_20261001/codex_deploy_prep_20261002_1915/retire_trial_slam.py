import os
import pathlib
import signal
import subprocess
import time

parent=int(pathlib.Path('runtime_trial/slam.pid').read_text())
cmd=pathlib.Path(f'/proc/{parent}/cmdline').read_bytes().replace(b'\0',b' ')
assert b'slam_toolbox online_async_launch.py' in cmd
children=subprocess.run(['pgrep','-P',str(parent)],capture_output=True,text=True).stdout.split()
targets=[parent]
for child in children:
    c=pathlib.Path(f'/proc/{child}/cmdline').read_bytes()
    assert b'async_slam_toolbox_node' in c
    targets.append(int(child))
for pid in targets:
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:pass
limit=time.monotonic()+4
while any(pathlib.Path(f'/proc/{pid}').exists() for pid in targets) and time.monotonic()<limit:time.sleep(.1)
assert not any(pathlib.Path(f'/proc/{pid}').exists() for pid in targets)
print('OLD_TRIAL_SLAM_RETIRED',targets)
