"""Evaluate mean policy over fixed seeds per curriculum level, without learning."""

import argparse
import json
from pathlib import Path
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.trainers.ppo_agent import PPOAgent


def evaluate_agent(agent: PPOAgent, level: int, episodes: int = 100,
                   seed: int = 1000, randomize: bool = True, max_steps: int = 600) -> dict:
    env = AGVMotionEnv(level=level, randomize=randomize, max_steps=max_steps)
    success = collisions = timeouts = 0
    rewards, episode_steps, min_clearances = [], [], []
    collision_seeds, timeout_seeds = [], []
    try:
        for index in range(episodes):
            obs, _ = env.reset(seed=seed + index)
            if callable(getattr(agent, 'reset', None)):
                agent.reset()
            episode_reward = 0.
            minimum_clearance = float("inf")
            while True:
                action, _, _ = agent.act(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                episode_reward += reward
                minimum_clearance = min(minimum_clearance, float(info["clearance_m"]))
                if terminated or truncated:
                    success += int(info["success"])
                    collisions += int(info["collision"])
                    timeouts += int(truncated)
                    if info["collision"]:
                        collision_seeds.append(seed + index)
                    if truncated:
                        timeout_seeds.append(seed + index)
                    rewards.append(episode_reward)
                    episode_steps.append(info["steps"])
                    min_clearances.append(minimum_clearance)
                    break
    finally:
        env.close()
    return {"level": level, "episodes": episodes, "seed_start": seed,
            "domain_randomization": randomize,
            "success_rate": success / episodes, "collision_rate": collisions / episodes,
            "timeout_rate": timeouts / episodes,
            "mean_episode_steps": sum(episode_steps) / episodes,
            "mean_min_clearance_m": sum(min_clearances) / episodes,
            "collision_seeds": collision_seeds, "timeout_seeds": timeout_seeds,
            "mean_reward": sum(rewards) / episodes}


def evaluate(checkpoint: Path, level: int, episodes: int = 100,
             seed: int = 1000, randomize: bool = True, max_steps: int = 600) -> dict:
    torch.set_num_threads(1)
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    state = agent.load(checkpoint)
    return {"checkpoint": str(checkpoint), "training_steps": state["steps"],
            **evaluate_agent(agent, level, episodes, seed, randomize, max_steps)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--level", type=int, choices=range(1, 7), default=1)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--max-steps", type=int, default=600)
    parser.add_argument("--clean", action="store_true", help="Disable domain randomization")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("--episodes must be positive")
    result = evaluate(args.checkpoint, args.level, args.episodes, args.seed,
                      not args.clean, args.max_steps)
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
