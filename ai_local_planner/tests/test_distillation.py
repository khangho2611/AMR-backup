"""Guard against frame-level validation leakage in six-stage imitation."""

import numpy as np

from ai_local_planner.scripts.distill_locked_experts import build_balanced_split


def test_balanced_split_never_mixes_frames_from_one_episode():
    data = {}
    for level in (1, 2, 3):
        # First column identifies the complete episode from which a frame came.
        labels = np.repeat(np.array([10 * level, 10 * level + 1], np.float32), 12)
        obs = np.zeros((24, 365), np.float32)
        obs[:, 0] = labels
        action = np.tile([-.5, .25], (24, 1)).astype(np.float32)
        groups = np.repeat(np.arange(2), 12)
        data[level] = obs, action, groups
    train_obs, train_act, valid_obs, valid_act, distribution = (
        build_balanced_split(data, seed=42, frames_per_level=5))
    assert train_obs.shape == (15, 365)
    assert valid_obs.shape == (3, 365)
    assert train_act.shape == (15, 2) and valid_act.shape == (3, 2)
    assert set(train_obs[:, 0]).isdisjoint(set(valid_obs[:, 0]))
    assert all(item["train_frames"] == 5 and item["heldout_frames"] == 1
               for item in distribution.values())
