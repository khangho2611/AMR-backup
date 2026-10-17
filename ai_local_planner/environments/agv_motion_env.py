"""Gymnasium 2-D differential-drive AGV with vectorized analytic 360-ray LiDAR.

Actions are normalized [-1,1]^2, observations are (365,) float32. Simulator
uses ground-truth geometry for collision/reward; corrupted LiDAR is policy-only.
"""

from collections import deque
import math

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.scenarios import Circle, Scenario, create_scenario


def point_segment_distance(point: np.ndarray, segments: np.ndarray) -> np.ndarray:
    a = segments[:, :2]
    ab = segments[:, 2:] - a
    fractions = np.clip(np.sum((point - a) * ab, axis=1) /
                        np.maximum(np.sum(ab * ab, axis=1), 1e-12), 0., 1.)
    return np.linalg.norm(point - (a + fractions[:, None] * ab), axis=1)


def raycast(position: np.ndarray, theta: float, walls: np.ndarray,
            obstacles: list[Circle], max_range: float = 12.) -> np.ndarray:
    """Ray/segment and ray/circle intersections. Index 0 points forward."""
    angles = theta + np.deg2rad(np.arange(360, dtype=np.float64))
    rays = np.stack((np.cos(angles), np.sin(angles)), axis=-1)
    result = np.full(360, max_range, dtype=np.float64)
    if len(walls):
        a = walls[:, :2]
        s = walls[:, 2:] - a
        q = a - position
        # Cross(r, s); axes (rays, segments)
        denom = rays[:, None, 0] * s[None, :, 1] - rays[:, None, 1] * s[None, :, 0]
        valid_denom = np.abs(denom) > 1e-10
        safe_denom = np.where(valid_denom, denom, 1.)
        t = (q[None, :, 0] * s[None, :, 1] - q[None, :, 1] * s[None, :, 0]) / safe_denom
        u = (q[None, :, 0] * rays[:, None, 1] - q[None, :, 1] * rays[:, None, 0]) / safe_denom
        candidate = np.where(valid_denom & (t >= 0) & (u >= 0) & (u <= 1), t, np.inf)
        result = np.minimum(result, np.min(candidate, axis=1))
    for circle in obstacles:
        offset = np.array([circle.x, circle.y]) - position
        along = rays @ offset
        perp2 = max(0., float(offset @ offset)) - along ** 2
        hit = (perp2 <= circle.radius ** 2) & (along + circle.radius >= 0)
        half_chord = np.sqrt(np.maximum(0., circle.radius ** 2 - perp2))
        distance = np.maximum(0., along - half_chord)
        result = np.minimum(result, np.where(hit, distance, np.inf))
    return np.clip(result, 0., max_range)


def kinetic_speed_profile(front_scan: np.ndarray, actual_v: float,
                          a_max: float, v_max: float, trigger_m: float = 1.,
                          margin_m: float = .25, scale: float = -3.) -> tuple[float, float, float]:
    """Use true +/-15 degree ranges; return (penalty, d_front, v_safe).

    Ground truth is used only for reward, never injected into the observation.
    """
    scan = np.asarray(front_scan, dtype=np.float64)
    if scan.shape != (360,):
        raise ValueError("Expected a 360-ray scan")
    d_front = float(np.min(np.concatenate((scan[-15:], scan[:16]))))
    v_safe = min(v_max, math.sqrt(2. * a_max * max(0., d_front - margin_m)))
    penalty = (scale * max(0., actual_v - v_safe) if d_front < trigger_m else 0.)
    return float(penalty), d_front, float(v_safe)


