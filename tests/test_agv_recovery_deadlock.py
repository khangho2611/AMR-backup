"""A spent escape-turn budget must not deadlock a known A* mission."""
import math
import time

import pytest

from test_agv_ai_integration import node_fixture
from test_agv_rpm_profile import ready


def spent_recovery(node):
    node.control.latest.update(x=0., y=0., th=0.)
    node._spin_recovery = dict(anchor=(0., 0.), yaw=0., angle=math.pi+.2,
                               started=time.monotonic()-10.)


def test_exhausted_escape_budget_does_not_preempt_astar_goal_alignment():
    _, node, commands = node_fixture()
    spent_recovery(node)
    grid = node._grid()
    # The route turns first; straight forward is blocked, rotation is clear.
    grid.swept_clear = lambda pose, v, w: v == 0.
    node._grid = lambda margin=None: grid
    node.goal = (0., 2.)
    escapes = []
    node._try_escape = lambda: escapes.append(True) or False
    node.auto_nav_loop()
    assert commands and commands[-1] != 'V 0.000 0.000'
    assert not escapes, 'A planned waypoint turn must run before random escape'
    assert node.goal == (0., 2.)


@pytest.mark.parametrize('writer_accepts', [True, False])
def test_planned_turn_uses_geometry_writer_even_after_escape_budget_is_spent(writer_accepts):
    brain, node, _ = node_fixture()
    node.control, uart = ready()
    spent_recovery(node)
    node.control.rotation_clear = writer_accepts
    result = brain.AGVROSNode.send_cmd(node, 'V 0.000 1.000', autonomous=True, planned_turn=True)
    assert result[0] is writer_accepts
    assert bool(uart.writes) is writer_accepts
    if not writer_accepts:
        assert 'SWEEP_NOT_CLEAR' in node.control.command_events[-1]['blockers']


def test_retired_turn_budget_does_not_override_the_final_writer():
    brain, node, _ = node_fixture()
    spent_recovery(node)
    writes = []
    node.control.drive = lambda cmd, **kw: writes.append(cmd) or (False, 'SWEEP_NOT_CLEAR')
    assert brain.AGVROSNode.send_cmd(node, 'V 0.000 1.000', autonomous=True) == (
        False, 'SWEEP_NOT_CLEAR')
    assert writes == ['V 0.000 1.000']


def test_scan_buffer_rejection_tries_existing_slow_corridor_before_random_turn():
    _, node, _ = node_fixture()
    attempts = []
    def reject(cmd, **kwargs):
        attempts.append(cmd)
        node._last_arc_reason = 'SCAN_BODY_CLEARANCE'
        return False, 'SESSION_OR_SENSOR_NOT_READY'
    node.send_cmd = reject
    node._enter_cautious = lambda pose: setattr(node, '_cautious', True) or True
    node._try_escape = lambda: pytest.fail('No random escape before trying the valid slow corridor')
    node.auto_nav_loop()
    assert node._cautious
    assert len([cmd for cmd in attempts if cmd != 'V 0.000 0.000']) == 1
    assert node.goal == (2., 0.)


def test_goal_alignment_finishes_by_heading_not_an_arbitrary_turn_timer():
    brain, node, commands = node_fixture()
    node.goal = (0., 2.)
    node._is_pure_spinning = True
    node._spin_start_time = time.monotonic() - 1.0
    for deg in range(-25, 26):
        brain.state.ranges[deg % 360] = .50
    node.auto_nav_loop()
    _, v, w = commands[-1].split()
    assert float(v) == 0., 'Do not start driving before the planned turn has aligned'
    assert float(w) > 0.
    assert 'HƯỚNG MỤC TIÊU' in brain.state.explore_phase


def test_normal_clearance_is_not_restored_while_fresh_scan_still_needs_slow_buffer():
    brain, node, _ = node_fixture()
    grid = node._grid()
    grid.radius = .35
    node._grid = lambda margin=None: grid
    node._cautious = True
    node._normal_clear_since = time.monotonic() - 3.
    brain.state.ranges[90] = .24
    brain.AGVROSNode._restore_normal_clearance(node, (0., 0., 0.))
    assert node._cautious
    assert node._normal_clear_since is None
