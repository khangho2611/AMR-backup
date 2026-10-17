"""Evaluate classical observation-only baseline on independent randomized seeds."""

import argparse
import json
from pathlib import Path

from ai_local_planner.models.reactive_lidar import ReactiveLiDARPolicy, CrossingObstaclePolicy
from ai_local_planner.scripts.evaluate_policy import evaluate_agent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--level', type=int, choices=range(1, 7), required=True)
    parser.add_argument('--episodes', type=int, default=30)
    parser.add_argument('--seed', type=int, default=700000)
    parser.add_argument('--policy', choices=('gap', 'yield'), default='gap')
    parser.add_argument('--lookahead', type=float, default=1.5)
    parser.add_argument('--half-width', type=float, default=.65)
    parser.add_argument('--margin', type=float, default=.12)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    policy = (ReactiveLiDARPolicy(margin=args.margin) if args.policy == 'gap' else
              CrossingObstaclePolicy(args.lookahead, args.half_width))
    report = evaluate_agent(policy, args.level, args.episodes, args.seed)
    report['checkpoint'] = f'untrained_{args.policy}_lidar_baseline'
    report['policy'] = args.policy
    if args.policy == 'gap':
        report['inflation_margin_m'] = args.margin
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
