"""PC-only AI/Navigation regressions: ROS, serial hardware and motor I/O are mocked."""

from collections import deque
import io
import json
import math
import pathlib
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from agv_ai_bridge import (ai1_prepare_scan, ai1_velocity, ai2_action_direction,
                           ai2_observation, ai2_ranked_candidates, measured_twist,
                           ai2_valid_action_mask, reproject_visited_cells)
from test_agv_navigation_fix import load_brain
from agv_navigation import GridPlanner


class OfflineGrid:
    w = h = 40
    res = .1
    origin = (0., 0., 0.)

    def world_to_cell(self, x, y):
        return (int(x / self.res), int(y / self.res))

    def cell_to_world(self, x, y):
        return ((x + .5) * self.res, (y + .5) * self.res)

    def traversable(self, cell):
        return cell is not None and 0 <= cell[0] < self.w and 0 <= cell[1] < self.h

    def swept_clear(self, pose, v, w):
        return True

    def path(self, start, goal):
        if not self.traversable(self.world_to_cell(*start)) or not self.traversable(self.world_to_cell(*goal)):
            return None
        return [start, goal] if start != goal else [start]


class OfflineAI1:
    def __init__(self, cmd=(.025, 0.0), error=None):
        self.cmd, self.error = cmd, error
        self.calls = []

    def predict_from_sensors(self, ranges, pose, goal, v, w):
        self.last_ranges = list(ranges)
        self.calls.append((v, w))
        self.last_goal = goal
        if self.error:
            raise self.error
        return self.cmd


def test_ai1_scan_densifies_tiny_missing_bins_conservatively():
    scan = [3.0] * 360
    scan[0], scan[1], scan[359] = 1.0, 0.0, 0.0
    scan[2] = 2.0
    prepared = ai1_prepare_scan(scan)
    assert len(prepared) == 360
    assert prepared[1] == 1.0
    assert prepared[359] == 1.0
    assert prepared[0] == 1.0


def test_ai1_scan_rejects_unobserved_sector_and_excessive_holes():
    import pytest
    scan = [3.0] * 360
    scan[20:23] = [0.0] * 3
    with pytest.raises(ValueError, match='UNOBSERVED_SECTOR'):
        ai1_prepare_scan(scan)
    scan = [3.0] * 360
    for deg in range(0, 80, 2):
        scan[deg] = 0.0
    with pytest.raises(ValueError, match='INSUFFICIENT_COVERAGE'):
        ai1_prepare_scan(scan)


def test_ai1_does_not_convert_unobserved_16m_bins_into_free_space():
    scan = [2.0] * 360
    scan[40:45] = [16.0] * 5
    with pytest.raises(ValueError, match='UNOBSERVED_SECTOR'):
        ai1_prepare_scan(scan)
    with pytest.raises(ValueError, match='INSUFFICIENT_COVERAGE'):
        ai1_prepare_scan([16.0] * 360)


class OfflineAI2:
    def __init__(self, q):
        self.q = q
        self.calls = []

    def run(self, _, inputs):
        self.calls.append(inputs)
        assert inputs['map'].shape == (1, 3, 9, 9)
        assert inputs['feat'].shape == (1, 8)
        return [np.asarray(self.q, dtype=np.float32)[None, :]]


