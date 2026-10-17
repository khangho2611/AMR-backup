"""Geometric corner emphasis and weighted imitation objectives."""

import numpy as np
import pytest
import torch

from ai_local_planner.scripts.corner_approach_dagger import (
    corner_weight, split_frames, weighted_actor_mse, mixed_rehearsal_loss)


def test_corner_zone_or_front_clearance_gives_three_times_weight():
    clear = np.full(360, 12., np.float32)
    assert corner_weight([2.20, 1.85], clear) == 3.
    assert corner_weight([1., 1.85], clear) == 1.
    clear[350] = 1.1
    assert corner_weight([1., 1.85], clear) == 3.
    clear[350] = 12.
    clear[16] = .2
    assert corner_weight([1., 1.85], clear) == 1.


def test_weighted_loss_increases_corner_gradient_by_exact_factor_three():
    predictions = torch.tensor([[1., 0.], [1., 0.]], requires_grad=True)
    labels = torch.zeros_like(predictions)
    weights = torch.tensor([1., 3.])
    weighted_actor_mse(predictions, labels, weights).backward()
    assert float(predictions.grad[1, 0] / predictions.grad[0, 0]) == pytest.approx(3.)


def test_replay_gradient_budget_is_35_percent_despite_3x_corner_weights():
    prediction = torch.tensor([[1., 0.], [1., 0.], [1., 0.]], requires_grad=True)
    labels = torch.zeros_like(prediction)
    weights = torch.tensor([1., 1., 3.])
    replay = torch.tensor([True, True, False])
    mixed_rehearsal_loss(prediction, labels, weights, replay).backward()
    replay_grad = float(prediction.grad[:2, 0].sum())
    corner_grad = float(prediction.grad[2, 0])
    assert replay_grad / (replay_grad + corner_grad) == pytest.approx(.35)


def test_episode_split_keeps_corner_holdout_disjoint():
    obs = np.zeros((20, 365), np.float32)
    obs[:, 0] = np.repeat(np.arange(10), 2)
    labels = np.zeros((20, 2), np.float32)
    weights = np.ones(20, np.float32)
    groups = np.repeat(np.arange(10), 2)
    train, valid = split_frames((obs, labels, weights, groups), seed=13)
    assert set(train[0][:, 0]).isdisjoint(set(valid[0][:, 0]))
