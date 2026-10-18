"""Bounded DAgger repair and one independent five-level simulation release gate.

Development failures can be trained on; final acceptance seeds are never trained
on or reused for model selection. Pi4 and physical AGV require separate signoff.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.scripts.evaluate_policy import evaluate
from ai_local_planner.scripts.repair_stages_l2_l4 import collect_dagger
from ai_local_planner.scripts.run_fast_gate import run as independent_release_gate
from ai_local_planner.scripts.train_context_residual import initialise, prepare_replay, update_residual
from ai_local_planner.trainers.ppo_agent import PPOAgent

TEACHER = Path('ai_local_planner/exported/locked_scene_margin070_experimental/gap_level4_margin012.onnx')
DEFAULT_RESUME = Path('ai_local_planner/checkpoints/single_actor_zero_collision_20261018/retention_candidate.pth')
DEFAULT_REF = Path('ai_local_planner/checkpoints/single_actor_context_recalibration_20261018/retention_candidate.pth')
SCENE = Path('ai_local_planner/checkpoints/scene_classifier_six_experimental.pth')
OUTPUT_DIR = Path('ai_local_planner/checkpoints/single_actor_final_release_20261018')
OFFICIAL_ONNX = Path('ai_local_planner/exported/local_planner_single_actor_l1_l5.onnx')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def seed_windows(train_seed: int, development_seed: int, final_seed: int,
                 development_episodes: int = 20) -> dict:
    """Document exact seed windows and fail before execution on any overlap."""
    training = {str(i): [train_seed + i * 10000 + j
                         for j in range(40 if i == 2 else 10)]
                for i in (1, 2, 3, 5)}
    training['4'] = [train_seed + 200000 + j for j in range(40)]
    development = {str(i): [development_seed + i * 1000 + j
                            for j in range(development_episodes)]
                   for i in range(1, 6)}
    final = {str(i): [final_seed + i * 1000 + j for j in range(100)]
             for i in range(1, 6)}
    exposed = {s for group in (training, development)
               for values in group.values() for s in values}
    # The extra seeds for refinement lie inside this dedicated training band.
    refinement_band = {train_seed + 400000 + rnd * 1000 + lvl * 100 + k
                       for rnd in range(1, 100) for lvl in (2, 4)
                       for k in range(10)}
    exposed.update(refinement_band)
    final_values = [s for values in final.values() for s in values]
    if len(final_values) != len(set(final_values)) or exposed.intersection(final_values):
        raise ValueError('Final seed windows overlap training or development windows')
    return {'training': training, 'development': development, 'final': final}


def score(reports: dict) -> float:
    """Select a frozen candidate using development results across all levels."""
    return sum((2. if level in (2, 4) else 1.5) *
               (r['success_rate'] - 4. * r['collision_rate'] -
                2. * r['timeout_rate']) for level, r in reports.items())


def evaluate_dev(checkpoint: Path, seed: int, episodes: int,
                 output: Path, iteration: int) -> dict:
    reports = {}
    for level in range(1, 6):
        result = evaluate(checkpoint, level, episodes, seed + level * 1000,
                          randomize=True, max_steps=600)
        reports[level] = result
        print(f'DEV round={iteration} L{level}: success={result["success_rate"]:.1%}, '
              f'collision={result["collision_rate"]:.1%}, '
              f'timeout={result["timeout_rate"]:.1%}', flush=True)
    save_json(output / 'development' / f'round_{iteration:02d}.json',
              {'checkpoint': str(checkpoint), 'sha256': sha256(checkpoint),
               'score': score(reports),
               'levels': {str(i): r for i, r in reports.items()}})
    return reports


def refine(student, teacher, replay, reports, rng, train_seed: int,
           iteration: int) -> dict:
    """Use development failures as DAgger seeds, including Level 2 errors."""
    blocks, collection = [], []
    for level, budget in ((4, 10), (2, 6)):
        failures = (reports[level].get('collision_seeds', []) +
                    reports[level].get('timeout_seeds', []))
        unused = [train_seed + 400000 + iteration * 1000 + level * 100 + k
                  for k in range(budget)]
        seeds = list(dict.fromkeys(failures + unused))[:budget]
        data = collect_dagger(
            teacher, student, level, seeds, 600, rng,
            perturb_probability=.1 if level == 4 else 0.,
            stage=f'development_refinement_{iteration}',
            teacher_probability=.7 if level == 4 else 0.,
            risk_override_probability=.9, level2_weight=5.,
            level4_side_weight=2.5, flank_rescue=True)
        blocks.append(data[:3])
        collection.append({'level': level, 'seeds': seeds, 'report': data[4]})
    merged = tuple(np.concatenate([block[k] for block in blocks], axis=0)
                   for k in range(3))
    updates = update_residual(
        student, merged, replay, learning_rate=.00001, updates=50,
        batch_size=128, rng=rng, train_context=False, directional_loss=True,
        level2_replay_weight=2.5)
    return {'collections': collection, 'updates': updates}


def append_implementation(output: Path, released: bool, seed: int) -> None:
    gate = json.loads((output / 'single_actor_l1_to_l5_final_acceptance.json').read_text())
    lines = ['', '### Independent final release attempt (18/10/2026)', '',
             f'- Held-out final seed base: `{seed}`, 100 episodes/level, domain randomization.',
             f'- Five-level simulation gate: **{"PASS" if gate["simulation_gate_passed"] else "FAIL"}**.',
             '| Level | Success | Collision | Timeout | Gate |',
             '| --- | ---: | ---: | ---: | --- |']
    for level in range(1, 6):
        r = json.loads((output / f'final_eval_l{level}.json').read_text())
        passed = gate['levels'][str(level)]['passed']
        lines.append(f'| {level} | {r["success_rate"]:.0%} | {r["collision_rate"]:.0%} '
                     f'| {r["timeout_rate"]:.0%} | {"PASS" if passed else "FAIL"} |')
    if released:
        latency = json.loads((output / 'cpu_latency_benchmark.json').read_text())
        lines.append(f'- Host CPU P99: **{latency["p99_ms"]:.4f} ms**, limit <2ms.')
        lines.append(f'- Simulation ONNX: `{OFFICIAL_ONNX}`. SHA and parity verified.')
    else:
        lines.append('- Official ONNX withheld due to failed simulation or CPU gate.')
    lines.append('- Real Pi4 CPU P99, STM32 independent E-stop and jack-up test unverified.')
    with Path('ai_local_planner/IMPLEMENTATION.md').open('a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def create_certificate(output: Path, checkpoint: Path) -> Path:
    manifest = json.loads(OFFICIAL_ONNX.with_suffix('.json').read_text())
    gate = json.loads((output / 'single_actor_l1_to_l5_final_acceptance.json').read_text())
    report = json.loads((output / 'retention_report.json').read_text())
    latency = json.loads((output / 'cpu_latency_benchmark.json').read_text())
    if (not gate['simulation_gate_passed'] or not report['all_gates_passed'] or
            not latency['target_p99_below_2ms'] or
            sha256(checkpoint) != report['evaluated_checkpoint_sha256'] or
            sha256(OFFICIAL_ONNX) != manifest['sha256'] or
            manifest['checkpoint_metadata']['verified_model_sha256'] != report['evaluated_model_sha256']):
        raise RuntimeError('Release gate, latency or digest inconsistent; certificate rejected')
    certificate = {
        'status': 'SIMULATION_RELEASED',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'evaluated_checkpoint': str(checkpoint),
        'evaluated_checkpoint_sha256': sha256(checkpoint),
        'model_weights_sha256': report['evaluated_model_sha256'],
        'onnx': str(OFFICIAL_ONNX), 'onnx_sha256': sha256(OFFICIAL_ONNX),
        'simulation_acceptance': gate, 'host_cpu_latency': latency,
        'pi4_latency_verified': False, 'physical_agv_approved': False,
        'hardware_notice': 'Verify Pi4 p99, STM32 independent hard E-stop at >=0.41m '
                           'from LiDAR center, and jack-up test before real deployment.'}
    destination = OFFICIAL_ONNX.with_suffix('.release_certificate.json')
    temp = destination.with_suffix('.release_certificate.json.tmp')
    save_json(temp, certificate)
    os.replace(temp, destination)
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', type=Path, default=DEFAULT_RESUME)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT_DIR)
    parser.add_argument('--train-seed', type=int, default=24000000)
    parser.add_argument('--eval-seed', type=int, default=25000000)
    parser.add_argument('--final-seed', type=int, default=27000000)
    parser.add_argument('--development-episodes', type=int, default=20)
    parser.add_argument('--updates', type=int, default=160)
    parser.add_argument('--learning-rate', type=float, default=.00002)
    parser.add_argument('--max-refinements', type=int, default=3)
    args = parser.parse_args(argv)
    if (not 1 <= args.development_episodes <= 100 or args.updates < 1 or
            args.learning_rate <= 0 or not 0 <= args.max_refinements <= 98):
        parser.error('Invalid training/refinement configuration')
    windows = seed_windows(args.train_seed, args.eval_seed, args.final_seed,
                           args.development_episodes)
    for required in (args.resume, DEFAULT_REF, TEACHER, SCENE):
        if not required.is_file():
            raise FileNotFoundError(f'Missing model: {required}')
    output = args.output_dir
    if (output / 'retention_candidate.pth').exists() or (output / 'provenance.json').exists():
        raise FileExistsError(f'Existing run detected in {output}')
    output.mkdir(parents=True, exist_ok=True)
    print('AI1: initial DAgger, bounded refinements, ONE independent final gate', flush=True)
    rng = np.random.default_rng(args.train_seed)
    torch.manual_seed(args.train_seed)
    torch.set_num_threads(1)
    student = initialise(args.resume, SCENE, conservative_gate=False,
                         train_context=False, directional_pool=True)
    ref = PPOAgent(load_config()['ppo'], 'cpu')
    ref.initialize_from(DEFAULT_REF)
    teacher = ONNXAgent(TEACHER)
    replay = prepare_replay(student, ref, episodes=10, seed=args.train_seed,
                            max_steps=600, level2_teacher=teacher, level2_episodes=40)
    data = collect_dagger(
        teacher, student, 4, windows['training']['4'], 600, rng,
        perturb_probability=.15, stage='initial', teacher_probability=.6,
        risk_override_probability=.8, level4_side_weight=2., flank_rescue=True)
    train_info = update_residual(student, data[:3], replay, args.learning_rate,
                                 args.updates, 256, rng, train_context=False,
                                 directional_loss=True, level2_replay_weight=2.)
    history = [{'round': 0, 'training': train_info, 'collection': data[4]}]
    best_path, best_score = None, float('-inf')
    for iteration in range(args.max_refinements + 1):
        trial = output / f'development_round_{iteration:02d}.pth'
        student.save(trial, 0, 5, method='context_residual_dagger_not_ppo',
                     independently_gated=False, eligible_for_real_robot=False)
        reports = evaluate_dev(trial, args.eval_seed, args.development_episodes,
                               output, iteration)
        grade = score(reports)
        history[-1].update({'score': grade, 'checkpoint': str(trial),
                            'checkpoint_sha256': sha256(trial)})
        if grade > best_score:
            best_score, best_path = grade, trial
        if iteration == args.max_refinements:
            break
        history.append({'round': iteration + 1,
                        **refine(student, teacher, replay, reports, rng,
                                 args.train_seed, iteration + 1)})
    candidate = output / 'retention_candidate.pth'
    shutil.copy2(best_path, candidate)
    save_json(output / 'provenance.json', {
        'config': {'train_seed': args.train_seed, 'pilot_seed': args.eval_seed,
                   'episodes': 40, 'replay_episodes': 10,
                   'level2_replay_episodes': 40, 'pilot_episodes': args.development_episodes},
        'seed_sets': {'training': windows['training'], 'development': windows['development']},
        'final_gate_seed_base': args.final_seed,
        'selected_checkpoint': str(best_path), 'candidate_sha256': sha256(candidate),
        'history': history,
    })
    print(f'Frozen candidate: {candidate}, SHA256={sha256(candidate)}', flush=True)
    print('Starting independent five-level 500-episode acceptance and host CPU gate', flush=True)
    released = independent_release_gate(candidate, seed=args.final_seed, episodes=100)
    append_implementation(output, released, args.final_seed)
    if not released:
        print('RELEASE BLOCKED: acceptance or latency gate failed; no certificate.', flush=True)
        return 1
    cert = create_certificate(output, candidate)
    print(f'SUCCESS: SIMULATION RELEASED. ONNX={OFFICIAL_ONNX}', flush=True)
    print(f'Certificate={cert}; physical robot not approved', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