def node_fixture():
    brain = load_brain()
    brain.state = brain.AGVSharedState()
    node = brain.AGVROSNode.__new__(brain.AGVROSNode)
    # Bypass ROS init and model-loading entirely; all command outputs are captured.
    node.control = SimpleNamespace(strict_preflight=False, armed=False,
                                   latest={'v': .12, 'w': -.3})
    node.progress = deque()
    node.home = (0., 0., 0.)
    node.goal = (2., 0.)
    node._goal_time = time.monotonic()
    node._goal_type = 'FRONTIER'
    node._auto_task_mode = 'EXPLORE'
    node.blocked_goals = []
    node.blocked_regions = []
    node.explore_state = 'EXPLORING'
    node._ai1_active = False
    node._ai1_shadow_cmd = None
    node._ai1_error = None
    node.ai1_mode = 'off'
    node.ai2_mode = 'off'
    node.ai1_runtime = None
    node.ai2_session = None
    node._ai2_shadow_goal = None
    node._ai2_error = None
    node._ai2_best_action = None
    node._ai2_q_vals = None
    node._grid = lambda margin=None: OfflineGrid()
    node._pose_map = lambda: (0., 0., 0.)
    node._restore_normal_clearance = lambda _: None
    commands = []

    def capture(cmd, autonomous=False, planned_turn=False):
        assert autonomous
        commands.append(cmd)
        return (True, 'MOCK_ONLY')

    node.send_cmd = capture
    with brain.state.lock:
        brain.state.auto_mode = True
        brain.state.scan_mono = time.monotonic()
        brain.state.ranges = [1.5] * 360
        brain.state.cruise_speed_mps = .15
        brain.state.frontier_reachable = 1
        brain.state.unknown_cells = 100
        brain.state.map_data = [0] * 1600
        brain.state.map_resolution = .1
    return brain, node, commands


def test_ai1_measured_odometry_and_invalid_data():
    assert measured_twist({'v': .1, 'w': -.5}) == (.1, -.5)
    assert measured_twist({'v': 'nan', 'w': .1}) == (0., 0.)
    assert measured_twist({}) == (0., 0.)


@pytest.mark.parametrize('cmd,result', [((0., 0.), (0., 0.)),
                                            ((.015, -.05), (.015, -.05)),
                                            ((.6, 5.), (.15, 1.))])
def test_ai1_preserves_filtered_stop_slow_speed_and_limits(cmd, result):
    assert ai1_velocity(cmd, .15, 1.) == result


@pytest.mark.parametrize('cmd', [(math.nan, 0.), (0., math.inf),
                                     (0.,), (0., 0., 0.), (-.1, 0.)])
def test_ai1_rejects_invalid_or_unsafe_action(cmd):
    with pytest.raises(ValueError):
        ai1_velocity(cmd, .15, 1.)


def test_ai1_shadow_infers_from_telemetry_without_command_authority():
    _, node, sent = node_fixture()
    policy = OfflineAI1((0., 0.))
    node.ai1_runtime, node.ai1_mode = policy, 'shadow'
    node.auto_nav_loop()
    assert policy.calls == [(.12, -.3)]
    assert node._ai1_shadow_cmd == (0., 0.)
    assert not node._ai1_active
    assert any(c != 'V 0.000 0.000' for c in sent)  # Traditional navigation controls.


@pytest.mark.parametrize('cmd', [(0., 0.), (.015, -.05)])
def test_ai1_control_sends_exact_filtered_command_to_mock_only(cmd):
    _, node, sent = node_fixture()
    node.ai1_runtime, node.ai1_mode = OfflineAI1(cmd), 'control'
    node.auto_nav_loop()
    assert sent[-1] == f'V {cmd[0]:.3f} {cmd[1]:.3f}'
    assert node._ai1_active


def test_operator_ai1_aims_for_astar_detour_not_through_wall():
    _, node, sent = node_fixture()
    width = height = 60
    data = [0] * (width * height)
    for y in range(12, 48):
        data[y * width + 30] = 100
    grid = GridPlanner(width, height, .1, (0., 0., 0.), data,
                       body_radius=.08, margin=.04, budget_s=.75)
    pose = (1.0, 2.0, 0.)
    goal = (4.8, 2.0)
    assert grid.path(pose[:2], goal)
    node._grid = lambda margin=None: grid
    node._pose_map = lambda: pose
    node.goal = goal
    node._goal_time = time.monotonic()
    policy = OfflineAI1((.025, 0.))
    node.ai1_runtime, node.ai1_mode = policy, 'control'
    node.auto_nav_loop()
    assert policy.last_goal != goal
    assert math.dist(policy.last_goal, pose[:2]) < .40
    assert sent[-1] == 'V 0.025 0.000'


