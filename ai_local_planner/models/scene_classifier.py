"""Observation-only arena classifier for the six fixed simulator curricula.

Training labels come from the simulator level; deployed inference receives
only the 365-element LiDAR/goal/odometry contract, never a map/level ID.
The classifier is not a PPO policy and is not guaranteed to generalize OOD.
"""

import torch
from torch import nn


class SceneClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.lidar_net = nn.Sequential(
            nn.Conv1d(1, 16, 7, padding=3, padding_mode='circular'), nn.ReLU(),
            nn.Conv1d(16, 32, 5, stride=2, padding=2), nn.ReLU(),
            nn.Conv1d(32, 32, 5, stride=2, padding=2), nn.ReLU(),
            nn.AvgPool1d(9, stride=9), nn.Flatten(),
        )
        self.head = nn.Sequential(nn.Linear(325, 128), nn.ReLU(),
                                  nn.Linear(128, 64), nn.ReLU(),
                                  nn.Linear(64, 6))

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.head(torch.cat((self.lidar_net(obs[..., :360].unsqueeze(-2)),
                                    obs[..., 360:]), dim=-1))
