"""Regressions for the live 1.4-second pivot/escape oscillation, no hardware."""
import math
import time

import pytest

from agv_speed_profile import SLOW_RPM, rpm_to_speed, running_wheels, twist_to_wheels
from test_agv_ai_integration import node_fixture


@pytest.mark.parametrize('left,right', [(40., 0.), (0., 40.)])
def test_intentionally_stationary_inner_wheel_is_not_a_stall(left, right):
    _, node, commands = node_fixture()
    node.control.latest = dict(l_tgt=left, r_tgt=right, l_rpm=left, r_rpm=right)
    node._stall_start = time.monotonic() - 2.
    escapes = []
    node._try_escape = lambda: escapes.append(True) or True
    node.auto_nav_loop()
    assert not escapes, 'A commanded zero wheel must not trigger the 1.4s escape switch'
    assert node._stall_start is None
    assert commands and node.goal == (2., 0.)


@pytest.mark.parametrize('left,right,measured', [(40., 40., (0., 40.)),
                                               (40., 0., (0., 0.)),
                                               (0., -40., (0., 0.))])
def test_actually_commanded_wheel_stall_reports_without_inventing_a_turn(left, right, measured):
    _, node, _ = node_fixture()
    node.control.latest = dict(l_tgt=left, r_tgt=right,
                               l_rpm=measured[0], r_rpm=measured[1])
    node._stall_start = time.monotonic() - 2.
    escapes = []
    node._try_escape = lambda: escapes.append(True) or True
    node.auto_nav_loop()
    assert not escapes
    assert node._motion_warning == 'WHEEL_RPM_BELOW_TARGET'
    assert node.goal == (2., 0.)


@pytest.mark.parametrize('home', [False, True])
def test_small_heading_correction_in_40rpm_mode_does_not_become_a_pivot(home):
    _, node, commands = node_fixture()
    node.control.operator_rpm_profile = True
    node._cautious = True
    node.goal = (2., .2)
    if home:
        assert node._follow((0., 0., 0.), node.goal)
    else:
        node.auto_nav_loop()
    _, v, w = commands[0].split()
    v, w = float(v), float(w)
    assert .14 <= v <= rpm_to_speed(SLOW_RPM) + .001
    wheels = running_wheels(*twist_to_wheels(v, w), slow=True)
    assert wheels[0] > 0 and wheels[1] > 0 and min(wheels) >= 20.0, 'Small corrections must allow both wheels to advance'


def test_strict_cautious_follower_keeps_its_existing_speed_limit():
    _, node, commands = node_fixture()
    node.control.strict_preflight = True
    node._cautious = True
    assert node._follow((0., 0., 0.), (2., 0.))
    assert 0 < float(commands[0].split()[1]) <= .04


def test_hysteresis_keeps_spinning_until_below_exit_threshold():
    _, node, commands = node_fixture()
    # Ban đầu error = 0.95 rad (> 0.80) -> bật _is_pure_spinning = True, v = 0.000
    goal_95 = (math.cos(0.95), math.sin(0.95))
    assert node._follow((0., 0., 0.), goal_95)
    assert node._is_pure_spinning is True
    assert float(commands[-1].split()[1]) == 0.000

    # Robot đã xoay một phần, error giảm về 0.55 rad (trong vùng trễ 0.35 <= error <= 0.80)
    # Hysteresis duy trì _is_pure_spinning = True và v = 0.000, không nhả tiến sớm
    goal_55 = (math.cos(0.55), math.sin(0.55))
    assert node._follow((0., 0., 0.), goal_55)
    assert node._is_pure_spinning is True
    assert float(commands[-1].split()[1]) == 0.000

    # Error giảm xuống 0.20 rad (< 0.35) -> chuyển _is_pure_spinning = False, v > 0
    goal_20 = (math.cos(0.20), math.sin(0.20))
    assert node._follow((0., 0., 0.), goal_20)
    assert node._is_pure_spinning is False
    assert float(commands[-1].split()[1]) > 0.0


