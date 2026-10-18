"""Measure learned scene-context ambiguity without using level IDs at inference.

This is a diagnostic of the fixed simulation curricula, not a deployable guard.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.models.scene_classifier import SceneClassifier
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.trainers.ppo_agent import PPOAgent


def diagnose(episodes: int, stride: int, seed: int):
    torch.set_num_threads(1)
    actor = PPOAgent(load_config()['ppo'], 'cpu')
    actor.initialize_from(Path('ai_local_planner/checkpoints/single_model_l1_l5_pcgrad_20261018/retention_candidate.pth'))
    expert = ONNXAgent(Path('ai_local_planner/exported/locked_scene_margin070_experimental/gap_level4_margin012.onnx'))
    weights = torch.load('ai_local_planner/checkpoints/scene_classifier_six_experimental.pth',
                         weights_only=False, map_location='cpu')['model']
    scene = SceneClassifier().eval()
    scene.load_state_dict(weights)
    result = {}
    for level in range(1, 6):
        env = AGVMotionEnv(level=level, randomize=True)
        obs_list, terminal = [], [0, 0, 0]
        try:
            for i in range(episodes):
                obs, _ = env.reset(seed=seed + level * 1000 + i)
                for step in range(600):
                    if step % stride == 0:
                        obs_list.append(obs.copy())
                    command = (expert if level == 4 else actor).act(obs, deterministic=True)[0]
                    obs, _, done, trunc, info = env.step(command)
                    if done or trunc:
                        terminal[0] += int(info['success'])
                        terminal[1] += int(info['collision'])
                        terminal[2] += int(trunc)
                        break
        finally:
            env.close()
        with torch.no_grad():
            probabilities = torch.cat([scene(torch.tensor(batch)).softmax(-1)[:, 3]
                                       for batch in np.array_split(np.asarray(obs_list),
                                                                   max(1, len(obs_list) // 1024))]).numpy()
        result[level] = {'n': len(probabilities), 'episodes': episodes,
                         'success_collision_timeout': terminal,
                         'p4_mean': float(probabilities.mean()),
                         'p4_gt_05': float(np.mean(probabilities > .5)),
                         'p4_gt_09': float(np.mean(probabilities > .9)),
                         'p4_gt_099': float(np.mean(probabilities > .99)),
                         'p4_quantiles': np.quantile(probabilities, [.01, .1, .5, .9, .99]).tolist()}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--episodes', type=int, default=15)
    parser.add_argument('--stride', type=int, default=5)
    parser.add_argument('--seed', type=int, default=11700000)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.episodes, args.stride, args.seed), indent=2), flush=True)
