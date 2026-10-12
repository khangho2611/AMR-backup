"""New source-linked OFFLINE residuals; no hardware or implementation edit."""
import json,pathlib,sys,hashlib
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=ROOT/'evidence_agv_20261001/review_startup_runner_20261002_0835.py'
ns={'__file__':str(p)};exec(p.read_text(encoding='utf-8').split('tail=')[0],ns)
tail=[ns['line'](ns['d0'])]*120
ns['run']('F0_optional_VIN_absent_source_positive',[ns['ready'],ns['scan'],ns['found']]+tail,0)
ns['run']('F1_scan_without_found_then_D0',[ns['ready'],ns['scan']]+tail,1)
ns['run']('F2_zero_address',[ns['ready'],ns['scan'],ns['line']({'i2c_found':'0x00'})]+tail,1)
ns['run']('F3_fractional_VIN',[ns['ready'],ns['scan'],ns['found'],ns['line']({'vin_mv':.5})]+tail,1)
ns['run']('F4_UINT32_overflow',[ns['ready'],ns['scan'],ns['found'],ns['line']({'vin_mv':2**32})]+tail,1)
ns['run']('F5_postdiag_observation_fixed',[ns['ready']]+[ns['line'](ns['d0'])]*20+[ns['scan'],ns['found'],ns['vin']]+tail,0)
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
from agv_motion_supervisor_runner import MotionSupervisor
d0=ns['d0'];cases=ns['cases']
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
for name,packet in [('T1_RPM_NaN',dict(d0,safety='ARMED',l_rpm=float('nan'),r_rpm=float('nan'),rx_mono=100.03)),('T2_RPM_corrupt',dict(d0,safety='ARMED',l_rpm='bad')),('T3_stale_data',dict(d0,safety='ARMED',rx_mono=90.))]:
 r,g,s=setup()
 try:ret=r.update_cycle(100.05,packet);err=None
 except Exception as e:ret=None;err=type(e).__name__
 cases.append(dict(id=name,result=ret,exception=err,active=r.is_active,tx=list(s.writes)))
r,g,s=setup();r.trigger_estop(100.05,'offline_stop')
packet=dict(d0,raw_line=json.dumps(d0))
ret=r.update_cycle(100.06,packet)
cases.append(dict(id='T4_missing_rx_replaced_by_now',result=ret,runner_confirmed=r.stop_confirmed,gate_confirmed=g.stop_confirmed,tx=list(s.writes)))
r,g,s=setup();r.trigger_estop(100.05,'offline_stop');ret=r.update_cycle(100.06,dict(d0,raw_line=json.dumps(d0),rx_mono=100.06))
cases.append(dict(id='T0_positive_explicit_fresh_D0',result=ret,runner_confirmed=r.stop_confirmed,gate_confirmed=g.stop_confirmed,tx=list(s.writes)))
r,g,s=setup();r.trigger_estop(100.05,'offline_stop')
for t in [100.1,100.2,100.3,100.4,100.5]:r.update_cycle(t,{})
cases.append(dict(id='T5_missing_data_resets_STOP_deadline',first_stop=100.05,last_stop=r.stop_requested_mono,last_gate_stop=g.last_stop_command_time,fault_reason=r.fault_reason,tx=list(s.writes)))
after=ns['hashes']();assert ns['before']==after
out=dict(scope='OFFLINE ONLY actual main CLI + actual gate protocol, fake transport/clock; no connect',before=ns['before'],after=after,stable=True,cases=cases)
with (ROOT/'evidence_agv_20261001/review_startup_runner_residual_20261002_0845.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(dict(before=out['before'],stable=True,cases=[{k:v for k,v in x.items() if k not in ['report','evidence_file']} for x in cases]),ensure_ascii=False))
