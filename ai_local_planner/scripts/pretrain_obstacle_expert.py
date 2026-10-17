"""Warm-start Levels 2-3 from geometry teachers with earlier-level replay."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.trainers.expert import (RightAngleCorridorTeacher,
                                             SingleObstacleTeacher, goal_tracking_action)
from ai_local_planner.trainers.ppo_agent import PPOAgent


def collect(level: int, episodes: int, seed: int, max_steps: int,
            return_episode_ids: bool = False):
    env = AGVMotionEnv(level=level, randomize=True, max_steps=max_steps)
    observations, labels, episode_ids = [], [], []
    successes = 0
    try:
        for episode in range(episodes):
            obs, _ = env.reset(seed=seed + episode)
            teacher = (SingleObstacleTeacher(env.scenario.obstacles[0], env.goal)
                       if level == 2 else RightAngleCorridorTeacher(env.goal)
                       if level == 3 else None)
            for _ in range(max_steps):
                action = (teacher.act(obs, env.pose) if teacher else
                          goal_tracking_action(obs))
                observations.append(obs)
                labels.append(action)
                episode_ids.append(episode)
                obs, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    successes += int(info["success"])
                    break
    finally:
        env.close()
    result = (np.stack(observations), np.stack(labels), successes / episodes)
    if return_episode_ids:
        return (*result, np.asarray(episode_ids, dtype=np.int32))
    return result


def collect_policy_rollouts(level: int, episodes: int, seed: int, max_steps: int,
                            actor: PPOAgent, label_agent: PPOAgent | None = None):
    """Collect student failures for DAgger or on-policy reference replay.

    The Level 3 expert uses privileged pose only to label offline samples.
    Actions executed in the environment always come from the rollout actor.
    """
    env = AGVMotionEnv(level=level, randomize=True, max_steps=max_steps)
    observations, labels, episode_ids = [], [], []
    successes = 0
    try:
        for episode in range(episodes):
            obs, _ = env.reset(seed=seed + episode)
            teacher = RightAngleCorridorTeacher(env.goal) if level == 3 else None
            for _ in range(max_steps):
                action, _, _ = actor.act(obs, deterministic=True)
                if teacher is not None:
                    label = teacher.act(obs, env.pose)
                else:
                    if label_agent is None:
                        raise ValueError("Reference replay needs a label policy")
                    label, _, _ = label_agent.act(obs, deterministic=True)
                observations.append(obs)
                labels.append(label)
                episode_ids.append(episode)
                obs, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    successes += int(info["success"])
                    break
    finally:
        env.close()
    return (np.stack(observations), np.stack(labels), successes / episodes,
            np.asarray(episode_ids, dtype=np.int32))


def episode_split(groups: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Split complete episodes so neighboring frames never leak into validation."""
    unique = np.unique(groups)
    if len(unique) < 2:
        raise ValueError("Episode-level validation requires at least two episodes")
    rng = np.random.default_rng(seed)
    heldout = rng.choice(unique, size=max(1, int(np.ceil(.1 * len(unique)))),
                         replace=False)
    validation_mask = np.isin(groups, heldout)
    return np.flatnonzero(~validation_mask), np.flatnonzero(validation_mask)


