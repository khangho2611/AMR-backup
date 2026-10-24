"""Tests for wall collision prevention and self-recovery fixes (BAO_CAO_QUAN_SAT_KET_TUONG_20261008)."""
import pathlib
import sys
import time
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from test_agv_navigation_fix import load_brain
from agv_command_session import CommandSession


class WallEscapeRegression(unittest.TestCase):
    def setUp(self):
        self.brain = load_brain()
        self.node = self.brain.AGVROSNode.__new__(self.brain.AGVROSNode)
        self.brain.state = self.brain.AGVSharedState()
        self.node.initialize_navigation()
        self.node.explore_state = 'EXPLORING'
        self.node.home = (0.0, 0.0, 0.0)
        self.node._auto_start_time = time.monotonic()
        self.node._pose_map = lambda: (0.0, 0.0, 0.0)

        class DummyGrid:
            res = 0.05
            body_radius = 0.20
            def swept_clear(self, pose, v, w): return True
            def traversable(self, cell): return True
            def world_to_cell(self, x, y): return (0, 0)
            def swept_clear_result(self, pose, v, w): return True, 'CLEAR'
            def escape_swept_clear(self, pose, v, w, bounds=None, require_progress=False): return True
            def frontiers(self, origin, goals, regions): return {'goals': [(1.0, 1.0)], 'reachable_frontiers': 1, 'unknown_cells': 500}
            def path(self, start, goal): return [(0.0, 0.0), (0.1, 0.1)]
        now = time.monotonic()
        with self.brain.state.lock:
            self.brain.state.map_mono = now
            self.brain.state.scan_mono = now
            self.brain.state.map_version = 1
            self.brain.state.map_frame = 'map'
            self.brain.state.body_radius_m = 0.20

        self.node._grid = lambda margin=None: DummyGrid()
        self.node._restore_normal_clearance = lambda pose: None

    def test_front_obstacle_prioritizes_reverse_escape(self):
        """When an obstacle is dangerously close in front (16cm, 5°), candidates must prioritize reverse."""
        with self.brain.state.lock:
            self.brain.state.min_dist_m = 0.16
            self.brain.state.min_angle_deg = 5
            self.brain.state.safety_status = "DANGER_STOP"
            self.brain.state.body_radius_m = 0.20
            self.brain.state.body_bounds_m = (-0.16, -0.11, 0.10, 0.11)
            # Rear is clear, front has obstacle at 0.16m
            ranges = [2.0] * 360
            for deg in range(-20, 21):
                ranges[deg % 360] = 0.16
            self.brain.state.ranges = ranges
            self.brain.state.scan_mono = time.monotonic()

        calls = []
        self.node.control = types.SimpleNamespace(
            drive=lambda command, **kw: (calls.append((command, kw)) or True, 'SENT'),
            _event=lambda *a, **kw: None
        )
        escaped = self.node._try_escape()
        self.assertTrue(escaped)
        self.assertTrue(len(calls) > 0)
        # First executed candidate must be reversing
        self.assertTrue(calls[0][0].startswith('V -0.090'))
        self.assertEqual(calls[0][1], {'autonomous': True, 'escape': True})
        self.assertIn('NÉ VÙNG ĐỎ: lùi', self.brain.state.explore_phase)

    def test_auto_nav_loop_escapes_on_danger_close_even_if_grid_clear(self):
        """When LiDAR sees obstacle at 16cm (danger_close), auto_nav_loop must trigger escape."""
        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 0.16
            self.brain.state.min_angle_deg = 4
            self.brain.state.safety_status = "DANGER_STOP"
            self.brain.state.body_bounds_m = (-0.16, -0.11, 0.10, 0.11)
            ranges = [2.0] * 360
            for deg in range(-20, 21):
                ranges[deg % 360] = 0.16
            self.brain.state.ranges = ranges
            self.brain.state.scan_mono = time.monotonic()

        calls = []
        self.node.control = types.SimpleNamespace(
            drive=lambda command, **kw: (calls.append((command, kw)) or True, 'SENT'),
            _event=lambda *a, **kw: None,
            clock=lambda: time.monotonic(),
            last_command=time.monotonic(),
            armed=True
        )
        self.node.auto_nav_loop()
        self.assertTrue(len(calls) > 0)
        self.assertTrue(calls[0][0].startswith('V -0.090'))

    def test_wheel_stall_differential_slip_triggers_escape(self):
        """Detect slip/stall when one wheel spins and one is pinned against the wall."""
        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 0.80
            self.brain.state.min_angle_deg = 0
            self.brain.state.safety_status = "SAFE"
            self.brain.state.ranges = [2.0] * 360
            self.brain.state.scan_mono = time.monotonic()

        escape_calls = []
        self.node._try_escape = lambda: (escape_calls.append(True) or True)

        now = time.monotonic()
        # Telemetry: target is 25 RPM, left wheel spins at 32 RPM, right wheel pinned at 0.0 RPM
        mock_control = types.SimpleNamespace(
            latest={'l_rpm': 32.0, 'r_rpm': 0.0, 'l_tgt': 25.0, 'r_tgt': 25.0},
            clock=lambda: now,
            last_command=now,
            armed=True,
            drive=lambda *a, **kw: (True, 'SENT'),
            _event=lambda *a, **kw: None
        )
        self.node.control = mock_control

        # First tick initializes stall timer
        self.node.auto_nav_loop()
        self.assertIsNotNone(getattr(self.node, '_stall_start', None))
        self.assertEqual(len(escape_calls), 0)

        # After 1.9s, stall is confirmed and _try_escape must be called
        self.node._stall_start = now - 2.0
        self.node.auto_nav_loop()
        self.assertEqual(len(escape_calls), 1)

    def test_operator_mode_drive_cannot_clear_stop_unconfirmed(self):
        """An unconfirmed STOP always blocks motion, including manual mode."""
        class MockSer:
            is_open = True
            def write(self, b): return len(b)

        session = CommandSession(MockSer(), require_transport_sync=False, strict_preflight=False)
        session.stage = 3
        session.fault = 'STOP_UNCONFIRMED'
        session.armed = True
        session.opened = time.monotonic() - 10.0

        ok, reason = session.drive('V 0.040 0.000', autonomous=False)
        self.assertFalse(ok)
        self.assertEqual(session.fault, 'STOP_UNCONFIRMED')

    def test_operator_mode_accepts_map_age_up_to_5s(self):
        """In operator mode (strict_preflight=False), map age up to 5s is valid."""
        node = self.brain.AGVROSNode.__new__(self.brain.AGVROSNode)
        node.control = types.SimpleNamespace(strict_preflight=False)
        with self.brain.state.lock:
            self.brain.state.map_received = True
            self.brain.state.map_mono = time.monotonic() - 3.5
            self.brain.state.map_version = 1
            self.brain.state.map_width = 10
            self.brain.state.map_height = 10
            self.brain.state.map_resolution = 0.05
            self.brain.state.map_origin_x = 0.0
            self.brain.state.map_origin_y = 0.0
            self.brain.state.map_origin_yaw = 0.0
            self.brain.state.map_data = [0] * 100
            self.brain.state.body_radius_m = 0.20
            self.brain.state.wall_margin_m = 0.15
        grid = node._grid()
        self.assertIsNotNone(grid)

    def test_rejected_arc_aligns_to_astar_not_the_more_open_side(self):
        """When forward drive is rejected by safety/arc, the follower may align only toward its waypoint."""
        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 0.80
            self.brain.state.min_angle_deg = 0
            self.brain.state.safety_status = "SAFE"
            self.brain.state.body_bounds_m = (-0.16, -0.11, 0.10, 0.11)
            # Front clear in ranges, but left is more open than right
            ranges = [1.0] * 360
            for deg in range(25, 90): ranges[deg] = .5
            for deg in range(-90, -25): ranges[deg] = 1.5
            self.brain.state.ranges = ranges
            self.brain.state.scan_mono = time.monotonic()

        # Reactive safety remains available only with a planned A* target.
        self.node.goal = (1.0, 1.0)
        cmd_history = []
        def mock_send(cmd_str, autonomous=False, planned_turn=False):
            cmd_history.append(cmd_str)
            if float(cmd_str.split()[1]) > 0:
                return False, 'SESSION_OR_SENSOR_NOT_READY'
            return True, 'SENT'

        self.node.send_cmd = mock_send
        self.node.control = types.SimpleNamespace(
            strict_preflight=False,
            clock=lambda: time.monotonic(),
            last_command=time.monotonic(),
            armed=True,
            latest={'l_rpm': 0.0, 'r_rpm': 0.0, 'l_tgt': 0.0, 'r_tgt': 0.0}
        )

        self.node.auto_nav_loop()
        # First command is forward along the A* carrot, which failed.
        self.assertGreater(float(cmd_history[0].split()[1]), 0)
        # Second command was turning in place (w > 0 since left is more open)
        self.assertTrue(len(cmd_history) >= 2)
        self.assertTrue(cmd_history[1].startswith('V 0.000'))
        self.assertGreater(float(cmd_history[1].split()[2]), 0.)
        self.assertEqual(self.node.goal, (1., 1.))


    def test_command_session_accepts_raised_escape_velocities(self):
        """CommandSession must accept escape commands up to 0.090 m/s and reject excessive speeds."""
        class DummySerial:
            def __init__(self):
                self.writes = []
                self.is_open = True
            def write(self, data): self.writes.append(data); return len(data)
            def flush(self): pass
        ser = DummySerial()
        session = CommandSession(ser, strict_preflight=False)
        session.armed = True
        session.autonomy_allowed = True
        session.latest = {'safety': 'ARMED'}
        session.last_d0 = session.clock()
        session.scan_time = session.clock()
        session.escape_validator = lambda v, w: True
        
        ok, reason = session.drive('V -0.090 0.000', autonomous=True, escape=True)
        self.assertTrue(ok)
        self.assertEqual(reason, 'SENT')
        
        ok, reason = session.drive('V 0.090 0.600', autonomous=True, escape=True)
        self.assertTrue(ok)
        self.assertEqual(reason, 'SENT')

        # Excessive velocity > 0.10 m/s must be rejected
        ok, reason = session.drive('V -0.150 0.000', autonomous=True, escape=True)
        self.assertFalse(ok)
        self.assertEqual(reason, 'INVALID_ESCAPE_CALLER_OR_COMMAND')

    def test_side_buffer_cannot_override_the_validated_astar_bearing(self):
        """When front has space (35cm) but side wall is close (32cm), side proximity cannot replace the path heading."""
        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 0.32
            self.brain.state.min_angle_deg = 60
            self.brain.state.safety_status = "SAFE"
            self.brain.state.body_bounds_m = (-0.16, -0.11, 0.10, 0.11)
            self.brain.state.auto_target_speed_rpm = 38.0
            ranges = [1.5] * 360
            # Front is 0.35m
            for d in range(-25, 26): ranges[d % 360] = 0.35
            # Left side is 0.32m (< 0.35m)
            for d in range(25, 90): ranges[d % 360] = 0.32
            # Right side is open (1.5m)
            for d in range(-90, -25): ranges[d % 360] = 1.50
            self.brain.state.ranges = ranges
            self.brain.state.scan_mono = time.monotonic()

        self.node.goal = (1.0, 1.0)
        cmd_history = []
        self.node.send_cmd = lambda cmd, **kw: (cmd_history.append(cmd) or True, 'SENT')
        self.node.control = types.SimpleNamespace(
            strict_preflight=False,
            clock=lambda: time.monotonic(),
            last_command=time.monotonic(),
            armed=True,
            latest={'l_rpm': 0.0, 'r_rpm': 0.0, 'l_tgt': 0.0, 'r_tgt': 0.0}
        )

        self.node.auto_nav_loop()
        self.assertTrue(len(cmd_history) > 0)
        self.assertEqual(len(cmd_history), 1)
        self.assertGreater(float(cmd_history[0].split()[1]), 0.)
        self.assertGreater(float(cmd_history[0].split()[2]), 0.,
                           'Waypoint is left even though left wall is nearer')


    def test_heading_alignment_rolls_arc_when_front_open(self):
        """When front is clear (>=50cm) and heading error is large (>45°), robot rolls forward arc at v=0.050 instead of dead pivot."""
        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 0.80
            self.brain.state.min_angle_deg = 0
            self.brain.state.safety_status = "SAFE"
            self.brain.state.body_bounds_m = (-0.16, -0.11, 0.10, 0.11)
            self.brain.state.auto_target_speed_rpm = 38.0
            ranges = [1.2] * 360
            self.brain.state.ranges = ranges
            self.brain.state.scan_mono = time.monotonic()

        # Goal is at (0.0, 1.0) while robot is at (0.0, 0.0, yaw=0.0) -> heading_err is +90° (+1.57 rad)
        self.node.goal = (0.0, 1.0)
        self.node._goal_time = time.monotonic()
        cmd_history = []
        self.node.send_cmd = lambda cmd, **kw: (cmd_history.append(cmd) or True, 'SENT')
        self.node.control = types.SimpleNamespace(
            strict_preflight=False,
            clock=lambda: time.monotonic(),
            last_command=time.monotonic(),
            armed=True,
            latest={'l_rpm': 0.0, 'r_rpm': 0.0, 'l_tgt': 0.0, 'r_tgt': 0.0}
        )

        self.node.auto_nav_loop()
        self.assertTrue(len(cmd_history) > 0)
        # With the A* carrot at (+0.1,+0.1), turn toward the local path
        # (+45 degrees) rather than the distant global goal (+90 degrees).
        v, w = map(float, cmd_history[0].split()[1:])
        self.assertGreater(v, 0.0)
        self.assertGreater(w, 0.0)
        self.assertLess(w, 1.0)

    def test_escape_latch_clears_early_when_front_open(self):
        """If escape latch is active but front clearance is restored (>=40cm), latch clears early."""
        now = time.monotonic()
        self.node._escape_latch_until = now + 1.0
        self.node._last_escape_cmd = (-0.090, 0.0)

        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 0.80
            self.brain.state.min_angle_deg = 0
            self.brain.state.safety_status = "SAFE"
            self.brain.state.body_bounds_m = (-0.16, -0.11, 0.10, 0.11)
            self.brain.state.ranges = [0.80] * 360  # Front is 0.80m (clear)
            self.brain.state.scan_mono = now

        cmd_history = []
        self.node.send_cmd = lambda cmd, **kw: (cmd_history.append(cmd) or True, 'SENT')
        self.node.control = types.SimpleNamespace(
            strict_preflight=False,
            clock=lambda: now,
            last_command=now,
            armed=True,
            drive=lambda cmd, **kw: (cmd_history.append(cmd) or True, 'SENT'),
            latest={'l_rpm': 0.0, 'r_rpm': 0.0, 'l_tgt': 0.0, 'r_tgt': 0.0}
        )

        self.node.auto_nav_loop()
        # Latch must have been cancelled
        self.assertEqual(self.node._escape_latch_until, 0)

    def test_danger_close_cannot_force_an_unvalidated_in_place_turn(self):
        """Actual writer rejection must produce zero only, never a guessed U-turn."""
        from test_agv_rpm_profile import ready
        now = time.monotonic()
        ranges = [.22] * 360
        self.brain.state.auto_mode = True
        self.brain.state.ranges = ranges
        self.brain.state.scan_mono = now
        self.node.goal = (1., 1.)
        self.node.control, uart = ready()
        self.node.control.arc_validator = lambda v, w: False
        self.node.control.rotation_clear = False
        self.node._rotation_clear = lambda: False
        self.node._enter_cautious = lambda pose: False
        self.node.send_cmd = lambda cmd, **kw: self.brain.AGVROSNode.send_cmd(self.node, cmd, **kw)
        self.node.auto_nav_loop()
        self.assertTrue(uart.writes)
        self.assertTrue(all(line == b'S 0.000 0.000\n' for line in uart.writes))
        self.assertIn('HOLD', self.brain.state.explore_phase)
        self.assertIsNone(self.node.goal)


    def test_in_place_turn_latch_early_clear_at_50cm(self):
        """Active turn latch must immediately clear when front clearance reaches >= 50cm."""
        now = time.monotonic()
        self.node._turn_latch_until = now + 1.15
        self.node._turn_latch_dir = True

        ranges = [0.25] * 360
        # Clear front corridor to 0.60m (>= 0.50m)
        for deg in range(-25, 26):
            ranges[deg % 360] = 0.60

        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 0.60
            self.brain.state.min_angle_deg = 0
            self.brain.state.safety_status = "SAFE"
            self.brain.state.ranges = ranges
            self.brain.state.scan_mono = now

        cmd_history = []
        self.node.send_cmd = lambda cmd, **kw: (cmd_history.append(cmd) or True, 'SENT')
        self.node.control = types.SimpleNamespace(
            strict_preflight=False,
            clock=lambda: now,
            last_command=now,
            armed=True,
            drive=lambda cmd, **kw: (cmd_history.append(cmd) or True, 'SENT'),
            latest={'l_rpm': 0.0, 'r_rpm': 0.0, 'l_tgt': 0.0, 'r_tgt': 0.0}
        )

        self.node.auto_nav_loop()
        # Latch must be cleared early to 0
        self.assertEqual(self.node._turn_latch_until, 0)


    def test_narrow_corridor_cannot_force_a_u_turn_when_geometry_rejects_it(self):
        """Actual writer rejection must produce zero only, never a guessed U-turn."""
        from test_agv_rpm_profile import ready
        now = time.monotonic()
        ranges = [.22] * 360
        for deg in range(-25, 26): ranges[deg % 360] = .36
        for deg in range(155, 206): ranges[deg % 360] = 2.5
        self.brain.state.auto_mode = True
        self.brain.state.ranges = ranges
        self.brain.state.scan_mono = now
        self.node.goal = (1., 1.)
        self.node.control, uart = ready()
        self.node.control.arc_validator = lambda v, w: False
        self.node.control.rotation_clear = False
        self.node._rotation_clear = lambda: False
        self.node._enter_cautious = lambda pose: False
        self.node.send_cmd = lambda cmd, **kw: self.brain.AGVROSNode.send_cmd(self.node, cmd, **kw)
        self.node.auto_nav_loop()
        self.assertTrue(uart.writes)
        self.assertTrue(all(line == b'S 0.000 0.000\n' for line in uart.writes))
        self.assertIn('HOLD', self.brain.state.explore_phase)
        self.assertEqual(self.node.goal, (1., 1.))


    def test_operational_speed_profile_cruises_at_80_rpm(self):
        """Requested speed is an upper bound; path curvature can reduce cruise speed."""
        now = time.monotonic()
        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 1.5
            self.brain.state.min_angle_deg = 0
            self.brain.state.auto_target_speed_rpm = 80.0
            self.brain.state.auto_target_turn_rpm = 80.0
            self.brain.state.cruise_speed_mps = 0.307
            self.brain.state.turn_w_rads = 3.194
            self.brain.state.safety_status = "SAFE"
            self.brain.state.ranges = [1.5] * 360
            self.brain.state.scan_mono = now

        cmd_history = []
        self.node.send_cmd = lambda cmd, **kw: (cmd_history.append(cmd) or True, 'SENT')
        self.node.control = types.SimpleNamespace(
            strict_preflight=False,
            clock=lambda: now,
            last_command=now,
            armed=True,
            drive=lambda cmd, **kw: (cmd_history.append(cmd) or True, 'SENT'),
            latest={'l_rpm': 75.0, 'r_rpm': 75.0, 'l_tgt': 80.0, 'r_tgt': 80.0}
        )

        self.node.auto_nav_loop()
        self.assertTrue(len(cmd_history) > 0)
        _, v, w = cmd_history[0].split()
        self.assertGreater(float(v), 0.0)
        self.assertLessEqual(float(v), 0.307)
        self.assertLessEqual(abs(float(w)), self.brain.state.turn_w_rads)

    def test_operator_mode_triggers_escape_on_danger_close(self):
        """Operator mode (strict_preflight=False) must call _try_escape when front obstacle < 25cm."""
        with self.brain.state.lock:
            self.brain.state.auto_mode = True
            self.brain.state.min_dist_m = 0.16
            self.brain.state.min_angle_deg = 4
            self.brain.state.safety_status = "DANGER_STOP"
            self.brain.state.body_bounds_m = (-0.16, -0.11, 0.10, 0.11)
            ranges = [2.0] * 360
            for deg in range(-20, 21):
                ranges[deg % 360] = 0.16
            self.brain.state.ranges = ranges
            self.brain.state.scan_mono = time.monotonic()

        calls = []
        self.node.control = types.SimpleNamespace(
            drive=lambda command, **kw: (calls.append((command, kw)) or True, 'SENT'),
            _event=lambda *a, **kw: None,
            clock=lambda: time.monotonic(),
            last_command=time.monotonic(),
            armed=True,
            strict_preflight=False,
            operator_rpm_profile=False,
            autonomy_allowed=True,
        )
        self.node.auto_nav_loop()
        self.assertTrue(len(calls) > 0, "Operator mode must issue escape command when danger_close")
        self.assertTrue(calls[0][0].startswith('V -0.09'), f"First command must be reverse, got: {calls[0][0]}")


if __name__ == '__main__':
    unittest.main()


