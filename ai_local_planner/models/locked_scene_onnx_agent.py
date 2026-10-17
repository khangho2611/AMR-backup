"""CPU ONNXRuntime implementation of the five-frame locked scene supervisor.

The classifier and five specialist models are separate ONNX sessions. This
pipeline deliberately keeps episode state in the external supervisor and is
not a single stateless ONNX PPO model.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

from ai_local_planner.scripts.evaluate_onnx import ONNXAgent


class LockedSceneONNXAgent:
    def __init__(self, package: Path, calibration_frames: int = 5):
        if calibration_frames < 1:
            raise ValueError('calibration_frames must be positive')
        self.package_path = Path(package)
        config = json.loads(self.package_path.read_text(encoding='utf-8'))
        base = self.package_path.parent
        paths = {name: base / path for name, path in config['models'].items()}
        for name, path in paths.items():
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
            if sha != manifest['sha256']:
                raise ValueError(f'SHA mismatch for {name}')
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        self.classifier = ort.InferenceSession(str(paths['classifier']),
                                               sess_options=opts,
                                               providers=['CPUExecutionProvider'])
        self.class_input = self.classifier.get_inputs()[0].name
        reference = ONNXAgent(paths['reference'])
        self.experts = [reference, reference,
                        ONNXAgent(paths['corridor']), ONNXAgent(paths['gap_level4']),
                        ONNXAgent(paths['pocket']), ONNXAgent(paths['gap_level6'])]
        self.calibration_frames = calibration_frames
        self.choices = Counter()
        self.reset()

    def reset(self):
        self.vote_sum = np.zeros(6, dtype=np.float64)
        self.frames = 0
        self.locked_category = None

    def act(self, obs, deterministic=True):
        if not deterministic:
            raise ValueError('Only deterministic ONNX mode is exported')
        observation = np.asarray(obs, dtype=np.float32)
        if observation.shape != (365,) or not np.isfinite(observation).all():
            raise ValueError('Expected finite float32 observation[365]')
        if self.locked_category is None:
            logits = self.classifier.run(None, {self.class_input: observation[None]})[0][0]
            exp = np.exp(logits.astype(np.float64) - logits.max())
            self.vote_sum += exp / exp.sum()
            self.frames += 1
            if self.frames == self.calibration_frames:
                self.locked_category = int(self.vote_sum.argmax())
                self.choices[self.locked_category + 1] += 1
            return np.array([-1., 0.], dtype=np.float32), 0., 0.
        return self.experts[self.locked_category].act(observation)
