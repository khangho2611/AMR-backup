"""Offline regression coverage for HOME and SLAM state transitions.

Physical motor I/O and ROS transports are never opened in these tests.
"""
import math
import time
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_agv_navigation_fix import load_brain
from agv_navigation import GridPlanner


brain = load_brain()
state = brain.state


class HomeAndMapSafety(unittest.TestCase):
    def setUp(self):
        state.map_width = state.map_height = 80
        state.map_resolution = .05
        state.map_origin_x = state.map_origin_y = state.map_origin_yaw = 0.
        state.map_received = True
        state.map_mono = time.monotonic()
        state.map_data = [0] * 6400
        state.map_version = 1
        state.body_radius_m = .10
        state.wall_margin_m = .05
        state.path_history.clear()
        state.visited_cells.clear()
        state.last_path_pose = None
        state.auto_mode = False
        state.scan_mono = time.monotonic()
        state.ranges = [2.] * 360
        state.cruise_speed_mps = .10
        state.auto_target_speed_rpm = 30.
        state.frontier_reachable = state.unknown_cells = 0

    def node(self):
        n = brain.AGVROSNode.__new__(brain.AGVROSNode)
        n.control = MagicMock()
        n.control.strict_preflight = False
        n.control.latest = {'l_rpm': 0, 'r_rpm': 0, 'l_tgt': 0, 'r_tgt': 0}
        n.goal = None
        n.blocked_goals = []
        n.blocked_regions = []
        n.progress = deque()
        n.explore_state = 'EXPLORING'
        n._auto_task_mode = 'EXPLORE'
        n._goal_type = 'FRONTIER'
        n._goal_time = time.monotonic()
        n._auto_start_time = time.monotonic() - 20.
        n._last_frontier_search = 0.
        n._restore_normal_clearance = lambda pose: None
        n.send_cmd = MagicMock(return_value=(True, 'SENT'))
        return n

    def grid(self, data=None, yaw=0.):
        return GridPlanner(80, 80, .05, (0., 0., yaw),
                           state.map_data if data is None else data, .10, .05)

    def test_home_free_but_disconnected_by_wall_holds(self):
        n = self.node()
        n.home = (1., 1., 0.)
        class BlockedPath:
            def world_to_cell(self, x, y): return (20, 20)
            def traversable(self, c): return True
            def cell_to_world(self, x, y): return (1., 1.)
            def path(self, start, dest): return None
        n._grid = lambda margin=None: BlockedPath()
        n._pose_map = lambda: (2., 2., 0.)
        self.assertIsNone(n._get_safe_home_target())

    def test_home_with_no_map_is_never_returned_as_safe(self):
        n = self.node()
        n.home = (1., 1., 0.)
        n._grid = lambda margin=None: None
        self.assertIsNone(n._get_safe_home_target((2., 2., 0.)))

    def test_home_completion_waits_for_post_stop_confirmation(self):
        n = self.node()
        n.home = (1., 1., 0.)
        n.goal = (1., 1.)
        n._goal_type = 'HOME'
        n.explore_state = 'RETURNING_HOME'
        n._pose_map = lambda: (1.06, 1.06, 0.)
        grid = self.grid()
        n._grid = lambda margin=None: grid
        n.control.health.return_value = {'stop_confirmed': False}
        state.auto_mode = True

        n.auto_nav_loop()
        self.assertEqual(n.explore_state, 'WAIT_STOP')
        self.assertTrue(state.auto_mode)
        n.control.request_stop.assert_called_once_with('HOME_STOP', wait=False)

        n.auto_nav_loop()
        self.assertEqual(n.explore_state, 'WAIT_STOP')
        self.assertTrue(state.auto_mode)

        n.control.health.return_value = {'stop_confirmed': True}
        n.auto_nav_loop()
        self.assertEqual(n.explore_state, 'COMPLETED')
        self.assertFalse(state.auto_mode)

    def test_unconfirmed_home_stop_is_failure_not_success(self):
        n = self.node()
        n.explore_state = 'WAIT_STOP'
        n._home_stop_started = time.monotonic() - 1.5
        n.control.health.return_value = {'stop_confirmed': False}
        state.auto_mode = True
        n.auto_nav_loop()
        self.assertEqual(n.explore_state, 'HOME_FAILED')
        self.assertIn('UNCONFIRMED', state.explore_phase)
        self.assertFalse(state.auto_mode)

    def test_explore_with_disconnected_home_does_not_roam(self):
        n = self.node()
        n.home = (1., 1., 0.)
        n._pose_map = lambda: (2., 2., 0.)
        n._grid = lambda margin=None: self.grid()
        n.find_best_frontier = lambda x, y: None
        n._get_safe_home_target = lambda pose: None
        state.auto_mode = True
        n.auto_nav_loop()
        self.assertIn('HOLD', state.explore_phase)
        self.assertEqual(n.explore_state, 'EXPLORING')
        n.send_cmd.assert_called_with('V 0.000 0.000', autonomous=True)

    def test_unreachable_frontiers_with_unknown_cells_report_partial_mapping(self):
        n = self.node()
        n.home = (1., 1., 0.)
        n._pose_map = lambda: (2., 2., 0.)
        n._grid = lambda margin=None: self.grid()
        n.find_best_frontier = lambda x, y: None
        n._get_safe_home_target = lambda pose: (1., 1.)
        state.frontier_reachable = 0
        state.unknown_cells = 1500
        state.auto_mode = True
        n.auto_nav_loop()
        self.assertTrue(n._explore_partial)
        self.assertEqual(n._goal_type, 'HOME')
        self.assertIn('MỘT PHẦN', state.explore_phase)

        n._pose_map = lambda: (1.05, 1.05, 0.)
        n.auto_nav_loop()
        self.assertIn('MỘT PHẦN', n._home_completion_phase)

    def test_reset_refuses_autonomy_stale_and_moving_wheels(self):
        n = self.node()
        n.control.health.return_value = {
            'd0_age_s': 0.01, 'latest_d0': {
                'l_rpm': 0., 'r_rpm': 0., 'l_tgt': 0., 'r_tgt': 0.}}
        original = state.map_data
        state.auto_mode = True
        self.assertEqual(n.reset_slam_map(), (False, 'AUTO_ACTIVE_STOP_FIRST'))
        state.auto_mode = False
        n.control.health.return_value['d0_age_s'] = 2.
        self.assertEqual(n.reset_slam_map()[1], 'D0_STALE_CANNOT_CONFIRM_STATIONARY')
        n.control.health.return_value['d0_age_s'] = 0.01
        n.control.health.return_value['latest_d0']['l_rpm'] = 12.
        self.assertEqual(n.reset_slam_map()[1], 'MCU_MOVING_STOP_FIRST')
        self.assertIs(state.map_data, original)

        n.control.health.return_value['latest_d0']['l_rpm'] = float('nan')
        self.assertEqual(n.reset_slam_map()[1], 'MCU_STATIONARITY_UNKNOWN')
        n.control.health.return_value['latest_d0'] = {}
        self.assertEqual(n.reset_slam_map()[1], 'MCU_STATIONARITY_UNKNOWN')

    def test_failed_slam_restart_leaves_coverage_and_goals_intact(self):
        n = self.node()
        n.control.health.return_value = {
            'd0_age_s': .01, 'latest_d0': {
                'l_rpm': 0., 'r_rpm': 0., 'l_tgt': 0., 'r_tgt': 0.}}
        n.get_logger = MagicMock()
        n.goal = (2., 3.)
        state.visited_cells.add((20, 20))
        old_map = state.map_data
        with patch('subprocess.run', side_effect=OSError('SLAM launcher unavailable')):
            ok, reason = n.reset_slam_map()
        self.assertFalse(ok)
        self.assertIn('SLAM_RESTART_FAILED', reason)
        self.assertIs(state.map_data, old_map)
        self.assertEqual(n.goal, (2., 3.))
        self.assertEqual(state.visited_cells, {(20, 20)})

    def test_launcher_return_code_and_process_check_are_required_before_map_reset(self):
        n = self.node()
        n.control.health.return_value = {
            'd0_age_s': .01, 'latest_d0': {
                'l_rpm': 0., 'r_rpm': 0., 'l_tgt': 0., 'r_tgt': 0.}}
        n.get_logger = MagicMock()
        n.goal = (2., 3.)
        old_map = state.map_data
        with patch('subprocess.run') as run:
            run.return_value.returncode = 1
            run.return_value.stderr = b'failure'
            self.assertEqual(n.reset_slam_map()[1], 'SLAM_RESTART_SCRIPT_FAILED')
            run.assert_called_once()
        self.assertIs(state.map_data, old_map)
        self.assertEqual(n.goal, (2., 3.))
        with (patch('subprocess.run') as run,
              patch.object(brain.time, 'monotonic', side_effect=[100., 101., 107.]),
              patch.object(brain.time, 'sleep')):
            run.side_effect = [SimpleNamespace(returncode=0), SimpleNamespace(returncode=1)]
            self.assertEqual(n.reset_slam_map()[1], 'SLAM_RESTART_NODE_NOT_RUNNING')
        self.assertIs(state.map_data, old_map)
        self.assertEqual(n.goal, (2., 3.))

    def test_reset_waits_for_delayed_slam_node_before_clearing_state(self):
        n = self.node()
        n.control.health.return_value = {
            'd0_age_s': .01, 'latest_d0': {
                'l_rpm': 0., 'r_rpm': 0., 'l_tgt': 0., 'r_tgt': 0.}}
        n.get_logger = MagicMock()
        n.goal = (2., 3.)
        with patch('subprocess.run', side_effect=[
            SimpleNamespace(returncode=0),
            SimpleNamespace(returncode=1),
            SimpleNamespace(returncode=0),
        ]) as run, patch.object(brain.time, 'sleep') as sleep:
            self.assertEqual(n.reset_slam_map(), (True, 'SLAM_RESTART_REQUESTED'))
        self.assertEqual(run.call_count, 3)
        sleep.assert_called_once_with(.25)
        self.assertIsNone(n.goal)
        self.assertIsNone(n.home)
        self.assertFalse(state.map_received)

    def test_auto_start_waits_for_transient_tf_before_arm_motion_gate(self):
        n = self.node()
        n._pose_map = MagicMock(side_effect=[None, None, (1., 1., 0.)])
        n._grid = lambda: self.grid()
        n._scan_tf_valid = True
        n.control.clock = time.monotonic
        n.control._ages.return_value = {
            'd0_age_s': .01, 'scan_age_s': .02, 'caller_age_s': .01}
        n.control.armed = True
        n.control.latched = False
        n.control.fault = None
        n.control.latest = {'safety': 'ARMED'}
        n.control.trial_deadline = None
        n.control.generation = 1
        n.initialize_navigation = MagicMock()
        state.map_frame = 'map'
        with patch.object(brain.time, 'sleep') as sleep:
            success, reason, blockers, gate = n.start_auto()
        self.assertTrue(success)
        self.assertEqual(reason, 'STARTED')
        self.assertEqual(blockers, [])
        self.assertEqual(n._pose_map.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(state.auto_mode)
        self.assertEqual(gate['pose'], (1., 1., 0.))
        n.send_cmd.assert_called_once_with('V 0.000 0.000', autonomous=True)

    def test_map_origin_shift_reprojects_coverage_cells(self):
        n = self.node()
        n._yaw = lambda rotation: 0.
        n._fresh_ros_header = lambda header, max_age: True
        state.map_frame = 'map'
        state.visited_cells.add((20, 20))
        origin = SimpleNamespace(position=SimpleNamespace(x=-.05, y=-.05),
                                 orientation=SimpleNamespace())
        info = SimpleNamespace(width=80, height=80, resolution=.05, origin=origin)
        msg = SimpleNamespace(info=info, header=SimpleNamespace(frame_id='map'),
                              data=list(state.map_data))
        n.map_cb(msg)
        self.assertEqual(state.visited_cells, {(21, 21)})
        self.assertEqual(state.map_origin_x, -.05)

        # A TF frame change cannot be reprojected safely and must stop motion.
        n.initialize_navigation = MagicMock()
        n.ai1_runtime = object()
        n.ai2_session = object()
        n.home = (1., 1., 0.)
        n.goal = (2., 2.)
        state.auto_mode = True
        state.visited_cells.add((5, 5))
        msg.header.frame_id = 'new_map'
        n.map_cb(msg)
        self.assertFalse(state.auto_mode)
        self.assertEqual(state.visited_cells, set())
        self.assertIsNone(n.home)
        self.assertIsNone(n.goal)
        self.assertIsNotNone(n.ai1_runtime)
        self.assertIsNotNone(n.ai2_session)
        n.initialize_navigation.assert_not_called()
        n.control.request_stop.assert_called_with('MAP_FRAME_CHANGED', wait=False)

    def test_home_timeout_cannot_mark_mission_completed(self):
        n = self.node()
        n.home = (1., 1., 0.)
        n.goal = (1., 1.)
        n._goal_type = 'HOME'
        n._goal_time = time.monotonic() - 40.
        n._goal_progress = (n.goal, (2., 2.), time.monotonic() - 40.)
        n._pose_map = lambda: (2., 2., 0.)
        n._grid = lambda margin=None: self.grid()
        state.auto_mode = True
        n.auto_nav_loop()
        self.assertFalse(state.auto_mode)
        self.assertEqual(n.explore_state, 'HOME_FAILED')
        n.control.request_stop.assert_called_with('HOME_TIMEOUT', wait=False)

    def test_visited_cells_follow_rotated_map_axes(self):
        state.map_origin_yaw = math.pi / 2
        grid = self.grid(yaw=math.pi / 2)
        px, py = grid.cell_to_world(20, 20)
        n = self.node()
        n.home = (px, py, 0.)
        n._pose_map = lambda: (px, py, 0.)
        n._grid = lambda margin=None: grid
        state.auto_mode = True
        class EndAfterCoverage(Exception): pass
        def end_after_coverage(pose): raise EndAfterCoverage()
        n._restore_normal_clearance = end_after_coverage
        with self.assertRaises(EndAfterCoverage):
            n.auto_nav_loop()
        self.assertIn((20, 20), state.visited_cells)
        self.assertTrue(all(0 <= x < 80 and 0 <= y < 80
                            and state.map_data[y * 80 + x] == 0
                            for x, y in state.visited_cells))


if __name__ == '__main__':
    unittest.main()