def pretrain(args):
    torch.manual_seed(args.seed)
    torch.set_num_threads(1)
    observations, actions, groups = [], [], []
    success_rates = {}
    group_offset = 0

    def add_data(obs, acts, episode_ids, episodes):
        nonlocal group_offset
        observations.append(obs)
        actions.append(acts)
        groups.append(episode_ids + group_offset)
        group_offset += episodes

    for level, episodes in ((1, args.level1_episodes), (2, args.level2_episodes),
                            (3, args.level3_episodes)):
        if episodes:
            obs, acts, rate, episode_ids = collect(
                level, episodes, args.seed + 1000 * level,
                args.max_episode_steps, return_episode_ids=True)
            if rate < .99:
                raise RuntimeError(f"Level {level} teacher success {rate:.1%} < 99%")
            add_data(obs, acts, episode_ids, episodes)
            success_rates[f"level_{level}"] = rate

    agent = PPOAgent(load_config()["ppo"], device=args.device)
    agent.load(args.resume)
    replay_stats = {}
    if args.reference_replay_episodes:
        reference = PPOAgent(load_config()["ppo"], device=args.device)
        reference.load(args.reference_checkpoint)
        for level in (1, 2):
            episodes = args.reference_replay_episodes
            obs, acts, rate, group_ids = collect_policy_rollouts(
                level, episodes, args.seed + 9000 * level, args.max_episode_steps,
                actor=reference, label_agent=reference)
            add_data(obs, acts, group_ids, episodes)
            replay_stats[f"reference_level_{level}"] = rate
    if args.dagger_episodes:
        episodes = args.dagger_episodes
        obs, acts, rate, group_ids = collect_policy_rollouts(
            3, episodes, args.seed + 30000, args.max_episode_steps, actor=agent)
        add_data(obs, acts, group_ids, episodes)
        replay_stats["dagger_student_level_3"] = rate
    if not observations:
        raise ValueError("At least one dataset must have episodes")
    dataset_obs = torch.as_tensor(np.concatenate(observations), dtype=torch.float32)
    dataset_act = torch.as_tensor(np.concatenate(actions), dtype=torch.float32)
    network = agent.network
    optimizer = torch.optim.Adam(network.parameters(), lr=args.learning_rate)
    device = agent.device
    dataset_obs, dataset_act = dataset_obs.to(device), dataset_act.to(device)
    train_rows, valid_rows = episode_split(np.concatenate(groups), args.seed)
    train_idx = torch.as_tensor(train_rows, device=device)
    valid_idx = torch.as_tensor(valid_rows, device=device)
    train_n = len(train_idx)
    for epoch in range(args.epochs):
        network.train()
        shuffled = train_idx[torch.randperm(len(train_idx), device=device)]
        mean_error = 0.
        for batch in shuffled.split(args.batch_size):
            prediction = torch.tanh(network(dataset_obs[batch])[0])
            loss = F.mse_loss(prediction, dataset_act[batch])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(network.parameters(), 1.)
            optimizer.step()
            mean_error += float(loss.detach()) * len(batch)
        network.eval()
        with torch.no_grad():
            validation = float(F.mse_loss(torch.tanh(network(dataset_obs[valid_idx])[0]),
                                           dataset_act[valid_idx]))
        print(json.dumps({"epoch": epoch + 1, "train_mse": mean_error / train_n,
                          "validation_mse": validation}), flush=True)
    agent.optimizer = torch.optim.Adam(network.parameters(),
                                      lr=agent.config["learning_rate"], eps=1e-5)
    trained_levels = [level for level, episodes in
                      ((1, args.level1_episodes), (2, args.level2_episodes),
                       (3, args.level3_episodes), (3, args.dagger_episodes))
                      if episodes]
    if args.reference_replay_episodes:
        trained_levels.append(2)
    trained_level = max(trained_levels)
    agent.save(args.output, 0, trained_level, method="mixed_level_behavioral_cloning",
               teacher_success_rates=success_rates,
               teacher_states=len(dataset_obs), validation_mse=validation,
               validation_scheme="held_out_episodes", replay_stats=replay_stats)
    print(json.dumps({"checkpoint": str(args.output), "samples": len(dataset_obs),
                      "teacher_success_rates": success_rates,
                      "replay_stats": replay_stats,
                      "validation_mse": validation}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--level1-episodes", type=int, default=60)
    parser.add_argument("--level2-episodes", type=int, default=100)
    parser.add_argument("--level3-episodes", type=int, default=0)
    parser.add_argument("--reference-checkpoint", type=Path,
                        help="Original successful Level 1-2 checkpoint for replay")
    parser.add_argument("--reference-replay-episodes", type=int, default=0,
                        help="Number of independent reference rollouts at each of Levels 1 and 2")
    parser.add_argument("--dagger-episodes", type=int, default=0,
                        help="Level 3 student rollouts, labeled by privileged teacher offline")
    parser.add_argument("--max-episode-steps", type=int, default=600)
    parser.add_argument("--epochs", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--seed", type=int, default=31415)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    if (min(args.batch_size, args.epochs, args.max_episode_steps) <= 0 or
            min(args.level1_episodes, args.level2_episodes, args.level3_episodes,
                args.dagger_episodes, args.reference_replay_episodes) < 0 or
            args.learning_rate <= 0):
        parser.error("Invalid epochs, steps, episodes, batch size or learning rate")
    if args.reference_replay_episodes and not args.reference_checkpoint:
        parser.error("--reference-checkpoint required for reference replay")
    pretrain(args)
