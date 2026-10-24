"""Goal persistence and branch exploration with real grids, offline only."""
import math
import time

from agv_navigation import GridPlanner
from test_agv_ai_integration import node_fixture


def test_frontier_twenty_cm_away_is_not_reported_arrived():
    _, node, commands = node_fixture()
    node.goal = (.20, 0.)
    node._last_frontier_search = time.monotonic()
    node.auto_nav_loop()
    assert node.goal == (.20, 0.)
    assert not node.blocked_goals


def test_wheel_stall_warning_preserves_frontier_without_unplanned_recovery():
    _, node, _ = node_fixture()
    node.control.latest = dict(l_tgt=20., r_tgt=20., l_rpm=0., r_rpm=0.)
    node._stall_start = time.monotonic() - 2.
    escaped = []
    node._try_escape = lambda: (escaped.append(True) or True)
    node.auto_nav_loop()
    assert not escaped
    assert node._motion_warning == 'WHEEL_RPM_BELOW_TARGET'
    assert node.goal == (2., 0.)
    assert not node.blocked_regions


def test_cautious_operator_command_uses_the_speed_accepted_by_its_validator():
    for front_distance in (1.5, .35):
        brain, node, commands = node_fixture()
        node._cautious = True
        brain.state.auto_target_speed_rpm = 48.
        for deg in range(-25, 26):
            brain.state.ranges[deg % 360] = front_distance
        node.auto_nav_loop()
        v = float(commands[0].split()[1])
        assert 0 < v <= .04


def test_blocked_start_without_goal_attempts_escape_instead_of_frontier_hold():
    _, node, _ = node_fixture()
    grid = node._grid()
    grid.traversable = lambda cell: False
    grid.swept_clear = lambda *args: False
    grid.frontiers = lambda *args: dict(goals=[], reachable_frontiers=0, unknown_cells=100)
    node._grid = lambda margin=None: grid
    node._enter_cautious = lambda pose: False
    node.goal = None
    escaped = []
    node._try_operator_clearance_recovery = lambda pose: (escaped.append(True) or True)
    node.auto_nav_loop()
    assert escaped


def test_old_goal_is_retained_when_the_robot_is_making_progress():
    _, node, _ = node_fixture()
    node._goal_time = time.monotonic() - 65.
    node._last_frontier_search = time.monotonic()
    node.progress.append((time.monotonic() - 1., (-.15, 0., 0.)))
    node.auto_nav_loop()
    assert node.goal == (2., 0.)
    assert not node.blocked_regions


def test_goal_without_translation_eventually_releases_for_another_branch():
    _, node, _ = node_fixture()
    node._goal_progress = (node.goal, (0., 0.), time.monotonic() - 61.)
    node._last_frontier_search = time.monotonic()
    node.auto_nav_loop()
    assert node.goal is None
    assert node.blocked_regions
    assert node._last_goal_change['reason'] == 'NO_TRANSLATION_FOR_60S'


def corridor():
    w, h, res = 100, 14, .05
    data = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            if x in (0, w - 1) or y in (0, h - 1):
                data[y*w+x] = -1
    return GridPlanner(w, h, res, (0., 0., 0.), data, .20, .03, budget_s=2.)


def test_failed_viewpoint_does_not_remove_both_ends_of_long_thin_corridor():
    grid = corridor()
    start = (2.5, .35)
    initial = grid.frontiers(start)
    assert initial and initial['goals']
    first = initial['goals'][0]
    other = grid.frontiers(start, rejected=[(*first, .35)])
    assert other and other['goals'], 'A local failed viewpoint must not exclude the whole corridor'
    assert any((first[0] - start[0]) * (goal[0] - start[0]) < 0
               and math.dist(first, goal) >= .60 for goal in other['goals'])
    assert all(grid.path(start, goal) for goal in other['goals'])


def test_new_frontier_is_outside_the_arrival_radius():
    grid = corridor()
    start = (2.5, .35)
    summary = grid.frontiers(start)
    assert summary and summary['goals']
    assert all(math.dist(start, goal) >= .30 for goal in summary['goals'])


def test_small_inflation_change_keeps_original_yellow_goal_and_safe_approach():
    _, node, _ = node_fixture()
    w = h = 100
    data = [0] * (w*h)
    for y in range(h):
        data[y*w+60] = 100
    grid = GridPlanner(w, h, .05, (0., 0., 0.), data, .20, .15, budget_s=2.)
    pose, goal = (1., 2.525, 0.), (2.725, 2.525)
    assert grid.path(pose[:2], goal) is None
    assert grid.last_path_status == 'GOAL_BLOCKED'
    node.goal = goal
    assert node._local_path_target(grid, pose, goal) is not None
    assert node.goal == goal


def test_goal_tolerance_still_cannot_cross_unknown_or_an_actual_wall():
    _, node, _ = node_fixture()
    for barrier in (-1, 100):
        w = h = 60
        data = [0] * (w*h)
        for y in range(h):
            data[y*w+30] = barrier
        grid = GridPlanner(w, h, .05, (0., 0., 0.), data, .20, .03, budget_s=2.)
        assert node._local_path_target(grid, (.7, 1.5, 0.), (2.1, 1.5)) is None
