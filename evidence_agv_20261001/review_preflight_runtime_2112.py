"""OFFLINE unchanged product sources; fake Serial/clock only, exclusive evidence."""
import pathlib,sys,json,hashlib,types
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import agv_preflight_static_collector as m
import agv_ros2_runtime_adapter as r
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
files=['agv_preflight_static_collector.py','agv_ros2_runtime_adapter.py','agv_serial_arbiter_bridge_v3.py']
def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
before=hashes();cases=[]
d0=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0,r_rpm=0,l_pwm=0,r_pwm=0,x=0,y=0,th=0,v=0,w=0)
line=(json.dumps(d0)+'\n').encode()
class Clock:
 def __init__(self):self.x=100.
 def __call__(self):self.x+=.01;return self.x
for name,lines,extra in [('C1_burst_gap',[line]*30,{}),('C2_corrupt_after_safe',[line]*30+[b'{"safety":"ARMED"\n'],{}),('C4_NaN_gap_age',[line]*30,dict(max_gap_s=float('nan'),max_age_s=float('nan')))]:
 with patch.object(m.time,'monotonic',side_effect=Clock()),patch.object(m.time,'sleep',return_value=None):
  code,rep=m.run_preflight_collector(mock=True,mock_lines=lines,wall_timeout_s=15,min_samples=30,**extra)
 cases.append(dict(id=name,code=code,report=rep))
# Invalid primary duration is rejected before fake port open.
opens=[];clock={'x':100.}
class FakePort:
 def __init__(self):self.is_open=False
 def open(self):opens.append('open');clock['x']+=2.;self.is_open=True
 def readline(self,size):clock['x']+=.6;return line
 def close(self):self.is_open=False
fake_module=types.ModuleType('serial');fake_module.Serial=FakePort
with patch.dict(sys.modules,{'serial':fake_module}),patch.object(m.time,'monotonic',side_effect=lambda:clock['x']):
 code,rep=m.run_preflight_collector(mock=False,wall_timeout_s=-1)
cases.append(dict(id='C3_invalid_primary_duration',code=code,opens=list(opens)))
clock['x']=100.;opens.clear()
with patch.dict(sys.modules,{'serial':fake_module}),patch.object(m.time,'monotonic',side_effect=lambda:clock['x']):
 code,rep=m.run_preflight_collector(mock=False,wall_timeout_s=.1,min_samples=1,max_samples=1)
cases.append(dict(id='C5_read_and_open_budget',code=code,report=rep,total_wall=clock['x']-100.,opens=list(opens)))
# Reuse actual-constructor setup and protocol helper without rewriting earlier evidence.
ns={'__file__':str(ROOT/'evidence_agv_20261001/review_node_residual_2028.py')}
base=(ROOT/'evidence_agv_20261001/review_node_residual_2028.py').read_text(encoding='utf-8').split('for label,meta in')[0]
exec(compile(base,'prior_fake_protocol_setup','exec'),ns)
n,g,ser=ns['setup']()
with patch.object(r.time,'monotonic',return_value=100.06):n.destroy_node()
ok=n.adapter.parse_and_ingest(json.dumps(d0),rx_mono=100.08)
cases.append(dict(id='S1_fixed_adapter_D0',accepted=ok,gate_confirmed=g.stop_confirmed,public_confirmed=n.watchdog.last_stop_confirmed))
# Whole ingress must handle ARM ACK, not only telemetry. No pre-set lifecycle flags.
ser=ns['FakeSerial']();g=SerialArbiterGateV3(mock_serial=ser);n=r.AGVRos2RuntimeNode(serial_arbiter=g,is_mock=False)
first=n.adapter.parse_and_ingest(json.dumps(d0),rx_mono=100.)
requested=g.arm_control_session('fake_authorized_session',100.01)[0]
ack=n.adapter.parse_and_ingest('{"ack":"ARM","state":"ARMED"}',rx_mono=100.02)
armed=n.adapter.parse_and_ingest(json.dumps(dict(d0,safety='ARMED')),rx_mono=100.03)
cases.append(dict(id='P1_whole_adapter_ARM_ACK',first_D0=first,request=requested,ack_accepted=ack,armed_accepted=armed,gate_ACK=g.session_arm_ack_received,gate_stop_latched=g.stop_latched,writes=list(ser.writes)))
assert cases[0]['code']==1 and cases[1]['code']==1
assert cases[3]['code']==1 and not cases[3]['opens']
assert cases[5]['gate_confirmed'] is True and cases[5]['public_confirmed'] is True
out=dict(scope='OFFLINE only; no annotation override or hardware; product suites separate',before=before,after=hashes(),stable=before==hashes(),cases=cases)
with (ROOT/'evidence_agv_20261001/review_preflight_runtime_2112.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2,ensure_ascii=False)
print(json.dumps(out,ensure_ascii=False))
