"""Offline adapter/watchdog review; fake Serial only, no ROS or hardware."""
import ast
import hashlib
import json
import pathlib
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agv_ros2_runtime_adapter import FirmwarePacketAdapter, ActiveLeaseWatchdogThread
from agv_ros2_arbiter_bridge import AGVRos2ArbiterBridge
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
files=['agv_ros2_runtime_adapter.py','agv_ros2_arbiter_bridge.py','agv_serial_arbiter_bridge_v3.py']
before={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
packet=dict(safety='DISARMED',x=0,y=0,th=0,v=0,w=0,l_rpm=0,r_rpm=0,l_pwm=0,r_pwm=0)
cases=[]
b=AGVRos2ArbiterBridge()
adapter=FirmwarePacketAdapter(b)
r=adapter.parse_and_ingest(json.dumps(packet),rx_mono=float('nan'))
cases.append(dict(id='A1',scenario='explicit invalid receive timestamp NaN',observed=r,
                  resulting_stamp=b.last_valid_odom_stamp,expected=False))
try:
    r=adapter.parse_and_ingest(json.dumps(dict(packet,x='corrupt')),rx_mono=100)
except Exception as e:
    r=dict(exception=type(e).__name__,message=str(e))
cases.append(dict(id='A2',scenario='corrupt numeric JSON field',observed=r,
                  expected='structured rejection without exception'))

class FailingSerial:
    def __init__(self): self.attempts=[]
    def write(self,data): self.attempts.append(data.decode()); raise OSError('mock write failure')
    def flush(self): pass

s=FailingSerial();g=SerialArbiterGateV3(mock_serial=s)
b=AGVRos2ArbiterBridge(serial_arbiter=g)
b.active_lease_source=2;b.active_lease_id='mock';b.active_lease_deadline=time.monotonic()-.01
w=ActiveLeaseWatchdogThread(b,check_interval_s=.005)
w.start()
try:time.sleep(.035)
finally:w.stop()
cases.append(dict(id='W1',scenario='real watchdog thread, actual gate, STOP write failure',
                  attempts=s.attempts,trip_count=w.watchdog_tripped_count,
                  active_lease=b.active_lease_source,gate_state=g.safety_state,
                  gate_stop_confirmed=g.stop_confirmed,
                  watchdog_public_state={k:v for k,v in vars(w).items()
                                         if k not in ['bridge','thread']},
                  expected='retain/report failed STOP outcome and unconfirmed stop to supervisor'))
tree=ast.parse((ROOT/'agv_ros2_runtime_adapter.py').read_text(encoding='utf-8'))
calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
runtime=dict(classes=[n.name for n in tree.body if isinstance(n,ast.ClassDef)],
             ros_runtime_calls=[x for x in calls if x in ['create_publisher','create_subscription','create_timer','spin','spin_once','get_clock','add_node']])
after={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
out=dict(scope='OFFLINE SOURCE + FAKE SERIAL ONLY',before=before,after=after,stable=before==after,cases=cases,runtime=runtime)
with (ROOT/'evidence_agv_20261001/review_runtime_1902.json').open('x',encoding='utf-8') as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(out,ensure_ascii=False))
