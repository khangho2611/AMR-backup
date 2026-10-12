"""OFFLINE actual HardwareMotionRunner + actual gate, responsive fake UART only."""
import hashlib,json,pathlib,sys,time,tempfile,subprocess,threading
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import agv_motion_supervisor_runner as mod
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
p=ROOT/'agv_motion_supervisor_runner.py';before=hashlib.sha256(p.read_bytes()).hexdigest()
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_pwm=0,r_pwm=0,l_rpm=0.,r_rpm=0.,x=0.,y=0.,th=0.,v=0.,w=0.)
class UART:
 def __init__(self,case):self.case=case;self.armed=False;self.ack=False;self.writes=[];self.closed=False;self.lock=threading.Lock()
 def write(self,b):
  with self.lock:
   self.writes.append(dict(t=time.monotonic(),bytes=b.decode()))
   if b==b'ARM\n':self.armed=True;self.ack=True
   if b in [b'STOP\n',b'DISARM\n']:self.armed=False
  return len(b)
 def flush(self):pass
 def close(self):self.closed=True
 def readline(self):
  time.sleep(.02)
  with self.lock:
   if self.ack:self.ack=False;return b'{"ack":"ARM","state":"ARMED"}\n'
   d=dict(D0,safety='ARMED' if self.armed else 'DISARMED')
   if self.armed and self.case=='overspeed':d.update(l_rpm=100.,r_rpm=100.)
   if self.case=='boot_error':d['error']='MKE_M18_INIT_FAILED';d['fault']=True
   return (json.dumps(d)+'\n').encode()
cases=[]
for name,opts in [('normal',{}),('overspeed',{}),('boot_error',{}),('negative_duration',{'nominal_time':-.1})]:
 u=UART(name);out=tempfile.mkdtemp(prefix='agv_OFFLINE_0915_');counts={}
 original=SerialArbiterGateV3.process_incoming_line
 def tracked(g,line,now):
  key=(line,now);counts[key]=counts.get(key,0)+1
  return original(g,line,now)
 r=mod.HardwareMotionRunner(mock_serial=u,output_dir=out,nominal_time=.15,hard_time_cap=.5)
 for k,v in opts.items():setattr(r,k,v)
 started=time.monotonic()
 with patch.object(SerialArbiterGateV3,'process_incoming_line',tracked):
  try:code=r.execute_lifecycle();error=None
  except Exception as e:code=None;error=type(e).__name__+':'+str(e)
 report=dict(r.final_report)
 cases.append(dict(case=name,code=code,error=error,elapsed=time.monotonic()-started,report=report,
  closed=u.closed,arm_writes=sum(x['bytes']=='ARM\n' for x in u.writes),velocity_writes=sum(x['bytes'].startswith('V ') for x in u.writes),
  stop_confirmed=r.supervisor.stop_confirmed if r.supervisor else None,fault=r.supervisor.fault_reason if r.supervisor else None,
  duplicated_same_rx=max(counts.values()) if counts else 0,evidence_files=len(list(pathlib.Path(out).glob('*.json'))),
  records=len(r.evidence_records),tx_records=len(r.tx_records),writes=u.writes))
q=subprocess.run([sys.executable,'-X','utf8',str(p),'--mock','--output-dir',tempfile.mkdtemp(prefix='agv_OFFLINE_CLI_0915_')],capture_output=True,text=True,timeout=5)
after=hashlib.sha256(p.read_bytes()).hexdigest();assert before==after
result=dict(scope='OFFLINE ONLY injected responsive fake UART; actual runtime+gate, no serial.Serial/connect',before=before,after=after,stable=True,
 cases=cases,cli_proposed_output_dir=dict(exit=q.returncode,stderr=q.stderr,stdout=q.stdout))
dest=ROOT/'evidence_agv_20261001/review_executable_runner_20261002_0915.json'
with dest.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