def test_spin_timeout_breaks_infinite_circling_into_forward_arc():
    _, node, commands = node_fixture()
    node._is_pure_spinning = True
    node._spin_start_time = time.monotonic() - 2.0

    # Lệch góc error ~ 0.90 rad (<= 1.20 rad) sau khi đã xoay hơn 1.8s
    goal_90 = (math.cos(0.90), math.sin(0.90))
    assert node._follow((0., 0., 0.), goal_90)
    assert node._is_pure_spinning is False
    v = float(commands[-1].split()[1])
    assert v > 0.0


def test_waypoint_stabilization_while_spinning():
    _, node, commands = node_fixture()
    grid = node._grid()
    node._grid = lambda margin=None: grid
    goal = (0., 2.)
    # Enter pure spin towards goal
    assert node._follow((0., 0., 0.), goal)
    assert node._is_pure_spinning is True
    assert node._locked_spin_wp is not None
    assert node._locked_spin_goal == goal
    original_locked_wp = node._locked_spin_wp

    # Next tick: even if a planned candidate is provided, locked wp is preserved
    candidate_wp = (0.5, 1.5)
    assert node._follow((0., 0., 0.), goal, planned=(grid, candidate_wp))
    assert node._locked_spin_wp == original_locked_wp
    assert node._is_pure_spinning is True

    # When robot approaches within 0.12m of locked waypoint, it unlocks
    close_pose = (original_locked_wp[0] - 0.05, original_locked_wp[1] - 0.05, 0.)
    new_candidate = (1.0, 2.0)
    node._follow(close_pose, goal, planned=(grid, new_candidate))
    assert node._locked_spin_wp == new_candidate or not node._is_pure_spinning


def test_state_variables_reset_on_goal_change_and_auto_start():
    brain, node, _ = node_fixture()
    node._is_pure_spinning = True
    node._spin_start_time = time.monotonic()
    node._locked_spin_wp = (1.0, 1.0)
    node._locked_spin_goal = (2.0, 2.0)

    # _exclude_goal resets
    node.goal = (2.0, 2.0)
    node._exclude_goal(time.monotonic(), failed=False)
    assert node._is_pure_spinning is False
    assert node._spin_start_time is None
    assert node._locked_spin_wp is None
    assert node._locked_spin_goal is None

    # initialize_navigation resets
    node._is_pure_spinning = True
    node._spin_start_time = time.monotonic()
    node._locked_spin_wp = (1.0, 1.0)
    node._locked_spin_goal = (2.0, 2.0)
    node.initialize_navigation()
    assert node._is_pure_spinning is False
    assert node._spin_start_time is None
    assert node._locked_spin_wp is None
    assert node._locked_spin_goal is None


def test_small_heading_error_inside_deadband_commands_straight():
    _, node, commands = node_fixture()
    goal = (2.0, 0.05)
    assert node._follow((0., 0., 0.), goal)
    assert len(commands) > 0
    cmd_type, v_str, w_str = commands[-1].split()
    assert cmd_type == 'V'
    v, w = float(v_str), float(w_str)
    assert w == 0.000
    assert v > 0.0


def test_heading_error_above_deadband_steers_proportional_to_excess():
    brain, node, commands = node_fixture()
    error_angle = 0.3
    goal = (2.0 * math.cos(error_angle), 2.0 * math.sin(error_angle))
    assert node._follow((0., 0., 0.), goal)
    assert len(commands) > 0
    _, v_str, w_str = commands[-1].split()
    w = float(w_str)
    assert (w > 0) == (error_angle > 0)
    assert 0 < abs(w) < error_angle * 0.95
    assert abs(w - (error_angle - brain.STEER_DEADBAND_RAD) * 0.95) <= 0.01

    # Also verify negative heading error (rotate pose yaw so error = -0.3 rad while staying in grid bounds)
    commands.clear()
    assert node._follow((0., 0., error_angle), (2.0, 0.0))
    assert len(commands) > 0
    _, _, neg_w_str = commands[-1].split()
    neg_w = float(neg_w_str)
    assert neg_w < 0
    assert 0 < abs(neg_w) < error_angle * 0.95
    assert abs(abs(neg_w) - (error_angle - brain.STEER_DEADBAND_RAD) * 0.95) <= 0.01


