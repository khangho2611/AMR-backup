"""Source QA OFFLINE: Fake stream and clock, isolated retained files, no hardware."""
import pathlib,sys,json,hashlib,tempfile,builtins,io
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import agv_preflight_static_collector as m
before=hashlib.sha256((ROOT/'agv_preflight_static_collector.py').read_bytes()).hexdigest()
OUT=pathlib.Path(tempfile.mkdtemp(prefix='parent_collector_2130_',dir=ROOT/'evidence_agv_20261001'))
d0=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0,r_rpm=0,l_pwm=0,r_pwm=0,x=0,y=0,th=0,v=0,w=0)
def line(data):return (json.dumps(data)+'\n').encode()
class Clock:
 def __init__(self):self.x=100.
 def mono(self):return self.x
 def sleep(self,dt):self.x+=dt
class Stream:
 def __init__(self,clock,lines):self.clock=clock;self.lines=list(lines);self.tx=[];self.closed=False
 def readline(self,size):self.clock.x+=.1;return self.lines.pop(0) if self.lines else b''
 def write(self,data):self.tx.append(data);raise AssertionError('TX attempted')
 def flush(self):self.tx.append('flush');raise AssertionError('TX attempted')
 def close(self):self.closed=True
cases=[]
def run(name,lines,write_failure=False):
 c=Clock();ser=Stream(c,lines)
 real_open=builtins.open
 def guarded_open(file,mode='r',*args,**kwargs):
  if write_failure and pathlib.Path(file).name.startswith('preflight_raw_evidence_'):raise PermissionError('offline evidence sink failure')
  return real_open(file,mode,*args,**kwargs)
 with patch.object(m,'MockSerialStream',return_value=ser),patch.object(m.time,'monotonic',side_effect=c.mono),patch.object(m.time,'sleep',side_effect=c.sleep),patch.object(m.time,'time',return_value=1700000000.),patch('builtins.open',side_effect=guarded_open):
  code,rep=m.run_preflight_collector(mock=True,wall_timeout_s=.5,min_observation_s=.05,min_samples=2,max_samples=2,output_dir=str(OUT))
 case=dict(id=name,code=code,report=rep,tx=list(ser.tx),closed=ser.closed);cases.append(case);return rep
rep=run('E1_positive', [line(d0)]*2)
f=pathlib.Path(rep['evidence_file']);first=f.read_bytes();parsed=json.loads(first)
case=cases[-1];case['records_have_raw_bytes']=all(any(k in q for k in ['raw_bytes','raw_hex','raw_base64']) for q in parsed['records'])
run('E2_write_failure_still_PASS',[line(d0)]*2,True)
rep=run('E3_filename_collision_overwrites',[line(dict(d0,x=1))]*2)
cases[-1]['same_file']=str(f)==rep['evidence_file'];cases[-1]['prior_evidence_changed']=f.read_bytes()!=first
run('E4_unsafe_midstream_no_evidence',[line(d0),line(dict(d0,l_pwm=1))])
# Whole unchanged CLI entry point through a fake stream; captures SystemExit.
c=Clock();ser=Stream(c,[line(d0)]*2)
with patch.object(m,'MockSerialStream',return_value=ser),patch.object(m.time,'monotonic',side_effect=c.mono),patch.object(m.time,'sleep',side_effect=c.sleep),patch.object(sys,'argv',['collector','--mock','--wall-timeout','.5','--min-obs','.05','--min-samples','2','--max-samples','2','--output-dir',str(OUT)]),patch.object(sys,'stdout',new_callable=io.StringIO) as stdout:
 try:m.main()
 except SystemExit as e:code=e.code
cases.append(dict(id='CLI_positive_fake',exit_code=code,stdout=stdout.getvalue(),tx=ser.tx,closed=ser.closed))
assert cases[0]['code']==0 and not cases[0]['tx'] and cases[0]['closed']
assert cases[4]['exit_code']==0 and not cases[4]['tx'] and cases[4]['closed']
out=dict(scope='OFFLINE unchanged source/fakeStream/clock only; collision and sink faults isolated in retained directory',before=before,after=hashlib.sha256((ROOT/'agv_preflight_static_collector.py').read_bytes()).hexdigest(),output_dir=str(OUT),cases=cases)
with (ROOT/'evidence_agv_20261001/review_collector_contract_2130.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2,ensure_ascii=False)
print(json.dumps(out,ensure_ascii=False))
