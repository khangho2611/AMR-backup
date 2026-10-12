import json, os, signal, subprocess, time
pid=23834
expected_cwd='/home/khangho/agv_codex_diag_20261002_201411'
expected_cmd='python3 -B -u agv_unified_brain.py --motion-window-s 15'
def cwd(p):
    try: return os.readlink(f'/proc/{p}/cwd')
    except OSError: return None
def cmd(p):
    try: return open(f'/proc/{p}/cmdline','rb').read().replace(b'\0',b' ').decode('utf-8','replace').strip()
    except OSError: return None
def fuser():
    r=subprocess.run(['fuser','-v','/dev/ttyUSB0'],text=True,capture_output=True,timeout=3)
    return {'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
pre={'pid':pid,'cwd':cwd(pid),'cmd':cmd(pid),'fuser':fuser()}
pre['verified']=pre['cwd']==expected_cwd and pre['cmd']==expected_cmd and str(pid) in (pre['fuser']['stdout']+pre['fuser']['stderr'])
out={'pre':pre,'action':'REFUSED_IDENTITY_MISMATCH'}
if pre['verified']:
    os.kill(pid,signal.SIGTERM)
    out['action']='SIGTERM_EXACT_PID'
    deadline=time.monotonic()+8
    while time.monotonic()<deadline and os.path.exists(f'/proc/{pid}'):
        time.sleep(.2)
    out['process_gone']=not os.path.exists(f'/proc/{pid}')
    out['fuser_after']=fuser()
    out['post_cwd']=cwd(pid); out['post_cmd']=cmd(pid)
print(json.dumps(out,ensure_ascii=False))