def test_alternating_small_errors_do_not_flip_steering_sign():
    brain, node, commands = node_fixture()
    goal = (2.0, 0.0)
    for i in range(20):
        yaw = -0.025 if i % 2 == 0 else 0.025
        pose = (0., 0., yaw)
        assert node._follow(pose, goal)
        _, _, w_str = commands[-1].split()
        w = float(w_str)
        assert w == 0.000, f'Iteration {i} with error={-yaw:+.3f} commanded non-zero w={w}'


@pytest.mark.parametrize('initial_yaw', [0.0, 0.3])
def test_closed_loop_straight_tracking_with_motor_lag_and_asymmetry_uses_fake_clock(initial_yaw):
    import sys
    from agv_navigation import GridPlanner
    from agv_speed_profile import wheels_to_twist
    from test_agv_rpm_profile import UART
    from agv_command_session import CommandSession

    current_sim_time = [100.0]
    def fake_clock():
        return current_sim_time[0]

    for mod in [sys.modules.get('agv_unified_brain'), sys.modules.get('agv_command_session'), sys.modules.get('agv_navigation')]:
        if mod is not None:
            mod.time.monotonic = fake_clock

    brain, node, _ = node_fixture()
    w, h, res = 120, 14, .05
    data = [0 if 0 < x < w-1 and 0 < y < h-1 else 100 for y in range(h) for x in range(w)]
    grids = {margin: GridPlanner(w, h, res, (0., 0., 0.), data, .20, margin, budget_s=2.) for margin in (.15, .03)}
    node._grid = lambda margin=None: grids[margin if margin is not None else (.03 if getattr(node, '_cautious', False) else .15)]
    pose = [1., .325, initial_yaw]
    node._pose_map = lambda: tuple(pose)
    node.home, node.goal = (1., .325, 0.), (4.5, .325)
    node._try_escape = lambda: pytest.fail('unexpected escape')
    uart = UART()
    s = CommandSession(uart, strict_preflight=False, clock=fake_clock)
    s.operator_rpm_profile = True
    s.armed = True
    s.autonomy_allowed = True
    s.last_d0 = s.scan_time = fake_clock()
    s.latest = {'safety': 'ARMED'}
    s.scan_clear = s.rotation_clear = True
    s.arc_validator = node._forward_arc_clear
    s.escape_validator = node._escape_clear
    node.control = s
    node.control.slow_speed_requested = lambda: getattr(node, '_cautious', False)
    node.send_cmd = lambda cmd, **kw: brain.AGVROSNode.send_cmd(node, cmd, **kw)

    state = brain.state
    state.map_width, state.map_height, state.map_resolution = w, h, res
    state.map_data, state.map_frame, state.map_received = data, 'map', True
    state.body_radius_m, state.wall_margin_m = .20, .15
    state.body_bounds_m = (-.16, -.12, .10, .12)
    state.cruise_speed_mps = .2491282974296706

    targets = (0., 0.)
    actual_wheels = [0., 0.]

    for step in range(70):
        current_sim_time[0] += 0.1
        now = fake_clock()
        rays = []
        for deg in range(360):
            a = pose[2] + math.radians(deg)
            dx, dy = math.cos(a), math.sin(a)
            distances = []
            for p, delta, lo, hi in ((pose[0], dx, .05, 5.95), (pose[1], dy, .05, .65)):
                if abs(delta) > 1e-9:
                    distances.append(((hi if delta > 0 else lo)-p)/delta)
            rays.append(min(distances))
        state.ranges = rays
        state.scan_mono = state.map_mono = now
        node.control.scan_time = node.control.last_d0 = now
        v, omega = wheels_to_twist(*actual_wheels)
        node.control.latest = dict(safety='ARMED', x=pose[0], y=pose[1], th=pose[2],
                                   l_tgt=targets[0], r_tgt=targets[1],
                                   l_rpm=actual_wheels[0], r_rpm=actual_wheels[1], v=v, w=omega)
        node.control.scan_clear = True
        node.control.rotation_clear = node._rotation_clear()
        prev_w = len(uart.writes)
        node.auto_nav_loop()
        assert len(uart.writes) > prev_w
        command = uart.writes[-1].decode().split()
        targets = tuple(map(float, command[1:]))

        # 1st-order motor lag (tau=0.1s, dt=0.1s -> alpha=0.5) and 2% asymmetry
        actual_wheels[0] += 0.5 * (targets[0] - actual_wheels[0])
        actual_wheels[1] += 0.5 * (targets[1] * 1.02 - actual_wheels[1])

        v, omega = wheels_to_twist(*actual_wheels)
        pose[0] += v * .1 * math.cos(pose[2] + omega * .05)
        pose[1] += v * .1 * math.sin(pose[2] + omega * .05)
        pose[2] += omega * .1

    assert pose[0] > 1.8, f'Progress failed: x={pose[0]:.3f}'
    assert abs(pose[1] - 0.325) < (0.070 if initial_yaw > 0 else 0.025), f'Lateral error too high: y={pose[1]:.4f}'
    assert abs(pose[2]) < 0.10, f'Heading error too high: yaw={pose[2]:.4f}'


