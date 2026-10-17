"""GAE with correct differentiation between termination and time truncation."""

import numpy as np
import torch


class RolloutBuffer:
    def __init__(self):
        self.clear()

    def clear(self):
        self.data: list[tuple] = []
        self.reference_actions: list[np.ndarray | None] = []

    def add(self, obs, action, logp, reward, value, next_value,
            terminated: bool, truncated: bool, reference_action=None):
        self.data.append((np.asarray(obs, np.float32).copy(),
                          np.asarray(action, np.float32).copy(), float(logp),
                          float(reward), float(value), float(next_value),
                          bool(terminated), bool(truncated)))
        if reference_action is None:
            self.reference_actions.append(None)
        else:
            target = np.asarray(reference_action, dtype=np.float32)
            if target.shape != (2,) or not np.isfinite(target).all() or np.any(np.abs(target) > 1.00001):
                raise ValueError("Reference action must be a finite normalized [2] vector")
            self.reference_actions.append(target.copy())

    def reference_tensor(self, device: torch.device) -> torch.Tensor:
        if len(self.reference_actions) != len(self.data) or not self.data:
            raise ValueError("Missing reference actions for rollout")
        if any(a is None for a in self.reference_actions):
            raise ValueError("Teacher anchors must be collected for every transition")
        return torch.as_tensor(np.stack(self.reference_actions),
                               dtype=torch.float32, device=device)

    def finish_last(self, next_value: float):
        """Fill bootstrap value using the subsequent action's already computed V(s)."""
        if not self.data:
            raise ValueError("Empty rollout")
        last = self.data[-1]
        if last[6] or last[7]:
            raise ValueError("Cannot bootstrap completed episode")
        self.data[-1] = (*last[:5], float(next_value), *last[6:])

    def tensors(self, gamma: float, gae_lambda: float, device: torch.device):
        if not self.data:
            raise ValueError("Cannot train on empty rollout")
        observations, actions, logps, rewards, values, next_values, terminated, truncated = (
            np.asarray(component) for component in zip(*self.data))
        adv = np.zeros_like(rewards, dtype=np.float32)
        gae = 0.
        for t in reversed(range(len(rewards))):
            bootstrap = 0. if terminated[t] else 1.
            cont = 0. if (terminated[t] or truncated[t]) else 1.
            delta = rewards[t] + gamma * bootstrap * next_values[t] - values[t]
            gae = delta + gamma * gae_lambda * cont * gae
            adv[t] = gae
        returns = adv + values
        as_t = lambda data: torch.as_tensor(data, dtype=torch.float32, device=device)
        return (as_t(observations), as_t(actions), as_t(logps),
                as_t(adv), as_t(returns))
