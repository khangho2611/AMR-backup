import json,os,pathlib,signal,subprocess,time
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='6c0476e0-29bf-4510-a153-b7708dcbbec7'
owner=subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True)
assert owner.returncode==1 and not owner.stdout.strip()
body=pathlib.Path('/home/khangho/agv_codex_body_20261003_0106')
journal=body/'logs/command_outcomes.jsonl'
records=[json.loads(line) for line in journal.read_text().splitlines()[-4:]]
out={'controller_port_released':True,'recent_command_outcomes':records,'processes':[]}
old=pathlib.Path('/home/khangho/agv_codex_operator_20261003_002911/runtime')
launch=int((old/'slam.pid').read_text())
for pid,token in ((2107,b'async_slam_toolbox_node'),(launch,b'online_async_launch.py')):
    p=pathlib.Path(f'/proc/{pid}')
    if not p.exists() or (p/'stat').read_text().split()[2]=='Z':continue
    command=(p/'cmdline').read_bytes()
    assert token in command and b'slam_toolbox' in command
    record={'pid':pid,'cmdline':command.decode().replace('\0',' '),'signal':'SIGTERM'}
    os.kill(pid,signal.SIGTERM)
    for _ in range(40):
        if not p.exists() or (p/'stat').read_text().split()[2]=='Z':break
        time.sleep(.1)
    else:
        # Only this verified non-motor SLAM process; MCU owner is already gone.
        assert token in (p/'cmdline').read_bytes()
        os.kill(pid,signal.SIGKILL);record['signal']='SIGTERM_THEN_SIGKILL'
        time.sleep(.2)
    record['retired']=not p.exists() or (p/'stat').read_text().split()[2]=='Z'
    assert record['retired'];out['processes'].append(record)
print(json.dumps(out))
