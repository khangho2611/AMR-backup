"""Independent source review: mocks only, never opens hardware Serial or ROS nodes."""
import hashlib
import json
import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agv_ros2_arbiter_bridge import AGVRos2ArbiterBridge
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
import agv_reachability_costmap_planner_v2 as planner_module

FILES = ['agv_ros2_arbiter_bridge.py', 'agv_serial_arbiter_bridge_v3.py',
         'agv_reachability_costmap_planner_v2.py']
before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}
cases = []


class SerialMock:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data.decode())
        return len(data)

    def flush(self):
        pass


serial = SerialMock()
bridge = AGVRos2ArbiterBridge(serial_arbiter=SerialArbiterGateV3(mock_serial=serial))
try:
    observed = bridge.submit_cmd_vel(2, 'nav', 0.04, 0.0, now_mono=100)
except Exception as exc:
    observed = dict(exception=type(exc).__name__, message=str(exc))
cases.append(dict(id='B1', scenario='bridge connected to actual gate with mock Serial',
                  observed=observed, expected='structured rejection without exception',
                  mock_writes=serial.writes))


class RejectingGate:
    def send_velocity_command(self, **kwargs):
        return False, 'REJECT_FAULT'

    def send_stop(self, **kwargs):
        return False


bridge = AGVRos2ArbiterBridge(serial_arbiter=RejectingGate())
cases.append(dict(id='B2', scenario='gate returns (False,REJECT_FAULT)',
                  observed=bridge.submit_cmd_vel(2, 'nav', 0.04, 0, now_mono=100),
                  expected_accepted=False))
cases.append(dict(id='B3', scenario='STOP write fails',
                  observed=bridge.submit_cmd_vel(0, 'stop', 0, 0, now_mono=100.1),
                  expected_accepted=False))

bridge = AGVRos2ArbiterBridge()
packet = dict(t=100, x=0, y=0, th=0, v=0, w=0, safety='DISARMED')
cases.append(dict(id='B4', scenario='NaN current clock on telemetry',
                  observed=bridge.ingest_telemetry_packet(packet, now_mono=float('nan')),
                  expected=False))
cases.append(dict(id='B5', scenario='NaN angles/ranges and whitespace-only scan frame',
                  observed=bridge.ingest_scan_packet(float('nan'), float('nan'), 0,
                  [float('nan')], 100, frame_id='   ', now_mono=100.1), expected=False))
bridge = AGVRos2ArbiterBridge()
cases.append(dict(id='B6', scenario='command without any scan/odom/gate and NaN lease TTL',
                  observed=bridge.submit_cmd_vel(2, 'nav', 0.04, 0, now_mono=100,
                                                deadline_ttl_s=float('nan')),
                  expected_accepted=False))
bridge = AGVRos2ArbiterBridge()
bridge.submit_cmd_vel(1, 'manual', 0.04, 0, now_mono=100)
cases.append(dict(id='B7', scenario='invalid priority -1 preempts active manual lease',
                  observed=bridge.submit_cmd_vel(-1, 'invalid', 0.04, 0, now_mono=100.01),
                  expected_accepted=False))

planner = planner_module.ReachabilityCostmapPlannerV2()
planner.ingest_occupancy_grid(20, 20, 1, (0, 0), 'map', [0]*400, stamp=100)
with patch.object(planner_module.time, 'monotonic', return_value=101):
    path = planner.find_path_world((2.5, 5.5), (8.5, 5.5), timeout_s=0.01, now_mono=100)
cases.append(dict(id='P3', scenario='deadline100.01 expired at actual clock101; now_mono freezes clock',
                  observed_path=path, expected_path=None))
for ident, budget in [('P4', float('inf')), ('P5', True)]:
    path = planner.find_path_world((2.5, 5.5), (8.5, 5.5), timeout_s=budget)
    cases.append(dict(id=ident, scenario='nonfinite/bool timeout budget',
                      budget_repr=repr(budget), observed_path=path, expected_path=None))

after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}
result = dict(scope='OFFLINE MOCK ONLY; no Serial connect, no Node launch',
              before=before, after=after, stable_snapshot=before == after, cases=cases)
path = ROOT / 'evidence_agv_20261001' / 'review_ros_planner_1800.json'
with path.open('x', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
for c in cases:
    print(json.dumps(c, ensure_ascii=False))
print('stable_snapshot', result['stable_snapshot'])
