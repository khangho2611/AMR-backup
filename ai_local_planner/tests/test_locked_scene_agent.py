"""Stateful supervisor must calibrate and reset at each episode boundary."""

import numpy as np
import torch
from torch import nn

from ai_local_planner.models.locked_scene_agent import LockedSceneAgent


class FixedClassifier(nn.Module):
    def forward(self, observations):
        logits = torch.zeros((len(observations), 6), dtype=torch.float32)
        logits[:, 2] = 9.0
        return logits


class FrozenAction:
    def __init__(self, value):
        self.value = np.array(value, dtype=np.float32)

    def act(self, obs, deterministic=True):
        return self.value.copy(), 0., 0.


def test_scene_lock_waits_five_frames_then_preserves_mode_and_resets():
    agent = LockedSceneAgent(FrozenAction((.5, 0.)),
                             FrozenAction((.8, .3)),
                             FrozenAction((-.1, -.5)),
                             FixedClassifier(), calibration_frames=5)
    obs = np.zeros(365, dtype=np.float32)
    for frame in range(5):
        action, _, _ = agent.act(obs)
        np.testing.assert_array_equal(action, np.array([-1., 0.], dtype=np.float32))
        if frame < 4:
            assert agent.locked_category is None
    assert agent.locked_category == 2
    np.testing.assert_allclose(agent.act(obs)[0], [.8, .3])
    assert agent.choices[3] == 1
    agent.reset()
    assert agent.locked_category is None and agent.frames == 0
    np.testing.assert_array_equal(agent.act(obs)[0], [-1., 0.])
