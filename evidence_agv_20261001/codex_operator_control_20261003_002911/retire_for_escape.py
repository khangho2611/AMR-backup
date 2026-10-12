import json,os,pathlib,signal,subprocess,sys,time,urllib.request
root=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '/home/khangho/agv_codex_operator_20261003_002911')
assert str(root) in ('/home/khangho/agv_codex_operator_20261003_002911','/home/khangho/agv_codex_escape_20261003_0044')
pid=int((root/'runtime/brain.pid').read_text())
proc=pathlib.Path('/proc')/str(pid)
assert (proc/'cwd').resolve()==root
assert b'--operator-control' in (proc/'cmdline').read_bytes()
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='6c0476e0-29bf-4510-a153-b7708dcbbec7'
def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=3))
out={'before':get('/api/telemetry'),'diagnostics':get('/api/diagnostics')}
out['stop']=({'reason':'ALREADY_CONFIRMED'} if out['before']['control']['stop_confirmed'] and
              out['before']['control']['latest_d0']['safety']=='DISARMED' else get('/api/cmd?val=STOP'))
out['after_stop']=get('/api/telemetry')
assert out['after_stop']['control']['stop_confirmed']
assert out['after_stop']['control']['stop_write_ok']
os.kill(pid,signal.SIGTERM)
for _ in range(40):
    if not proc.exists():break
    if (proc/'stat').read_text().split()[2]=='Z':break
    time.sleep(.1)
out['owner']=subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True).stdout.strip()
assert not out['owner'],'MCU port still owned; do not start another controller'
out['retired_pid']=pid
print(json.dumps(out))
