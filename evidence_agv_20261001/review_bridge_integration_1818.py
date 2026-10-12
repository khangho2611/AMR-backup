"""Source integration review; exclusively fake Serial, no ROS or hardware launch."""
import hashlib
import json
import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agv_ros2_arbiter_bridge import AGVRos2ArbiterBridge
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
import agv_reachability_costmap_planner_v2 as pm

FILES = ['agv_ros2_arbiter_bridge.py', 'agv_serial_arbiter_bridge_v3.py',
         'agv_reachability_costmap_planner_v2.py']
before = {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}
cases = []

class SerialMock:
    def __init__(self): self.writes = []
    def write(self, data): self.writes.append(data.decode()); return len(data)
    def flush(self): pass

def prepared_mock_gate():
    serial = SerialMock()
    gate = SerialArbiterGateV3(mock_serial=serial)
    d0 = dict(safety='DISARMED', mode='PID', l_tgt=0, r_tgt=0,
              l_rpm=0, r_rpm=0, l_pwm=0, r_pwm=0, x=0, y=0, th=0, v=0, w=0)
    gate.process_incoming_line(json.dumps(d0), 100)
    assert gate.arm_control_session('authorized_mock_session', 100.01)[0]
    gate.process_incoming_line('{"ack":"ARM","state":"ARMED"}', 100.02)
    gate.process_incoming_line(json.dumps(dict(d0, safety='ARMED')), 100.03)
    serial.writes.clear()
    return gate, serial

gate, serial = prepared_mock_gate()
b = AGVRos2ArbiterBridge(serial_arbiter=gate)
result = b.submit_cmd_vel(2, 'unauthorized_source_lease', .04, 0, now_mono=100.04)
cases.append(dict(id='I1', scenario='arbitrary source lease inherits active gate token, no scan/odom',
                  observed=result, mock_writes=serial.writes, expected_accepted=False))
gate, serial = prepared_mock_gate()
b = AGVRos2ArbiterBridge(serial_arbiter=gate)
result = b.submit_cmd_vel(2, 'unbounded_lease', .04, 0, now_mono=100.04, deadline_ttl_s=100)
cases.append(dict(id='I2', scenario='100-second lease bypasses documented 200ms source TTL',
                  observed=result, lease_deadline=b.active_lease_deadline,
                  mock_writes=serial.writes, expected_accepted=False))
b = AGVRos2ArbiterBridge(is_mock=False)
cases.append(dict(id='I3', scenario='production flag with missing gate and no sensor data',
                  observed=b.submit_cmd_vel(2, 'nav', .04, 0, now_mono=100),
                  expected_accepted=False, publisher_type=type(b.mock_odom_pub).__name__))
b = AGVRos2ArbiterBridge()
cases.append(dict(id='I4', scenario='STOP without any actual gate/transport',
                  observed=b.submit_cmd_vel(0, 'stop', 0, 0, now_mono=100),
                  expected='unconfirmed / unavailable, never hardware ENFORCED'))
b = AGVRos2ArbiterBridge()
cases.append(dict(id='I5', scenario='negative ranges and reversed angles accepted scan',
                  observed=b.ingest_scan_packet(2, -2, .1, [-1, -2], 100, now_mono=100.1),
                  expected=False))
p = pm.ReachabilityCostmapPlannerV2()
p.ingest_occupancy_grid(20, 20, 1, (0,0), 'map', [0]*400, stamp=100)
with patch.object(pm.time, 'monotonic', return_value=101):
    for ident, t in [('I6', 100), ('I7', float('nan'))]:
        cases.append(dict(id=ident, scenario='start==goal bypass expired/NaN now_mono',
                          clock_repr=repr(t), observed_path=p.find_path_world((2.5,5.5), (2.5,5.5),
                          timeout_s=.01, now_mono=t), expected_path=None))
after = {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}
result = dict(scope='OFFLINE SOURCE + MOCK SERIAL ONLY', before=before, after=after,
              stable_snapshot=before==after, cases=cases)
out = ROOT/'evidence_agv_20261001/review_bridge_integration_1818.json'
with out.open('x', encoding='utf-8') as f: json.dump(result, f, ensure_ascii=False, indent=2)
for case in cases: print(json.dumps(case, ensure_ascii=False))
print('stable_snapshot', before==after)
