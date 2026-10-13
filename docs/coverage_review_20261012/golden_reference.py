"""Reference components, NOT a full trainer or a robot controller.

Default deployment proposal: 3 map channels and 8 scalar features.
Minimal known-map ablation: CoverageQNet(channels=2, feature_dim=2).
Safety masks and feature extraction remain outside the exported network.
"""
import torch
from torch import nn


class CoverageQNet(nn.Module):
    def __init__(self, channels=3, feature_dim=8):
        super().__init__()
        self.image = nn.Sequential(
            nn.Conv2d(channels, 8, 3, padding=1), nn.ReLU(),
            nn.Conv2d(8, 16, 3, stride=2, padding=1), nn.ReLU(),
            nn.Flatten(), nn.Linear(16 * 5 * 5, 64), nn.ReLU(),
        )
        self.vector = nn.Sequential(nn.Linear(feature_dim, 16), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(80, 64), nn.ReLU(), nn.Linear(64, 4))

    def forward(self, local_map, features):
        return self.head(torch.cat((self.image(local_map), self.vector(features)), dim=1))


def greedy_safe_action(q_values, valid_mask):
    """Single-state CPU controller reference. None means STOP/replan, never argmax."""
    if not torch.isfinite(q_values).all() or not valid_mask.any():
        return None
    return int(q_values.masked_fill(~valid_mask, -torch.inf).argmax().item())


@torch.no_grad()
def double_dqn_target(reward, terminated, discount, next_online_q,
                      next_target_q, next_valid_mask):
    """All scalar tensors are [B]; Q and boolean masks are [B, 4].

    discount is gamma for fixed-duration transitions, gamma**duration_units
    for duration-aware options. A collector time limit (truncated) does NOT
    suppress bootstrap. Pass the final pre-reset observation for truncations.
    A no-action terminal failure must be explicitly labelled by the environment.
    """
    if not torch.isfinite(next_online_q).all() or not torch.isfinite(next_target_q).all():
        raise ValueError('Non-finite Q values')
    has_action = next_valid_mask.any(dim=1)
    if ((~terminated) & (~has_action)).any():
        raise ValueError('Nonterminal state has no valid action: define STOP/replan semantics')
    selected = next_online_q.masked_fill(~next_valid_mask, -torch.inf).argmax(dim=1)
    selected_q = next_target_q.gather(1, selected[:, None]).squeeze(1)
    bootstrap = torch.where(terminated, torch.zeros_like(selected_q), selected_q)
    return reward + discount * bootstrap


def shaped_reward(new_area_units, revisit_units, duration_units, blocked,
                  success, phi_before, phi_after, discount, terminated):
    """Example weights only; tune on validation maps. Phi is a full-state potential.

    new_area_units counts only newly covered reachable service area.
    revisit_units counts actual travel overlap, not turning in place or standing.
    phi_after must come from the actual next state, including target changes.
    """
    next_phi = 0.0 if terminated else phi_after
    return (new_area_units - .02 * revisit_units - .01 * duration_units
            - 2.0 * float(blocked) + 10.0 * float(success)
            + .2 * (discount * next_phi - phi_before))


def reference_checks():
    network = CoverageQNet().eval()
    assert sum(p.numel() for p in network.parameters()) == 32644
    assert network(torch.zeros(1, 3, 9, 9), torch.zeros(1, 8)).shape == (1, 4)
    q = torch.tensor([[1., 20., 3., 4.], [1., 2., 3., 4.]])
    target = torch.tensor([[10., 200., 30., 40.], [10., 20., 30., 40.]])
    mask = torch.tensor([[True, False, True, True], [False, False, False, False]])
    # First row can represent a collector truncation: bootstrap persists.
    # Second row is terminal: no bootstrap, including when all actions masked.
    y = double_dqn_target(torch.tensor([1., 1.]), torch.tensor([False, True]),
                          .99, q, target, mask)
    torch.testing.assert_close(y, torch.tensor([40.6, 1.]))
    assert greedy_safe_action(q[0], mask[0]) == 3
    assert greedy_safe_action(q[1], mask[1]) is None
    assert greedy_safe_action(torch.tensor([float('nan'), 1., 2., 3.]), mask[0]) is None
    print('Reference checks passed; default network: 32,644 parameters / 130,576 FP32 weight bytes.')


if __name__ == '__main__':
    reference_checks()
