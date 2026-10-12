"""Independent source QA, actual collector CLI/gate, fake transport/clock only."""
import pathlib,sys,json,hashlib,tempfile,io
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import agv_preflight_static_collector as m
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
from agv_motion_supervisor_runner import MotionSupervisor
files=['agv_preflight_static_collector.py','agv_motion_supervisor_runner.py','agv_serial_arbiter_bridge_v3.py']
def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
before=hashes();cases=[]
outdir=pathlib.Path(tempfile.mkdtemp(prefix='parent_startup_0835_',dir=ROOT/'evidence_agv_20261001'))
d0=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_pwm=0,r_pwm=0,l_rpm=0,r_rpm=0,v=0,w=0,x=0,y=0,th=0)
def line(d):return (json.dumps(d)+'\n').encode()
ready=line({'info':m.EXACT_BOOT_BANNER});scan=line({'info':m.EXACT_I2C_SCAN_BANNER})
found=line({'i2c_found':'0x42'});vin=line({'vin_mv':12000})
raw=json.loads((ROOT/'evidence_agv_20261001/preflight_raw_evidence_1790903955404_1548_0.json').read_text())
actual=[bytes.fromhex(r['raw_hex']) for r in raw['records']]
class Clock:
 def __init__(self):self.t=100.
 def mono(self):return self.t
 def sleep(self,t):self.t+=t
class Stream:
 def __init__(self,c,lines):self.c=c;self.lines=list(lines);self.closed=False;self.tx=[]
 def readline(self,size):self.c.t+=.1;return self.lines.pop(0) if self.lines else b''
 def close(self):self.closed=True
 def write(self,data):self.tx.append(data);raise AssertionError('TX prohibited')
 def flush(self):raise AssertionError('TX prohibited')
def run(name,lines,expected):
 c=Clock();s=Stream(c,lines)
 argv=['collector','--mock','--wall-timeout','15','--min-obs','10','--min-samples','80','--max-samples','120','--output-dir',str(outdir)]
 with patch.object(m,'MockSerialStream',return_value=s),patch.object(m.time,'monotonic',side_effect=c.mono),patch.object(m.time,'sleep',side_effect=c.sleep),patch.object(sys,'argv',argv),patch.object(sys,'stdout',new_callable=io.StringIO) as stdout:
  try:m.main()
  except SystemExit as e:code=e.code
 rep=json.loads(stdout.getvalue());ev=json.loads(pathlib.Path(rep['evidence_file']).read_text()) if rep.get('evidence_file') else None
 recs=ev['records'] if ev else []
 diag=[x['rx_mono'] for x in recs if x.get('classification')=='VIN_MV']
 good=[x['rx_mono'] for x in recs if x.get('payload',{} ) and x['payload'].get('safety')=='DISARMED' and not x.get('error')]
 cases.append(dict(id=name,expected_exit=expected,actual_exit=code,meets_expectation=code==expected,report=rep,post_diagnostic_D0_span=(good[-1]-next((v for v in good if v>diag[-1]),good[-1])) if diag and good else None,tx=list(s.tx),closed=s.closed,evidence_file=rep.get('evidence_file')))
tail=[line(d0)]*120
run('C0_actual_raw26_then_source_diagnostics_then_stable_D0',actual+[found,vin]+tail,0)
run('C1_repeated_scanning_within_startup',[ready,scan,scan,found,vin]+tail,1)
run('C2_found_without_scan_bad_address',[ready,line({'i2c_found':'arbitrary'})]+tail,1)
run('C3_vin_nan',[ready,scan,found,line({'vin_mv':float('nan')})]+tail,1)
run('C4_vin_bool',[ready,scan,found,line({'vin_mv':True})]+tail,1)
run('C5_vin_negative',[ready,scan,found,line({'vin_mv':-1})]+tail,1)
run('C6_error_after_scan',[ready,scan,line({'error':'No I2C device found'})]+tail,1)
run('C7_unsafe_mixed_diagnostic',[ready,scan,line(dict(d0,vin_mv=12000,l_pwm=1))]+tail,1)
run('C8_late_diagnostic',[ready]+[line(d0)]*40+[scan]+tail,1)
class FakeSerial:
 def __init__(self):self.writes=[];self.fail=False
 def write(self,data):
  self.writes.append(data.decode())
  if self.fail:raise OSError('offline write failure')
  return len(data)
 def flush(self):pass
def setup():
 s=FakeSerial();g=SerialArbiterGateV3(mock_serial=s)
 g.process_incoming_line(json.dumps(d0),100.)
 assert g.arm_control_session('offline_authorized',100.01)[0]
 g.process_incoming_line('{"ack":"ARM","state":"ARMED"}',100.02)
 g.process_incoming_line(json.dumps(dict(d0,safety='ARMED')),100.03)
 r=MotionSupervisor(g);assert r.start_motion(100.04)
 s.writes.clear();return r,g,s
r,g,s=setup();v=r.update_cycle(100.05,dict(d0,safety='ARMED'))
cases.append(dict(id='R0_actual_gate_positive_velocity',result=v,tx=list(s.writes)))
r,g,s=setup();s.fail=True;r.trigger_estop(100.05,'offline_failure');v=r.update_cycle(100.06,{'safety':'DISARMED','rx_mono':90.,'l_pwm':100,'l_tgt':100})
cases.append(dict(id='R1_failed_STOP_stale_unsafe_D0',result=v,runner_confirmed=r.stop_confirmed,gate_confirmed=g.stop_confirmed,gate_state=g.safety_state,tx=list(s.writes)))
r,g,s=setup();r.trigger_estop(100.05,'offline_stop');v=r.update_cycle(100.06,dict(d0,rx_mono=90.))
cases.append(dict(id='R2_stale_D0_without_gate_parser',result=v,runner_confirmed=r.stop_confirmed,gate_confirmed=g.stop_confirmed,tx=list(s.writes)))
r,g,s=setup();v=r.update_cycle(100.05,{})
cases.append(dict(id='R3_missing_telemetry',result=v,tx=list(s.writes)))
r,g,s=setup();vals=[r.update_cycle(100.05,dict(d0,safety='ARMED')) for _ in range(7)]
cases.append(dict(id='R4_same_clock_repeated_ramp',results=vals,cmd_v=r.current_cmd_v,tx=list(s.writes)))
after=hashes();assert before==after
assert all(not x['tx'] and x['closed'] for x in cases if x['id'].startswith('C'))
out=dict(scope='OFFLINE ONLY; actual collector main + actual gate protocol with fake transport/clock; no connect/hardware',before=before,after=after,stable=before==after,cases=cases)
with (ROOT/'evidence_agv_20261001/review_startup_runner_20261002_0835.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(dict(before=before,stable=True,cases=[{k:v for k,v in x.items() if k not in ['report','evidence_file']} for x in cases]),ensure_ascii=False))
