"""Offline A* replanning regressions. No Pi, ROS, serial or real motion."""

import time

from agv_navigation import GridPlanner
from test_agv_ai_integration import OfflineGrid, node_fixture


def test_astar_routes_around_known_wall_without_corner_cutting():
    size = 60
    data = [0] * (size * size)
    for y in range(12, 48):
        data[y * size + 30] = 100
    grid = GridPlanner(size, size, .1, (0., 0., 0.), data,
                       body_radius=.08, margin=.04, budget_s=1.5)
    start, goal = (1.5, 3.), (4.5, 3.)
    route = grid.path(start, goal)
    assert grid.last_path_status == 'OK'
    assert route and len(route) > 35  # detour is longer than a straight line
    assert all(grid.traversable(grid.world_to_cell(*point)) for point in route)
    assert any(abs(y - 3.) > 1.0 for _, y in route)


def test_real_inflated_costmap_allows_body_sized_corridor_only_in_cautious_mode():
    size = 100
    data = [0] * (size * size)
    for x in range(15, 86):
        data[39 * size + x] = 100
        data[52 * size + x] = 100
    kwargs = dict(width=size, height=size, resolution=.05,
                  origin=(0., 0., 0.), data=data, body_radius=.20,
                  budget_s=1.5)
    normal = GridPlanner(**kwargs, margin=.15)
    narrow = GridPlanner(**kwargs, margin=.03)
    start, goal = (1.5, 2.3), (3.7, 2.3)
    assert normal.path(start, goal) is None
    assert normal.last_path_status == 'START_BLOCKED'
    assert narrow.path(start, goal)
    assert narrow.swept_clear((*start, 0.), 0., 0.)

    # Unknown across the entire map cannot be crossed in either mode.
    for y in range(size):
        data[y * size + 50] = -1
    unknown = GridPlanner(**{**kwargs, 'data': data}, margin=.03)
    assert unknown.path(start, goal) is None
    assert unknown.last_path_status == 'NO_ROUTE'


def test_definitively_blocked_frontier_is_excluded_and_new_one_is_selected():
    _, node, commands = node_fixture()
    grid = OfflineGrid()
    old_goal = node.goal

    def path(start, goal):
        if goal == old_goal:
            grid.last_path_status = 'GOAL_BLOCKED'
            return None
        grid.last_path_status = 'OK'
        return [start, goal]

    grid.path = path
    node._grid = lambda margin=None: grid
    node.find_best_frontier = lambda x, y: (1.5, .3)

    node.auto_nav_loop()
    assert commands == ['V 0.000 0.000']
    assert node.goal is None
    assert node.blocked_regions and node.blocked_regions[-1][:2] == old_goal

    # The next control tick must find a different reachable frontier.
    node.auto_nav_loop()
    assert node.goal == (1.5, .3)
    assert len(commands) == 2
    assert commands[-1] != 'V 0.000 0.000'


def test_search_timeout_keeps_goal_for_retry_instead_of_blacklisting():
    _, node, commands = node_fixture()
    grid = OfflineGrid()

    def timeout(start, goal):
        grid.last_path_status = 'SEARCH_TIMEOUT'
        return None

    grid.path = timeout
    node._grid = lambda margin=None: grid
    goal = node.goal
    node.auto_nav_loop()
    assert node.goal == goal
    assert node.blocked_regions == []
    assert commands == ['V 0.000 0.000']


def test_cautious_route_recovery_requires_known_free_full_path():
    _, node, commands = node_fixture()
    normal, narrow = OfflineGrid(), OfflineGrid()

    def blocked_start(start, goal):
        normal.last_path_status = 'START_BLOCKED'
        return None

    normal.path = blocked_start
    node._grid = lambda margin=None: narrow if margin == .03 else normal
    node._cautious = False
    node.auto_nav_loop()
    assert node._cautious
    assert commands == ['V 0.000 0.000']
    assert node.goal is not None
    assert node.blocked_regions == []


def test_cautious_route_recovery_rejects_unknown_or_disconnected_corridor():
    _, node, commands = node_fixture()
    normal, narrow = OfflineGrid(), OfflineGrid()

    def blocked_start(start, goal):
        normal.last_path_status = 'START_BLOCKED'
        return None

    normal.path = blocked_start
    narrow.path = lambda start, goal: None
    node._grid = lambda margin=None: narrow if margin == .03 else normal
    node._cautious = False
    node.auto_nav_loop()
    assert not node._cautious
    assert node.goal is not None
    assert commands == ['V 0.000 0.000']


def test_failed_frontier_cooldown_does_not_clear_itself_when_none_eligible():
    brain, node, _ = node_fixture()
    grid = OfflineGrid()
    grid.frontiers = lambda start, excluded, rejected: {
        'goals': [] if rejected else [(2., 0.)],
        'reachable_frontiers': 1,
        'unknown_cells': 100,
    }
    node._grid = lambda margin=None: grid
    node.blocked_regions = [(2., 0., .35, time.monotonic() + 60.)]
    assert node.find_best_frontier(0., 0.) is None
    assert len(node.blocked_regions) == 1
    assert brain.state.frontier_reachable == 1
