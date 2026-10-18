"""Near-field guard must survive LiDAR dropout and match exported control."""

import numpy as np
import torch
from torch import nn

from ai_local_planner.models.actor_critic import MeanPolicy
from ai_local_planner.configs.settings import load_config
from ai_local_planner.trainers.ppo_agent import PPOAgent


class NeutralNetwork(nn.Module):
    def forward(self, obs):
        return (torch.zeros((*obs.shape[:-1], 2), dtype=obs.dtype),
                torch.zeros(obs.shape[:-1], dtype=obs.dtype))


class SlowNetwork(NeutralNetwork):
    def forward(self, obs):
        mean, value = super().forward(obs)
        mean[..., 0] = -5.
        return mean, value


class FastNetwork(NeutralNetwork):
    def forward(self, obs):
        mean, value = super().forward(obs)
        mean[..., 0] = 5.
        return mean, value


def observation():
    x = torch.ones((1, 365), dtype=torch.float32)
    x[:, 361] = 1.
    x[:, 362] = 0.
    return x


def test_dropped_isolated_minimum_range_returns_do_not_force_stop():
    x = observation()
    x[:, [10, 50, 120, 180, 270, 359]] = 0.
    command = MeanPolicy(NeutralNetwork())(x)[0]
    assert abs(command[0].item() - .175) < 1e-6
    assert abs(command[1].item()) < 1e-6


def test_sustained_left_and_right_hazards_limit_speed_and_steer_away():
    policy = MeanPolicy(NeutralNetwork())
    for side, desired_sign in ((50, -1), (270, 1)):
        x = observation()
        x[:, side:side + 5] = (.20 - .12) / 11.88
        command = policy(x)[0]
        assert 0. <= command[0].item() <= .0800001
        assert command[1].item() * desired_sign >= .59


def test_hazard_spanning_scan_wrap_is_detected():
    x = observation()
    x[:, [358, 359, 0, 1, 2]] = (.19 - .12) / 11.88
    command = MeanPolicy(NeutralNetwork())(x)[0]
    assert command[0].item() <= .0800001
    assert command[1].item() >= .59


def test_ppo_agent_deterministic_action_uses_same_shield_as_mean_policy():
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    obs = observation().numpy()[0]
    obs[270:275] = (.20 - .12) / 11.88
    normalized, _, _ = agent.act(obs, deterministic=True)
    physical = MeanPolicy(agent.network)(torch.from_numpy(obs[None]))[0].detach().numpy()
    np.testing.assert_allclose((normalized[0] + 1.) * .175, physical[0], atol=1e-7)
    np.testing.assert_allclose(normalized[1] * 1.5, physical[1], atol=1e-7)
    assert physical[0] <= .0800001


def test_dual_wall_clear_corridor_centering_and_progress():
    x = observation()
    x[:, 361] = 0.
    x[:, 362] = 1.
    x[:, 75:106] = (.48 - .12) / 11.88
    x[:, 255:286] = (.27 - .12) / 11.88
    command = MeanPolicy(SlowNetwork())(x)[0]
    assert command[0].item() >= .09999
    assert command[1].item() > .20  # right wall nearer, steer left


def test_one_sided_clutter_does_not_trigger_corridor_cruise():
    x = observation()
    x[:, 255:286] = (.27 - .12) / 11.88
    command = MeanPolicy(SlowNetwork())(x)[0]
    assert command[0].item() < .01
    assert abs(command[1].item()) < 1e-6


def test_predictive_forward_braking_uses_contiguous_rays():
    x = observation()
    x[:, 4:9] = (.60 - .12) / 11.88
    command = MeanPolicy(FastNetwork())(x)[0]
    assert .07 < command[0].item() <= .181

    x = observation()
    x[:, 4:7] = (.12 - .12) / 11.88  # three minimum-range dropouts
    command = MeanPolicy(FastNetwork())(x)[0]
    assert command[0].item() > .34


def test_unilateral_forward_flank_guard_maintains_escape_turn():
    model = MeanPolicy(NeutralNetwork())
    for start, sign in ((15, -1.), (305, 1.)):
        x = observation()
        x[:, start:start + 40] = (.65 - .12) / 11.88
        command = model(x)[0]
        assert command[1].item() * sign >= .649
        assert command[0].item() >= 0.
