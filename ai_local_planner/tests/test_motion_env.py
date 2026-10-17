import numpy as np
import pytest

from ai_local_planner.environments.agv_motion_env import AGVMotionEnv, raycast, kinetic_speed_profile
from ai_local_planner.environments.scenarios import Circle
from ai_local_planner.runtime import CommandSafetyFilter, build_observation
from ai_local_planner.trainers.expert import (goal_tracking_action, SingleObstacleTeacher,
                                             RightAngleCorridorTeacher)
from ai_local_planner.scripts.pretrain_obstacle_expert import episode_split


def test_lidar_geometry_and_angle_convention():
    walls = np.array([[0., 0., 10., 0.], [10., 0., 10., 4.],
                      [10., 4., 0., 4.], [0., 4., 0., 0.]])
    ranges = raycast(np.array([2., 2.]), 0., walls, [])
    assert ranges.shape == (360,)
    assert ranges[[0, 90, 180, 270]] == pytest.approx([8., 2., 2., 2.], abs=1e-6)
    ranges = raycast(np.array([2., 2.]), 0., walls, [Circle(4., 2., .4)])
    assert ranges[0] == pytest.approx(1.6, abs=1e-6)


def test_speed_penalty_front_sector_threshold_and_physical_braking():
    scan = np.full(360, 12., dtype=np.float64)
    scan[345] = .26  # -15 degrees belongs to the frontal arc
    penalty, distance, safe = kinetic_speed_profile(scan, .32, .5, .35)
    assert distance == pytest.approx(.26)
    assert safe == pytest.approx(.1)
    assert penalty == pytest.approx(-3. * (.32 - .1))
    scan[345] = 12.
    scan[16] = .2  # +16 degrees must NOT trigger braking
    assert kinetic_speed_profile(scan, .32, .5, .35)[0] == 0.
    scan[16] = 12.
    scan[15] = .3
    assert kinetic_speed_profile(scan, .05, .5, .35)[0] == 0.
    scan[15] = 1.0
    assert kinetic_speed_profile(scan, .35, .5, .35)[0] == 0.


def test_speed_reward_component_corresponds_to_returned_true_scan():
    env = AGVMotionEnv(level=3, randomize=True)
    env.reset(seed=4000000)
    for _ in range(5):
        _, _, done, truncated, info = env.step([1., 0.])
        penalty, front, safe = kinetic_speed_profile(
            env._true_scan, info["actual_vw"][0], .5, .35)
        assert info["reward_components"]["speed_excess"] == pytest.approx(penalty)
        assert info["forward_clearance_m"] == pytest.approx(front)
        assert info["kinetic_safe_speed_mps"] == pytest.approx(safe)
        if done or truncated:
            break


def test_forward_braking_guard_covers_robot_footprint_and_uart_delay():
    guard = CommandSafetyFilter()
    scan = np.full(360, 12., dtype=np.float64)
    scan[0] = .40  # outside the old .18m threshold but inside braking distance
    assert guard.update([.35, 0.], scan) == pytest.approx([0., 0.])
    scan[0] = 12.
    scan[270] = .3  # a close side wall does not demand a front stop
    assert guard.update([.35, 0.], scan) == pytest.approx([.05, 0.])
    with pytest.raises(ValueError, match='Safety distance'):
        CommandSafetyFilter(stop_distance=.18)


@pytest.mark.parametrize("level", range(1, 7))
def test_six_levels_have_safe_start_and_observation(level):
    env = AGVMotionEnv(level=level, randomize=False)
    obs, info = env.reset(seed=17)
    assert env.observation_space.contains(obs)
    assert obs.dtype == np.float32 and obs.shape == (365,)
    assert info["level"] == level
    assert env._clearance() > .20
    assert 0. <= obs[360] <= 1.
    assert abs(obs[361] ** 2 + obs[362] ** 2 - 1) < 1e-5
    assert all(.12 <= d <= 12. for d in env._true_scan)


def test_uart_delay_and_acceleration_limit():
    env = AGVMotionEnv(randomize=False)
    env.reset(seed=10)
    _, _, _, _, one = env.step(np.array([1., 1.]))
    assert one["applied_vw"] == pytest.approx([0., 0.])
    _, _, _, _, two = env.step(np.array([1., 1.]))
    assert two["applied_vw"] == pytest.approx([.05, .2])
    _, _, _, _, three = env.step(np.array([-1., -1.]))
    assert three["applied_vw"] == pytest.approx([.10, .4])
    _, _, _, _, four = env.step(np.array([-1., -1.]))
    assert four["applied_vw"] == pytest.approx([.05, .2])


