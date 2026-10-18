"""Circular LiDAR Conv1D + 5-variable goal/velocity MLP PPO policy."""

import math

import torch
from torch import nn
from torch.distributions import Normal
from torch.nn import functional as F


class ActorCritic(nn.Module):
    def __init__(self, legacy: bool = False):
        super().__init__()
        sectors = 10 if legacy else 30
        self.lidar_net = nn.Sequential(
            nn.Conv1d(1, 16, 7, padding=3, padding_mode="circular"), nn.ReLU(),
            nn.Conv1d(16, 32, 5, stride=2, padding=2), nn.ReLU(),
            nn.Conv1d(32, 32, 5, stride=2, padding=2), nn.ReLU(),
            # 360 -> 180 -> 90 -> 30 sectors (12 degrees per sector).
            # Legacy support is used only for explicit historical exports/migration.
            nn.AvgPool1d(kernel_size=9 if legacy else 3,
                         stride=9 if legacy else 3), nn.Flatten(),
            nn.Linear(32 * sectors, 128), nn.ReLU(),
        )
        self.goal_net = nn.Sequential(nn.Linear(5, 32), nn.Tanh(),
                                      nn.Linear(32, 32), nn.Tanh())
        self.fusion = nn.Sequential(nn.Linear(160, 128), nn.ReLU(),
                                    nn.Linear(128, 64 if legacy else 128), nn.ReLU())
        self.actor = nn.Linear(64 if legacy else 128, 2)
        self.critic = nn.Linear(64 if legacy else 128, 1)
        self.log_std = nn.Parameter(torch.full((2,), -0.7))
        # Start approximately stationary, so initial random actions are gradual.
        nn.init.zeros_(self.actor.weight)
        nn.init.zeros_(self.actor.bias)


    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if not torch.onnx.is_in_onnx_export() and obs.shape[-1] != 365:
            raise ValueError("Expected observation[...,365]")
        lidar = self.lidar_net(obs[..., :360].unsqueeze(-2))
        goal = self.goal_net(obs[..., 360:])
        features = self.fusion(torch.cat((lidar, goal), dim=-1))
        return self.actor(features), self.critic(features).squeeze(-1)

    def value(self, obs: torch.Tensor) -> torch.Tensor:
        return self.forward(obs)[1]

    def sample(self, obs: torch.Tensor):
        mean, value = self(obs)
        dist = Normal(mean, self.log_std.clamp(-5., 1.).exp())
        raw = dist.rsample()
        action = torch.tanh(raw)
        return action, self._log_prob(dist, raw), value

    @staticmethod
    def _log_prob(dist: Normal, raw: torch.Tensor) -> torch.Tensor:
        # Stable log(1-tanh(raw)^2) Jacobian for the squashed Gaussian.
        log_jacobian = 2. * (math.log(2.) - raw - F.softplus(-2. * raw))
        return (dist.log_prob(raw) - log_jacobian).sum(dim=-1)

    def evaluate(self, obs: torch.Tensor, actions: torch.Tensor):
        mean, value = self(obs)
        dist = Normal(mean, self.log_std.clamp(-5., 1.).exp())
        # The tanh inversion is numerically well conditioned for |a|<1.
        safe = actions.clamp(-1 + 1e-6, 1 - 1e-6)
        raw = torch.atanh(safe)
        log_prob = self._log_prob(dist, raw)
        # Base Gaussian entropy is a proxy (squashed entropy has no simple form).
        return log_prob, dist.entropy().sum(dim=-1), value


class ContextualResidualActorCritic(ActorCritic):
    """One ActorCritic with one context-gated *correction*, one actor output.

    All inputs are the same 365 floats. There are no external controllers or
    scene IDs at inference. Context weights were supervised on simulator maps;
    this cannot be represented as a newly trained, pure PPO policy.
    """

    def __init__(self):
        super().__init__()
        from ai_local_planner.models.scene_classifier import SceneClassifier
        self.context_scene = SceneClassifier()
        self.correction = nn.Sequential(nn.Linear(128 + 72 + 5, 192), nn.ReLU(),
                                        nn.Linear(192, 128), nn.ReLU(),
                                        nn.Linear(128, 2))
        # Exact baseline action at initialization even when scene confidence is 1.
        nn.init.zeros_(self.correction[-1].weight)
        nn.init.zeros_(self.correction[-1].bias)

    def freeze_pretrained(self):
        for name, parameter in self.named_parameters():
            parameter.requires_grad_(name.startswith('correction.'))

    def context_probability(self, obs: torch.Tensor) -> torch.Tensor:
        probability = self.context_scene(obs).softmax(dim=-1)[..., 3]
        # Two-sided odds: p=.05 -> gain=.5; p>.3 -> gain~1;
        # p<.005 -> near zero. Using LiDAR/goal only, no oracle level IDs.
        numerator = probability.square()
        denominator = numerator + ((1. - probability) * (.05 / .95)).square()
        return numerator / denominator.clamp_min(1e-12)

    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if not torch.onnx.is_in_onnx_export() and obs.shape[-1] != 365:
            raise ValueError('Expected observation[...,365]')
        lidar = self.lidar_net(obs[..., :360].unsqueeze(-2))
        goal = self.goal_net(obs[..., 360:])
        features = self.fusion(torch.cat((lidar, goal), dim=-1))
        pooled = F.avg_pool1d(obs[..., :360].unsqueeze(-2), 5, 5).flatten(-2)
        residual_input = torch.cat((features, pooled, obs[..., 360:]), dim=-1)
        gain = self.context_probability(obs).unsqueeze(-1)
        mean = self.actor(features) + gain * self.correction(residual_input)
        return mean, self.critic(features).squeeze(-1)


