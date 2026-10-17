"""Experimental six-scene, observation-only hybrid ONNX policy.

The scene network is trained with simulator labels; three policy experts were
trained separately. This is not one end-to-end PPO-trained actor, and the
classifier has no temporal memory. Restrict claims to evaluated trajectories.
"""

import torch
from torch import nn

from ai_local_planner.models.actor_critic import ActorCritic, MeanPolicy
from ai_local_planner.models.reactive_onnx import ReactiveONNXPolicy
from ai_local_planner.models.scene_classifier import SceneClassifier


class SceneRoutedMeanPolicy(nn.Module):
    def __init__(self, reference: ActorCritic, corridor: ActorCritic,
                 pocket: ActorCritic, classifier: SceneClassifier):
        super().__init__()
        self.classifier = classifier
        self.reference = MeanPolicy(reference)
        self.corridor = MeanPolicy(corridor)
        self.pocket = MeanPolicy(pocket)
        self.reactive = ReactiveONNXPolicy(margin=.12)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        category = self.classifier(obs).argmax(dim=-1)
        # Level 4 gap inflation: robot radius 0.20 + 0.12 m.
        # Level 6 gap inflation: robot radius 0.20 + 0.36 m.
        inflation = torch.where(category == 5,
                                torch.full_like(category, .56, dtype=obs.dtype),
                                torch.full_like(category, .32, dtype=obs.dtype))
        gap_action = self.reactive(obs, inflation_override=inflation)
        output = torch.where((category == 2).unsqueeze(-1),
                             self.corridor(obs), self.reference(obs))
        output = torch.where((category == 3).unsqueeze(-1), gap_action, output)
        output = torch.where((category == 4).unsqueeze(-1), self.pocket(obs), output)
        output = torch.where((category == 5).unsqueeze(-1), gap_action, output)
        return output
