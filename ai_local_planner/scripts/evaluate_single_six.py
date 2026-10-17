"""Audit ONE learned ActorCritic (PyTorch or ONNX) across all 6 sim levels."""

import argparse
import json
from pathlib import Path

import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.scripts.acceptance_gate import assess
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.trainers.ppo_agent import PPOAgent


def evaluate_all(source: Path, onnx: bool, episodes: int, seed_base: int,
                 max_steps: int = 600, max_level: int = 6):
    torch.set_num_threads(1)
    if onnx:
        actor = ONNXAgent(source)
    else:
        actor = PPOAgent(load_config()["ppo"], device="cpu")
        actor.load(source)
    reports = {}
    for level in range(1, max_level + 1):
        report = evaluate_agent(actor, level=level, episodes=episodes,
                                seed=seed_base + level * 1000,
                                randomize=True, max_steps=max_steps)
        report["checkpoint"] = str(source)
        reports[level] = report
        print(json.dumps({"level": level, "success": report["success_rate"],
                          "collision": report["collision_rate"],
                          "timeout": report["timeout_rate"]}), flush=True)
    gate = assess(reports, min_episodes=100)
    return {"policy": "single_actor_critic_onnx" if onnx else "single_actor_critic_pytorch",
            "source": str(source), "gate": gate,
            "reports": {str(key): value for key, value in reports.items()},
            "pi4_latency_verified": False, "real_robot_approved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--checkpoint", type=Path)
    target.add_argument("--onnx", type=Path)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed-base", type=int, default=3500000)
    parser.add_argument("--max-steps", type=int, default=600)
    parser.add_argument("--max-level", type=int, choices=[3, 5, 6], default=6)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.episodes < 1 or args.max_steps < 1:
        parser.error("Episodes and max-steps must be positive")
    source = args.onnx or args.checkpoint
    result = evaluate_all(source, args.onnx is not None, args.episodes,
                          args.seed_base, args.max_steps, args.max_level)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"simulation_gate_passed": result["gate"]["simulation_gate_passed"],
                      "output": str(args.output)}), flush=True)
    return 0 if result["gate"]["simulation_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