class ConservativeContextualResidualActorCritic(ContextualResidualActorCritic):
    """Versioned context gate: zero residual where L4 evidence is very weak.

    Registering a buffer differentiates new checkpoints from the historical
    context-gate experiment so old saved gate metrics remain reproducible.
    """

    def __init__(self):
        super().__init__()
        self.register_buffer('gate_min_probability', torch.tensor(.01))

    def context_probability(self, obs: torch.Tensor) -> torch.Tensor:
        probability = self.context_scene(obs).softmax(dim=-1)[..., 3]
        return ((probability - self.gate_min_probability) / .09).clamp(0., 1.)


class DirectionalContextualResidualActorCritic(ConservativeContextualResidualActorCritic):
    """Versioned high-resolution flank-aware correction, still one actor head.

    Retains the frozen 30-sector PPO backbone and observation-only context
    gate. Min/mean 5-ray bins plus directional clearances reach the *residual*
    so a small flank return need not vanish inside mean pooling. As with the
    parent, the scene classifier was trained on simulator-specific geometry.
    """

    def __init__(self):
        super().__init__()
        self.register_buffer('directional_pool_version', torch.tensor(1))
        self.correction = nn.Sequential(
            nn.Linear(128 + 144 + 6 + 5, 256), nn.ReLU(),
            nn.Linear(256, 128), nn.ReLU(), nn.Linear(128, 2))
        nn.init.zeros_(self.correction[-1].weight)
        nn.init.zeros_(self.correction[-1].bias)

    @staticmethod
    def directional_clearances(scan: torch.Tensor) -> torch.Tensor:
        """Six normalized min ranges, degrees CCW from the robot's front."""
        front = torch.cat((scan[..., 335:], scan[..., :26]), dim=-1).amin(-1)
        left_shoulder = scan[..., 25:66].amin(-1)
        right_shoulder = scan[..., 295:336].amin(-1)
        left_flank = scan[..., 65:116].amin(-1)
        right_flank = scan[..., 245:296].amin(-1)
        global_min = scan.amin(-1)
        return torch.stack((front, left_shoulder, right_shoulder,
                            left_flank, right_flank, global_min), dim=-1)

    @staticmethod
    def sustained_flank_clearance_m(scan: torch.Tensor) -> torch.Tensor:
        """Nearest *contiguous* five-ray flank return, in physical metres.

        A raw minimum is almost always an isolated 0.12 m dropout when each
        LiDAR ray has a 5% failure probability. Taking the minimum over sliding
        five-ray maxima requires five adjacent returns to confirm an obstacle;
        unlike a whole-flank 15th percentile, it still catches narrow objects
        that occupy only five consecutive degrees. MaxPool/ReduceMin also map
        to standard ONNX operations and do not add checkpoint parameters.
        """
        left = F.max_pool1d(scan[..., 65:116].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        right = F.max_pool1d(scan[..., 245:296].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        return .12 + 11.88 * torch.minimum(left, right)

    @staticmethod
    def sustained_flank_distances_m(scan: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Robust left/right flank & shoulder ranges, excluding isolated LiDAR dropouts."""
        left = F.max_pool1d(scan[..., 25:120].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        right = F.max_pool1d(scan[..., 240:335].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        return .12 + 11.88 * left, .12 + 11.88 * right

    def effective_context_gain(self, obs: torch.Tensor) -> torch.Tensor:
        """Sustain residual for unilateral flank/shoulder exposure with a clear exit side.

        Clearance is measured from the LiDAR origin, not the chassis edge.
        Symmetric narrow corridors (L3) have both flanks nearby (far - near < 0.15 m);
        indiscriminately engaging the L4 residual there stalls the robot.
        Require unilateral opening (far - near > 0.15 m) and front clearance > 0.80 m
        (to avoid interfering with L3 90-degree corner wall).
        """
        left, right = self.sustained_flank_distances_m(obs[..., :360])
        near, far = torch.minimum(left, right), torch.maximum(left, right)
        proximity = ((.45 - near) / .20).clamp(0., 1.)
        unilateral = ((far - near - .15) / .20).clamp(0., 1.)
        front_arc = torch.cat((obs[..., 345:360], obs[..., :16]), dim=-1)
        robust_front = F.max_pool1d(front_arc.unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        front_not_corner = ((.12 + 11.88 * robust_front - .80) / .30).clamp(0., 1.)
        flank_risk = proximity * unilateral * front_not_corner
        return torch.maximum(self.context_probability(obs), flank_risk)

    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if not torch.onnx.is_in_onnx_export() and obs.shape[-1] != 365:
            raise ValueError('Expected observation[...,365]')
        scan = obs[..., :360]
        lidar = self.lidar_net(scan.unsqueeze(-2))
        goal = self.goal_net(obs[..., 360:])
        features = self.fusion(torch.cat((lidar, goal), dim=-1))
        rays = scan.unsqueeze(-2)
        min_pooled = -F.max_pool1d(-rays, 5, 5).flatten(-2)
        avg_pooled = F.avg_pool1d(rays, 5, 5).flatten(-2)
        residual_input = torch.cat((features, min_pooled, avg_pooled,
                                    self.directional_clearances(scan),
                                    obs[..., 360:]), dim=-1)
        gain = self.effective_context_gain(obs).unsqueeze(-1)
        mean = self.actor(features) + gain * self.correction(residual_input)
        return mean, self.critic(features).squeeze(-1)


def upgrade_contextual_to_directional(weights: dict) -> dict:
    """Losslessly embed an existing context residual into the wider actor.

    New min and clearance channels start with zero input weights; the old
    average-pool residual and its learned actor behavior remain functional.
    This avoids restarting Level 1–5 retention from a zeroed correction head.
    """
    if 'directional_pool_version' in weights:
        return weights
    if 'correction.0.weight' not in weights or 'gate_min_probability' not in weights:
        raise ValueError('Expected a conservative contextual checkpoint')
    expanded = DirectionalContextualResidualActorCritic().state_dict()
    for key, value in weights.items():
        if key not in ('correction.0.weight', 'correction.0.bias',
                       'correction.2.weight', 'correction.2.bias'):
            expanded[key] = value
    old_first = weights['correction.0.weight']
    if old_first.shape != (192, 205):
        raise ValueError(f'Unexpected pre-upgrade correction shape: {old_first.shape}')
    expanded['correction.0.weight'].zero_()
    expanded['correction.0.bias'].zero_()
    expanded['correction.0.weight'][:192, :128] = old_first[:, :128]
    expanded['correction.0.weight'][:192, 200:272] = old_first[:, 128:200]
    expanded['correction.0.weight'][:192, 278:] = old_first[:, 200:]
    expanded['correction.0.bias'][:192] = weights['correction.0.bias']
    expanded['correction.2.weight'].zero_()
    expanded['correction.2.bias'].copy_(weights['correction.2.bias'])
    expanded['correction.2.weight'][:, :192] = weights['correction.2.weight']
    return expanded


def is_legacy_state_dict(weights: dict) -> bool:
    """Recognize historical 10-sector/64-fusion checkpoints by tensor sizes."""
    return weights["lidar_net.8.weight"].shape[1] == 32 * 10


def migrate_legacy_state_dict(weights: dict) -> dict:
    """Embed the old 10-sector actor in the 30-sector network without drift.

    Nine-sample averaging equals averaging three successive three-sample pools.
    Duplicating each legacy weight across those sectors with /3 preserves it.
    New fusion channels initially have zero impact on actor/critic outputs.
    """
    if not is_legacy_state_dict(weights):
        return weights
    target = ActorCritic().state_dict()
    for name, value in weights.items():
        if name == "lidar_net.8.weight":
            target[name] = (value.reshape(128, 32, 10)
                            .repeat_interleave(3, dim=2).div(3)
                            .reshape(128, 32 * 30))
        elif name in ("fusion.2.weight", "fusion.2.bias"):
            target[name].zero_()
            target[name][:64] = value
        elif name in ("actor.weight", "critic.weight"):
            target[name].zero_()
            target[name][:, :64] = value
        else:
            if target[name].shape != value.shape:
                raise ValueError(f"Cannot migrate incompatible legacy parameter: {name}")
            target[name] = value
    return target


class MeanPolicy(nn.Module):
    """Deterministic ONNX contract with an observation-only near-field shield."""

    def __init__(self, network: ActorCritic, v_max: float = .35, w_max: float = 1.5):
        super().__init__()
        self.network = network
        self.v_max, self.w_max = v_max, w_max

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        mean, _ = self.network(obs)
        action = torch.tanh(mean)
        v = (action[..., 0] + 1.) * (.5 * self.v_max)
        w = action[..., 1] * self.w_max
        # The simulator corrupts 5% of LiDAR rays with 0.12 m minimum-range
        # readings. The global raw minimum is therefore unusable for braking.
        # A hazard is confirmed by five *consecutive* short returns, including
        # rays straddling the 359 -> 0 degree scan boundary.
        scan = obs[..., :360]
        wrapped = torch.cat((scan[..., -4:], scan), dim=-1)
        windows = F.max_pool1d(wrapped.unsqueeze(-2), 5, stride=1).squeeze(-2)
        nearest_confirmed_m = .12 + 11.88 * windows.amin(dim=-1)
        danger = nearest_confirmed_m < .22
        v = torch.where(danger, v.clamp(max=.08), v)

        # Prefer turning away from the nearest side. If the hazard is straight
        # ahead or symmetric, follow the goal bearing. No external scene labels,
        # recurrent state or changes to the 365 -> 2 ONNX contract are needed.
        left = F.max_pool1d(scan[..., 25:155].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        right = F.max_pool1d(scan[..., 205:335].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        signed_opening = right - left  # positive: left obstacle closer -> right turn
        goal_direction = torch.where(obs[..., 361] >= 0., torch.ones_like(w), -torch.ones_like(w))
        direction = torch.where(signed_opening.abs() > (.03 / 11.88),
                                torch.where(signed_opening > 0., -torch.ones_like(w),
                                            torch.ones_like(w)), goal_direction)
        rescue = direction * torch.maximum(w.abs(), torch.full_like(w, .6))
        # Preserve an already-correct steering command, including its strength.
        should_rescue = danger & (w * direction < .6)
        w = torch.where(should_rescue, rescue, w)

        # A narrow corridor has two continuous, approximately parallel walls.
        # The frozen actor can occasionally drift against a wall when the
        # wheel-slip randomization is adverse, or stall after a right-angle
        # turn even though the path and goal heading are clear. Compensate
        # using only the observation, without retraining or scene-level IDs.
        left_wall = F.max_pool1d(scan[..., 75:106].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        right_wall = F.max_pool1d(scan[..., 255:286].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        front_scan = torch.cat((scan[..., -20:], scan[..., :21]), dim=-1)
        front_clear = F.max_pool1d(front_scan.unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        left_m = .12 + 11.88 * left_wall
        right_m = .12 + 11.88 * right_wall
        front_m = .12 + 11.88 * front_clear
        # Predictive front-cone speed envelope for the 100 ms UART delay and
        # 0.5 m/s² drive deceleration. Braking only at 0.22 m is too late at
        # 0.3 m/s; use a gradual bound as an obstacle enters +/-20 degrees.
        # Five adjacent rays reject artificial single-ray minimum dropouts.
        approach_speed_limit = ((front_m - .30) * .6).clamp(min=.08, max=.35)
        v = torch.minimum(v, approach_speed_limit)
        # When passing a single obstacle the actor can begin steering back
        # toward the goal before its flank has cleared. A unilateral threat
        # within the forward +/-55-degree arcs needs a sustained turn away,
        # even at low speed, rather than repeated forward creeping.
        left_approach = F.max_pool1d(scan[..., 7:56].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        right_approach = F.max_pool1d(scan[..., 304:353].unsqueeze(-2), 5, 1).amin(-1).squeeze(-1)
        left_approach_m = .12 + 11.88 * left_approach
        right_approach_m = .12 + 11.88 * right_approach
        turn_right = ((left_approach_m < .85) & (right_approach_m > 1.25)
                      & (front_m < 1.2))
        turn_left = ((right_approach_m < .85) & (left_approach_m > 1.25)
                     & (front_m < 1.2))
        w = torch.where(turn_right, -torch.maximum(w.abs(), torch.full_like(w, .65)), w)
        w = torch.where(turn_left, torch.maximum(w.abs(), torch.full_like(w, .65)), w)
        corridor = ((left_m > .22) & (right_m > .22) &
                    (left_m < .55) & (right_m < .55) & (front_m > .8))
        lateral_error = left_m - right_m
        # Positive angular velocity is leftward; steer toward the more open
        # flank while limiting the correction to a low angular velocity.
        correction = (1.3 * lateral_error).clamp(min=-.35, max=.35)
        correct_lateral = corridor & (lateral_error.abs() > .08)
        w = torch.where(correct_lateral, (w + correction).clamp(-1.5, 1.5), w)
        # Preserve progress when facing the goal on a straight, unobstructed
        # corridor; a lower speed of 0.10 m/s is well within the 0.35 limit.
        go_straight = corridor & (obs[..., 362] > .90) & (front_m > 1.25)
        v = torch.where(go_straight, v.clamp(min=.10), v)
        return torch.stack((v, w), dim=-1)
