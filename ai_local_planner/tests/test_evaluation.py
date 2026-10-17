"""Regression checks for closed-loop policy evaluation and BC-anchored PPO."""

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.trainers.ppo_agent import PPOAgent


class StationaryPolicy:
    def act(self, obs, deterministic=False):
        assert deterministic
        return np.array([-1., 0.], dtype=np.float32), 0., 0.


def test_evaluator_counts_timeouts_separately_from_collisions():
    result = evaluate_agent(StationaryPolicy(), level=1, episodes=2,
                            seed=123, randomize=False, max_steps=3)
    assert result["success_rate"] == 0.
    assert result["collision_rate"] == 0.
    assert result["timeout_rate"] == 1.
    assert result["mean_episode_steps"] == 3.
    assert result["mean_min_clearance_m"] > .20


def test_reference_policy_is_frozen_and_matches_source(tmp_path):
    torch.set_num_threads(1)
    source = PPOAgent(load_config()["ppo"], device="cpu")
    path = tmp_path / "source.pth"
    source.save(path, 0, 2)
    trained = PPOAgent(load_config()["ppo"], device="cpu")
    trained.set_reference_policy(path, 10.)
    observations = torch.rand(4, 365)
    observations[:, 361:363] = torch.tensor([0., 1.])
    with torch.no_grad():
        expected = source.network(observations)[0]
        reference = trained.reference_network(observations)[0]
    assert torch.equal(expected, reference)
    assert not any(param.requires_grad for param in trained.reference_network.parameters())
