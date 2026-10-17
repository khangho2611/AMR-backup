"""Geometric teachers for generating Level 1-3 imitation trajectories.

The Level 2 waypoint teacher uses simulator geometry *only for offline labels*.
The deployed policy still receives only the 365-dimensional observation.
Actions respect the normalized [-1,1] policy contract.
"""

import math

import numpy as np


def goal_tracking_action(obs: np.ndarray) -> np.ndarray:
    heading = math.atan2(float(obs[361]), float(obs[362]))
    distance = float(obs[360]) * 10.
    measured_w = float(obs[364]) * 1.5
    w_cmd = float(np.clip(2.8 * heading - 0.45 * measured_w, -1.5, 1.5))
    # Reduce speed on turns and near the goal to avoid goal overshoot.
    v_cmd = min(.32, max(.025, .65 * max(0., distance - .16)))
    v_cmd *= max(.02, math.cos(heading))
    return np.asarray([2. * v_cmd / .35 - 1., w_cmd / 1.5], dtype=np.float32)


class SingleObstacleTeacher:
    """Stateful waypoint oracle for the one-circle Level 2 curriculum."""

    def __init__(self, obstacle, goal_xy, robot_radius: float = .20):
        # Pick one consistent side to avoid contradictory BC action labels.
        lateral = obstacle.y + obstacle.radius + robot_radius + .35
        self.waypoints = [
            np.asarray([obstacle.x - 1., lateral], dtype=np.float64),
            np.asarray([obstacle.x + 1., lateral], dtype=np.float64),
            np.asarray(goal_xy, dtype=np.float64),
        ]
        self.index = 0

    def act(self, obs: np.ndarray, pose_xytheta) -> np.ndarray:
        pose = np.asarray(pose_xytheta, dtype=np.float64)
        while (self.index < 2 and
               np.linalg.norm(self.waypoints[self.index] - pose[:2]) < .22):
            self.index += 1
        delta = self.waypoints[self.index] - pose[:2]
        delta_theta = math.atan2(delta[1], delta[0]) - pose[2]
        proxy = obs.copy()
        proxy[360] = min(np.linalg.norm(delta) / 10., 1.)
        proxy[361], proxy[362] = math.sin(delta_theta), math.cos(delta_theta)
        return goal_tracking_action(proxy)


class RightAngleCorridorTeacher:
    """Privileged offline teacher following the centreline of Level 3's L corridor.

    The corner waypoint must be reached *before* making the 90-degree turn:
    the 0.7 m corridor leaves only 0.15 m nominal lateral margin per side.
    The teacher sees simulator pose for training labels; the actor never does.
    """

    def __init__(self, goal_xy, corner_xy=(3.65, 1.85)):
        self.corner = np.asarray(corner_xy, dtype=np.float64)
        self.goal = np.asarray(goal_xy, dtype=np.float64)
        self.passed_corner = False

    def act(self, obs: np.ndarray, pose_xytheta) -> np.ndarray:
        pose = np.asarray(pose_xytheta, dtype=np.float64)
        if not self.passed_corner and np.linalg.norm(self.corner - pose[:2]) < .075:
            self.passed_corner = True
        target = self.goal if self.passed_corner else self.corner
        delta = target - pose[:2]
        error = math.atan2(delta[1], delta[0]) - pose[2]
        proxy = obs.copy()
        proxy[360] = min(float(np.linalg.norm(delta)) / 10., 1.)
        proxy[361], proxy[362] = math.sin(error), math.cos(error)
        return goal_tracking_action(proxy)
