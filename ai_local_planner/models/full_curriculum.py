"""Experimental observation-only router covering all six curriculum maps.

Composes frozen PPO Level 1-2, BC Level 3/5 and two geometric LiDAR
controllers. It is a *hybrid*, not a single PPO policy, and its heuristics are
valid only for the six known simulator map families until OOD-tested.
"""

import numpy as np
import torch
from torch import nn

from ai_local_planner.models.actor_critic import ActorCritic, MeanPolicy
from ai_local_planner.models.hybrid_policy import (RANGE_THRESHOLD_NORMALIZED,
                                                  MIN_CLOSE_RAYS)
from ai_local_planner.models.reactive_lidar import ReactiveLiDARPolicy
from ai_local_planner.models.reactive_onnx import ReactiveONNXPolicy


def route_from_observation(obs: np.ndarray) -> str:
    obs = np.asarray(obs, dtype=np.float32)
    if obs.shape != (365,) or not np.isfinite(obs).all():
        raise ValueError('Router requires a finite 365-D observation')
    scan = .12 + 11.88 * np.clip(obs[:360], 0., 1.)
    # Robust upper-quartile wall distances across 51-ray side arcs.
    span = float(np.partition(scan[65:116], 38)[38] +
                 np.partition(scan[245:296], 38)[38])
    pocket = (1.05 < span < 2.2 and obs[360] * 10. < 3.4)
    if pocket:
        return 'pocket_bc'
    left = np.count_nonzero(obs[55:125] < RANGE_THRESHOLD_NORMALIZED)
    right = np.count_nonzero(obs[235:305] < RANGE_THRESHOLD_NORMALIZED)
    if left >= MIN_CLOSE_RAYS and right >= MIN_CLOSE_RAYS:
        return 'corridor_bc'
    if span >= 9.1:
        return 'clutter_gap'
    if span >= 7.0:
        return 'dynamic_gap'
    return 'reference_ppo'


class FullCurriculumONNX(nn.Module):
    """Outputs physical velocity using ONNX-safe conditional selection."""

    def __init__(self, reference: ActorCritic, corridor: ActorCritic,
                 pocket: ActorCritic):
        super().__init__()
        self.reference = MeanPolicy(reference)
        self.corridor = MeanPolicy(corridor)
        self.pocket = MeanPolicy(pocket)
        self.clutter = ReactiveONNXPolicy(margin=.12)
        self.dynamic = ReactiveONNXPolicy(margin=.36)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        scan = obs[..., :360].clamp(0., 1.) * 11.88 + .12
        # 13th largest of 51 is the empirical 75th percentile (index 38).
        a = torch.topk(scan[..., 65:116], 13, dim=-1).values[..., -1]
        b = torch.topk(scan[..., 245:296], 13, dim=-1).values[..., -1]
        span = a + b
        pocket = (span > 1.05) & (span < 2.2) & (obs[..., 360] * 10. < 3.4)
        left = (obs[..., 55:125] < RANGE_THRESHOLD_NORMALIZED).sum(-1)
        right = (obs[..., 235:305] < RANGE_THRESHOLD_NORMALIZED).sum(-1)
        corridor = (left >= MIN_CLOSE_RAYS) & (right >= MIN_CLOSE_RAYS) & ~pocket
        clutter = (span >= 9.1) & ~pocket & ~corridor
        dynamic = (span >= 7.) & (span < 9.1) & ~pocket & ~corridor
        result = self.reference(obs)
        result = torch.where(dynamic.unsqueeze(-1), self.dynamic(obs), result)
        result = torch.where(clutter.unsqueeze(-1), self.clutter(obs), result)
        result = torch.where(corridor.unsqueeze(-1), self.corridor(obs), result)
        result = torch.where(pocket.unsqueeze(-1), self.pocket(obs), result)
        return result


class FullCurriculumAgent:
    """Python router for controlled comparison; network actors are frozen."""

    def __init__(self, reference, corridor, pocket):
        self.reference = reference
        self.corridor = corridor
        self.pocket = pocket
        self.clutter = ReactiveLiDARPolicy(margin=.12)
        self.dynamic = ReactiveLiDARPolicy(margin=.36)
        self.calls = {key: 0 for key in ('reference_ppo', 'corridor_bc',
                                        'pocket_bc', 'clutter_gap', 'dynamic_gap')}

    def act(self, obs, deterministic=True):
        route = route_from_observation(obs)
        self.calls[route] += 1
        actor = {'reference_ppo': self.reference, 'corridor_bc': self.corridor,
                 'pocket_bc': self.pocket, 'clutter_gap': self.clutter,
                 'dynamic_gap': self.dynamic}[route]
        return actor.act(obs, deterministic=deterministic)
