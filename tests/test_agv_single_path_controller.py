"""AUTO has one source of steering: its validated A* route, never side votes."""
import math
import time

import pytest

from test_agv_ai_integration import node_fixture
from agv_navigation import GridPlanner
from agv_speed_profile import wheels_to_twist
from test_agv_rpm_profile import ready


def no_escape():
    pytest.fail('Operator AUTO must not inject an unplanned spin/escape')


def test_nearer_left_wall_cannot_steer_away_from_a_left_astar_waypoint():
    brain, node, commands = node_fixture()
    node.goal = (2., .4)
    brain.state.ranges[75] = .30
    node._try_escape = no_escape
    node.auto_nav_loop()
    assert len(commands) == 1
    _, v, w = commands[0].split()
    assert float(v) > 0. and float(w) > 0., 'Follow the actual waypoint bearing'


def test_front_buffer_distance_does_not_choose_an_arbitrary_turn():
    brain, node, commands = node_fixture()
    for deg in range(-25, 26):
        brain.state.ranges[deg % 360] = .35
    node._try_escape = no_escape
    node.auto_nav_loop()
    assert len(commands) == 1
    _, v, w = commands[0].split()
    assert float(v) > 0. and float(w) == 0., 'Final writer validates geometry; proximity is not a heading'


def test_previous_escape_latch_cannot_override_home_route():
    brain, node, commands = node_fixture()
    node._goal_type = 'HOME'
    node.home = (*node.goal, 0.)
    node._escape_latch_until = time.monotonic() + 5.
    node._last_escape_cmd = (0., -1.8)
    node._spin_recovery = None
    for deg in range(-25, 26):
        brain.state.ranges[deg % 360] = .35
    node.control.drive = lambda *a, **kw: pytest.fail('Old escape latch must never own AUTO')
    followed = []
    node._follow = lambda pose, goal: followed.append(goal) or True
    node.auto_nav_loop()
    assert followed == [node.goal]


def test_wheel_tracking_error_does_not_select_a_random_recovery_heading():
    _, node, commands = node_fixture()
    node.control.latest = dict(l_tgt=40., r_tgt=40., l_rpm=0., r_rpm=0.)
    node._stall_start = time.monotonic() - 2.
    node._try_escape = no_escape
    node.auto_nav_loop()
    assert commands and float(commands[-1].split()[1]) > 0.
    assert node.goal == (2., 0.)


def test_blocked_operator_start_only_uses_checked_translation_not_rotation():
    _, node, _ = node_fixture()
    grid = node._grid()
    grid.traversable = lambda cell: False
    grid.swept_clear = lambda *args: False
    node._grid = lambda margin=None: grid
    node._enter_cautious = lambda pose: False
    node._escape_clear = lambda v, w: True
    node._try_escape = no_escape
    checked = []
    node.control.drive = lambda cmd, **kw: checked.append((cmd, kw)) or (True, 'MOCK')
    node.control._event = lambda *a, **kw: None
    node.auto_nav_loop()
    assert checked
    _, v, w = checked[0][0].split()
    assert float(v) != 0. and float(w) == 0.
    assert checked[0][1] == dict(autonomous=True, escape=True)


def test_no_checked_exit_means_no_unplanned_turn_command():
    _, node, commands = node_fixture()
    grid = node._grid()
    grid.traversable = lambda cell: False
    grid.swept_clear = lambda *args: False
    node._grid = lambda margin=None: grid
    node._enter_cautious = lambda pose: False
    node._escape_clear = lambda v, w: False
    node._try_escape = no_escape
    node.control.drive = lambda *a, **kw: pytest.fail('No geometric exit: no motor command')
    node.auto_nav_loop()
    assert commands == ['V 0.000 0.000']


def test_operator_heading_turn_completes_before_forward_motion():
    _, node, commands = node_fixture()
    node.goal = (0., 2.)
    node._try_escape = no_escape
    node.auto_nav_loop()
    _, v, w = commands[0].split()
    assert float(v) == 0. and float(w) > 0.


