"""Independent offline collector contract QA; no Serial or motor hardware."""
import json,pathlib,sys,tempfile,hashlib,types
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import agv_preflight_static_collector as m
before=hashlib.sha256((ROOT/'agv_preflight_static_collector.py').read_bytes()).hexdigest()
OUT=pathlib.Path(tempfile.mkdtemp(prefix='parent_collector_2152_',dir=ROOT/'evidence_agv_20261001'))
d0=dict(safety='DISARMED',l_tgt=0,r_tgt=0,l_pwm=0,r_pwm=0,l_rpm=0,r_rpm=0,x=0,y=0,th=0,v=0,w=0)
def line(d):return (json.dumps(d)+'\n').encode()
class Clock:
 def __init__(self):self.x=100.
 def mono(self):return self.x
 def sleep(self,x):self.x+=x
class Stream:
 def __init__(self,c,lines):self.c=c;self.lines=list(lines);self.closed=False;self.tx=[]
 def readline(self,size):self.c.x+=.1;return self.lines.pop(0) if self.lines else b''
 def close(self):self.closed=True
 def write(self,x):self.tx.append(x);raise AssertionError('TX attempted')
class Lock:
 def __init__(self):self.closed=False
 def close(self):self.closed=True
cases=[]
def run(name,lines,port_case=None):
 c=Clock();ser=Stream(c,lines);lock=Lock();caught=None;code=None;report=None
 ser.open=lambda:None
 if port_case=='partial_open':
  def fail_open():raise OSError('fake partially opened port failure')
  ser.open=fail_open
 if port_case=='close_error':
  def fail_close():raise OSError('fake close failure')
  ser.close=fail_close
 with patch.object(m,'MockSerialStream',return_value=ser),patch.object(m,'acquire_port_lock',return_value=(lock,None)),patch.dict(sys.modules,{'serial':types.SimpleNamespace(Serial=lambda:ser)}),patch.object(m.time,'monotonic',side_effect=c.mono),patch.object(m.time,'sleep',side_effect=c.sleep):
  try:code,report=m.run_preflight_collector(mock=port_case is None,wall_timeout_s=.8,min_observation_s=.05,min_samples=2,max_samples=2,max_gap_s=.15,output_dir=str(OUT))
  except Exception as e:caught=type(e).__name__+': '+str(e)
 data=None
 if report and report.get('evidence_file') and pathlib.Path(report['evidence_file']).is_file():data=json.loads(pathlib.Path(report['evidence_file']).read_text(encoding='utf-8'))
 cases.append(dict(id=name,code=code,report=report,evidence=data,exception=caught,stream_closed=ser.closed,lock_closed=lock.closed,tx=ser.tx))
run('E4_unsafe_raw_and_count',[line(d0),line(dict(d0,l_pwm=1))])
run('F_gap_evidence',[line(d0)])
run('F_corrupt_evidence',[line(d0),b'corrupt\n'])
run('F_partial_open_cleanup',[],port_case='partial_open')
run('F_close_error_cleanup',[line(d0),line(d0)],port_case='close_error')
out=dict(scope='OFFLINE actual collector + fake stream/port/clock; no hardware',before=before,after=hashlib.sha256((ROOT/'agv_preflight_static_collector.py').read_bytes()).hexdigest(),output_dir=str(OUT),cases=cases)
with (ROOT/'evidence_agv_20261001/review_collector_residual_2152.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
print(json.dumps(out,ensure_ascii=False))