def test_front_blocked_by_obstacle_does_not_spin_endlessly_in_place():
    _, node, _ = node_fixture()
    node._cautious = True
    node._last_arc_reason = 'SCAN_BODY_CLEARANCE'
    def fail_send(cmd, **kw):
        node._last_arc_reason = 'SCAN_BODY_CLEARANCE'
        return False, 'SESSION_OR_SENSOR_NOT_READY'
    node.send_cmd = fail_send
    res = node._follow((0., 0., 0.), (2.0, 0.0))
    assert res is False, 'Must return False when front is blocked'
    assert node._is_pure_spinning is False, 'Must not enter pure spin towards blocked waypoint'


def test_near_side_yellow_obstacle_alone_does_not_trigger_danger_close_steering():
    brain, node, _ = node_fixture()
    brain.state.ranges = [2.0] * 360
    brain.state.ranges[75] = 0.30
    brain.state.min_dist_m = 0.30
    brain.state.min_angle_deg = 75

    escapes = []
    node._try_escape = lambda: escapes.append(True) or True
    node.auto_nav_loop()
    assert len(escapes) == 0, 'Side obstacle alone must not trigger escape'


def test_closed_loop_straight_tracking_with_prolonged_motor_stiction_and_asymmetry():
    import sys
    from agv_navigation import GridPlanner
    from agv_speed_profile import wheels_to_twist
    from test_agv_rpm_profile import UART
    from agv_command_session import CommandSession

    current_sim_time = [100.0]
    def fake_clock():
        return current_sim_time[0]

    for mod in [sys.modules.get('agv_unified_brain'), sys.modules.get('agv_command_session'), sys.modules.get('agv_navigation')]:
        if mod is not None:
            mod.time.monotonic = fake_clock

    brain, node, _ = node_fixture()
    w, h, res = 120, 14, .05
    data = [0 if 0 < x < w-1 and 0 < y < h-1 else 100 for y in range(h) for x in range(w)]
    grids = {margin: GridPlanner(w, h, res, (0., 0., 0.), data, .20, margin, budget_s=2.) for margin in (.15, .03)}
    node._grid = lambda margin=None: grids[margin if margin is not None else (.03 if getattr(node, '_cautious', False) else .15)]
    pose = [1., .325, 0.0]
    node._pose_map = lambda: tuple(pose)
    node.home, node.goal = (1., .325, 0.), (4.5, .325)
    node._try_escape = lambda: pytest.fail('unexpected escape')
    uart = UART()
    s = CommandSession(uart, strict_preflight=False, clock=fake_clock)
    s.operator_rpm_profile = True
    s.armed = True
    s.autonomy_allowed = True
    s.last_d0 = s.scan_time = fake_clock()
    s.latest = {'safety': 'ARMED'}
    s.scan_clear = s.rotation_clear = True
    s.arc_validator = node._forward_arc_clear
    s.escape_validator = node._escape_clear
    node.control = s
    node.control.slow_speed_requested = lambda: getattr(node, '_cautious', False)
    node.send_cmd = lambda cmd, **kw: brain.AGVROSNode.send_cmd(node, cmd, **kw)

    state = brain.state
    state.map_width, state.map_height, state.map_resolution = w, h, res
    state.map_data, state.map_frame, state.map_received = data, 'map', True
    state.body_radius_m, state.wall_margin_m = .20, .15
    state.body_bounds_m = (-.16, -.12, .10, .12)
    state.cruise_speed_mps = .2491282974296706

    targets = (0., 0.)
    actual_wheels = [0., 0.]
    l_stiction_ticks = 8  # 0.8s stiction on left
    r_stiction_ticks = 4  # 0.4s stiction on right

    for step in range(70):
        current_sim_time[0] += 0.1
        now = fake_clock()
        rays = []
        for deg in range(360):
            a = pose[2] + math.radians(deg)
            dx, dy = math.cos(a), math.sin(a)
            distances = []
            for p, delta, lo, hi in ((pose[0], dx, .05, 5.95), (pose[1], dy, .05, .65)):
                if abs(delta) > 1e-9:
                    distances.append(((hi if delta > 0 else lo)-p)/delta)
            rays.append(min(distances))
        state.ranges = rays
        state.scan_mono = state.map_mono = now
        node.control.scan_time = node.control.last_d0 = now
        v, omega = wheels_to_twist(*actual_wheels)
        node.control.latest = dict(safety='ARMED', x=pose[0], y=pose[1], th=pose[2],
                                   l_tgt=targets[0], r_tgt=targets[1],
                                   l_rpm=actual_wheels[0], r_rpm=actual_wheels[1], v=v, w=omega)
        node.control.scan_clear = True
        node.control.rotation_clear = node._rotation_clear()
        prev_w = len(uart.writes)
        node.auto_nav_loop()
        assert len(uart.writes) > prev_w
        command = uart.writes[-1].decode().split()
        targets = tuple(map(float, command[1:]))

        if step < l_stiction_ticks:
            actual_wheels[0] = 0.0
        else:
            actual_wheels[0] += 0.5 * (targets[0] - actual_wheels[0])

        if step < r_stiction_ticks:
            actual_wheels[1] = 0.0
        else:
            actual_wheels[1] += 0.5 * (targets[1] * 1.02 - actual_wheels[1])

        v, omega = wheels_to_twist(*actual_wheels)
        pose[0] += v * .1 * math.cos(pose[2] + omega * .05)
        pose[1] += v * .1 * math.sin(pose[2] + omega * .05)
        pose[2] += omega * .1

    assert pose[0] > 1.8, f'Progress failed: x={pose[0]:.3f}'
    assert abs(pose[1] - 0.325) < 0.070, f'Lateral error too high: y={pose[1]:.4f}'
    assert abs(pose[2]) < 0.10, f'Heading error too high: yaw={pose[2]:.4f}'


