import json, os, signal, subprocess, time
pid=14214
expected_cwd='/home/khangho/agv_codex_20261002_1915'
expected_cmd='python3 -B -u agv_unified_brain.py --motion-window-s 15'
def proc_cwd(p):
    try: return os.readlink(f'/proc/{p}/cwd')
    except OSError: return None
def proc_cmd(p):
    try:
        b=open(f'/proc/{p}/cmdline','rb').read()
        return b.replace(b'\0',b' ').decode('utf-8','replace').strip()
    except OSError: return None
def fuser():
    r=subprocess.run(['fuser','-v','/dev/ttyUSB0'],text=True,capture_output=True,timeout=3)
    return {'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
pre={'pid':pid,'cwd':proc_cwd(pid),'cmd':proc_cmd(pid),'fuser':fuser()}
pre['verified']=pre['cwd']==expected_cwd and pre['cmd']==expected_cmd and str(pid) in (pre['fuser']['stdout']+pre['fuser']['stderr'])
result={'captured_unix':time.time(),'pre':pre}
if not pre['verified']:
    result['action']='REFUSED_IDENTITY_MISMATCH'
else:
    os.kill(pid,signal.SIGTERM)
    result['action']='SIGTERM_EXACT_PID'
    deadline=time.monotonic()+8
    while time.monotonic()<deadline and os.path.exists(f'/proc/{pid}'):
        time.sleep(.2)
    result['process_gone']=not os.path.exists(f'/proc/{pid}')
    result['fuser_after']=fuser()
    result['post_cwd']=proc_cwd(pid)
    result['post_cmd']=proc_cmd(pid)
print(json.dumps(result,ensure_ascii=False))
