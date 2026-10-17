"""Out-of-distribution Level 3 test: vary width, corner position and start yaw.

This is a stress test, independent of the fixed Level 3 acceptance gate.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.models.locked_scene_onnx_agent import LockedSceneONNXAgent


def change_corridor_geometry(env: AGVMotionEnv, width: float, corner_x: float,
                             center_y: float, start_yaw: float) -> np.ndarray:
    if not .4 < width < 1.5:
        raise ValueError("Passable corridor width must exceed robot diameter 0.4m")
    if env.level != 3 or env.scenario is None:
        raise ValueError("Reset a Level 3 environment before changing geometry")
    left, right = corner_x - width / 2., corner_x + width / 2.
    bottom, top = center_y - width / 2., center_y + width / 2.
    env.scenario.walls = [(0., bottom, right, bottom),
                          (0., top, left, top),
                          (left, top, left, 7.),
                          (right, bottom, right, 7.)]
    env.scenario.start = (1., center_y, start_yaw)
    env.scenario.goal = (corner_x, 5.65)
    env.pose[:] = env.scenario.start
    env.goal[:] = env.scenario.goal
    env.walls = env.scenario.all_walls()
    return env._observe()


def run(model: Path, episodes: int, seed: int, rng_offset: int,
        width_min: float, width_max: float, corner_jitter: float,
        center_jitter: float, yaw_jitter: float,
        package: Path | None = None) -> dict:
    agent = LockedSceneONNXAgent(package) if package else ONNXAgent(model)
    env = AGVMotionEnv(level=3, randomize=True, max_steps=600)
    records = []
    try:
        for index in range(episodes):
            episode_seed = seed + index
            env.reset(seed=episode_seed)
            rng = np.random.default_rng(episode_seed + rng_offset)
            width = float(rng.uniform(width_min, width_max))
            corner_x = 3.65 + float(rng.uniform(-corner_jitter, corner_jitter))
            center_y = 1.85 + float(rng.uniform(-center_jitter, center_jitter))
            start_yaw = float(rng.uniform(-yaw_jitter, yaw_jitter))
            obs = change_corridor_geometry(env, width, corner_x, center_y, start_yaw)
            if callable(getattr(agent, 'reset', None)):
                agent.reset()
            for _ in range(env.max_steps):
                action, _, _ = agent.act(obs)
                obs, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    records.append({
                        "seed": episode_seed, "width": width, "corner_x": corner_x,
                        "center_y": center_y, "start_yaw": start_yaw,
                        "success": bool(info["success"]),
                        "collision": bool(info["collision"]),
                        "timeout": bool(truncated), "steps": int(info["steps"]),
                    })
                    break
    finally:
        env.close()
    return {
        "model": str(package if package else model), "seed_start": seed,
        "episodes": len(records),
        "domain_randomization": True,
        "perturbation": {"width_min_m": width_min, "width_max_m": width_max,
                         "corner_x_jitter_m": corner_jitter,
                         "center_y_jitter_m": center_jitter,
                         "start_yaw_jitter_rad": yaw_jitter,
                         "rng_offset": rng_offset},
        "success_rate": sum(r["success"] for r in records) / len(records),
        "collision_rate": sum(r["collision"] for r in records) / len(records),
        "timeout_rate": sum(r["timeout"] for r in records) / len(records),
        "failures": [r for r in records if not r["success"]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    paths = parser.add_mutually_exclusive_group(required=True)
    paths.add_argument("--model", type=Path)
    paths.add_argument("--package", type=Path)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=680000)
    parser.add_argument("--rng-offset", type=int, default=20000)
    parser.add_argument("--width-min", type=float, default=.58)
    parser.add_argument("--width-max", type=float, default=.82)
    parser.add_argument("--corner-jitter", type=float, default=.30)
    parser.add_argument("--center-jitter", type=float, default=.12)
    parser.add_argument("--yaw-jitter", type=float, default=.12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if (args.episodes < 1 or not .4 < args.width_min <= args.width_max < 1.5 or
            min(args.corner_jitter, args.center_jitter, args.yaw_jitter) < 0):
        parser.error("Invalid episode count, corridor width or perturbations")
    report = run(args.model, args.episodes, args.seed, args.rng_offset,
                 args.width_min, args.width_max, args.corner_jitter,
                 args.center_jitter, args.yaw_jitter, package=args.package)
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
