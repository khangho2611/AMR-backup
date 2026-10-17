"""Circular LiDAR Conv1D + 5-variable goal/velocity MLP PPO policy."""

import math

import torch
from torch import nn
from torch.distributions import Normal
from torch.nn import functional as F


class ActorCritic(nn.Module):
    def __init__(self, legacy: bool = False):
        super().__init__()
        sectors = 10 if legacy else 30
        self.lidar_net = nn.Sequential(
            nn.Conv1d(1, 16, 7, padding=3, padding_mode="circular"), nn.ReLU(),
            nn.Conv1d(16, 32, 5, stride=2, padding=2), nn.ReLU(),
            nn.Conv1d(32, 32, 5, stride=2, padding=2), nn.ReLU(),
            # 360 -> 180 -> 90 -> 30 sectors (12 degrees per sector).
            # Legacy support is used only for explicit historical exports/migration.
            nn.AvgPool1d(kernel_size=9 if legacy else 3,
                         stride=9 if legacy else 3), nn.Flatten(),
            nn.Linear(32 * sectors, 128), nn.ReLU(),
        )
        self.goal_net = nn.Sequential(nn.Linear(5, 32), nn.Tanh(),
                                      nn.Linear(32, 32), nn.Tanh())
        self.fusion = nn.Sequential(nn.Linear(160, 128), nn.ReLU(),
                                    nn.Linear(128, 64 if legacy else 128), nn.ReLU())
        self.actor = nn.Linear(64 if legacy else 128, 2)
        self.critic = nn.Linear(64 if legacy else 128, 1)
        self.log_std = nn.Parameter(torch.full((2,), -0.7))
        # Start approximately stationary, so initial random actions are gradual.
        nn.init.zeros_(self.actor.weight)
        nn.init.zeros_(self.actor.bias)


    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if not torch.onnx.is_in_onnx_export() and obs.shape[-1] != 365:
            raise ValueError("Expected observation[...,365]")
        lidar = self.lidar_net(obs[..., :360].unsqueeze(-2))
        goal = self.goal_net(obs[..., 360:])
        features = self.fusion(torch.cat((lidar, goal), dim=-1))
        return self.actor(features), self.critic(features).squeeze(-1)

    def value(self, obs: torch.Tensor) -> torch.Tensor:
        return self.forward(obs)[1]

    def sample(self, obs: torch.Tensor):
        mean, value = self(obs)
        dist = Normal(mean, self.log_std.clamp(-5., 1.).exp())
        raw = dist.rsample()
        action = torch.tanh(raw)
        return action, self._log_prob(dist, raw), value

    @staticmethod
    def _log_prob(dist: Normal, raw: torch.Tensor) -> torch.Tensor:
        # Stable log(1-tanh(raw)^2) Jacobian for the squashed Gaussian.
        log_jacobian = 2. * (math.log(2.) - raw - F.softplus(-2. * raw))
        return (dist.log_prob(raw) - log_jacobian).sum(dim=-1)

    def evaluate(self, obs: torch.Tensor, actions: torch.Tensor):
        mean, value = self(obs)
        dist = Normal(mean, self.log_std.clamp(-5., 1.).exp())
        # The tanh inversion is numerically well conditioned for |a|<1.
        safe = actions.clamp(-1 + 1e-6, 1 - 1e-6)
        raw = torch.atanh(safe)
        log_prob = self._log_prob(dist, raw)
        # Base Gaussian entropy is a proxy (squashed entropy has no simple form).
        return log_prob, dist.entropy().sum(dim=-1), value


def is_legacy_state_dict(weights: dict) -> bool:
    """Recognize historical 10-sector/64-fusion checkpoints by tensor sizes."""
    return weights["lidar_net.8.weight"].shape[1] == 32 * 10


def migrate_legacy_state_dict(weights: dict) -> dict:
    """Embed the old 10-sector actor in the 30-sector network without drift.

    Nine-sample averaging equals averaging three successive three-sample pools.
    Duplicating each legacy weight across those sectors with /3 preserves it.
    New fusion channels initially have zero impact on actor/critic outputs.
    """
    if not is_legacy_state_dict(weights):
        return weights
    target = ActorCritic().state_dict()
    for name, value in weights.items():
        if name == "lidar_net.8.weight":
            target[name] = (value.reshape(128, 32, 10)
                            .repeat_interleave(3, dim=2).div(3)
                            .reshape(128, 32 * 30))
        elif name in ("fusion.2.weight", "fusion.2.bias"):
            target[name].zero_()
            target[name][:64] = value
        elif name in ("actor.weight", "critic.weight"):
            target[name].zero_()
            target[name][:, :64] = value
        else:
            if target[name].shape != value.shape:
                raise ValueError(f"Cannot migrate incompatible legacy parameter: {name}")
            target[name] = value
    return target


class MeanPolicy(nn.Module):
    """Deterministic ONNX contract: (N,365) -> physical (v,w) (N,2)."""

    def __init__(self, network: ActorCritic, v_max: float = .35, w_max: float = 1.5):
        super().__init__()
        self.network = network
        self.v_max, self.w_max = v_max, w_max

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        mean, _ = self.network(obs)
        action = torch.tanh(mean)
        return torch.stack(((action[..., 0] + 1.) * (.5 * self.v_max),
                            action[..., 1] * self.w_max), dim=-1)
