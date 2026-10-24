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

class TestAGVFrontierLifecycle(unittest.TestCase):
    def setUp(self):
        state.target_goal_x = 1.5
        state.target_goal_y = 2.5
        state.map_width = 100
        state.map_height = 100
        state.map_resolution = 0.05
        state.map_origin_x = 0.0
        state.map_origin_y = 0.0
        state.map_origin_yaw = 0.0
        state.map_version = 1
        state.map_received = True
        state.map_mono = time.monotonic()
        state.body_radius_m = 0.22
        state.wall_margin_m = 0.15
        state.map_data = [0] * (100 * 100)

    def test_exclude_goal_clears_web_coordinates_and_sets_duration(self):
        node = AGVROSNode.__new__(AGVROSNode)
        node.goal = (1.5, 2.5)
        node.blocked_goals = []
        node.blocked_regions = []
        node.progress = []
        node.control = MagicMock()
        node.control.strict_preflight = False  # operator mode

        now = time.monotonic()
        # Test failed exclusion (doorway blocked) -> at least 60s
        node._exclude_goal(now, failed=True)
        self.assertIsNone(node.goal)
        self.assertEqual(state.target_goal_x, 0.0)
        self.assertEqual(state.target_goal_y, 0.0)
        self.assertEqual(len(node.blocked_regions), 1)
        bx, by, br, expiry = node.blocked_regions[0]
        self.assertAlmostEqual(bx, 1.5)
        self.assertAlmostEqual(by, 2.5)
        self.assertGreaterEqual(expiry - now, 59.0)

        # Test completed exclusion -> at least 90s
        node.goal = (3.0, 4.0)
        now2 = time.monotonic()
        node._exclude_goal(now2, failed=False)
        self.assertIsNone(node.goal)
        self.assertEqual(state.target_goal_x, 0.0)
        self.assertEqual(state.target_goal_y, 0.0)
        self.assertEqual(len(node.blocked_goals), 1)
        bx, by, br, expiry = node.blocked_goals[0]
        self.assertAlmostEqual(bx, 3.0)
        self.assertAlmostEqual(by, 4.0)
        self.assertGreaterEqual(expiry - now2, 89.0)

    def test_reset_slam_map_clears_all_navigation_and_goals(self):
        node = AGVROSNode.__new__(AGVROSNode)
        state.auto_mode = False
        node.control = MagicMock()
        node.control.health.return_value = {'d0_age_s': 0.01, 'latest_d0': {
            'l_rpm': 0.0, 'r_rpm': 0.0, 'l_tgt': 0.0, 'r_tgt': 0.0}}
        node.goal = (2.0, 3.0)
        node.blocked_goals = [(2.0, 3.0, 0.35, time.monotonic() + 100)]
        node.blocked_regions = [(1.0, 1.0, 0.35, time.monotonic() + 100)]
        node.progress = [1, 2, 3]
        state.target_goal_x = 2.0
        state.target_goal_y = 3.0

        node.get_logger = MagicMock()
        with unittest.mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            ok, _ = node.reset_slam_map()
        self.assertTrue(ok)

        self.assertIsNone(node.goal)
        self.assertEqual(len(node.blocked_goals), 0)
        self.assertEqual(len(node.blocked_regions), 0)
        self.assertEqual(len(node.progress), 0)
        self.assertEqual(state.target_goal_x, 0.0)
        self.assertEqual(state.target_goal_y, 0.0)

    def test_goal_acceptance_within_42cm_and_blocked_count(self):
        node = AGVROSNode.__new__(AGVROSNode)
        node.goal = (1.40, 1.25)
        node.blocked_goals = []
        node.blocked_regions = []
        node.progress = []
        node.control = MagicMock()
        node.control.strict_preflight = False
        node._goal_time = time.monotonic()
        node._goal_blocked_count = 0

        pose = (1.0, 1.25, 0.0)
        dist = math.hypot(pose[0] - node.goal[0], pose[1] - node.goal[1])
        self.assertLessEqual(dist, 0.42)

        # Distance <= 0.42m triggers completion
        now = time.monotonic()
        if dist <= 0.42:
            node._exclude_goal(now, failed=False)
            node.goal = None
            node._goal_blocked_count = 0

        self.assertIsNone(node.goal)
        self.assertEqual(state.target_goal_x, 0.0)
        self.assertEqual(state.target_goal_y, 0.0)
        self.assertEqual(len(node.blocked_goals), 1)

if __name__ == '__main__':
    unittest.main()
