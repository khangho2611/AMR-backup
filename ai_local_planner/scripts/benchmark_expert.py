"""Confirm Level 1 simulator is navigable using an independent PID-like expert."""

import argparse
import json

from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.trainers.expert import goal_tracking_action


def run(episodes: int = 100, seed: int = 1000, max_steps: int = 600):
    env = AGVMotionEnv(level=1, randomize=True, max_steps=max_steps)
    success = collisions = 0
    durations = []
    try:
        for episode in range(episodes):
            obs, _ = env.reset(seed=seed + episode)
            while True:
                obs, _, terminated, truncated, info = env.step(goal_tracking_action(obs))
                if terminated or truncated:
                    success += int(info["success"])
                    collisions += int(info["collision"])
                    durations.append(info["steps"])
                    break
    finally:
        env.close()
    return dict(episodes=episodes, success_rate=success / episodes,
                collision_rate=collisions / episodes,
                mean_steps=sum(durations) / episodes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1000)
    args = parser.parse_args()
    print(json.dumps(run(args.episodes, args.seed), indent=2))
