"""Level-2 early obstacle approach weighting for retention DAgger."""

import numpy as np

from ai_local_planner.scripts.repair_retention import (
    level2_safety_weights, level4_safety_weights, level5_trap_weights,
    episode_counts, five_level_budgets, task_loss_weights)


def _observations():
    return np.ones((3, 365), dtype=np.float32)


def test_level2_obstacle_approach_weights_early_narrow_central_obstacle():
    observations = _observations()
    # Eleven of 51 frontal rays see a narrow obstacle at 2.0 m.
    normalized = (2.0 - .12) / (12.0 - .12)
    observations[0, :6] = normalized
    observations[0, 355:360] = normalized
    # Only two minimum-range points simulate LiDAR dropout, not an obstacle.
    observations[1, 0] = 0.
    observations[1, 359] = 0.

    weights = level2_safety_weights(observations, near_weight=3., approach_weight=4.)

    np.testing.assert_allclose(weights, [4., 1., 1.])
    assert weights.dtype == np.float32


def test_level2_near_lateral_obstacle_preserves_existing_weight():
    observations = _observations()
    normalized = (0.8 - .12) / (12.0 - .12)
    observations[0, 26:46] = normalized
    weights = level2_safety_weights(observations, near_weight=3., approach_weight=4.)
    np.testing.assert_allclose(weights, [3., 1., 1.])


def test_level2_collection_budget_can_expand_without_reducing_rehearsal():
    assert episode_counts(1, 20, 20, 80, 90) == (20, 20)
    assert episode_counts(2, 20, 20, 80, 90) == (80, 90)
    assert episode_counts(3, 20, 20, 80, 90) == (20, 20)
    assert episode_counts(2, 20, 20, None, None) == (20, 20)


def test_level4_close_obstacles_get_threefold_weight_without_dropout_bias():
    obs = np.ones((3, 365), dtype=np.float32)
    obs[0, 35:65] = (.42 - .12) / 11.88
    obs[1, :5] = 0.  # Isolated dropout is not a close obstacle.
    weights = level4_safety_weights(obs)
    np.testing.assert_array_equal(weights, [3., 1., 1.])
    assert weights.dtype == np.float32


def test_level5_trap_weights_detect_three_walls_with_robust_quantiles():
    obs = np.ones((3, 365), dtype=np.float32)
    near = (.45 - .12) / 11.88
    obs[0, :26] = near
    obs[0, 334:360] = near
    obs[0, 65:105] = near
    obs[0, 255:295] = near
    obs[1, :2] = 0.
    np.testing.assert_array_equal(level5_trap_weights(obs), [3., 1., 1.])


def test_five_level_budgets_and_loss_weights_preserve_old_levels():
    assert five_level_budgets([15, 25, 25, 40, 35]) == {
        1: (8, 7), 2: (13, 12), 3: (13, 12), 4: (20, 20), 5: (18, 17)}
    task_weights = task_loss_weights(5)
    assert set(task_weights) == {1, 2, 3, 4, 5}
    assert np.isclose(sum(task_weights.values()), 1.)
    assert sum(task_weights[i] for i in (1, 2, 3)) >= .50
