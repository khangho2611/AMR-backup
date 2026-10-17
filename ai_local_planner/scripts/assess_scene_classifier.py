"""Measure initial-scene classification independently of trajectory labels."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.models.scene_classifier import SceneClassifier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--episodes', type=int, default=100)
    parser.add_argument('--seed', type=int, default=1510000)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error('Expected positive episode count')
    torch.set_num_threads(1)
    model = SceneClassifier().eval()
    model.load_state_dict(torch.load(args.checkpoint, map_location='cpu',
                                     weights_only=True)['model'])
    confusion = np.zeros((6, 6), dtype=int)
    confidences = {}
    for level in range(1, 7):
        env = AGVMotionEnv(level=level, randomize=True)
        try:
            samples = [env.reset(seed=args.seed + level * 1000 + s)[0]
                       for s in range(args.episodes)]
        finally:
            env.close()
        with torch.no_grad():
            probabilities = model(torch.from_numpy(np.stack(samples))).softmax(-1)
        guesses = probabilities.argmax(-1).numpy()
        for target in guesses:
            confusion[level - 1, target] += 1
        prob = probabilities[:, level - 1].numpy()
        confidences[str(level)] = {'mean_correct_class_probability': float(np.mean(prob)),
                                   'p10_correct_class_probability': float(np.quantile(prob, .1))}
    report = {'seed': args.seed, 'episodes_per_level': args.episodes,
              'confusion_rows_actual_columns_predicted': confusion.tolist(),
              'accuracies': {str(i + 1): float(confusion[i, i] / args.episodes)
                             for i in range(6)}, 'confidence': confidences}
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