def test_prolonged_mechanical_stall_triggers_stall_warning_without_inventing_spin():
    _, node, _ = node_fixture()
    node.control.latest = dict(l_tgt=40.0, r_tgt=40.0, l_rpm=0.0, r_rpm=0.0)
    node._stall_start = time.monotonic() - 2.0
    escapes = []
    node._try_escape = lambda: escapes.append(True) or True
    node.auto_nav_loop()
    assert node._motion_warning == 'WHEEL_RPM_BELOW_TARGET'
    assert node._is_pure_spinning is False


def test_segment_heading_and_signed_cte_affects_steering_with_identical_waypoint():
    brain, node, commands = node_fixture()
    PathTarget = brain.PathTarget
    pose = (1.0, 0.0, 0.0)
    goal = (3.0, 0.0)

    # Case A: horizontal segment along y = 0.0
    target_A = PathTarget(2.0, 0.0, path_yaw=0.0, e_lat=0.0)
    commands.clear()
    assert node._follow(pose, goal, planned=(node._grid(), target_A))
    w_A = float(commands[-1].split()[2])

    # Case B: identical waypoint (2.0, 0.0), but segment slanted with e_lat = 0.25m
    seg_yaw_B = math.atan2(-0.5, 2.0)
    target_B = PathTarget(2.0, 0.0, path_yaw=seg_yaw_B, e_lat=0.25)
    commands.clear()
    assert node._follow(pose, goal, planned=(node._grid(), target_B))
    w_B = float(commands[-1].split()[2])

    assert w_A == 0.0, f'Expected 0.0 for aligned segment, got {w_A}'
    assert w_B < -0.15, f'Expected negative steering for slanted segment, got {w_B}'
    assert abs(w_B) != abs(w_A), 'Different segment geometry must produce different steering commands'