def test_local_astar_lookahead_advances_in_clear_inflated_corridor():
    _, node, _ = node_fixture()
    grid = GridPlanner(60, 60, .05, (0., 0., 0.), [0] * 3600,
                       body_radius=.06, margin=.02, budget_s=.75)
    pose, goal = (1.0, 1.0, 0.), (2.0, 1.0)
    wp = node._local_path_target(grid, pose, goal)
    assert wp is not None
    assert .15 <= math.dist(wp, pose[:2]) <= .26


def test_local_astar_lookahead_never_cuts_through_inflated_wall():
    _, node, _ = node_fixture()
    w = h = 60
    data = [0] * (w * h)
    for y in range(15, 45):
        data[y * w + 30] = 100
    grid = GridPlanner(w, h, .05, (0., 0., 0.), data,
                       body_radius=.06, margin=.04, budget_s=.75)
    pose, goal = (1.25, 1.30, 0.), (1.90, 1.30)
    wp = node._local_path_target(grid, pose, goal)
    assert wp is not None
    start, end = grid.world_to_cell(*pose[:2]), grid.world_to_cell(*wp)
    assert grid.segment_known_free(start, end)
    assert math.dist(wp, pose[:2]) <= .26


def test_operator_auto_holds_when_astar_path_missing():
    _, node, sent = node_fixture()
    grid = OfflineGrid()
    grid.path = lambda start, goal: None
    node._grid = lambda margin=None: grid
    policy = OfflineAI1((.05, 0.))
    node.ai1_runtime, node.ai1_mode = policy, 'control'
    node.auto_nav_loop()
    assert sent == ['V 0.000 0.000']
    assert not policy.calls
    assert not node._ai1_active


def test_operator_auto_holds_without_target_instead_of_open_loop_cruise():
    _, node, sent = node_fixture()
    node.goal = None
    node._last_frontier_search = time.monotonic()
    node.auto_nav_loop()
    assert sent == ['V 0.000 0.000']


def test_operator_open_space_emits_only_one_velocity_per_control_tick():
    _, node, sent = node_fixture()
    node.ai1_mode = 'off'
    node.auto_nav_loop()
    assert len(sent) == 1
    assert sent[0] != 'V 0.000 0.000'


def test_operator_ai1_shadow_emits_only_one_baseline_velocity_per_tick():
    _, node, sent = node_fixture()
    node.ai1_runtime, node.ai1_mode = OfflineAI1((0., 0.)), 'shadow'
    node.auto_nav_loop()
    assert len(sent) == 1
    assert not node._ai1_active


def test_ai1_inference_error_enters_hold_via_mock_stop():
    _, node, sent = node_fixture()
    node.ai1_runtime, node.ai1_mode = OfflineAI1(error=RuntimeError('offline failed')), 'control'
    node.auto_nav_loop()
    assert sent[-1] == 'V 0.000 0.000'
    assert 'HOLD' in node._ai1_error or 'RuntimeError' in node._ai1_error
    assert not node._ai1_active


def test_ai1_control_sensor_dropout_delegates_to_validated_astar_follower():
    brain, node, sent = node_fixture()
    policy = OfflineAI1((.03, 0.))
    node.ai1_runtime, node.ai1_mode = policy, 'control'
    with brain.state.lock:
        brain.state.ranges[20:27] = [0.] * 7
    node.auto_nav_loop()
    assert not policy.calls
    assert node._ai1_error.endswith('AI1_LIDAR_UNOBSERVED_SECTOR')
    assert sent and sent[-1] != 'V 0.000 0.000'
    assert not node._ai1_active


def test_ai1_error_in_shadow_preserves_baseline():
    _, node, sent = node_fixture()
    node.ai1_runtime, node.ai1_mode = OfflineAI1(error=RuntimeError('offline failed')), 'shadow'
    node.auto_nav_loop()
    assert any(c != 'V 0.000 0.000' for c in sent)
    assert node._ai1_shadow_cmd is None
    assert node._ai1_error.startswith('RuntimeError:')


