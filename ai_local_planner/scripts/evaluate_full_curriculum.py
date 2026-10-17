"""Measure full hybrid router on the six randomized curriculum maps."""

import argparse
import json
from pathlib import Path

import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.models.full_curriculum import FullCurriculumAgent
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.trainers.ppo_agent import PPOAgent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--corridor', type=Path, required=True)
    parser.add_argument('--pocket', type=Path, required=True)
    parser.add_argument('--level', type=int, choices=range(1, 7), required=True)
    parser.add_argument('--episodes', type=int, default=100)
    parser.add_argument('--seed', type=int, default=950000)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    agents = []
    for checkpoint in (args.reference, args.corridor, args.pocket):
        agent = PPOAgent(load_config()['ppo'], device='cpu')
        agent.load(checkpoint)
        agents.append(agent)
    routed = FullCurriculumAgent(*agents)
    result = evaluate_agent(routed, args.level, args.episodes, args.seed)
    result.update(checkpoint='full_curriculum_hybrid_experimental',
                  reference=str(args.reference), corridor=str(args.corridor),
                  pocket=str(args.pocket), routing_calls=routed.calls)
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
