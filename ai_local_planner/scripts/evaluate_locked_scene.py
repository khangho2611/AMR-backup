"""Evaluate a calibrated, episode-locked six-specialist hybrid in simulation."""

import argparse
import json
from pathlib import Path

import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.models.locked_scene_agent import LockedSceneAgent
from ai_local_planner.models.scene_classifier import SceneClassifier
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.trainers.ppo_agent import PPOAgent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--corridor', type=Path, required=True)
    parser.add_argument('--pocket', type=Path, required=True)
    parser.add_argument('--classifier', type=Path, required=True)
    parser.add_argument('--level', type=int, choices=range(1, 7), required=True)
    parser.add_argument('--episodes', type=int, default=100)
    parser.add_argument('--seed', type=int, default=1600000)
    parser.add_argument('--calibration-frames', type=int, default=5)
    parser.add_argument('--dynamic-margin', type=float, default=.5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    actors = []
    for path in (args.reference, args.corridor, args.pocket):
        actor = PPOAgent(load_config()['ppo'], device='cpu')
        actor.load(path)
        actors.append(actor)
    classifier = SceneClassifier()
    classifier.load_state_dict(torch.load(args.classifier, map_location='cpu',
                                          weights_only=True)['model'])
    agent = LockedSceneAgent(*actors, classifier,
                             calibration_frames=args.calibration_frames,
                             dynamic_margin=args.dynamic_margin)
    result = evaluate_agent(agent, args.level, args.episodes, args.seed)
    result.update(checkpoint='locked_scene_hybrid_experimental_v1',
                  policy='stateful_scene_lock_5_frame_calibration',
                  trained_by_single_ppo=False, backend='torch_cpu',
                  scene_selections=dict(agent.choices),
                  calibration_frames=args.calibration_frames,
                  dynamic_margin_m=args.dynamic_margin,
                  pi4_latency_verified=False, real_robot_approved=False)
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
