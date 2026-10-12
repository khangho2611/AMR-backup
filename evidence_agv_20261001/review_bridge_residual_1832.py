"""Independent offline source checks, exclusively mocked Serial."""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agv_ros2_arbiter_bridge import AGVRos2ArbiterBridge
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3

class SerialMock:
    def __init__(self): self.writes=[]
    def write(self, data): self.writes.append(data.decode()); return len(data)
    def flush(self): pass

def setup():
    s=SerialMock(); g=SerialArbiterGateV3(mock_serial=s)
    packet=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0,r_rpm=0,
                l_pwm=0,r_pwm=0,x=0,y=0,th=0,v=0,w=0)
    g.process_incoming_line(json.dumps(packet),100)
    assert g.arm_control_session('authorized_mock',100.01)[0]
    g.process_incoming_line('{"ack":"ARM","state":"ARMED"}',100.02)
    g.process_incoming_line(json.dumps(dict(packet,safety='ARMED')),100.03)
    b=AGVRos2ArbiterBridge(serial_arbiter=g,is_mock=False)
    assert b.ingest_telemetry_packet(dict(packet,safety='ARMED',t=100.03),100.04)
    s.writes.clear()
    return b,g,s

files=['agv_ros2_arbiter_bridge.py','agv_serial_arbiter_bridge_v3.py']
before={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
cases=[]
b,g,s=setup()
r=b.submit_cmd_vel(2,'arbitrary_unregistered_nav_lease',.04,0,now_mono=100.05)
cases.append(dict(id='R1',scenario='fresh odom masks still-missing auth source and scan/TF',
                  observed=r,mock_writes=s.writes,scan=b.last_scan_data,expected_accepted=False))
b,g,s=setup()
r=b.submit_cmd_vel(0,'stop',0,0,now_mono=100.05)
cases.append(dict(id='R2',scenario='STOP write succeeds but no fresh D0 confirmation',
                  observed=r,gate_stop_confirmed=g.stop_confirmed,
                  expected='STOP_REQUESTED/WRITE_OK_UNCONFIRMED, not ENFORCED'))
b,g,s=setup()
r=b.submit_cmd_vel(0,'stop',0,0,now_mono=100.05,deadline_ttl_s=100)
cases.append(dict(id='R3',scenario='STOP blocked by velocity lease TTL validation',
                  observed=r,mock_writes=s.writes,gate_safety=g.safety_state,
                  expected='safety STOP independent of velocity lease TTL'))
after={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
out=dict(scope='OFFLINE MOCK ONLY',before=before,after=after,stable=before==after,cases=cases)
with (ROOT/'evidence_agv_20261001/review_bridge_residual_1832.json').open('x',encoding='utf-8') as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(out,ensure_ascii=False))
