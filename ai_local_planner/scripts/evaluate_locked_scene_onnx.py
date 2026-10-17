"""Six-level randomized evaluation of a multi-session ONNX scene-lock pipeline."""

import argparse
import json
from pathlib import Path

from ai_local_planner.models.locked_scene_onnx_agent import LockedSceneONNXAgent
from ai_local_planner.scripts.evaluate_policy import evaluate_agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--level', type=int, choices=range(1, 7), required=True)
    parser.add_argument('--episodes', type=int, default=100)
    parser.add_argument('--seed', type=int, default=1800000)
    parser.add_argument('--calibration-frames', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    agent = LockedSceneONNXAgent(args.package, args.calibration_frames)
    result = evaluate_agent(agent, args.level, args.episodes, args.seed)
    result.update(checkpoint=str(args.package), policy='locked_scene_multi_onnx',
                  scene_selections=dict(agent.choices), trained_by_single_ppo=False,
                  calibration_frames=args.calibration_frames,
                  pi4_latency_verified=False, real_robot_approved=False)
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
