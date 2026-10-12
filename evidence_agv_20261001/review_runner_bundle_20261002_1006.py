"""Independent OFFLINE QA of unscaled production path; no hardware OPEN/connect."""
import pathlib,sys,time,json,tempfile,hashlib,concurrent.futures
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import agv_motion_supervisor_runner as mod
P=ROOT/'agv_motion_supervisor_runner.py';before=hashlib.sha256(P.read_bytes()).hexdigest()
assert before=='01903753bb7855d119e490e6899e6a82fd60b5a9b39454b2eef3f3bebb7a8113',before
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_pwm=0,r_pwm=0,l_rpm=0.,r_rpm=0.,x=0.,y=0.,th=0.,v=0.,w=0.)
class UART:
 def __init__(self,name):
  self.name=name;self.writes=[];self.received=[];self.armed=False;self.ack=False;self.closed=False;self.n=0
  self.startup=[{'info':mod.EXACT_BOOT_BANNER},{'info':mod.EXACT_I2C_SCAN_BANNER}]
  if name!='scan_without_found':self.startup += [{'i2c_found':'0x42'},{'vin_mv':12033}]
  if name=='arbitrary_corrupt_boot':self.startup.insert(0,'THIS IS NOT ANY FIRMWARE ROM LINE')
 def write(self,b):
  self.writes.append(dict(t=time.monotonic(),bytes=b.decode()))
  if b==b'ARM\n':self.armed=True;self.ack=True
  if b in [b'STOP\n',b'DISARM\n']:self.armed=False
  return len(b)
 def flush(self):pass
 def close(self):self.closed=True
 def readline(self):
  self.n+=1;time.sleep(1.0 if self.name=='gap_1s_only' and self.n==15 else (.02 if self.armed else .08))
  if self.startup:packet=self.startup.pop(0)
  elif self.ack:self.ack=False;packet={'ack':'ARM','state':'ARMED'}
  else:
   packet=dict(D0,safety='ARMED' if self.armed else 'DISARMED')
   if self.name=='unsafe_pwm_then_clean' and self.n==8:packet['l_pwm']=100
  self.received.append(dict(t=time.monotonic(),packet=packet))
  return ((packet if isinstance(packet,str) else json.dumps(packet))+'\n').encode()
def run(name):
 u=UART(name);out=tempfile.mkdtemp(prefix='agv_OFFLINE_bundle1006_')
 r=mod.HardwareMotionRunner(mock_serial=None,output_dir=out,nominal_time=.15,hard_time_cap=.5)
 r.acquire_port_lock=lambda:True
 def fake_open():r.ser=u;r.transport=mod.TransportWrapper(u);return True
 r.open_transport=fake_open
 started=time.monotonic();code=r.execute_lifecycle()
 arm=[x for x in u.writes if x['bytes']=='ARM\n'];stop=[x for x in u.writes if x['bytes']=='STOP\n']
 pre=[x for x in u.received if not arm or x['t']<arm[0]['t']]
 gaps=[b['t']-a['t'] for a,b in zip(pre,pre[1:])]
 files=list(pathlib.Path(out).glob('*.json'));metadata=json.loads(files[0].read_text(encoding='utf8')) if files else {}
 return dict(case=name,exit=code,elapsed=time.monotonic()-started,report=r.final_report,
  preflight_passed=r.preflight_passed,preflight_failed=r.preflight_failed,fsm_state=r.fsm_diag_state,
  arm_count=len(arm),velocity_count=sum(x['bytes'].startswith('V ') for x in u.writes),stop_count=len(stop),
  first_arm_elapsed=arm[0]['t']-started if arm else None,max_preflight_gap=max(gaps) if gaps else None,
  postdiag_count=len(r.preflight_valid_samples),postdiag_span=(r.preflight_last_mono-r.preflight_first_mono) if r.preflight_first_mono else None,
  gate_confirmed=r.arbiter.stop_confirmed,runner_confirmed=r.supervisor.stop_confirmed,fault=r.supervisor.fault_reason,
  closed=u.closed,evidence_status=metadata.get('final_report',{}).get('status'),tx_records=len(metadata.get('tx_records',[])),
  records=u.received,writes=u.writes)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 cases=list(pool.map(run,['positive_exact_startup','gap_1s_only','scan_without_found','arbitrary_corrupt_boot','unsafe_pwm_then_clean']))
after=hashlib.sha256(P.read_bytes()).hexdigest();assert before==after
result=dict(scope='OFFLINE actual execute_lifecycle/gate/reader/watchdog; ONLY physical OPEN and lock replaced; real advancing clock, no scaling of 10s/80 contract; no Serial/connect',before=before,after=after,stable=True,cases=cases)
dest=ROOT/'evidence_agv_20261001/review_runner_bundle_20261002_1006.json'
with dest.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(dict(stable=True,hash=before,cases=[{k:v for k,v in c.items() if k not in ['records','writes']} for c in cases]),ensure_ascii=False))
