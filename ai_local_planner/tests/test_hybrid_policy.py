"""Ensure experimental corridor gating is robust to isolated false returns."""

import numpy as np
import pytest
import torch
from torch import nn

from ai_local_planner.models.hybrid_policy import (CorridorRoutedMeanPolicy,
                                                   corridor_from_observation)
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.scripts.evaluate_corridor_robustness import change_corridor_geometry


class ConstantActor(nn.Module):
    def __init__(self, logits):
        super().__init__()
        self.register_buffer("logits", torch.tensor(logits, dtype=torch.float32))

    def forward(self, observations):
        return (self.logits.expand(observations.shape[0], -1),
                torch.zeros(observations.shape[0]))


def test_route_requires_bilateral_dense_near_returns():
    obs = np.ones(365, dtype=np.float32)
    obs[55:60] = 0.  # occasional false short returns
    obs[235:240] = 0.
    assert not corridor_from_observation(obs)
    obs[55:100] = .03
    assert not corridor_from_observation(obs)  # single close obstacle
    obs[235:280] = .03
    assert corridor_from_observation(obs)
    with pytest.raises(ValueError):
        corridor_from_observation(np.zeros(364))


def test_numpy_switch_matches_torch_ensemble():
    far = np.ones(365, dtype=np.float32)
    near = far.copy()
    near[55:95] = near[235:275] = .02
    policy = CorridorRoutedMeanPolicy(ConstantActor([-1., 0.]),
                                     ConstantActor([1., 1.])).eval()
    result = policy(torch.tensor(np.stack([far, near]))).detach().numpy()
    assert not corridor_from_observation(far)
    assert corridor_from_observation(near)
    assert result.shape == (2, 2)
    assert result[0] == pytest.approx([.35 * (1. - np.tanh(1)) / 2., 0.])
    assert result[1] == pytest.approx([.35 * (1. + np.tanh(1)) / 2.,
                                      1.5 * np.tanh(1)])


def test_ood_geometry_produces_consistent_pose_walls_and_lidar():
    env = AGVMotionEnv(level=3, randomize=False)
    env.reset(seed=4)
    obs = change_corridor_geometry(env, .65, 3.9, 1.75, .10)
    assert obs.shape == (365,)
    assert env.goal == pytest.approx([3.9, 5.65])
    assert env.pose == pytest.approx([1., 1.75, .10])
    assert env._clearance() == pytest.approx(.325)
    with pytest.raises(ValueError, match="width"):
        change_corridor_geometry(env, .4, 3.9, 1.75, 0.)
