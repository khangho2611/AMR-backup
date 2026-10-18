"""Read-only safety diagnosis for independently failed Level-4 seeds.

Do not use these failure seeds as training data or pilot model selection seeds;
any later acceptance gate must use a fresh, separately held-out seed range.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.trainers.ppo_agent import PPOAgent


def diagnose(checkpoint: Path, evaluation: Path, teacher_path: Path, limit: int):
    torch.set_num_threads(1)
    agent = PPOAgent(load_config()['ppo'], 'cpu')
    agent.load(checkpoint)
    agent.network.eval()
    expert = ONNXAgent(teacher_path)
    seeds = json.loads(evaluation.read_text(encoding='utf-8'))['collision_seeds'][:limit]
    reports = []
    env = AGVMotionEnv(level=4, randomize=True)
    try:
        for seed in seeds:
            obs, _ = env.reset(seed=int(seed))
            frames = []
            for _ in range(600):
                student_action = agent.act(obs, deterministic=True)[0]
                teacher_action = expert.act(obs, deterministic=True)[0]
                with torch.no_grad():
                    x = torch.from_numpy(obs[None, :])
                    prob_l4 = float(agent.network.context_scene(x).softmax(-1)[0, 3])
                    gain = float(agent.network.context_probability(x)[0])
                obs, _, done, trunc, info = env.step(student_action)
                frames.append({'actual_speed_mps': float(info['actual_vw'][0]),
                               'applied_omega_radps': float(info['actual_vw'][1]),
                               'front_clearance_m': float(info['forward_clearance_m']),
                               'radial_clearance_m': float(info['clearance_m']),
                               'student_action': student_action.tolist(),
                               'teacher_action': teacher_action.tolist(),
                               'p4': prob_l4, 'gain': gain})
                if done or trunc:
                    recent = frames[-15:]
                    reports.append({'seed': int(seed), 'success': info['success'],
                                    'collision': info['collision'], 'steps': len(frames),
                                    'prior_15_avg_actual_v_mps': float(np.mean(
                                        [r['actual_speed_mps'] for r in recent])),
                                    'prior_15_avg_front_clearance_m': float(np.mean(
                                        [r['front_clearance_m'] for r in recent])),
                                    'prior_15_avg_radial_clearance_m': float(np.mean(
                                        [r['radial_clearance_m'] for r in recent])),
                                    'prior_15_avg_context_probability': float(np.mean(
                                        [r['p4'] for r in recent])),
                                    'prior_15_avg_context_gain': float(np.mean(
                                        [r['gain'] for r in recent])),
                                    'prior_15_avg_action_abs_error': float(np.mean(
                                        [np.abs(np.array(r['student_action']) -
                                                np.array(r['teacher_action'])) for r in recent])),
                                    'prior_15_student_action': np.mean(
                                        [r['student_action'] for r in recent], axis=0).tolist(),
                                    'prior_15_teacher_action': np.mean(
                                        [r['teacher_action'] for r in recent], axis=0).tolist(),
                                    'last_step': frames[-1]})
                    break
    finally:
        env.close()
    return {'checkpoint': str(checkpoint), 'diagnosed_seeds': len(seeds),
            'failed_rollouts': reports,
            'means_over_failures': {
                key: float(np.mean([x[key] for x in reports]))
                for key in ('prior_15_avg_actual_v_mps',
                            'prior_15_avg_front_clearance_m',
                            'prior_15_avg_radial_clearance_m',
                            'prior_15_avg_context_probability',
                            'prior_15_avg_context_gain',
                            'prior_15_avg_action_abs_error')} if reports else {}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--teacher', type=Path, default=Path(
        'ai_local_planner/exported/locked_scene_margin070_experimental/gap_level4_margin012.onnx'))
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(args.checkpoint, args.evaluation, args.teacher, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'analyzed': report['diagnosed_seeds'],
                      'means': report['means_over_failures'],
                      'output': str(args.output)}), flush=True)
