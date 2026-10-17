"""Experimental LiDAR-based routing between two frozen specialist policies.

The switch is computed only from the existing normalized 365-D observation.
This prototype assumes the Level 3 corridor remains narrow on both sides;
it is not a general passage classifier or a real-robot safety controller.
"""

import numpy as np
import torch
from torch import nn

from ai_local_planner.models.actor_critic import ActorCritic, MeanPolicy


# 70 rays per side, 18 close returns on EACH side. Percentile-like aggregation
# tolerates sporadic dropped LiDAR beams much better than min(range).
RANGE_THRESHOLD_NORMALIZED = (.72 - .12) / (12. - .12)
MIN_CLOSE_RAYS = 18


def corridor_from_observation(obs: np.ndarray) -> bool:
    obs = np.asarray(obs, dtype=np.float32)
    if obs.shape != (365,) or not np.isfinite(obs).all():
        raise ValueError("Expected a finite 365-dimensional observation")
    return (np.count_nonzero(obs[55:125] < RANGE_THRESHOLD_NORMALIZED) >= MIN_CLOSE_RAYS
            and np.count_nonzero(obs[235:305] < RANGE_THRESHOLD_NORMALIZED) >= MIN_CLOSE_RAYS)


class CorridorRoutedMeanPolicy(nn.Module):
    """ONNX-exportable 365-D -> [v,w] ensemble; no extra observation fields."""

    def __init__(self, standard: ActorCritic, corridor: ActorCritic):
        super().__init__()
        self.standard = MeanPolicy(standard)
        self.corridor = MeanPolicy(corridor)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        close_left = (obs[..., 55:125] < RANGE_THRESHOLD_NORMALIZED).sum(dim=-1)
        close_right = (obs[..., 235:305] < RANGE_THRESHOLD_NORMALIZED).sum(dim=-1)
        use_corridor = ((close_left >= MIN_CLOSE_RAYS) &
                        (close_right >= MIN_CLOSE_RAYS)).unsqueeze(-1)
        return torch.where(use_corridor, self.corridor(obs), self.standard(obs))