def test_ai1_off_is_same_as_conventional_command_path():
    _, node, sent = node_fixture()
    node.auto_nav_loop()
    assert node._ai1_shadow_cmd is None
    assert any(c != 'V 0.000 0.000' for c in sent)


def test_ai1_shadow_data_clears_without_new_inference():
    _, node, _ = node_fixture()
    node.ai1_runtime, node.ai1_mode = OfflineAI1(), 'shadow'
    node.auto_nav_loop()
    assert node._ai1_shadow_cmd is not None
    node.ai1_mode = 'off'
    node.auto_nav_loop()
    assert node._ai1_shadow_cmd is None
    assert node._ai1_v is None


def test_ai2_observation_has_training_shape_and_north_up_patch():
    grid = OfflineGrid()
    obs = ai2_observation(grid, (15, 15), [(1., (1.5, 2.))], {(15, 16)},
                          (1.5, 1.5), 0., 17, 100)
    patch, features = obs
    assert patch.shape == (3, 9, 9) and patch.dtype == np.float32
    assert features.shape == (8,) and features.dtype == np.float32
    assert patch[2, 3, 4] == 1. and patch[0, 5, 4] == 1.
    assert features[2] == pytest.approx(1. / 64.)
    assert features[7] == pytest.approx(.17)


def test_ai2_action_coordinates_and_rotated_grid_transform():
    assert [ai2_action_direction(i) for i in range(4)] == [
        (0., 1.), (0., -1.), (-1., 0.), (1., 0.)]
    candidates = [(2., (0., 2.)), (2., (2., 0.))]
    action, ranked = ai2_ranked_candidates(candidates, [0., 0., 0., 1.], 0., 0., math.pi / 2)
    assert action == 3 and ranked[0][1] == (0., 2.)


def test_ai2_observation_rotated_map_direction_and_yaw():
    grid = OfflineGrid()
    grid.origin = (0., 0., math.pi / 2)
    grid.path = lambda start, end: [start, (start[0], start[1] + .1)]
    patch, features = ai2_observation(grid, (15, 15), [(1., (1.5, 2.))],
                                      set(), (1.5, 1.5), math.pi / 2, 0, 100)
    assert features[0] == pytest.approx(1.)  # World north maps to local +X.
    assert features[1] == pytest.approx(0.)
    assert features[4] == pytest.approx(0.)
    assert features[5] == pytest.approx(1.)


def test_ai2_nonfinite_scores_rejected():
    for q in ([0., math.nan, 0., 0.], [0., 1.], ['bad'] * 4):
        with pytest.raises(ValueError):
            ai2_ranked_candidates([(1., (1., 0.))], q, 0., 0.)


def test_ai2_cannot_choose_blocked_best_q_action():
    grid = OfflineGrid()
    grid.traversable = lambda c: c != (16, 15) and OfflineGrid.traversable(grid, c)
    mask = ai2_valid_action_mask(grid, (15, 15))
    assert mask == (True, True, True, False)
    action, _ = ai2_ranked_candidates([(1., (1., 2.))], [0., 4., 1., 999.],
                                       1.5, 1.5, valid_actions=mask)
    assert action == 1
    with pytest.raises(ValueError, match='safe'):
        ai2_ranked_candidates([(1., (1., 2.))], [0., 1., 2., 3.],
                              1.5, 1.5, valid_actions=(False,) * 4)


def test_ai2_grid_reframe_preserves_only_physically_valid_visited_cells():
    old = ('map', 20, 20, .1, -1., -1., 0.)
    new = ('map', 22, 22, .1, -1.1, -1.1, 0.)
    data = [0] * (22 * 22)
    data[6 * 22 + 6] = 100
    assert reproject_visited_cells({(5, 5), (8, 9)}, old, new, data) == {(9, 10)}
    assert reproject_visited_cells({(5, 5)}, old, ('other', *new[1:]), data) == set()