def test_randomization_is_deterministic_for_fixed_seed_and_has_valid_slip():
    e1, e2 = AGVMotionEnv(level=4), AGVMotionEnv(level=4)
    a, _ = e1.reset(seed=123)
    b, _ = e2.reset(seed=123)
    assert np.array_equal(a, b)
    assert .03 <= e1.noise_sigma <= .05
    assert np.all((np.abs(e1.wheel_slip) >= .05) & (np.abs(e1.wheel_slip) <= .1))
    for _ in range(4):
        a, reward_a, *_ = e1.step([0., .3])
        b, reward_b, *_ = e2.step([0., .3])
        assert np.array_equal(a, b)
        assert reward_a == reward_b


def test_geometry_based_collision_independent_of_noisy_lidar():
    env = AGVMotionEnv(level=1, randomize=True)
    env.reset(seed=5)
    env.scenario.obstacles.append(Circle(env.pose[0] + .12, env.pose[1], .12))
    _, _, terminal, _, info = env.step([-1., 0.])
    assert terminal and info["collision"] and not info["success"]
    assert info["reward_components"]["collision"] == -50.


def test_slip_model_uses_wheelbase():
    env = AGVMotionEnv(level=1, randomize=False)
    env.reset(seed=0)
    env.wheel_slip[:] = [.10, -.10]
    env.step([1., 0.])  # one-step UART delay
    _, _, _, _, info = env.step([1., 0.])
    assert info["actual_vw"][0] == pytest.approx(.05)
    assert info["actual_vw"][1] == pytest.approx(-.10 * .05 * 2 / .28)


def test_watchdog_stops_and_bypasses_deceleration_limits():
    guard = CommandSafetyFilter()
    clear = np.full(360, 3., dtype=np.float32)
    assert guard.update([.35, 1.5], clear) == pytest.approx([.05, .2])
    alert = clear.copy()
    alert[6] = .17
    assert guard.update([.35, 1.5], alert) == pytest.approx([0., 0.])
    assert guard.update([.35, 1.5], np.full(360, np.nan)) == pytest.approx([0., 0.])
    assert guard.update([.35, 1.5], clear) == pytest.approx([.05, .2])


def test_invalid_actions_rejected():
    env = AGVMotionEnv(randomize=False)
    env.reset()
    with pytest.raises(ValueError):
        env.step([float("nan"), 0.])


def test_live_observation_matches_simulator_without_noise():
    env = AGVMotionEnv(randomize=False)
    sim_obs, _ = env.reset(seed=3)
    live_obs = build_observation(env._true_scan, env.pose, env.goal, env.v, env.w)
    assert np.array_equal(live_obs, sim_obs)


def test_reference_teacher_reaches_level1_across_multiple_randomized_seeds():
    env = AGVMotionEnv(level=1, randomize=True)
    for seed in [1000, 1001, 1002, 1003, 1004]:
        obs, _ = env.reset(seed=seed)
        for _ in range(env.max_steps):
            obs, _, done, truncated, info = env.step(goal_tracking_action(obs))
            if done or truncated:
                assert info["success"], f"Teacher did not reach goal on seed {seed}"
                break
        else:
            pytest.fail("Episode did not terminate")


def test_single_obstacle_teacher_navigates_level2_with_domain_randomization():
    env = AGVMotionEnv(level=2, randomize=True)
    for seed in (3001, 3002, 3003, 3004, 3005):
        obs, _ = env.reset(seed=seed)
        teacher = SingleObstacleTeacher(env.scenario.obstacles[0], env.goal)
        for _ in range(env.max_steps):
            action = teacher.act(obs, env.pose)
            assert env.action_space.contains(action)
            obs, _, done, truncated, info = env.step(action)
            if done or truncated:
                assert info["success"], f"Waypoint teacher failed seed {seed}"
                break
        else:
            pytest.fail("Level 2 expert did not terminate")


def test_right_angle_teacher_navigates_level3_with_domain_randomization():
    env = AGVMotionEnv(level=3, randomize=True)
    for seed in (5001, 5002, 5003, 5004, 5005):
        obs, _ = env.reset(seed=seed)
        teacher = RightAngleCorridorTeacher(env.goal)
        for _ in range(env.max_steps):
            action = teacher.act(obs, env.pose)
            assert env.action_space.contains(action)
            obs, _, done, truncated, info = env.step(action)
            if done or truncated:
                assert info["success"], (f"Level 3 teacher failed on seed {seed}: "
                                         f"{info['steps']} steps, {env.pose}")
                assert teacher.passed_corner
                break
        else:
            pytest.fail("Level 3 teacher episode did not terminate")


def test_bc_validation_split_keeps_whole_episodes_apart():
    groups = np.repeat(np.arange(20), 4)
    training, validation = episode_split(groups, seed=13)
    assert len(training) + len(validation) == len(groups)
    assert not (set(groups[training]) & set(groups[validation]))
    assert len(np.unique(groups[validation])) == 2
