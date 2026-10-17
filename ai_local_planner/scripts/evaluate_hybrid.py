"""Independent closed-loop evaluation for experimental specialist routing."""

import argparse
import json
from pathlib import Path

import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.models.hybrid_policy import corridor_from_observation
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.trainers.ppo_agent import PPOAgent


class RoutedAgent:
    def __init__(self, reference: PPOAgent, specialist: PPOAgent):
        self.reference, self.specialist = reference, specialist
        self.calls = self.specialist_calls = 0

    def act(self, obs, deterministic=True):
        is_corridor = corridor_from_observation(obs)
        self.calls += 1
        self.specialist_calls += int(is_corridor)
        return (self.specialist if is_corridor else self.reference).act(
            obs, deterministic=deterministic)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--specialist", type=Path, required=True)
    parser.add_argument("--level", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=650000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("--episodes must be positive")
    torch.set_num_threads(1)
    config = load_config()["ppo"]
    a, b = PPOAgent(config, device="cpu"), PPOAgent(config, device="cpu")
    a.load(args.reference)
    b.load(args.specialist)
    agent = RoutedAgent(a, b)
    report = {
        "checkpoint": f"routed({args.reference}|{args.specialist})",
        "reference_checkpoint": str(args.reference),
        "specialist_checkpoint": str(args.specialist),
        **evaluate_agent(agent, args.level, args.episodes, args.seed),
    }
    report["specialist_fraction"] = agent.specialist_calls / max(agent.calls, 1)
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
