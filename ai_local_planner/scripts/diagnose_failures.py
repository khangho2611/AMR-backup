"""Trace closed-loop errors without changing checkpoints or training seeds.

Privileged simulator state is exported only for offline diagnosis. The actor
still receives its standard 365-dimensional observation.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv, point_segment_distance
from ai_local_planner.trainers.ppo_agent import PPOAgent


def diagnose_episode(agent, level: int, seed: int, tail: int = 15) -> dict:
    env = AGVMotionEnv(level=level, randomize=True, max_steps=600)
    obs, _ = env.reset(seed=seed)
    trajectory = []
    minimum_clearance = float("inf")
    try:
        for _ in range(env.max_steps):
            action, _, _ = agent.act(obs, deterministic=True)
            obs, _, terminated, truncated, info = env.step(action)
            clearance = float(info["clearance_m"])
            minimum_clearance = min(minimum_clearance, clearance)
            pose = env.pose.copy()
            wall_distances = point_segment_distance(pose[:2], env.walls)
            nearest_wall = float(wall_distances.min())
            nearest_obstacle = min(
                (float(np.hypot(pose[0] - c.x, pose[1] - c.y) - c.radius)
                 for c in env.scenario.obstacles), default=float("inf"))
            trajectory.append({
                "step": int(info["steps"]),
                "pose_xytheta": [round(float(v), 4) for v in pose],
                "action_normalized": [round(float(v), 4) for v in action],
                "actual_vw": [round(float(v), 4) for v in info["actual_vw"]],
                "clearance_m": round(clearance, 4),
                "nearest_geometry": "wall" if nearest_wall <= nearest_obstacle else "obstacle",
                "goal_distance_m": round(float(info["distance_to_goal_m"]), 4),
            })
            if terminated or truncated:
                return {
                    "seed": seed, "level": level, "success": bool(info["success"]),
                    "collision": bool(info["collision"]), "timeout": bool(truncated),
                    "steps": int(info["steps"]),
                    "minimum_clearance_m": round(minimum_clearance, 4),
                    "robot_radius_m": float(env.robot["radius"]),
                    "near_contact_start": next((entry for entry in trajectory
                                               if entry["clearance_m"] <= .35), None),
                    "last_steps": trajectory[-tail:],
                }
        raise AssertionError("Episode exceeded its maximum steps without termination")
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--level", type=int, choices=range(1, 7), default=2)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    agent.load(args.checkpoint)
    report = {
        "checkpoint": str(args.checkpoint),
        "episodes": [diagnose_episode(agent, args.level, seed) for seed in args.seeds],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for result in report["episodes"]:
        print(json.dumps({key: value for key, value in result.items()
                          if key != "last_steps"}, indent=2))
    print(f"Detailed traces: {args.output}")


if __name__ == "__main__":
    main()
