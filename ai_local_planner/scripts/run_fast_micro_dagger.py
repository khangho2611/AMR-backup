"""One-round, train-only L4 micro-DAgger. Never runs an acceptance gate.

Run from the repository root using ``python -m ai_local_planner.scripts.run_fast_micro_dagger``.
The pre-existing training module is imported for its individual functions only.
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnxruntime
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.scripts.repair_stages_l2_l4 import collect_dagger
from ai_local_planner.scripts.train_context_residual import (
    initialise, pilot, prepare_replay, update_residual,
)
from ai_local_planner.trainers.ppo_agent import PPOAgent


OUTPUT = Path('ai_local_planner/checkpoints/single_actor_zero_collision_20261018')
BASE = Path('ai_local_planner/checkpoints/single_actor_fast_gate_pass_20261018/retention_candidate.pth')
# Replay source must be the independently verified pre-Micro-DAgger baseline.
REFERENCE = Path('ai_local_planner/checkpoints/single_actor_context_recalibration_20261018/retention_candidate.pth')
SCENE = Path('ai_local_planner/checkpoints/scene_classifier_six_experimental.pth')
L4_TEACHER = Path('ai_local_planner/exported/locked_scene_margin070_experimental/gap_level4_margin012.onnx')
L2_TEACHER = Path('ai_local_planner/exported/locked_scene_margin070_experimental/ppo_levels12.onnx')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_new(path: Path, payload) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def git_info():
    def git(*args):
        return subprocess.run(['git', *args], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', check=True).stdout.strip()
    return {'commit': git('rev-parse', 'HEAD'),
            'tracked_diff_names': git('diff', '--name-only'),
            'staged_diff_names': git('diff', '--cached', '--name-only')}


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, message):
        for stream in self.streams:
            stream.write(message)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


def parser_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resume', type=Path, default=BASE)
    p.add_argument('--retention-reference', type=Path, default=REFERENCE)
    p.add_argument('--scene-checkpoint', type=Path, default=SCENE)
    p.add_argument('--level4-teacher', type=Path, default=L4_TEACHER)
    p.add_argument('--level2-teacher', type=Path, default=L2_TEACHER)
    p.add_argument('--output-dir', type=Path, default=OUTPUT)
    p.add_argument('--directional-pool', action='store_true')
    p.add_argument('--directional-loss', action='store_true')
    p.add_argument('--flank-rescue', action='store_true')
    p.add_argument('--episodes', type=int, default=40)
    p.add_argument('--replay-episodes', type=int, default=10)
    p.add_argument('--level2-replay-episodes', type=int, default=40)
    p.add_argument('--level2-replay-weight', type=float, default=2.)
    p.add_argument('--updates', type=int, default=150)
    p.add_argument('--learning-rate', type=float, default=.00002)
    p.add_argument('--batch-size', type=int, default=256)
    p.add_argument('--pilot-episodes', type=int, default=20)
    p.add_argument('--max-steps', type=int, default=600)
    p.add_argument('--train-seed', type=int, default=22300000)
    p.add_argument('--pilot-seed', type=int, default=22400000)
    p.add_argument('--teacher-probability', type=float, default=.6)
    p.add_argument('--risk-override-probability', type=float, default=1.)
    p.add_argument('--level4-side-weight', type=float, default=1.)
    p.add_argument('--hard-turn-weight', type=float, default=0.)
    return p.parse_args()


def main(args):
    # Only this worker's designated output directory is writable by this runner.
    if args.output_dir.resolve() != OUTPUT.resolve():
        raise ValueError('Output must be the designated zero_collision_20261018 directory')
    if any(n <= 0 for n in (args.episodes, args.replay_episodes,
                             args.level2_replay_episodes, args.updates,
                             args.batch_size, args.pilot_episodes, args.max_steps)):
        raise ValueError('Episode, update, batch and step budgets must be positive')
    if args.train_seed == args.pilot_seed:
        raise ValueError('Training and pilot seeds must be disjoint')
    if not (0 <= args.teacher_probability <= 1 and
            0 <= args.risk_override_probability <= 1):
        raise ValueError('Rollout probabilities must be in [0,1]')
    if args.learning_rate <= 0 or args.level2_replay_weight <= 0:
        raise ValueError('Learning rate and replay weight must be positive')
    if not (args.directional_pool and args.directional_loss and args.flank_rescue):
        raise ValueError('This experiment requires all three directional/flank flags')

    monitored = {
        'base_checkpoint': args.resume,
        'retention_reference': args.retention_reference,
        'scene_checkpoint': args.scene_checkpoint,
        'level4_teacher_onnx': args.level4_teacher,
        'level4_teacher_manifest': args.level4_teacher.with_suffix('.json'),
        'level2_teacher_onnx': args.level2_teacher,
        'level2_teacher_manifest': args.level2_teacher.with_suffix('.json'),
        'train_context_residual_source': Path('ai_local_planner/scripts/train_context_residual.py'),
        'repair_stages_source': Path('ai_local_planner/scripts/repair_stages_l2_l4.py'),
        'actor_critic_source': Path('ai_local_planner/models/actor_critic.py'),
        'ppo_agent_source': Path('ai_local_planner/trainers/ppo_agent.py'),
        'environment_source': Path('ai_local_planner/environments/agv_motion_env.py'),
        'evaluation_source': Path('ai_local_planner/scripts/evaluate_policy.py'),
        'runner_source': Path(__file__),
    }
    for label, path in monitored.items():
        if not path.is_file():
            raise FileNotFoundError(f'{label}: {path}')
    # Exclusive mkdir enforces no overwrite or silent reuse of another worker's run.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / 'execution.log').open('x', encoding='utf-8') as log:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = Tee(old_stdout, log)
        sys.stderr = Tee(old_stderr, log)
        try:
            started = datetime.now(timezone.utc).isoformat()
            provenance = {
                'started_utc': started,
                'invocation': [sys.executable, '-m', 'ai_local_planner.scripts.run_fast_micro_dagger', *sys.argv[1:]],
                'working_directory': str(Path.cwd()),
                'experiment': 'single_round_L4_micro_DAgger_training_and_self_drive_pilot',
                'rounds': 1,
                'config': {key: str(value) if isinstance(value, Path) else value
                           for key, value in vars(args).items()},
                'flags': {'train_context': False, 'external_context_routing': False,
                          'run_independent_gate': False, 'export_official_onnx': False},
                'replay_experts': {'1': 'retention_reference',
                                   '2': 'level2_teacher_onnx',
                                   '3': 'retention_reference', '5': 'retention_reference'},
                'pilot_policy': 'student_only_deterministic_no_teacher',
                'collection_policy': 'mixed_teacher_student_DAgger_not_self_drive',
                'inputs_sha256': {name: {'path': str(path.resolve()), 'sha256': sha256(path)}
                                  for name, path in monitored.items()},
                'git': git_info(),
                'runtime': {'python': sys.version, 'python_executable': sys.executable,
                            'platform': platform.platform(), 'torch': torch.__version__,
                            'numpy': np.__version__, 'onnxruntime': onnxruntime.__version__},
            }
            write_json_new(args.output_dir / 'provenance.json', provenance)
            print(json.dumps({'event': 'begin', 'rounds': 1, 'L4_collection_episodes': args.episodes,
                              'L2_replay_episodes': args.level2_replay_episodes,
                              'updates': args.updates, 'learning_rate': args.learning_rate}), flush=True)

            torch.set_num_threads(1)
            torch.manual_seed(args.train_seed)
            rng = np.random.default_rng(args.train_seed)
            student = initialise(args.resume, args.scene_checkpoint,
                                 conservative_gate=False, train_context=False,
                                 directional_pool=args.directional_pool)
            reference = PPOAgent(load_config()['ppo'], 'cpu')
            reference.initialize_from(args.retention_reference)
            l4_expert = ONNXAgent(args.level4_teacher)
            l2_expert = ONNXAgent(args.level2_teacher)

            replay = prepare_replay(student, reference, args.replay_episodes,
                                    args.train_seed, args.max_steps,
                                    level2_teacher=l2_expert,
                                    level2_episodes=args.level2_replay_episodes)
            replay_sizes = {str(level): {'episodes': (args.level2_replay_episodes if level == 2
                                                      else args.replay_episodes),
                                         'frames': len(samples[0])}
                            for level, samples in replay.items()}
            write_json_new(args.output_dir / 'replay_sizes.json', replay_sizes)

            seeds = [args.train_seed + 200000 + i for i in range(args.episodes)]
            obs, labels, importance, groups, collected = collect_dagger(
                l4_expert, student, 4, seeds, args.max_steps, rng,
                perturb_probability=.15, stage='micro_dagger_1',
                teacher_probability=args.teacher_probability,
                risk_override_probability=args.risk_override_probability,
                level4_side_weight=args.level4_side_weight,
                flank_rescue=args.flank_rescue)
            collected['rollout_type'] = 'mixed_teacher_student_not_self_drive'
            collected['seed_start'] = seeds[0]
            collected['seed_end'] = seeds[-1]
            collected['unique_groups'] = int(np.unique(groups).size)
            print(json.dumps({'collection_mixed_rollout': collected}), flush=True)
            training = update_residual(
                student, (obs, labels, importance), replay, args.learning_rate,
                args.updates, args.batch_size, rng,
                hard_turn_weight=args.hard_turn_weight,
                train_context=False, directional_loss=args.directional_loss,
                level2_replay_weight=args.level2_replay_weight)
            write_json_new(args.output_dir / 'training_metrics.json', {
                'method': 'DAgger_imitation_not_PPO',
                'rounds': 1, 'updates_total': args.updates,
                'collection_mixed_rollout_not_self_drive': collected,
                'replay': replay_sizes, 'optimizer': training,
            })
            print(json.dumps({'training_complete': training}), flush=True)

            score, reports = pilot(student, args.pilot_episodes,
                                   args.pilot_seed, args.max_steps)
            for level, report in reports.items():
                write_json_new(args.output_dir / f'pilot_l{level}.json', {
                    'policy': 'student_only_no_teacher',
                    'independent_gate': False, **report})
            write_json_new(args.output_dir / 'pilot_report.json', {
                'policy': 'student_only_no_teacher', 'pilot_not_acceptance': True,
                'independently_gated': False, 'score': score, 'levels': reports})
            write_json_new(args.output_dir / 'training_trials.json', [{
                'round': 1, 'learning_rate': args.learning_rate,
                'collect_mixed_rollout': collected, 'train': training,
                'pilot_self_drive_score': score, 'pilot_self_drive_not_acceptance': reports,
            }])
            print(json.dumps({'self_drive_pilot_score': score,
                              'self_drive_pilot_rates': {
                                  level: {'success': report['success_rate'],
                                          'collision': report['collision_rate'],
                                          'timeout': report['timeout_rate']}
                                  for level, report in reports.items()}}), flush=True)

            candidate = args.output_dir / 'retention_candidate.pth'
            if candidate.exists():
                raise FileExistsError(candidate)
            student.save(candidate, 0, 5,
                         method='context_residual_micro_dagger_not_ppo',
                         independently_gated=False,
                         eligible_for_real_robot=False,
                         train_context=False,
                         source_checkpoint_sha256=provenance['inputs_sha256']['base_checkpoint']['sha256'],
                         rounds=1, updates=args.updates, learning_rate=args.learning_rate)
            saved = torch.load(candidate, map_location='cpu', weights_only=True)
            assert saved['metadata']['independently_gated'] is False
            assert saved['metadata']['eligible_for_real_robot'] is False
            outcome = {
                'status': 'completed_training_and_pilot',
                'finished_utc': datetime.now(timezone.utc).isoformat(),
                'candidate': str(candidate.resolve()),
                'candidate_sha256': sha256(candidate),
                'candidate_architecture': saved.get('architecture'),
                'independently_gated': False,
                'independent_gate_run': False,
                'official_onnx_exported': False,
                'pilot_episodes_per_level': args.pilot_episodes,
                'pilot_policy': 'self_drive_student_only',
                'pilot_score': score,
                'pilot_success_rate': {level: item['success_rate'] for level, item in reports.items()},
                'pilot_collision_rate': {level: item['collision_rate'] for level, item in reports.items()},
                'mixed_rollout_success_rate_is_not_self_drive': collected['success_rate'],
                'training_metrics_file': 'training_metrics.json',
                'pilot_report_file': 'pilot_report.json',
                'provenance_file': 'provenance.json',
            }
            write_json_new(args.output_dir / 'outcome.json', outcome)
            print(json.dumps({'event': 'complete', **outcome}), flush=True)
        except BaseException as exception:
            traceback.print_exc()
            write_json_new(args.output_dir / 'failure.json', {
                'failed_utc': datetime.now(timezone.utc).isoformat(),
                'type': type(exception).__name__, 'message': str(exception),
                'traceback': traceback.format_exc()})
            raise
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr


if __name__ == '__main__':
    main(parser_args())
