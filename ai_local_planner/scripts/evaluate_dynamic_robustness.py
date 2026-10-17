"""Level 6 OOD stress test with unseen crossing speeds and geometries.

This is an additional stress test, not the fixed-six-map acceptance gate.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.environments.scenarios import Circle
from ai_local_planner.models.locked_scene_onnx_agent import LockedSceneONNXAgent


def change_dynamic_geometry(env: AGVMotionEnv, rng: np.random.Generator,
                            speed_min: float, speed_max: float):
    if env.level != 6 or env.scenario is None:
        raise ValueError('Reset a Level 6 environment first')
    count = int(rng.integers(2, 5))
    xs = np.linspace(2.8, 7.2, count) + rng.uniform(-.35, .35, count)
    circles = [Circle(x=float(x), y=float(rng.uniform(1.3, 6.7)),
                      radius=float(rng.uniform(.17, .31)),
                      vy=float(rng.choice([-1., 1.]) *
                               rng.uniform(speed_min, speed_max)))
               for x in xs]
    env.scenario.obstacles = circles
    env.pose[2] = float(rng.uniform(-.15, .15))
    env.goal[1] = float(4. + rng.uniform(-.3, .3))
    return env._observe()


def evaluate(package: Path, episodes: int, seed: int,
             speed_min: float, speed_max: float) -> dict:
    if episodes < 1 or speed_min <= 0 or speed_max < speed_min:
        raise ValueError('Invalid episodes or crossing speed interval')
    agent = LockedSceneONNXAgent(package)
    env = AGVMotionEnv(level=6, randomize=True, max_steps=600)
    results = []
    try:
        for i in range(episodes):
            episode_seed = seed + i
            env.reset(seed=episode_seed)
            rng = np.random.default_rng(episode_seed + 20_000)
            obs = change_dynamic_geometry(env, rng, speed_min, speed_max)
            agent.reset()
            for _ in range(env.max_steps):
                action, _, _ = agent.act(obs)
                obs, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    results.append({
                        'seed': episode_seed, 'success': bool(info['success']),
                        'collision': bool(info['collision']),
                        'timeout': bool(truncated), 'steps': int(info['steps']),
                        'selected_level': (agent.locked_category + 1
                                           if agent.locked_category is not None else None),
                    })
                    break
    finally:
        env.close()
    n = len(results)
    return {
        'model': str(package), 'level': 6, 'seed_start': seed,
        'episodes': n, 'domain_randomization': True,
        'stress_test': 'novel_dynamic_crossings',
        'speed_min_m_s': speed_min, 'speed_max_m_s': speed_max,
        'obstacle_count_range': [2, 4],
        'success_rate': sum(r['success'] for r in results) / n,
        'collision_rate': sum(r['collision'] for r in results) / n,
        'timeout_rate': sum(r['timeout'] for r in results) / n,
        'failures': [r for r in results if not r['success']],
        'route_counts': {str(level): sum(r['selected_level'] == level for r in results)
                         for level in range(1, 7)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--episodes', type=int, default=100)
    parser.add_argument('--seed', type=int, default=2906000)
    parser.add_argument('--speed-min', type=float, default=.25)
    parser.add_argument('--speed-max', type=float, default=.55)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate(args.package, args.episodes, args.seed,
                      args.speed_min, args.speed_max)
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
