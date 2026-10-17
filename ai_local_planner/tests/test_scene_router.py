"""Check every scene branch and the two distinct inflation radii."""

import numpy as np
import torch
from torch import nn

from ai_local_planner.models.reactive_onnx import ReactiveONNXPolicy
from ai_local_planner.models.scene_routed import SceneRoutedMeanPolicy


class StaticExpert(nn.Module):
    def __init__(self, value):
        super().__init__()
        self.register_buffer('mean', torch.tensor(value, dtype=torch.float32))

    def forward(self, observations):
        return self.mean.expand(len(observations), -1), torch.zeros(len(observations))


class SelectClass(nn.Module):
    def __init__(self, category):
        super().__init__()
        self.category = category

    def forward(self, obs):
        output = torch.zeros((len(obs), 6), dtype=obs.dtype)
        output[:, self.category] = 10.
        return output


def test_all_six_scene_routes_have_correct_frozen_expert():
    torch.set_num_threads(1)
    obs = torch.from_numpy(np.random.default_rng(5).random((2, 365),
                                                           dtype=np.float32))
    obs[:, 361:363] = torch.tensor([[0., 1.], [0., -1.]])
    reference = StaticExpert((0., 0.))
    corridor = StaticExpert((-.8, .6))
    pocket = StaticExpert((.6, -.8))
    for category in range(6):
        hybrid = SceneRoutedMeanPolicy(reference, corridor, pocket,
                                       SelectClass(category)).eval()
        with torch.no_grad():
            result = hybrid(obs)
            if category in (0, 1):
                expected = hybrid.reference(obs)
            elif category == 2:
                expected = hybrid.corridor(obs)
            elif category == 4:
                expected = hybrid.pocket(obs)
            else:
                expected = ReactiveONNXPolicy(margin=.12 if category == 3 else .36)(obs)
            torch.testing.assert_close(result, expected, atol=1e-6, rtol=0)
        assert result.shape == (2, 2)
        assert torch.isfinite(result).all()
        assert ((result[:, 0] >= 0.) & (result[:, 0] <= .35)).all()
        assert (result[:, 1].abs() <= 1.5).all()
