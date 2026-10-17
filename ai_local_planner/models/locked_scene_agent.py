"""Research-only stateful scene-lock supervisor for fixed curriculum maps.

Each episode spends five stationary control cycles collecting scene classifier
votes, then selects a frozen expert. The 365-D observation and 2-D action
contract remain intact. A stateless single-input ONNX policy cannot preserve
this episode state without an external supervisor; this module is that
supervisor, and it is NOT one PPO actor.
"""

from collections import Counter

import numpy as np
import torch

from ai_local_planner.models.reactive_lidar import ReactiveLiDARPolicy
from ai_local_planner.models.scene_classifier import SceneClassifier


class LockedSceneAgent:
    def __init__(self, reference, corridor, pocket, classifier: SceneClassifier,
                 calibration_frames: int = 5, dynamic_margin: float = .5):
        if calibration_frames < 1 or not 0. <= dynamic_margin <= 1.:
            raise ValueError('Invalid calibration_frames or dynamic_margin')
        self.experts = [reference, reference, corridor,
                        ReactiveLiDARPolicy(margin=.12), pocket,
                        ReactiveLiDARPolicy(margin=dynamic_margin)]
        self.classifier = classifier.eval()
        self.calibration_frames = calibration_frames
        self.choices = Counter()
        self.reset()

    def reset(self):
        self.vote_sum = np.zeros(6, dtype=np.float64)
        self.frames = 0
        self.locked_category = None

    def act(self, obs, deterministic=True):
        if not deterministic:
            raise ValueError('Stateful supervisor only supports deterministic evaluation')
        if self.locked_category is None:
            with torch.no_grad():
                observation = torch.as_tensor(np.asarray(obs, dtype=np.float32)[None])
                probs = torch.softmax(self.classifier(observation), dim=-1)[0]
                self.vote_sum += probs.cpu().numpy()
            self.frames += 1
            if self.frames == self.calibration_frames:
                self.locked_category = int(self.vote_sum.argmax())
                self.choices[self.locked_category + 1] += 1
            # Normalized linear action=-1 maps exactly to zero velocity.
            return np.array([-1., 0.], dtype=np.float32), 0., 0.
        return self.experts[self.locked_category].act(obs, deterministic=True)
