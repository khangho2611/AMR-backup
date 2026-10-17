"""Self-contained PPO clipped objective + minibatches, GAE and checkpoints."""

from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from ai_local_planner.models.actor_critic import (ActorCritic, is_legacy_state_dict,
                                                  migrate_legacy_state_dict)
from ai_local_planner.trainers.rollout_buffer import RolloutBuffer


class PPOAgent:
    def __init__(self, config: dict, device: str = "auto"):
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        self.config = config
        self.network = ActorCritic().to(self.device)
        self.optimizer = torch.optim.Adam(self.network.parameters(),
                                          lr=config["learning_rate"], eps=1e-5)
        self.reference_network = None
        self.reference_experts = None
        self.reference_coef = 0.

    def set_reference_policy(self, checkpoint: str | Path, coefficient: float):
        """Keep PPO close to a verified demonstration policy during fine-tuning."""
        if coefficient <= 0:
            raise ValueError("Reference coefficient must be positive")
        path = Path(checkpoint)
        if path.suffix.lower() == ".json":
            # Scene information is available in the simulator during *training*.
            # Direct expert dispatch avoids the supervisor's 5-frame calibration
            # and never introduces a scene label into the student's observation.
            from ai_local_planner.models.locked_scene_onnx_agent import LockedSceneONNXAgent
            supervisor = LockedSceneONNXAgent(path)
            self.reference_experts = supervisor.experts
            self.reference_network = None
        else:
            state = torch.load(path, map_location=self.device, weights_only=True)
            reference = ActorCritic().to(self.device)
            reference.load_state_dict(migrate_legacy_state_dict(state["model"]))
            reference.eval().requires_grad_(False)
            self.reference_network = reference
            self.reference_experts = None
        self.reference_coef = coefficient

    @torch.no_grad()
    def reference_action(self, obs: np.ndarray, level: int) -> np.ndarray | None:
        """Cache one normalized teacher action per transition, per actual level."""
        if self.reference_experts is not None:
            if level < 1 or level > len(self.reference_experts):
                raise ValueError(f"No reference teacher for Level {level}")
            action, _, _ = self.reference_experts[level - 1].act(obs)
            return np.asarray(action, np.float32)
        if self.reference_network is not None:
            x = torch.as_tensor(obs[None, :], dtype=torch.float32, device=self.device)
            return torch.tanh(self.reference_network(x)[0])[0].cpu().numpy()
        return None

    @torch.no_grad()
    def act(self, obs: np.ndarray, deterministic: bool = False):
        x = torch.as_tensor(obs[None, :], dtype=torch.float32, device=self.device)
        if deterministic:
            mean, val = self.network(x)
            return torch.tanh(mean)[0].cpu().numpy(), float(val.item()), 0.
        action, logp, val = self.network.sample(x)
        return action[0].cpu().numpy(), float(val.item()), float(logp.item())

    @torch.no_grad()
    def value(self, obs: np.ndarray) -> float:
        x = torch.as_tensor(obs[None, :], dtype=torch.float32, device=self.device)
        return float(self.network.value(x).item())

    def update(self, buffer: RolloutBuffer, epochs: int | None = None,
               batch_size: int | None = None) -> dict:
        p = self.config
        obs, acts, old_logp, advantages, returns = buffer.tensors(
            p["gamma"], p["gae_lambda"], self.device)
        teacher_actions = (buffer.reference_tensor(self.device)
                           if self.reference_experts is not None else None)
        advantages = (advantages - advantages.mean()) / (advantages.std(unbiased=False) + 1e-8)
        batch_size = min(batch_size or p["batch_size"], len(acts))
        metrics = []
        early_stopped = False
        for _ in range(epochs or p["epochs_per_update"]):
            for inds in torch.randperm(len(acts), device=self.device).split(batch_size):
                logp, entropy, values = self.network.evaluate(obs[inds], acts[inds])
                log_ratio = logp - old_logp[inds]
                ratio = log_ratio.exp()
                with torch.no_grad():
                    # Non-negative Schulman KL estimator. Stop before the next
                    # optimizer step if the actor has drifted too far.
                    approx_kl = float(((ratio - 1.) - log_ratio).mean())
                if p.get("target_kl") and approx_kl > 1.5 * p["target_kl"]:
                    early_stopped = True
                    break
                surrogate1 = ratio * advantages[inds]
                surrogate2 = ratio.clamp(1. - p["clip_range"],
                                         1. + p["clip_range"]) * advantages[inds]
                actor_loss = -torch.minimum(surrogate1, surrogate2).mean()
                # BC initializes the actor but leaves the critic untrained.
                # Huber prevents its initially huge errors from overwhelming
                # the shared LiDAR/goal encoder and erasing the BC policy.
                critic_loss = F.smooth_l1_loss(values, returns[inds])
                loss = (actor_loss + p["value_loss_coef"] * critic_loss
                        - p["entropy_coef"] * entropy.mean())
                anchor_mse = 0.
                if self.reference_network is not None or teacher_actions is not None:
                    with torch.no_grad():
                        target_actions = (teacher_actions[inds] if teacher_actions is not None
                                          else torch.tanh(self.reference_network(obs[inds])[0]))
                    current_actions = torch.tanh(self.network(obs[inds])[0])
                    bc_loss = F.mse_loss(current_actions, target_actions)
                    anchor_mse = float(bc_loss.detach())
                    loss = loss + self.reference_coef * bc_loss
                self.optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.network.parameters(), p["max_grad_norm"])
                self.optimizer.step()
                with torch.no_grad():
                    metrics.append((float(loss), float(actor_loss), float(critic_loss),
                                    approx_kl,
                                    float(((ratio - 1.).abs() > p["clip_range"]).float().mean()),
                                    anchor_mse))
            if early_stopped:
                break
        buffer.clear()
        if not metrics:
            # The first minibatch may exceed target KL if the numerical or
            # checkpoint contract is violated. Report rather than crash.
            return dict(loss=0., actor_loss=0., critic_loss=0.,
                        approx_kl=approx_kl, clip_fraction=0.,
                        reference_action_mse=0., early_stopped=1.)
        means = np.asarray(metrics).mean(axis=0)
        result = dict(zip(("loss", "actor_loss", "critic_loss", "approx_kl",
                           "clip_fraction", "reference_action_mse"),
                          [float(x) for x in means]))
        result["early_stopped"] = float(early_stopped)
        return result

    def save(self, path: str | Path, steps: int, level: int, **metadata):
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"model": self.network.state_dict(),
                    "optimizer": self.optimizer.state_dict(),
                    "steps": steps, "level": level, "metadata": metadata,
                    "architecture": "lidar30_fusion128"}, output)

    def load(self, path: str | Path):
        state = torch.load(path, map_location=self.device, weights_only=True)
        legacy = is_legacy_state_dict(state["model"])
        self.network.load_state_dict(migrate_legacy_state_dict(state["model"]))
        # Adam moment shapes from a 10-sector policy cannot be loaded into the
        # wider layers. Continue fine-tuning with a fresh optimizer after migration.
        if "optimizer" in state and not legacy:
            self.optimizer.load_state_dict(state["optimizer"])
        if legacy:
            state["migrated_from_legacy"] = True
        return state

    def initialize_from(self, path: str | Path):
        """Use pretrained weights as a new PPO run, with fresh Adam and step=0."""
        state = torch.load(path, map_location=self.device, weights_only=True)
        self.network.load_state_dict(migrate_legacy_state_dict(state["model"]))
        return state