@pytest.mark.parametrize('initial_yaw', [0., 1.2])
def test_closed_loop_straight_corridor_uses_real_rpm_writer_without_side_to_side_turns(initial_yaw):
    brain, node, _ = node_fixture()
    w, h, res = 120, 14, .05
    data = [0 if 0 < x < w-1 and 0 < y < h-1 else 100
            for y in range(h) for x in range(w)]
    grids = {margin: GridPlanner(w, h, res, (0., 0., 0.), data, .20, margin,
                                 budget_s=2.) for margin in (.15, .03)}
    node._grid = lambda margin=None: grids[margin if margin is not None else
                                           (.03 if getattr(node, '_cautious', False) else .15)]
    pose = [1., .325, initial_yaw]
    node._pose_map = lambda: tuple(pose)
    node.home, node.goal = (1., .325, 0.), (4.5, .325)
    node._try_escape = no_escape
    node.control, uart = ready()
    node.control.slow_speed_requested = lambda: getattr(node, '_cautious', False)
    node.control.arc_validator = node._forward_arc_clear
    node.control.escape_validator = node._escape_clear
    node.send_cmd = lambda cmd, **kw: brain.AGVROSNode.send_cmd(node, cmd, **kw)
    state = brain.state
    state.map_width, state.map_height, state.map_resolution = w, h, res
    state.map_data, state.map_frame, state.map_received = data, 'map', True
    state.body_radius_m, state.wall_margin_m = .20, .15
    state.body_bounds_m = (-.16, -.12, .10, .12)
    state.cruise_speed_mps = .2491282974296706
    targets = (0., 0.)
    for step in range(70):
        rays = []
        for deg in range(360):
            a = pose[2] + math.radians(deg)
            dx, dy = math.cos(a), math.sin(a)
            distances = []
            for p, delta, lo, hi in ((pose[0], dx, .05, 5.95),
                                      (pose[1], dy, .05, .65)):
                if abs(delta) > 1e-9:
                    distances.append(((hi if delta > 0 else lo)-p)/delta)
            rays.append(min(distances))
        now = time.monotonic()
        state.ranges = rays
        state.scan_mono = state.map_mono = now
        node.control.scan_time = node.control.last_d0 = node.control.clock()
        v, omega = wheels_to_twist(*targets)
        node.control.latest = dict(safety='ARMED', x=pose[0], y=pose[1], th=pose[2],
                                   l_tgt=targets[0], r_tgt=targets[1],
                                   l_rpm=targets[0], r_rpm=targets[1], v=v, w=omega)
        node.control.scan_clear = True
        node.control.rotation_clear = node._rotation_clear()
        previous_writes = len(uart.writes)
        node.auto_nav_loop()
        assert len(uart.writes) > previous_writes, (
            step, state.explore_phase, list(node.control.command_events)[-3:])
        command = uart.writes[-1].decode().split()
        assert command[0] == 'S'
        targets = tuple(map(float, command[1:]))
        v, omega = wheels_to_twist(*targets)
        pose[0] += v*.1*math.cos(pose[2]+omega*.05)
        pose[1] += v*.1*math.sin(pose[2]+omega*.05)
        pose[2] += omega*.1
    assert pose[0] > (1.9 if initial_yaw == 0 else 1.8), 'Steady progress down the existing corridor'
    assert abs(pose[1]-.325) < .03 and abs(pose[2]) < .1
    stable_writes = uart.writes if initial_yaw == 0 else uart.writes[-30:]
    assert all(line.decode().split()[1:] in (['0.000', '0.000'], ['40.000', '40.000'])
               for line in stable_writes), 'No hidden side votes or recovery pivots after alignment'


def test_one_validated_route_search_per_operator_tick():
    _, node, _ = node_fixture()
    grid = node._grid()
    searches = []
    grid.path = lambda start, goal: searches.append((start, goal)) or [start, goal]
    node._grid = lambda margin=None: grid
    node.auto_nav_loop()
    assert len(searches) == 1, 'Reuse the planned waypoint instead of spending scan freshness twice'


def test_operator_recovery_cannot_reverse_forever_along_a_blocked_narrow_corridor():
    brain, node, _ = node_fixture()
    w, h = 80, 9
    data = [0 if 0 < x < w-1 and 0 < y < h-1 else 100
            for y in range(h) for x in range(w)]
    grid = GridPlanner(w, h, .05, (0., 0., 0.), data, .20, .03, budget_s=2.)
    pose = (1., .225, 0.)
    node._grid = lambda margin=None: grid
    node._pose_map = lambda: pose
    node.control, uart = ready()
    node.control.escape_validator = node._escape_clear
    state = brain.state
    state.body_radius_m, state.body_bounds_m = .20, (-.16, -.12, .10, .12)
    state.scan_mono = state.map_mono = time.monotonic()
    assert not grid.traversable(grid.world_to_cell(*pose[:2]))
    assert not node._try_operator_clearance_recovery(pose)
    assert not uart.writes


def test_clear_subcell_pose_can_connect_forward_to_a_safe_planning_cell():
    brain, node, _ = node_fixture()
    w, h = 80, 60
    data = [0] * (w*h)
    for y in range(h): data[y*w+40] = 100
    grid = GridPlanner(w, h, .05, (0., 0., 0.), data, .20, .03, budget_s=2.)
    pose = (1.756, 1.5, math.pi)
    assert grid.swept_clear(pose, 0., 0.)
    assert not grid.traversable(grid.world_to_cell(*pose[:2]))
    node._grid = lambda margin=None: grid
    node._pose_map = lambda: pose
    node.goal = (1., 1.5)
    node._cautious = True
    node.control, uart = ready()
    node.control.slow_speed_requested = lambda: True
    node.control.arc_validator = node._forward_arc_clear
    node.control.escape_validator = node._escape_clear
    brain.state.body_radius_m, brain.state.body_bounds_m = .20, (-.16, -.12, .10, .12)
    brain.state.ranges[180] = .244
    brain.state.scan_mono = brain.state.map_mono = time.monotonic()
    assert node._try_operator_clearance_recovery(pose)
    assert uart.writes == [b'S 40.000 40.000\n']