def test_auto_nav_loop_front_obstacle_emits_checked_bounded_turn_then_resumes_motion():
    brain, node, _ = node_fixture()
    w, h, res = 80, 80, 0.05
    data = [0] * (w * h)
    from agv_navigation import GridPlanner
    from test_agv_rpm_profile import ready
    grid = GridPlanner(w, h, res, (0., 0., 0.), data, .20, .03, budget_s=2.)
    pose = [2.0, 2.0, 0.0]
    node._grid = lambda margin=None: grid
    node._pose_map = lambda: tuple(pose)
    node.home, node.goal = (2.0, 2.0, 0.0), (3.0, 2.0)
    node._cautious = True
    node.control, uart = ready()
    node.control.slow_speed_requested = lambda: True
    node.send_cmd = lambda cmd, **kw: brain.AGVROSNode.send_cmd(node, cmd, **kw)

    state = brain.state
    state.auto_mode = True
    state.map_width, state.map_height, state.map_resolution = w, h, res
    state.map_data, state.map_frame, state.map_received = data, 'map', True
    state.body_radius_m, state.wall_margin_m = .20, .15
    state.body_bounds_m = (-.16, -.12, .10, .12)
    state.cruise_speed_mps = .2491282974296706

    # Forward arc rejected by front obstacle, rotation clear
    node.control.arc_validator = node._forward_arc_clear
    node._rotation_clear = lambda: True
    node.control.rotation_clear = True
    node.control.scan_clear = True
    node.control.escape_validator = lambda v, w: abs(v) < 1e-9 and abs(w) > 0
    node._escape_clear = lambda v, w: abs(v) < 1e-9 and abs(w) > 0

    # Step 1: Front obstacle at 25cm
    ranges = [1.5] * 360
    for deg in range(-20, 21): ranges[deg % 360] = 0.25
    state.ranges = ranges
    state.min_dist_m = 0.25
    state.min_angle_deg = 0

    now = time.monotonic()
    state.scan_mono = state.map_mono = now
    node.control.scan_time = node.control.last_d0 = node.control.clock()
    node.control.latest = dict(safety='ARMED', x=pose[0], y=pose[1], th=pose[2],
                               l_tgt=0.0, r_tgt=0.0, l_rpm=0.0, r_rpm=0.0, v=0.0, w=0.0)

    node.auto_nav_loop()
    assert len(uart.writes) > 0
    first_cmd = uart.writes[-1].decode().strip()
    assert first_cmd.startswith('S')
    parts = list(map(float, first_cmd.split()[1:]))
    assert parts[0] != parts[1], 'Must be a rotation command'
    assert getattr(node, '_spin_recovery', None) is not None, 'Must track turn in _spin_recovery'

    # Step 2: Obstacle cleared, robot translates forward and clears spin recovery
    state.ranges = [1.5] * 360
    state.min_dist_m = 1.5
    now = time.monotonic()
    state.scan_mono = state.map_mono = now
    node.control.scan_time = node.control.last_d0 = node.control.clock()
    pose[0] = 2.15
    node.control.latest = dict(safety='ARMED', x=pose[0], y=pose[1], th=pose[2],
                               l_tgt=40.0, r_tgt=40.0, l_rpm=40.0, r_rpm=40.0, v=0.153, w=0.0)

    node.auto_nav_loop()
    second_cmd = uart.writes[-1].decode().split()
    sec_parts = list(map(float, second_cmd[1:]))
    assert sec_parts[0] > 0 and sec_parts[1] > 0, 'Must resume forward translation'
    assert getattr(node, '_spin_recovery', None) is None, 'Must clear recovery after translation'


