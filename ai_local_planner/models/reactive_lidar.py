"""Observation-only local navigation baseline for independent Levels 4-6 trials.

This is a classical LiDAR gap navigator (not a trained PPO actor). It is useful
as an offline demonstrator and a comparison against learned policies. All
geometry comes from the 365-D observation, never the simulator's ground truth.
"""

import math

import numpy as np


class ReactiveLiDARPolicy:
    def __init__(self, body_radius=.20, margin=.12):
        self.body_radius = body_radius
        self.margin = margin
        self.angles = np.deg2rad(np.arange(0, 360, 2, dtype=np.float64))
        self.candidates = np.deg2rad(np.arange(-90, 91, 5, dtype=np.float64))
        self.unit_points = np.stack((np.cos(self.angles), np.sin(self.angles)), axis=-1)
        self.unit_candidates = np.stack((np.cos(self.candidates), np.sin(self.candidates)), axis=-1)

    def act(self, obs, deterministic=True):
        obs = np.asarray(obs, dtype=np.float64)
        if obs.shape != (365,) or not np.all(np.isfinite(obs)):
            raise ValueError('Expected finite (365,) observation')
        raw = .12 + 11.88 * np.clip(obs[:360], 0., 1.)
        # Robust to isolated 5% min/max ray dropouts.
        scans = np.stack([np.roll(raw, shift) for shift in (-2, -1, 0, 1, 2)])
        ranges = np.median(scans, axis=0)[::2]
        goal_angle = math.atan2(float(obs[361]), float(obs[362]))
        goal_distance = float(obs[360]) * 10.
        current_w = float(obs[364]) * 1.5

        # For a rearward goal, turn in place: the AGV is forward-only.
        if abs(goal_angle) > math.radians(95):
            w = float(np.clip(2.8 * goal_angle - .4 * current_w, -1.5, 1.5))
            return np.asarray([-1., w / 1.5], dtype=np.float32), 0., 0.

        points = self.unit_points * ranges[:, None]
        along = self.unit_candidates @ points.T
        lateral = np.abs(self.unit_candidates[:, 0:1] * points[None, :, 1]
                         - self.unit_candidates[:, 1:2] * points[None, :, 0])
        # Exclude almost-orthogonal points: float32 cos(pi/2) may have a
        # different sign than float64 and create spurious zero-clearance hits.
        blocking = (along > 1e-3) & (lateral < self.body_radius + self.margin)
        free = np.min(np.where(blocking, along, 12.), axis=1)

        # Favor the goal, but choose a repeatable left-side pass when blocked.
        error = np.arctan2(np.sin(self.candidates - goal_angle),
                           np.cos(self.candidates - goal_angle))
        score = (3.0 * np.cos(error) - .35 * np.abs(self.candidates)
                 + 1.5 * np.clip(free - .45, 0., 1.5)
                 + .015 * np.sin(self.candidates))
        score[free < .45] -= 8.
        choice = int(np.argmax(score))
        desired = float(self.candidates[choice])
        path_free = float(free[choice])
        w = float(np.clip(3.0 * desired - .4 * current_w, -1.5, 1.5))

        # Limit speed until aligned and while close to obstacles (including
        # the command delay and acceleration-limited stopping distance).
        safe_distance = max(0., path_free - .32)
        speed = min(.30, .8 * safe_distance, max(.025, .65 * (goal_distance - .16)))
        speed *= max(0., math.cos(desired)) ** 2
        if abs(desired) > 1.0:
            speed = 0.
        return np.asarray([2. * speed / .35 - 1., w / 1.5], dtype=np.float32), 0., 0.


class CrossingObstaclePolicy:
    """Conservative forward lane and yield controller for moving crossings.

    Designed for controlled Level 6 benchmark maps, not a general autonomous
    navigator. Uses only the current noisy 365-D observation, no map labels.
    """

    def __init__(self, lookahead=1.5, half_width=.65):
        self.lookahead = lookahead
        self.half_width = half_width
        degrees = np.deg2rad(np.arange(360, dtype=np.float64))
        self.cos = np.cos(degrees)
        self.sin = np.sin(degrees)

    def act(self, obs, deterministic=True):
        obs = np.asarray(obs, dtype=np.float64)
        if obs.shape != (365,) or not np.isfinite(obs).all():
            raise ValueError('Expected finite (365,) observation')
        scan = .12 + 11.88 * np.clip(obs[:360], 0., 1.)
        # Discard isolated ray failures before checking the swept safety lane.
        scan = np.median(np.stack([np.roll(scan, s) for s in (-2, -1, 0, 1, 2)]), axis=0)
        x = scan * self.cos
        y = scan * self.sin
        blocked = np.any((x > .0) & (x < self.lookahead) & (np.abs(y) < self.half_width))

        heading = math.atan2(float(obs[361]), float(obs[362]))
        measured_w = float(obs[364]) * 1.5
        w_cmd = float(np.clip(2.8 * heading - .45 * measured_w, -1.5, 1.5))
        distance = float(obs[360]) * 10.
        speed = min(.30, max(0., .65 * (distance - .16)))
        speed *= max(0., math.cos(heading)) ** 2
        if blocked or abs(heading) > .7:
            speed = 0.
        return np.asarray([2. * speed / .35 - 1., w_cmd / 1.5], dtype=np.float32), 0., 0.
