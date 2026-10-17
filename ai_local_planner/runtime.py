"""Read-only inference helper and independent velocity/clearance guard.

Robot side must also retain its hardware E-stop watchdog. This file does not
issue motor commands or bypass the existing AGV safety supervisor.
"""

import hashlib
import json
import math
from pathlib import Path

import numpy as np


def build_observation(raw_lidar_m: np.ndarray, pose_xytheta, goal_xy,
                      measured_v: float, measured_w: float) -> np.ndarray:
    """Construct the exact 365-D input from robot sensors/odometry.

    LiDAR must be indexed at 0..359 deg CCW from the robot's forward axis.
    Invalid LiDAR data must be handled by the upstream emergency-stop watchdog.
    """
    scan = np.asarray(raw_lidar_m, dtype=np.float64)
    pose = np.asarray(pose_xytheta, dtype=np.float64)
    goal = np.asarray(goal_xy, dtype=np.float64)
    if (scan.shape != (360,) or pose.shape != (3,) or goal.shape != (2,) or
            not np.isfinite(scan).all() or not np.isfinite(pose).all() or
            not np.isfinite(goal).all() or
            not np.isfinite([measured_v, measured_w]).all()):
        raise ValueError("Invalid LiDAR, pose, goal or odometry")
    dx, dy = goal - pose[:2]
    theta_error = math.atan2(dy, dx) - pose[2]
    observation = np.empty(365, dtype=np.float32)
    observation[:360] = (np.clip(scan, .12, 12.) - .12) / (12. - .12)
    observation[360:] = (min(math.hypot(dx, dy) / 10., 1.),
                          math.sin(theta_error), math.cos(theta_error),
                          np.clip(measured_v / .35, 0., 1.),
                          np.clip(measured_w / 1.5, -1., 1.))
    return observation


class CommandSafetyFilter:
    def __init__(self, dt: float = .1, stop_distance: float = .46):
        """Software guard; real hardware still requires an independent E-stop.

        Front threshold is >= 0.20m footprint + 0.35m/s * 0.1s UART delay
        + 0.35^2/(2*0.5)=0.1225m braking distance + LiDAR error/margin.
        """
        if not 0 < dt <= .1 or stop_distance < .46:
            raise ValueError('Safety distance must cover footprint, braking and UART delay')
        self.dt, self.stop_distance = dt, stop_distance
        self.previous = np.zeros(2, dtype=np.float64)

    def update(self, cmd: np.ndarray, raw_lidar_m: np.ndarray) -> np.ndarray:
        cmd = np.asarray(cmd, dtype=np.float64)
        scan = np.asarray(raw_lidar_m, dtype=np.float64)
        # Reject invalid frames to prevent a corrupt scan silently appearing clear.
        if (cmd.shape != (2,) or not np.all(np.isfinite(cmd)) or
                scan.shape != (360,) or not np.all(np.isfinite(scan)) or
                np.any(scan < .12) or np.any(scan > 12.)):
            self.previous[:] = 0.
            return self.previous.astype(np.float32)
        # 0 degrees points forward; 325..359 and 0..35 are the front sector.
        # The full circumference still has a footprint exclusion radius.
        front = np.concatenate((scan[325:], scan[:36]))
        if np.any(scan < .25) or np.any(front < self.stop_distance):
            self.previous[:] = 0.  # E-stop bypasses acceleration limiter.
            return self.previous.astype(np.float32)
        target = np.clip(cmd, [0., -1.5], [.35, 1.5])
        self.previous = np.clip(target, self.previous - [.5 * self.dt, 2. * self.dt],
                                self.previous + [.5 * self.dt, 2. * self.dt])
        return self.previous.astype(np.float32)


class LocalPlannerRuntime:
    def __init__(self, model_path: str | Path):
        import onnxruntime as ort

        model_path = Path(model_path)
        manifest_path = model_path.with_suffix(".json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if hashlib.sha256(model_path.read_bytes()).hexdigest() != manifest["sha256"]:
            raise ValueError("ONNX model SHA256 does not match the export manifest")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_path), sess_options=options,
                                            providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.safety = CommandSafetyFilter()

    def predict(self, observation: np.ndarray, raw_lidar_m: np.ndarray) -> np.ndarray:
        observation = np.asarray(observation, dtype=np.float32)
        if observation.shape != (365,) or not np.all(np.isfinite(observation)):
            self.safety.previous[:] = 0.
            return np.zeros(2, dtype=np.float32)
        prediction = self.session.run(None, {self.input_name: observation[None]})[0]
        return self.safety.update(prediction[0], raw_lidar_m)

    def predict_from_sensors(self, raw_lidar_m, pose_xytheta, goal_xy,
                             measured_v: float, measured_w: float) -> np.ndarray:
        try:
            obs = build_observation(raw_lidar_m, pose_xytheta, goal_xy,
                                    measured_v, measured_w)
        except ValueError:
            self.safety.previous[:] = 0.
            return np.zeros(2, dtype=np.float32)
        return self.predict(obs, raw_lidar_m)