def test_auto_nav_loop_front_obstacle_when_rotation_not_clear_emits_zero_hold():
    brain, node, _ = node_fixture()
    w, h, res = 80, 80, 0.05
    data = [0] * (w * h)
    from agv_navigation import GridPlanner
    from test_agv_rpm_profile import ready
    grid = GridPlanner(w, h, res, (0., 0., 0.), data, .20, .03, budget_s=2.)
    pose = [2.0, 2.0, 0.0]
    node._grid = lambda margin=None: grid
    node._pose_map = lambda: tuple(pose)
    node.home, node.goal = (2.0, 2.0, 0.0), (3.0, 2.0)
    node.control, uart = ready()
    node.control.slow_speed_requested = lambda: True
    node.send_cmd = lambda cmd, **kw: brain.AGVROSNode.send_cmd(node, cmd, **kw)

    state = brain.state
    state.auto_mode = True
    state.map_width, state.map_height, state.map_resolution = w, h, res
    state.map_data, state.map_frame, state.map_received = data, 'map', True
    state.body_radius_m, state.wall_margin_m = .20, .15
    state.body_bounds_m = (-.16, -.12, .10, .12)
    state.cruise_speed_mps = .2491282974296706

    # Both forward arc and rotation are rejected
    node.control.arc_validator = lambda v, w: False
    node._forward_arc_clear = lambda v, w: False
    node._rotation_clear = lambda: False
    node.control.rotation_clear = False
    node.control.scan_clear = False
    node.control.escape_validator = lambda v, w: False
    node._escape_clear = lambda v, w: False

    ranges = [0.20] * 360
    state.ranges = ranges
    state.min_dist_m = 0.20
    state.min_angle_deg = 0

    now = time.monotonic()
    state.scan_mono = state.map_mono = now
    node.control.scan_time = node.control.last_d0 = node.control.clock()
    node.control.latest = dict(safety='ARMED', x=pose[0], y=pose[1], th=pose[2],
                               l_tgt=0.0, r_tgt=0.0, l_rpm=0.0, r_rpm=0.0, v=0.0, w=0.0)

    node.auto_nav_loop()
    assert len(uart.writes) > 0
    last_cmd = uart.writes[-1].decode().strip()
    assert last_cmd == 'S 0.000 0.000', f'Must emit zero command, got {last_cmd}'


