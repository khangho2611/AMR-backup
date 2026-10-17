"""Batched ONNX-exportable implementation of the LiDAR gap baseline.

This component is rule based and is NOT PPO; it provides an independent
reference implementation to compare against learned ActorCritic checkpoints.
"""

import math

import torch
from torch import nn


class ReactiveONNXPolicy(nn.Module):
    """Float32 [N,365] -> physical cmd_vel [N,2]."""

    def __init__(self, margin: float = .36):
        super().__init__()
        if not 0. <= margin <= 1.:
            raise ValueError('Inflation margin must lie in [0,1.0] metres')
        self.inflation = .20 + margin
        angles = torch.arange(0, 360, 2, dtype=torch.float32) * math.pi / 180.
        candidates = torch.arange(-90, 91, 5, dtype=torch.float32) * math.pi / 180.
        self.register_buffer('beam_x', torch.cos(angles))
        self.register_buffer('beam_y', torch.sin(angles))
        self.register_buffer('candidate_angles', candidates)
        self.register_buffer('candidate_x', torch.cos(candidates))
        self.register_buffer('candidate_y', torch.sin(candidates))

    def forward(self, obs: torch.Tensor,
                inflation_override: torch.Tensor | None = None) -> torch.Tensor:
        # Observation validation is the responsibility of the runtime guard.
        raw = .12 + 11.88 * obs[..., :360].clamp(0., 1.)
        stack = torch.stack([torch.roll(raw, shifts=s, dims=-1)
                             for s in (-2, -1, 0, 1, 2)], dim=-1)
        # Five-way median removes isolated min-range/max-range dropouts.
        # TopK is supported by ONNX Opset 14; aten::median is not.
        ranges = torch.topk(stack, k=3, dim=-1, largest=False).values[..., 2][..., ::2]
        px = ranges * self.beam_x
        py = ranges * self.beam_y
        along = (self.candidate_x[None, :, None] * px[:, None, :] +
                 self.candidate_y[None, :, None] * py[:, None, :])
        lateral = torch.abs(self.candidate_x[None, :, None] * py[:, None, :] -
                            self.candidate_y[None, :, None] * px[:, None, :])
        inflation = (self.inflation if inflation_override is None
                     else inflation_override[:, None, None])
        block = (along > 1e-3) & (lateral < inflation)
        free = torch.where(block, along, torch.full_like(along, 12.)).amin(dim=-1)

        heading = torch.atan2(obs[:, 361], obs[:, 362])
        # ORT may map atan2(+0,-1) to -pi due signed-zero differences.
        heading = torch.where((torch.abs(obs[:, 361]) < 1e-7) & (obs[:, 362] < 0.),
                              torch.full_like(heading, math.pi), heading)
        measured_w = obs[:, 364] * 1.5
        goal_distance = obs[:, 360] * 10.
        error = torch.atan2(torch.sin(self.candidate_angles[None, :] - heading[:, None]),
                            torch.cos(self.candidate_angles[None, :] - heading[:, None]))
        score = (3. * torch.cos(error) - .35 * torch.abs(self.candidate_angles)[None, :]
                 + 1.5 * (free - .45).clamp(0., 1.5)
                 + .015 * torch.sin(self.candidate_angles)[None, :])
        score = score - torch.where(free < .45, 8., 0.)
        choice = score.argmax(dim=-1, keepdim=True)
        desired = self.candidate_angles[choice[:, 0]]
        path_free = free.gather(-1, choice)[:, 0]

        turn_w = (3. * desired - .4 * measured_w).clamp(-1.5, 1.5)
        safe = (path_free - .32).clamp(min=0.)
        goal_speed = (.65 * (goal_distance - .16)).clamp(min=.025)
        speed = torch.minimum(torch.minimum(torch.full_like(safe, .30), .8 * safe), goal_speed)
        speed = speed * torch.cos(desired).clamp(min=0.) ** 2
        speed = torch.where(torch.abs(desired) > 1., 0., speed)

        reverse_goal = torch.abs(heading) > math.radians(95)
        speed = torch.where(reverse_goal, 0., speed)
        turning = (2.8 * heading - .4 * measured_w).clamp(-1.5, 1.5)
        w = torch.where(reverse_goal, turning, turn_w)
        return torch.stack((speed, w), dim=-1)
