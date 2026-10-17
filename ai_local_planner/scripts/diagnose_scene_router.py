"""Replay selected failed simulation seeds and trace the hybrid scene routes."""

import argparse
from collections import Counter
import json
from pathlib import Path

import torch

from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.models.scene_classifier import SceneClassifier
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--classifier', type=Path, required=True)
    parser.add_argument('--level', type=int, choices=range(1, 7), required=True)
    parser.add_argument('--seeds', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    classifier = SceneClassifier().eval()
    classifier.load_state_dict(torch.load(args.classifier, map_location='cpu',
                                          weights_only=True)['model'])
    policy = ONNXAgent(args.model)
    env = AGVMotionEnv(level=args.level, randomize=True)
    reports = []
    try:
        for seed in args.seeds:
            obs, _ = env.reset(seed=seed)
            modes = []
            previous = None
            transitions = []
            for step in range(env.max_steps):
                with torch.no_grad():
                    mode = int(classifier(torch.from_numpy(obs[None])).argmax(-1)[0]) + 1
                modes.append(mode)
                if previous is not None and mode != previous:
                    transitions.append({'step': step, 'from': previous, 'to': mode})
                previous = mode
                action, _, _ = policy.act(obs)
                obs, _, done, truncated, info = env.step(action)
                if done or truncated:
                    reports.append({'seed': seed, 'success': bool(info['success']),
                                    'collision': bool(info['collision']),
                                    'timeout': bool(truncated), 'steps': step+1,
                                    'modes_count': dict(Counter(modes)),
                                    'last_20_modes': modes[-20:],
                                    'mode_transitions': transitions[-20:]})
                    break
    finally:
        env.close()
    output = {'model': str(args.model), 'actual_level': args.level,
              'seed_reports': reports}
    print(json.dumps(output, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