def test_ai2_shadow_inference_does_not_change_coverage_goal():
    brain, node, _ = node_fixture()
    node.ai2_session, node.ai2_mode = OfflineAI2([0., 0., 0., 1.]), 'shadow'
    node.ai2_map_name, node.ai2_feat_name = 'map', 'feat'
    node.ai2_mode = 'off'
    baseline = node.find_best_coverage_goal(1.5, 1.5)
    node.ai2_mode = 'shadow'
    selected = node.find_best_coverage_goal(1.5, 1.5)
    assert selected == baseline
    assert node.ai2_session.calls
    assert node._ai2_shadow_goal is not None
    assert node._ai2_best_action == 3


def test_ai2_control_votes_for_reachable_goal_and_error_falls_back():
    brain, node, _ = node_fixture()
    node.ai2_session, node.ai2_mode = OfflineAI2([0., 0., 0., 1.]), 'control'
    node.ai2_map_name, node.ai2_feat_name = 'map', 'feat'
    chosen = node.find_best_coverage_goal(1.5, 1.5)
    assert chosen is not None
    assert node._ai2_shadow_goal is not None
    node.ai2_session = OfflineAI2([math.nan, 0., 0., 0.])
    fallback = node.find_best_coverage_goal(1.5, 1.5)
    assert node._ai2_shadow_goal is None
    assert node._ai2_best_action is None
    assert node._ai2_error.startswith('ValueError:')
    node.ai2_mode = 'off'
    baseline = node.find_best_coverage_goal(1.5, 1.5)
    assert fallback == baseline


def test_ai2_control_unreachable_direction_falls_back_to_nearest_path():
    _, node, _ = node_fixture()
    grid = OfflineGrid()
    original_path = grid.path
    grid.path = lambda start, goal: (original_path(start, goal)
                                     if goal[0] < 1.5 else None)
    node._grid = lambda margin=None: grid
    node.ai2_session = OfflineAI2([0., 0., 0., 100.])
    node.ai2_map_name, node.ai2_feat_name = 'map', 'feat'
    node.ai2_mode = 'control'
    goal = node.find_best_coverage_goal(1.5, 1.5)
    assert goal is not None and goal[0] < 1.5


def test_ai2_brain_masks_blocked_east_before_ranking_q_values():
    _, node, _ = node_fixture()
    grid = OfflineGrid()
    grid.traversable = lambda c: c != (16, 15) and OfflineGrid.traversable(grid, c)
    node._grid = lambda margin=None: grid
    node.ai2_session = OfflineAI2([0., 2., 1., 1000.])
    node.ai2_mode = 'control'
    node.ai2_map_name, node.ai2_feat_name = 'map', 'feat'
    assert node.find_best_coverage_goal(1.5, 1.5) is not None
    assert node._ai2_best_action == 1


def test_ai_telemetry_exposes_modes_shadow_command_and_errors():
    brain, node, _ = node_fixture()
    brain.ros_node = node
    brain.state.valid_points = 360
    node.control.health = lambda: {'status': 'MOCK'}
    node.ai1_mode = 'shadow'
    node._ai1_shadow_cmd = (.03, 0.)
    node._ai1_v = .03
    node._ai1_w = 0.
    node._ai1_error = None
    node.ai2_mode = 'off'
    node._ai2_error = 'offline diagnostic'
    handler = brain.WebHandler.__new__(brain.WebHandler)
    handler.path = '/api/telemetry'
    handler.wfile = io.BytesIO()
    handler.send_response = lambda *args: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.do_GET()
    payload = json.loads(handler.wfile.getvalue())['ai']
    assert payload['ai1_mode'] == 'shadow'
    assert payload['ai1_active'] is False
    assert payload['ai1_shadow_cmd'] == [.03, 0.]
    assert payload['ai1_scan_ready'] is True
    assert payload['ai1_scan_blocker'] is None
    assert payload['ai1_scan_valid_bins'] == 360
    assert payload['ai2_mode'] == 'off'
    assert payload['ai2_error'] == 'offline diagnostic'