class AGVMotionEnv(gym.Env):
    """State, obstacle movement and normalized LiDAR at fixed 10Hz."""

    metadata = {"render_modes": []}

    def __init__(self, level: int = 1, randomize: bool = True,
                 max_steps: int = 600, config: dict | None = None):
        super().__init__()
        self.config = config or load_config()
        self.robot = self.config["robot"]
        self.lidar = self.config["lidar"]
        self.domain = self.config["sim_to_real"]
        self.rewards = self.config["rewards"]
        self.level, self.randomize, self.max_steps = level, randomize, max_steps
        self.action_space = spaces.Box(-1., 1., shape=(2,), dtype=np.float32)
        low = np.zeros(365, dtype=np.float32)
        low[361] = low[362] = low[364] = -1.
        high = np.ones(365, dtype=np.float32)
        self.observation_space = spaces.Box(low, high, dtype=np.float32)
        self._ray_observation = None
        self.scenario: Scenario | None = None

    def set_level(self, level: int):
        if level not in range(1, 7):
            raise ValueError("Curriculum level must be 1..6")
        self.level = level

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self.scenario = create_scenario(self.level, self.np_random)
        self.walls = self.scenario.all_walls()
        self.pose = np.asarray(self.scenario.start, dtype=np.float64)
        self.goal = np.asarray(self.scenario.goal, dtype=np.float64)
        self.v = self.w = 0.
        self._applied = np.zeros(2, dtype=np.float64)
        self._delay = deque([np.zeros(2, dtype=np.float64)], maxlen=1)
        self.steps = 0
        self.noise_sigma = (float(self.np_random.uniform(*self.domain["lidar_noise_sigma"]))
                            if self.randomize else 0.)
        self.wheel_slip = np.array([
            float(self.np_random.choice([-1, 1]) * self.np_random.uniform(*self.domain["traction_slip_range"]))
            if self.randomize else 0. for _ in range(2)])
        self._true_scan = np.full(360, self.lidar["max_range"], dtype=np.float64)
        obs = self._observe()
        return obs, {"level": self.level, "goal": self.goal.copy()}

    def _update_obstacles(self):
        dt = self.robot["dt"]
        for circle in self.scenario.obstacles:
            if circle.vx or circle.vy:
                circle.anchor_x += circle.vx * dt
                circle.anchor_y += circle.vy * dt
                if circle.anchor_y <= .65 or circle.anchor_y >= self.scenario.bounds[1] - .65:
                    circle.vy *= -1.
                    circle.anchor_y = float(np.clip(circle.anchor_y, .65,
                                self.scenario.bounds[1] - .65))
            if self.randomize:
                jitter = self.domain["obstacle_jitter_sigma"]
                circle.x = circle.anchor_x + float(self.np_random.uniform(-jitter, jitter))
                circle.y = circle.anchor_y + float(self.np_random.uniform(-jitter, jitter))
            else:
                circle.x, circle.y = circle.anchor_x, circle.anchor_y

    def _clearance(self) -> float:
        p = self.pose[:2]
        wall_distance = float(np.min(point_segment_distance(p, self.walls)))
        circle_distance = min((float(np.hypot(p[0] - c.x, p[1] - c.y) - c.radius)
                               for c in self.scenario.obstacles), default=np.inf)
        return min(wall_distance, circle_distance)

    def _goal_distance(self) -> float:
        return float(np.linalg.norm(self.goal - self.pose[:2]))

    def _observe(self) -> np.ndarray:
        self._true_scan = raycast(self.pose[:2], self.pose[2], self.walls,
                                  self.scenario.obstacles, self.lidar["max_range"])
        scan = self._true_scan.copy()
        if self.randomize:
            scan += self.np_random.normal(0., self.noise_sigma, size=360)
            mask = self.np_random.random(360) < self.domain["lidar_dropout_rate"]
            scan[mask] = self.np_random.choice([self.lidar["min_range"],
                                                self.lidar["max_range"]], size=int(mask.sum()))
        min_range, max_range = self.lidar["min_range"], self.lidar["max_range"]
        obs = np.empty(365, dtype=np.float32)
        obs[:360] = ((np.clip(scan, min_range, max_range) - min_range) /
                     (max_range - min_range)).astype(np.float32)
        delta = math.atan2(self.goal[1] - self.pose[1], self.goal[0] - self.pose[0]) - self.pose[2]
        obs[360:] = (min(self._goal_distance() / 10., 1.), math.sin(delta), math.cos(delta),
                     np.clip(self.v / self.robot["v_max"], 0., 1.),
                     np.clip(self.w / self.robot["w_max"], -1., 1.))
        return obs

    def step(self, action):
        action = np.asarray(action, dtype=np.float64)
        if action.shape != (2,) or not np.all(np.isfinite(action)):
            raise ValueError("Action must be finite normalized float32 vector (2,)")
        action = np.clip(action, -1., 1.)
        desired = np.array([(action[0] + 1.) * .5 * self.robot["v_max"],
                             action[1] * self.robot["w_max"]])
        # Command sent at t is applied at t+1. Slew limits act on applied commands.
        delayed = self._delay.popleft()
        self._delay.append(desired)
        dt = self.robot["dt"]
        old_v, old_w = self.v, self.w
        old_distance = self._goal_distance()
        dv = self.robot["a_linear_max"] * dt
        dw = self.robot["a_angular_max"] * dt
        self._applied = np.clip(delayed, self._applied - [dv, dw], self._applied + [dv, dw])
        v, w = self._applied
        baseline = self.robot["wheel_base"]
        left = (v - w * baseline / 2.) * (1. + self.wheel_slip[0])
        right = (v + w * baseline / 2.) * (1. + self.wheel_slip[1])
        self.v, self.w = (right + left) / 2., (right - left) / baseline
        # Midpoint integration is accurate for constant twist at 10 Hz.
        mid = self.pose[2] + self.w * dt / 2.
        self.pose[:2] += np.array([math.cos(mid), math.sin(mid)]) * self.v * dt
        self.pose[2] = (self.pose[2] + self.w * dt + math.pi) % (2 * math.pi) - math.pi
        self._update_obstacles()
        self.steps += 1
        # Observe the updated pose before computing reward: preserves the
        # exact policy observation and random-number sequence per transition.
        obs = self._observe()
        clearance = self._clearance()
        distance = self._goal_distance()
        collision = clearance <= self.robot["radius"]
        success = distance < .20 and not collision
        heading_error = math.atan2(self.goal[1] - self.pose[1], self.goal[0] - self.pose[0]) - self.pose[2]
        rw = self.rewards
        speed_penalty, d_front, v_safe = kinetic_speed_profile(
            self._true_scan, self.v, self.robot["a_linear_max"],
            self.robot["v_max"], rw.get("speed_front_trigger_m", 1.),
            rw.get("speed_braking_margin_m", .25),
            rw.get("speed_excess_penalty", -3.))
        components = {
            "progress": rw["progress_scale"] * (old_distance - distance),
            "goal": rw["goal_reached"] if success else 0.,
            "collision": rw["collision_penalty"] if collision else 0.,
            "clearance": rw["clearance_penalty"] * max(0., .35 - clearance),
            "smoothness": (rw["w_smooth_penalty"] * (self.w - old_w) ** 2
                           + rw["v_smooth_penalty"] * (self.v - old_v) ** 2
                           + rw["w_magnitude_penalty"] * abs(self.w)),
            "heading": rw["heading_bonus"] * math.cos(heading_error) * (self.v / self.robot["v_max"]),
            "step": rw["step_penalty"],
            "speed_excess": speed_penalty,
        }
        terminated = bool(collision or success)
        truncated = bool(self.steps >= self.max_steps and not terminated)
        return obs, float(sum(components.values())), terminated, truncated, {
            "success": bool(success), "collision": bool(collision), "clearance_m": clearance,
            "distance_to_goal_m": distance, "reward_components": components,
            "applied_vw": self._applied.copy(), "actual_vw": (self.v, self.w),
            "level": self.level, "steps": self.steps,
            "forward_clearance_m": d_front, "kinetic_safe_speed_mps": v_safe,
        }
