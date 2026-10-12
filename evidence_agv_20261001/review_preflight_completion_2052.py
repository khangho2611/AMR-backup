"""OFFLINE ONLY. Collector diagnostics postpone annotations IN MEMORY to isolate defects after real import failure; this is NOT an unchanged-source PASS."""
import pathlib,json,hashlib,sys,types,__future__
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
files=['agv_preflight_static_collector.py','agv_ros2_runtime_adapter.py','agv_serial_arbiter_bridge_v3.py']
def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
before=hashes();cases=[]
m=types.ModuleType('diagnostic_only_collector')
exec(compile((ROOT/files[0]).read_text(encoding='utf-8'),files[0],'exec',flags=__future__.annotations.compiler_flag,dont_inherit=True),m.__dict__)
d0=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0,r_rpm=0,l_pwm=0,r_pwm=0,x=0,y=0,th=0,v=0,w=0)
line=(json.dumps(d0)+'\n').encode()
class Clock:
 def __init__(self):self.x=100.
 def __call__(self):self.x+=.01;return self.x
for name,lines in [('C1_30_burst_then_no_data',[line]*30),('C2_30_safe_then_malformed_armed',[line]*30+[b'{"safety":"ARMED"\n']*10)]:
 with patch.object(m.time,'monotonic',side_effect=Clock()):code,rep=m.run_preflight_collector(mock=True,mock_lines=lines,wall_timeout_s=15,min_samples=30)
 cases.append(dict(id=name,scope='diagnostic annotation-postponed IN MEMORY',code=code,report=rep))
# Validate all arguments before opening the FAKE port; no real serial imports/connections.
opens=[]
class FakePort(m.MockSerialStream):
 def __init__(self):super().__init__([line]*30)
 def open(self):opens.append('open')
fake_serial=types.ModuleType('serial');fake_serial.Serial=FakePort
with patch.dict(sys.modules,{'serial':fake_serial}),patch.object(m.time,'monotonic',side_effect=Clock()):
 code,rep=m.run_preflight_collector(mock=False,wall_timeout_s=-1,min_samples=30)
cases.append(dict(id='C3_invalid_duration_opens_port',fake_port_opens=list(opens),code=code))
# Reuse actual source constructor/protocol setup from earlier QA, without its output-writing block.
base=(ROOT/'evidence_agv_20261001/review_node_residual_2028.py').read_text(encoding='utf-8').split('for label,meta in')[0]
ns={'__file__':str(ROOT/'evidence_agv_20261001/review_node_residual_2028.py')};exec(compile(base,'existing_setup','exec'),ns)
r=ns['r'];n,g,ser=ns['setup']()
with patch.object(r.time,'monotonic',return_value=100.06):n.destroy_node()
ok=n.adapter.parse_and_ingest(json.dumps(d0),rx_mono=100.08)
cases.append(dict(id='S1_adapter_only_freshD0',accepted=ok,gate_confirmed=g.stop_confirmed,public_confirmed=n.watchdog.last_stop_confirmed,gate_state=g.safety_state))
n,g,ser=ns['setup']()
with patch.object(r.time,'monotonic',return_value=100.06):n.destroy_node()
g.process_incoming_line(json.dumps(d0),100.08)
ok=n.adapter.parse_and_ingest(json.dumps(d0),rx_mono=100.08)
cases.append(dict(id='S2_explicit_gate_then_adapter',accepted=ok,gate_confirmed=g.stop_confirmed,public_confirmed=n.watchdog.last_stop_confirmed))
out=dict(scope='OFFLINE fake transports only; real import failures in independent_preflight_suite_2050.json; C1-C3 use annotation-postponed diagnostics, S1-S2 unchanged product source',before=before,after=hashes(),cases=cases)
with (ROOT/'evidence_agv_20261001/review_preflight_completion_2052.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2,ensure_ascii=False)
print(json.dumps(out,ensure_ascii=False))
