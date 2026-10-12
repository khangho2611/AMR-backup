"""Offline review only: all Serial endpoints are mocks; never connect hardware."""
import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agv_serial_arbiter_bridge_v3 as gate_module
import agv_passive_encoder_logger_v2 as logger_module
from agv_reachability_costmap_planner_v2 import ReachabilityCostmapPlannerV2


class SerialMock:
    def __init__(self, lines=(), read_error=False):
        self.lines = list(lines)
        self.writes = []
        self.read_error = read_error

    def write(self, data):
        self.writes.append(data.decode())
        return len(data)

    def flush(self):
        pass

    def readline(self):
        if self.lines:
            return self.lines.pop(0)
        if self.read_error:
            raise OSError('injected offline read failure')
        return b''


zero = dict(safety='DISARMED', mode='PID', l_tgt=0, r_tgt=0, l_pwm=0,
            r_pwm=0, l_rpm=0, r_rpm=0, x=0, y=0, th=0, v=0, w=0)
rows = []
hashes_before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                ('agv_serial_arbiter_bridge_v3.py', 'agv_passive_encoder_logger_v2.py',
                 'agv_reachability_costmap_planner_v2.py')}

serial = SerialMock()
gate = gate_module.SerialArbiterGateV3(mock_serial=serial)
gate.process_incoming_line(json.dumps(zero), 100.0)
with patch.object(gate_module.time, 'monotonic', return_value=101.0):
    gate.send_stop()
gate.process_incoming_line(json.dumps(zero), 100.5)
rows.append(dict(id='G1', scenario='STOP at real mock clock101; buffered D0 stamped100.5',
                 stop_anchor=gate.last_stop_command_time, actual_stop_clock=101.0,
                 observed_confirmed=gate.stop_confirmed, expected_confirmed=False))

serial = SerialMock()
gate = gate_module.SerialArbiterGateV3(mock_serial=serial)
fraction = dict(zero, l_pwm=0.5, r_pwm=-0.5)
gate.process_incoming_line(json.dumps(fraction), 100.0)
arm_result = gate.arm_control_session('offline-fraction-test', 100.01)
rows.append(dict(id='G2', scenario='nonzero fractional PWM preflight',
                 observed_arm_requested=arm_result[0], expected_arm_requested=False,
                 result=arm_result, mock_writes=serial.writes))

for ident, pkt, read_error in [('L1', fraction, False), ('L2', zero, True)]:
    stream = SerialMock([json.dumps(pkt).encode()] * 13, read_error=read_error)
    with tempfile.TemporaryDirectory(prefix='agv_offline_') as temp:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = logger_module.run_passive_logger_v2(duration=2, log_dir=temp,
                                                       mock_serial=stream, min_samples=10)
    rows.append(dict(id=ident, scenario='fractional PWM' if ident == 'L1' else
                     'Serial read error after10 valid collection samples',
                     observed_success=result, expected_success=False,
                     mock_writes=stream.writes, output=output.getvalue()))

planner = ReachabilityCostmapPlannerV2()
grid = [0 if x < 6 else 100 if x == 6 else -1 for y in range(20) for x in range(20)]
planner.ingest_occupancy_grid(20, 20, 1.0, (0, 0), 'map', grid, stamp=0)
planner.set_home_pose(2.5, 5.5, 0)
status = planner.evaluate_mission_status((2.5, 5.5, 0), target_coverage=0.85)
rows.append(dict(id='P1', scenario='closed-wall separated unknown area; coverage below threshold; at home',
                 observed=status, expected_completed=False,
                 all_frontiers_count=len(planner.extract_frontiers())))

planner = ReachabilityCostmapPlannerV2()
planner.ingest_occupancy_grid(20, 20, 1.0, (0, 0), 'map', [0]*400, stamp=1)
planner.set_home_pose(2.5, 5.5, 0)
planner.ingest_occupancy_grid(20, 20, 1.0, (0, 0), 'different_map', [0]*400, version=2, stamp=2)
status = planner.evaluate_mission_status((2.5, 5.5, 0))
rows.append(dict(id='P2', scenario='home remains after map frame changed without TF',
                 observed=status, expected_completed=False, frame=planner.frame_id,
                 home=planner.home_pose_world))

hashes_after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in hashes_before}
result = dict(scope='OFFLINE MOCK ONLY; no physical Serial, no hardware action',
              source_hash_before=hashes_before, source_hash_after=hashes_after,
              stable_snapshot=hashes_before == hashes_after, cases=rows)
out = ROOT / 'evidence_agv_20261001' / (sys.argv[1] if len(sys.argv) > 1 else
      'review_workers_' + str(__import__('time').time_ns()) + '.json')
with out.open('x', encoding='utf-8') as evidence_file:
    evidence_file.write(json.dumps(result, ensure_ascii=False, indent=2))
for row in rows:
    print(json.dumps({k: v for k, v in row.items() if k != 'output'}, ensure_ascii=False))
print('stable_snapshot=', result['stable_snapshot'])
