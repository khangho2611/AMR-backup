"""Imitate an observation-only LiDAR expert to warm-start PPO for one level.

Collects full randomized episodes and holds out entire episode IDs for
validation. The resulting .pth is an experimental ActorCritic PPO warm-start;
it must pass independent closed-loop evaluation before curriculum promotion.
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
from ai_local_planner.scripts.pretrain_obstacle_expert import episode_split
from ai_local_planner.trainers.ppo_agent import PPOAgent


def collect(level: int, episodes: int, seed: int, max_steps: int,
            actor: PPOAgent | None = None):
    env = AGVMotionEnv(level=level, randomize=True, max_steps=max_steps)
    expert = ReactiveLiDARPolicy()
    observations, actions, groups = [], [], []
    success = collision = 0
    try:
        for episode in range(episodes):
            obs, _ = env.reset(seed=seed + episode)
            for _ in range(max_steps):
                label, _, _ = expert.act(obs)
                observations.append(obs)
                actions.append(label)
                groups.append(episode)
                executed = actor.act(obs, deterministic=True)[0] if actor else label
                obs, _, done, truncated, info = env.step(executed)
                if done or truncated:
                    success += int(info['success'])
                    collision += int(info['collision'])
                    break
    finally:
        env.close()
    return (np.asarray(observations, dtype=np.float32),
            np.asarray(actions, dtype=np.float32),
            np.asarray(groups, dtype=np.int32),
            {'success_rate': success / episodes, 'collision_rate': collision / episodes})


def train(args):
    torch.manual_seed(args.seed)
    torch.set_num_threads(1)
    agent = PPOAgent(load_config()['ppo'], device=args.device)
    if args.resume:
        agent.load(args.resume)

    obs, acts, groups, metrics = collect(args.level, args.episodes,
                                         args.seed, args.max_steps)
    if args.dagger_episodes:
        dagger_obs, dagger_acts, dagger_groups, dagger_metrics = collect(
            args.level, args.dagger_episodes, args.seed + 40000,
            args.max_steps, actor=agent)
        obs = np.concatenate((obs, dagger_obs))
        acts = np.concatenate((acts, dagger_acts))
        groups = np.concatenate((groups, dagger_groups + args.episodes))
    else:
        dagger_metrics = None

    train_rows, validation_rows = episode_split(groups, seed=args.seed + 31)
    network = agent.network
    optimizer = torch.optim.Adam(network.parameters(), lr=args.learning_rate)
    tensor_obs = torch.as_tensor(obs, dtype=torch.float32, device=agent.device)
    tensor_acts = torch.as_tensor(acts, dtype=torch.float32, device=agent.device)
    idx_train = torch.as_tensor(train_rows, dtype=torch.long, device=agent.device)
    idx_val = torch.as_tensor(validation_rows, dtype=torch.long, device=agent.device)
    best_mse = float('inf')
    best_weights = None
    for epoch in range(args.epochs):
        network.train()
        order = idx_train[torch.randperm(len(idx_train), device=agent.device)]
        for batch in order.split(args.batch_size):
            prediction = torch.tanh(network(tensor_obs[batch])[0])
            loss = F.mse_loss(prediction, tensor_acts[batch])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(network.parameters(), 1.)
            optimizer.step()
        network.eval()
        with torch.no_grad():
            mse = float(F.mse_loss(torch.tanh(network(tensor_obs[idx_val])[0]),
                                   tensor_acts[idx_val]))
        if mse < best_mse:
            best_mse = mse
            best_weights = {key: value.detach().clone()
                            for key, value in network.state_dict().items()}
        print(json.dumps({'level': args.level, 'epoch': epoch + 1,
                          'heldout_episode_mse': mse}), flush=True)

    network.load_state_dict(best_weights)
    agent.optimizer = torch.optim.Adam(network.parameters(),
                                      lr=agent.config['learning_rate'], eps=1e-5)
    agent.save(args.output, 0, args.level, method='reactive_expert_behavioral_cloning',
               teacher_rollout=metrics, dagger_rollout=dagger_metrics,
               episodes=args.episodes, samples=len(obs), validation_mse=best_mse,
               validation_scheme='held_out_episodes',
               independently_gated=False)
    print(json.dumps({'checkpoint': str(args.output), 'samples': len(obs),
                      'expert_rollout': metrics, 'dagger_rollout': dagger_metrics,
                      'heldout_episode_mse': best_mse}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level', type=int, choices=(4, 5, 6), required=True)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--episodes', type=int, default=40)
    parser.add_argument('--dagger-episodes', type=int, default=0)
    parser.add_argument('--max-steps', type=int, default=600)
    parser.add_argument('--epochs', type=int, default=12)
    parser.add_argument('--batch-size', type=int, default=256)
    parser.add_argument('--learning-rate', type=float, default=1e-4)
    parser.add_argument('--seed', type=int, default=800000)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cuda' if torch.cuda.is_available() else 'cpu')
    args = parser.parse_args()
    if (args.episodes < 2 or args.dagger_episodes < 0 or args.epochs < 1
            or args.batch_size < 1 or args.max_steps < 1 or args.learning_rate <= 0):
        parser.error('Invalid training configuration')
    train(args)