def test_auto_nav_loop_blocked_start_emits_checked_turn_when_translation_blocked():
    brain, node, _ = node_fixture()
    w, h, res = 80, 80, 0.05
    data = [100] * (w * h)
    from agv_navigation import GridPlanner
    from test_agv_rpm_profile import ready
    grid = GridPlanner(w, h, res, (0., 0., 0.), data, .20, .03, budget_s=2.)
    pose = [2.0, 2.0, 0.0]
    node._grid = lambda margin=None: grid
    node._pose_map = lambda: tuple(pose)
    node.home, node.goal = (2.0, 2.0, 0.0), (3.0, 2.0)
    node.control, uart = ready()
    node.control.slow_speed_requested = lambda: True
    node.send_cmd = lambda cmd, **kw: brain.AGVROSNode.send_cmd(node, cmd, **kw)

    state = brain.state
    state.auto_mode = True
    state.map_width, state.map_height, state.map_resolution = w, h, res
    state.map_data, state.map_frame, state.map_received = data, 'map', True
    state.body_radius_m, state.wall_margin_m = .20, .15
    state.body_bounds_m = (-.16, -.12, .10, .12)
    state.cruise_speed_mps = .2491282974296706

    # Translation blocked, rotation clear
    node.control.arc_validator = lambda v, w: False
    node._forward_arc_clear = lambda v, w: False
    node._rotation_clear = lambda: True
    node.control.rotation_clear = True
    node.control.scan_clear = True
    node.control.escape_validator = lambda v, w: abs(v) < 1e-9 and abs(w) > 0
    node._escape_clear = lambda v, w: abs(v) < 1e-9 and abs(w) > 0

    ranges = [2.0] * 360
    state.ranges = ranges
    state.min_dist_m = 0.50
    state.min_angle_deg = 0

    now = time.monotonic()
    state.scan_mono = state.map_mono = now
    node.control.scan_time = node.control.last_d0 = node.control.clock()
    node.control.latest = dict(safety='ARMED', x=pose[0], y=pose[1], th=pose[2],
                               l_tgt=0.0, r_tgt=0.0, l_rpm=0.0, r_rpm=0.0, v=0.0, w=0.0)

    node.auto_nav_loop()
    assert len(uart.writes) > 0
    cmd = uart.writes[-1].decode().strip()
    assert cmd.startswith('S')
    parts = list(map(float, cmd.split()[1:]))
    assert parts[0] != parts[1], 'Must be a rotation command'
    assert getattr(node, '_spin_recovery', None) is not None, 'Must track turn in _spin_recovery'


def test_rotation_invariance_0_90_180_with_real_local_path_target():
    from agv_navigation import GridPlanner
    w, h, res = 100, 100, 0.05
    data = [0] * (w * h)
    grid = GridPlanner(w, h, res, (0., 0., 0.), data, .20, .03, budget_s=2.)

    # 3 orientations: path along East (0 deg), North (90 deg), and West (180 deg)
    # In each case, robot has identical physical left offset of +5cm and is parallel to path
    cases = [
        ('0 deg (East)',   (1.0, 2.55, 0.0),            (4.0, 2.5)),
        ('90 deg (North)', (2.45, 1.0, math.pi/2),      (2.5, 4.0)),
        ('180 deg (West)', (4.0, 2.45, math.pi),        (1.0, 2.5)),
    ]

    results = []
    for name, pose, goal in cases:
        brain, node, commands = node_fixture()
        node._grid = lambda margin=None: grid
        wp = node._local_path_target(grid, pose, goal)
        assert isinstance(wp, brain.PathTarget)
        commands.clear()
        assert node._follow(pose, goal, planned=(grid, wp))
        assert len(commands) > 0
        w_cmd = float(commands[-1].split()[2])
        results.append(w_cmd)

    # 1. Verification of correct physical sign:
    # When robot is physically to the LEFT of the path, it must steer RIGHT (negative w, clockwise) in all orientations
    for r in results:
        assert r < 0.0, f'Expected negative w to turn right back to path, got {r}'

    # 2. Strict rotational invariance: identical physical offset must yield identical correction magnitude
    assert abs(results[0] - results[1]) < 0.005, f'0 deg ({results[0]}) vs 90 deg ({results[1]}) mismatch'
    assert abs(results[0] - results[2]) < 0.005, f'0 deg ({results[0]}) vs 180 deg ({results[2]}) mismatch'





