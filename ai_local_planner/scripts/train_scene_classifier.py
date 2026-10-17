"""Train a six-map classifier from randomized expert trajectories.

Per-class held-out episodes are disjoint from training. The model is merely
an observation-based router for a hybrid controller, not a PPO replacement.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.models.reactive_lidar import ReactiveLiDARPolicy
from ai_local_planner.models.scene_classifier import SceneClassifier
from ai_local_planner.trainers.ppo_agent import PPOAgent


def dataset_for_level(level, episodes, seed, stride, actor):
    env = AGVMotionEnv(level=level, randomize=True)
    observations = []
    successes = collisions = 0
    try:
        for index in range(episodes):
            obs, _ = env.reset(seed=seed + index)
            for step in range(env.max_steps):
                if step % stride == 0:
                    observations.append(obs.copy())
                action, _, _ = actor.act(obs, deterministic=True)
                obs, _, done, truncated, info = env.step(action)
                if done or truncated:
                    successes += int(info['success'])
                    collisions += int(info['collision'])
                    break
    finally:
        env.close()
    return (np.asarray(observations, dtype=np.float32),
            {'episodes': episodes, 'success_rate': successes / episodes,
             'collision_rate': collisions / episodes})


def run(args):
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(1)
    base = Path('ai_local_planner/checkpoints')
    paths = {
        'ppo': base / 'ppo_level2_anchored_20261016/best_level_2.pth',
        'corridor': base / 'bc_level3_dagger_replay_20261016.pth',
        'pocket': base / 'level5_bc_reactive_experimental.pth',
    }
    actors = {}
    for name, path in paths.items():
        actor = PPOAgent(load_config()['ppo'], device='cpu')
        actor.load(path)
        actors[name] = actor
    actors_by_level = [actors['ppo'], actors['ppo'], actors['corridor'],
                       ReactiveLiDARPolicy(margin=.12), actors['pocket'],
                       ReactiveLiDARPolicy(margin=.36)]
    train_x, train_y, valid_x, valid_y = [], [], [], []
    metrics = {}
    for level in range(1, 7):
        print(f'collecting level {level}', flush=True)
        train, train_stats = dataset_for_level(
            level, args.train_episodes, args.seed + level * 1000,
            args.stride, actors_by_level[level - 1])
        valid, valid_stats = dataset_for_level(
            level, args.validation_episodes, args.seed + 50000 + level * 1000,
            args.stride, actors_by_level[level - 1])
        train_x.append(train)
        train_y.append(np.full(len(train), level - 1, np.int64))
        valid_x.append(valid)
        valid_y.append(np.full(len(valid), level - 1, np.int64))
        metrics[str(level)] = {'train_samples': len(train), 'validation_samples': len(valid),
                               'training_rollout': train_stats,
                               'validation_rollout': valid_stats}
        print(json.dumps({'level': level, **metrics[str(level)]}), flush=True)

    device = torch.device(args.device)
    x = torch.from_numpy(np.concatenate(train_x)).to(device)
    y = torch.from_numpy(np.concatenate(train_y)).to(device)
    xv = torch.from_numpy(np.concatenate(valid_x)).to(device)
    yv = torch.from_numpy(np.concatenate(valid_y)).to(device)
    model = SceneClassifier().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    best = 0.
    weights = None
    for epoch in range(args.epochs):
        model.train()
        order = torch.randperm(len(x), device=device)
        for indices in order.split(args.batch_size):
            predictions = model(x[indices])
            loss = F.cross_entropy(predictions, y[indices])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            classes = torch.cat([model(batch).argmax(-1)
                                 for batch in xv.split(args.batch_size)])
        accuracy = float((classes == yv).float().mean())
        per_class = {str(i+1): float((classes[yv == i] == i).float().mean())
                     for i in range(6)}
        if accuracy > best:
            best = accuracy
            weights = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        print(json.dumps({'epoch': epoch+1, 'accuracy': accuracy,
                          'per_level_accuracy': per_class}), flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({'model': weights, 'validation_accuracy': best,
                'sampling': metrics, 'seed': args.seed,
                'training_method': 'supervised_scene_classifier'}, args.output)
    print(json.dumps({'output': str(args.output), 'best_validation_accuracy': best,
                      'stats': metrics}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--train-episodes', type=int, default=20)
    parser.add_argument('--validation-episodes', type=int, default=6)
    parser.add_argument('--stride', type=int, default=4)
    parser.add_argument('--batch-size', type=int, default=256)
    parser.add_argument('--epochs', type=int, default=24)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--seed', type=int, default=1000000)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda' if torch.cuda.is_available() else 'cpu')
    args = parser.parse_args()
    if min(args.train_episodes, args.validation_episodes, args.stride,
           args.batch_size, args.epochs) < 1 or args.lr <= 0:
        parser.error('Invalid training configuration')
    run(args)
