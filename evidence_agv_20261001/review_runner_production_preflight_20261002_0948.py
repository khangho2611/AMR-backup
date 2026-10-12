"""OFFLINE actual production 10s/80 path, fake UART only, real advancing clock."""
import pathlib,sys,time,json,hashlib,tempfile,concurrent.futures
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import agv_motion_supervisor_runner as mod
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
p=ROOT/'agv_motion_supervisor_runner.py';before=hashlib.sha256(p.read_bytes()).hexdigest()
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_pwm=0,r_pwm=0,l_rpm=0.,r_rpm=0.,x=0.,y=0.,th=0.,v=0.,w=0.)
class UART:
 def __init__(self,name):self.name=name;self.writes=[];self.armed=False;self.ack=False;self.closed=False;self.n=0;self.received=[]
 def write(self,b):
  self.writes.append(dict(t=time.monotonic(),bytes=b.decode()))
  if b==b'ARM\n':self.armed=True;self.ack=True
  if b==b'STOP\n':self.armed=False
  return len(b)
 def flush(self):pass
 def close(self):self.closed=True
 def readline(self):
  self.n+=1
  if self.name=='gap_and_unknown' and self.n==15:time.sleep(1.0)
  else:time.sleep(.08 if not self.armed else .02)
  if self.ack:self.ack=False;packet={'ack':'ARM','state':'ARMED'}
  else:
   packet=dict(D0,safety='ARMED' if self.armed else 'DISARMED')
   if self.name=='unsafe_then_clean' and self.n==3:packet['l_pwm']=100
   if self.name=='gap_and_unknown' and self.n==4:packet={'unknown_unconfigured':'NOT_D0'}
  t=time.monotonic();self.received.append(dict(t=t,packet=packet));return (json.dumps(packet)+'\n').encode()
def run(name):
 u=UART(name);directory=tempfile.mkdtemp(prefix='agv_OFFLINE_production_0948_')
 r=mod.HardwareMotionRunner(mock_serial=None,output_dir=directory,nominal_time=.2,hard_time_cap=.5)
 # Replace ONLY lock and physical OPEN operations. mock_serial stays None: unscaled production preflight.
 r.acquire_port_lock=lambda:True
 def fake_open():r.ser=u;return True
 r.open_transport=fake_open
 started=time.monotonic();code=r.execute_lifecycle();arm=[x for x in u.writes if x['bytes']=='ARM\n']
 pre=[x for x in u.received if not arm or x['t']<arm[0]['t']]
 gaps=[b['t']-a['t'] for a,b in zip(pre,pre[1:])]
 files=list(pathlib.Path(directory).glob('*.json'));metadata=json.loads(files[0].read_text(encoding='utf-8')) if files else {}
 return dict(case=name,exit=code,elapsed=time.monotonic()-started,report=r.final_report,
  arm_count=len(arm),first_arm_elapsed=arm[0]['t']-started if arm else None,max_preflight_gap=max(gaps) if gaps else None,
  unsafe_seen=any(x['packet'].get('l_pwm')==100 for x in pre),unknown_seen=any('unknown_unconfigured' in x['packet'] for x in pre),
  closed=u.closed,gate_stop_confirmed=r.arbiter.stop_confirmed,runner_stop_confirmed=r.supervisor.stop_confirmed,
  evidence_status=metadata.get('final_report',{}).get('status'),tx_records=len(metadata.get('tx_records',[])),writes=u.writes)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:cases=list(pool.map(run,['unsafe_then_clean','gap_and_unknown']))
# Independent caller-silent watchdog/reader component, full actual gate ARM protocol; no gate flags fabricated.
u=UART('component');r=mod.HardwareMotionRunner(mock_serial=u,hard_time_cap=.15,nominal_time=.1)
r.ser=u;r.arbiter=SerialArbiterGateV3(mock_serial=u);r.supervisor=mod.MotionSupervisor(r.arbiter,nominal_time_s=.1,hard_time_cap_s=.15)
import threading
r.running=True;r.reader_thread=threading.Thread(target=r.reader_loop,daemon=True);r.reader_thread.start()
assert r.d0_event.wait(1);assert r.arbiter.arm_control_session('OFFLINE_COMPONENT_AUTH',time.monotonic())[0]
deadline=time.monotonic()+1
while r.arbiter.stop_latched and time.monotonic()<deadline:time.sleep(.01)
assert r.supervisor.start_motion(time.monotonic())
r.watchdog_thread=threading.Thread(target=r.watchdog_loop,daemon=True);r.watchdog_thread.start()
time.sleep(.5)
cases.append(dict(case='caller_silent_after_start_no_update_calls',tx=list(u.writes),gate_stop_confirmed=r.arbiter.stop_confirmed,
 runner_stop_confirmed=r.supervisor.stop_confirmed,fault_reason=r.supervisor.fault_reason,
 elapsed_since_stop=time.monotonic()-r.supervisor.stop_requested_mono if r.supervisor.stop_requested_mono else None))
r.running=False;r.reader_thread.join(.2);r.watchdog_thread.join(.2);u.close()
after=hashlib.sha256(p.read_bytes()).hexdigest();assert before==after
result=dict(scope='OFFLINE ONLY production unscaled 10s/80 path; physical OPEN/lock replaced with fake, ownership not tested; caller-silent component separate',before=before,after=after,stable=True,cases=cases)
with (ROOT/'evidence_agv_20261001/review_runner_production_preflight_20261002_0948.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(dict(stable=True,before=before,cases=[{k:v for k,v in c.items() if k not in ['writes','tx']} for c in cases]),ensure_ascii=False))
