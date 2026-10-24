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


class TestAGVCoveragePatrol(unittest.TestCase):
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

    def test_find_best_coverage_goal_picks_unvisited_free_cell(self):
        node = AGVROSNode.__new__(AGVROSNode)
        node.goal = None
        node._goal_type = 'FRONTIER'
        node.blocked_goals = []
        node.blocked_regions = []
        node.control = MagicMock()
        node.control.strict_preflight = False

        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), [0] * 6400, 0.20, 0.05)
        node._grid = lambda margin=None: planner

        # When visited_cells covers only the area around (1.0, 1.0)
        gx, gy = planner.world_to_cell(1.0, 1.0)
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                state.visited_cells.add((gx + dx, gy + dy))

        goal = node.find_best_coverage_goal(1.0, 1.0)
        self.assertIsNotNone(goal)
        # Goal should be outside the visited zone
        goal_cell = planner.world_to_cell(*goal)
        self.assertNotIn(goal_cell, state.visited_cells)

    def test_coverage_mode_selects_coverage_goal_when_frontier_exhausted(self):
        node = AGVROSNode.__new__(AGVROSNode)
        node.initialize_navigation()
        node._auto_task_mode = 'COVERAGE'
        node.explore_state = 'EXPLORING'
        node.home = (1.0, 1.0, 0.0)
        node._auto_start_time = time.monotonic() - 20.0
        node._last_frontier_search = 0.0
        node.progress = []
        node.control = MagicMock()
        node.control.strict_preflight = False
        node.control.latest = {'l_rpm': 10.0, 'r_rpm': 10.0}

        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), [0] * 6400, 0.20, 0.05)
        node._grid = lambda margin=None: planner
        node._pose_map = lambda: (1.0, 1.0, 0.0)
        node.find_best_frontier = lambda rx, ry: None

        sent_cmds = []
        node.send_cmd = lambda cmd, autonomous=False, planned_turn=False: (sent_cmds.append(cmd) or (True, 'SENT'))

        state.scan_mono = time.monotonic()
        node.auto_nav_loop()

        self.assertEqual(node.explore_state, 'COVERAGE_PATROL')
        self.assertEqual(node._goal_type, 'COVERAGE')
        self.assertIsNotNone(node.goal)

    def test_return_to_home_when_all_coverage_is_complete(self):
        node = AGVROSNode.__new__(AGVROSNode)
        node.initialize_navigation()
        node.explore_state = 'COVERAGE_PATROL'
        node.home = (1.0, 1.0, 0.0)
        node._auto_start_time = time.monotonic() - 30.0
        node._last_frontier_search = 0.0
        node.progress = []
        node.control = MagicMock()
        node.control.strict_preflight = False
        node.control.latest = {'l_rpm': 10.0, 'r_rpm': 10.0}

        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), [0] * 6400, 0.20, 0.05)
        node._grid = lambda margin=None: planner
        node._pose_map = lambda: (2.5, 2.5, 0.0)
        node.find_best_frontier = lambda rx, ry: None
        node.find_best_coverage_goal = lambda rx, ry: None  # No unvisited cells left!

        sent_cmds = []
        node.send_cmd = lambda cmd, autonomous=False, planned_turn=False: (sent_cmds.append(cmd) or (True, 'SENT'))

        state.scan_mono = time.monotonic()
        node.auto_nav_loop()

        # Should transition to RETURNING_HOME
        self.assertEqual(node.explore_state, 'RETURNING_HOME')
        self.assertEqual(node._goal_type, 'HOME')
        self.assertAlmostEqual(node.goal[0], 1.0, delta=0.2)
        self.assertAlmostEqual(node.goal[1], 1.0, delta=0.2)

    def test_explore_mode_returns_home_directly_without_coverage(self):
        """In EXPLORE mode, robot must return directly to Home when mapping finishes, not wander into coverage."""
        node = AGVROSNode.__new__(AGVROSNode)
        node.initialize_navigation()
        node._auto_task_mode = 'EXPLORE'
        node.explore_state = 'EXPLORING'
        node.home = (1.0, 1.0, 0.0)
        node._auto_start_time = time.monotonic() - 25.0
        node._last_frontier_search = 0.0
        node.progress = []
        node.control = MagicMock()
        node.control.strict_preflight = False
        node.control.latest = {'l_rpm': 10.0, 'r_rpm': 10.0}

        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), [0] * 6400, 0.20, 0.05)
        node._grid = lambda margin=None: planner
        node._pose_map = lambda: (2.5, 2.5, 0.0)
        node.find_best_frontier = lambda rx, ry: None
        node.find_best_coverage_goal = lambda rx, ry: (2.0, 2.0)  # Coverage goal exists, but should be ignored!

        sent_cmds = []
        node.send_cmd = lambda cmd, autonomous=False, planned_turn=False: (sent_cmds.append(cmd) or (True, 'SENT'))

        state.scan_mono = time.monotonic()
        node.auto_nav_loop()

        # In EXPLORE mode, it must return to HOME, NEVER COVERAGE_PATROL
        self.assertEqual(node.explore_state, 'RETURNING_HOME')
        self.assertEqual(node._goal_type, 'HOME')
        self.assertAlmostEqual(node.goal[0], 1.0, delta=0.2)
        self.assertAlmostEqual(node.goal[1], 1.0, delta=0.2)

    def test_coverage_mode_patrols_floor(self):
        """In COVERAGE mode, robot must look for unvisited floor cells and enter COVERAGE_PATROL."""
        node = AGVROSNode.__new__(AGVROSNode)
        node.initialize_navigation()
        node._auto_task_mode = 'COVERAGE'
        node.explore_state = 'COVERAGE_PATROL'
        node.home = (1.0, 1.0, 0.0)
        node._auto_start_time = time.monotonic() - 10.0
        node._last_frontier_search = 0.0
        node.progress = []
        node.control = MagicMock()
        node.control.strict_preflight = False
        node.control.latest = {'l_rpm': 10.0, 'r_rpm': 10.0}

        planner = GridPlanner(80, 80, 0.05, (0.0, 0.0, 0.0), [0] * 6400, 0.20, 0.05)
        node._grid = lambda margin=None: planner
        node._pose_map = lambda: (1.0, 1.0, 0.0)
        node.find_best_coverage_goal = lambda rx, ry: (2.2, 2.2)

        sent_cmds = []
        node.send_cmd = lambda cmd, autonomous=False, planned_turn=False: (sent_cmds.append(cmd) or (True, 'SENT'))

        state.scan_mono = time.monotonic()
        node.auto_nav_loop()

        self.assertEqual(node.explore_state, 'COVERAGE_PATROL')
        self.assertEqual(node._goal_type, 'COVERAGE')
        self.assertEqual(node.goal, (2.2, 2.2))


if __name__ == '__main__':
    unittest.main()

