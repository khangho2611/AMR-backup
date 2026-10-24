import os
import sys
import time
import math
import unittest
from unittest.mock import MagicMock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from test_agv_navigation_fix import load_brain

brain_module = load_brain()
state = brain_module.state
AGVROSNode = brain_module.AGVROSNode
from agv_navigation import GridPlanner


class TestAGVPointNavigation(unittest.TestCase):
    def setUp(self):
        state.target_goal_x = 0.0
        state.target_goal_y = 0.0
        state.map_width = 80
        state.map_height = 80
        state.map_resolution = 0.05
        state.map_origin_x = 0.0
        state.map_origin_y = 0.0
        state.map_origin_yaw = 0.0
        state.map_version = 1
        state.map_received = True
        state.map_mono = time.monotonic()
        state.body_radius_m = 0.20
        state.wall_margin_m = 0.05
        state.map_data = [0] * (80 * 80)
        state.visited_cells = set()
        state.auto_mode = True
        state.cruise_speed_mps = 0.14
        state.auto_target_speed_rpm = 38.0
        state.frontier_reachable = 0
        state.unknown_cells = 0
        state.ranges = [2.0] * 360
        state.scan_mono = time.monotonic()

    def test_get_safe_point_target_valid_free_space(self):
        node = AGVROSNode.__new__(AGVROSNode)
        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), [0] * 6400, 0.20, 0.05)
        node._grid = lambda margin=None: planner
        node._pose_map = lambda: (1.0, 1.0, 0.0)

        target = node._get_safe_point_target(2.0, 2.0, pose=(1.0, 1.0, 0.0))
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target[0], 2.0, places=2)
        self.assertAlmostEqual(target[1], 2.0, places=2)

    def test_get_safe_point_target_snaps_near_wall(self):
        node = AGVROSNode.__new__(AGVROSNode)
        data = [0] * 6400
        # Put an obstacle cell at (50, 50)
        data[50 * 80 + 50] = 100
        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), data, 0.20, 0.05)
        node._grid = lambda margin=None: planner
        node._pose_map = lambda: (1.0, 1.0, 0.0)

        # Target directly at obstacle cell in world coordinates: (50 * 0.05, 50 * 0.05) = (2.5, 2.5)
        target = node._get_safe_point_target(2.5, 2.5, pose=(1.0, 1.0, 0.0))
        # Should snap to a nearby safe traversable cell
        self.assertIsNotNone(target)
        self.assertTrue(planner.traversable(planner.world_to_cell(*target)))

    def test_navigate_to_point_rejects_invalid_coords(self):
        node = AGVROSNode.__new__(AGVROSNode)
        ok, reason, blockers, _ = node.navigate_to_point(float('nan'), 2.0)
        self.assertFalse(ok)
        self.assertEqual(reason, 'INVALID_COORDINATES')

    def test_navigate_to_point_starts_auto_mode(self):
        node = AGVROSNode.__new__(AGVROSNode)
        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), [0] * 6400, 0.20, 0.05)
        node._grid = lambda margin=None: planner
        node._pose_map = lambda: (1.0, 1.0, 0.0)
        node.start_auto = MagicMock(return_value=(True, 'STARTED', [], {}))

        ok, reason, blockers, _ = node.navigate_to_point(2.0, 2.0)
        self.assertTrue(ok)
        node.start_auto.assert_called_once()
        _, kwargs = node.start_auto.call_args
        self.assertEqual(kwargs.get('mode'), 'NAV_TO_GOAL')
        self.assertAlmostEqual(kwargs.get('target')[0], 2.0, places=2)

    def test_point_goal_completion_at_destination(self):
        node = AGVROSNode.__new__(AGVROSNode)
        node.home = (0.0, 0.0, 0.0)
        node.goal = (2.0, 2.0)
        node._goal_type = 'POINT'
        node._goal_time = time.monotonic()
        node._goal_progress = ((2.0, 2.0), (1.98, 1.98), time.monotonic())
        node.explore_state = 'NAVIGATING_TO_GOAL'
        node.progress = []
        node.control = MagicMock()
        node.control.strict_preflight = False
        node.control.latest = {'l_rpm': 0.0, 'r_rpm': 0.0, 'l_tgt': 0.0, 'r_tgt': 0.0}
        node.control.health = MagicMock(return_value={'stop_confirmed': True})
        node.send_cmd = MagicMock(return_value=(True, 'ACCEPTED'))
        node._pose_map = lambda: (2.05, 2.05, 0.0)  # within 0.15m of (2.0, 2.0)
        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), [0] * 6400, 0.20, 0.05)
        node._grid = lambda margin=None: planner
        node._restore_normal_clearance = MagicMock()

        state.auto_mode = True
        state.scan_mono = time.monotonic()
        state.ranges = [2.0] * 360

        node.auto_nav_loop()

        # Robot should have arrived, stopped, and marked completion
        self.assertEqual(node.explore_state, 'COMPLETED')
        self.assertFalse(state.auto_mode)
        self.assertIn('ĐÃ ĐẾN ĐÍCH', state.explore_phase)
        node.control.request_stop.assert_called_with('GOAL_REACHED', wait=False)

    def test_goal_reached_stop_does_not_fault_session(self):
        from agv_command_session import CommandSession
        session = CommandSession(serial_stream=MagicMock(), strict_preflight=False)
        session._write = MagicMock(return_value=True)
        session.request_stop('GOAL_REACHED', wait=False)
        self.assertIsNone(session.fault)
        self.assertFalse(session.armed)
        self.assertTrue(session.latched)

    def test_point_cushion_away_from_wall(self):
        node = AGVROSNode.__new__(AGVROSNode)
        w, h, res = 80, 80, 0.05
        data = [0] * (w * h)
        for y in range(h):
            data[y * w + 20] = 100
        planner = GridPlanner(w, h, res, (0.0, 0.0, 0.0), data, 0.20, 0.02)
        safe_planner = GridPlanner(w, h, res, (0.0, 0.0, 0.0), data, 0.20, 0.08)
        node._grid = lambda margin=None: safe_planner if margin == 0.08 else planner
        node._pose_map = lambda: (0.5, 2.0, 0.0)
        safe_pt = node._get_safe_point_target(0.85, 2.0, pose=(0.5, 2.0, 0.0))
        self.assertIsNotNone(safe_pt)
        self.assertLessEqual(safe_pt[0], 0.75)


if __name__ == '__main__':
    unittest.main()