def test_ai_telemetry_flags_realistic_missing_lidar_sector_even_while_idle():
    brain, node, _ = node_fixture()
    brain.ros_node = node
    node.ai1_runtime = OfflineAI1()
    node.ai1_mode = 'shadow'
    node.control.health = lambda: {'status': 'MOCK'}
    with brain.state.lock:
        brain.state.auto_mode = False
        brain.state.ranges = [1.5] * 360
        brain.state.ranges[165:177] = [0.0] * 12
        brain.state.valid_points = 348
        brain.state.scan_mono = time.monotonic()
    handler = brain.WebHandler.__new__(brain.WebHandler)
    handler.path = '/api/telemetry'
    handler.wfile = io.BytesIO()
    handler.send_response = lambda *args: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.do_GET()
    payload = json.loads(handler.wfile.getvalue())['ai']
    assert payload['ai1_scan_ready'] is False
    assert payload['ai1_scan_valid_bins'] == 348
    assert payload['ai1_scan_blocker'] == 'AI1_LIDAR_UNOBSERVED_SECTOR'


def test_offline_closed_loop_filtered_stop_holds_pose():
    """10 mock plant ticks integrate captured twist; zero AI command never moves."""
    brain, node, commands = node_fixture()
    node.ai1_mode, node.ai1_runtime = 'control', OfflineAI1((0., 0.))
    x, y, theta = 0., 0., 0.
    node._pose_map = lambda: (x, y, theta)
    for _ in range(10):
        node.auto_nav_loop()
        linear, angular = (float(v) for v in commands[-1].split()[1:])
        x += linear * .1 * math.cos(theta)
        y += linear * .1 * math.sin(theta)
        theta += angular * .1
    assert all(cmd == 'V 0.000 0.000' for cmd in commands)
    assert x == y == theta == 0.


@pytest.mark.parametrize('ai1_mode,ai2_mode', [
    ('off', 'off'), ('control', 'off'), ('off', 'control'), ('control', 'control')])
def test_four_mode_closed_loop_mock_plant(ai1_mode, ai2_mode):
    """Synthetic differential-drive pose feedback, deterministic scans and mock output.

    This exercises real brain dispatch and coverage selection without opening ROS
    or serial. It does not validate learned policy accuracy or Pi scheduling.
    """
    _, node, commands = node_fixture()
    node.ai1_mode, node.ai2_mode = ai1_mode, ai2_mode
    node.ai1_runtime = OfflineAI1((.03, 0.))
    node.ai2_session = OfflineAI2([0., 0., 0., 1.])
    node.ai2_map_name, node.ai2_feat_name = 'map', 'feat'

    # Exercise AI2 goal selection against a collision-free synthetic occupancy grid.
    coverage_goal = node.find_best_coverage_goal(1.5, 1.5)
    assert coverage_goal is not None
    if ai2_mode == 'control':
        assert node._ai2_shadow_goal is not None
        assert node._ai2_best_action == 3
    else:
        assert not node.ai2_session.calls

    # Use a deterministic forward goal to separate AI1 authority from AI2 goal votes.
    x, y, theta = 1.5, 1.5, 0.
    node.goal = (2.5, 1.5)
    node._pose_map = lambda: (x, y, theta)
    node._goal_time = time.monotonic()
    for _ in range(12):
        node.auto_nav_loop()
        assert commands
        assert commands[-1].startswith('V ')
        v, w = (float(n) for n in commands[-1].split()[1:])
        assert 0. <= v <= .15 and abs(w) <= 2.
        x += v * .1 * math.cos(theta)
        y += v * .1 * math.sin(theta)
        theta += w * .1
    assert x > 1.5
    if ai1_mode == 'control':
        assert all(cmd == 'V 0.030 0.000' for cmd in commands)
        assert node._ai1_active
    else:
        assert all(cmd != 'V 0.030 0.000' for cmd in commands)
        assert not node._ai1_active
