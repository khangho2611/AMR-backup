"""Offline Node constructor and callbacks; no ROS launch or hardware Serial."""
import hashlib
import json
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agv_ros2_runtime_adapter as runtime
from agv_ros2_arbiter_bridge import AGVRos2ArbiterBridge
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3

files=['agv_ros2_runtime_adapter.py','agv_ros2_arbiter_bridge.py']
before={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
cases=[]
try:
    node=runtime.AGVRos2RuntimeNode(is_mock=True)
    observed=dict(constructed=True)
except Exception as exc:
    observed=dict(exception=type(exc).__name__,message=str(exc))
cases.append(dict(id='N1',scenario='construct advertised offline Node',
                  observed=observed,has_real_rclpy=runtime.HAVE_REAL_RCLPY,
                  expected='construct safely using fake ROS dependencies'))

# Constructor failed; invoke actual source callbacks with an explicitly injected mock bridge.
# This checks callback logic only, never claims a successful Node lifecycle.
b=AGVRos2ArbiterBridge()
n=object.__new__(runtime.AGVRos2RuntimeNode);n.bridge=b
old_scan=SimpleNamespace(angle_min=-1.,angle_max=1.,angle_increment=.1,ranges=[1.]*21,
                        header=SimpleNamespace(stamp=SimpleNamespace(sec=0,nanosec=0),frame_id='unknown_sensor'))
with patch.object(runtime.time,'monotonic',return_value=100):
    n._on_laserscan(old_scan)
cases.append(dict(id='N2',scenario='stale scan header0 and wrong frame re-stamped now',
                  scan=b.last_scan_data,expected='reject old/unknown-frame data'))
b2=AGVRos2ArbiterBridge();n.bridge=b2
with patch.object(runtime.time,'monotonic',return_value=100):
    n._on_laserscan(SimpleNamespace())
cases.append(dict(id='N3',scenario='empty scan message invents default ranges',
                  scan=b2.last_scan_data,expected='reject missing scan payload'))

class SerialMock:
    def __init__(self):self.writes=[]
    def write(self,data):self.writes.append(data.decode());return len(data)
    def flush(self):pass
s=SerialMock();g=SerialArbiterGateV3(mock_serial=s)
d0=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0,r_rpm=0,
        l_pwm=0,r_pwm=0,x=0,y=0,th=0,v=0,w=0)
g.process_incoming_line(json.dumps(d0),100)
assert g.arm_control_session('authorized_mock',100.01)[0]
g.process_incoming_line('{"ack":"ARM","state":"ARMED"}',100.02)
g.process_incoming_line(json.dumps(dict(d0,safety='ARMED')),100.03)
b3=AGVRos2ArbiterBridge(serial_arbiter=g,is_mock=False)
b3.ingest_telemetry_packet(dict(d0,safety='ARMED',t=100.03),100.04)
b3.ingest_scan_packet(-1,1,.1,[1.]*21,100.04,now_mono=100.04)
n.bridge=b3;s.writes.clear()
msg=SimpleNamespace(linear=SimpleNamespace(x=.04),angular=SimpleNamespace(z=0))
with patch.object(runtime.time,'monotonic',return_value=100.05):
    n._on_cmd_vel_nav(msg)
cases.append(dict(id='N4',scenario='bare cmd topic callback auto-inherits gate token',
                  mock_writes=s.writes,expected='bind source authorization/session and command age before dispatch'))
after={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
out=dict(scope='OFFLINE CALLBACKS AND MOCK SERIAL ONLY; constructor failure not bypassed for deployment',
         before=before,after=after,stable=before==after,cases=cases)
with (ROOT/'evidence_agv_20261001/review_node_1912.json').open('x',encoding='utf-8') as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(out,ensure_ascii=False))
