"""Experimental one-output ActorCritic slalom adapter with L1-L5 gate.

The prior ActorCritic and the observation-only context encoder are frozen.
Only the in-network actor residual is fitted via DAgger to L4's ONNX teacher.
This is NOT PPO fine-tuning, and no official ONNX is exported on a gate failure.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from ai_local_planner.configs.settings import load_config
from ai_local_planner.models.actor_critic import (ContextualResidualActorCritic,
                                                  ConservativeContextualResidualActorCritic,
                                                  DirectionalContextualResidualActorCritic,
                                                  upgrade_contextual_to_directional)
from ai_local_planner.scripts.acceptance_gate import assess
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.scripts.evaluate_policy import evaluate, evaluate_agent
from ai_local_planner.scripts.repair_stages_l2_l4 import collect_dagger, asymmetric_actor_loss
from ai_local_planner.trainers.ppo_agent import PPOAgent


def initialise(resume: Path, scene_checkpoint: Path,
               conservative_gate: bool = False,
               train_context: bool = False,
               directional_pool: bool = False) -> PPOAgent:
    cfg = load_config()['ppo']
    agent = PPOAgent(cfg, 'cpu')
    agent.initialize_from(resume)
    existing = isinstance(agent.network, ContextualResidualActorCritic)
    if existing and not conservative_gate:
        network = agent.network
    else:
        baseline_weights = agent.network.state_dict()
        network = (ConservativeContextualResidualActorCritic() if conservative_gate else
                   ContextualResidualActorCritic())
        network.load_state_dict(baseline_weights, strict=False)
        if not existing:
            scene = torch.load(scene_checkpoint, map_location='cpu', weights_only=True)
            network.context_scene.load_state_dict(scene['model'])
    if directional_pool and not isinstance(network, DirectionalContextualResidualActorCritic):
        network_weights = upgrade_contextual_to_directional(network.state_dict())
        network = DirectionalContextualResidualActorCritic()
        network.load_state_dict(network_weights)
    network.freeze_pretrained()
    if train_context:
        for parameter in network.context_scene.parameters():
            parameter.requires_grad_(True)
    network.eval()
    agent.network = network
    agent.optimizer = torch.optim.Adam(agent.network.parameters(), lr=cfg['learning_rate'], eps=1e-5)
    return agent


def prepare_replay(agent, reference, episodes: int, seed: int, max_steps: int,
                   level2_teacher=None, level2_episodes: int | None = None):
    """Collect student-visited states, labeled by the assigned expert policy."""
    replay = {}
    for level in (1, 2, 3, 5):
        expert = level2_teacher if level == 2 and level2_teacher is not None else reference
        count = level2_episodes if level == 2 and level2_episodes is not None else episodes
        observations, labels, _, _, result = collect_dagger(
            expert, agent, level,
            [seed + level * 10000 + j for j in range(count)],
            max_steps, np.random.default_rng(seed + level), stage='retain')
        replay[level] = (torch.from_numpy(observations),
                         torch.from_numpy(labels))
        print(json.dumps({'rehearsal': result}), flush=True)
    return replay


def update_residual(agent, demonstrations, replay, learning_rate: float,
                    updates: int, batch_size: int, rng,
                    hard_turn_weight: float = 0.,
                    train_context: bool = False,
                    context_loss_weight: float = .15,
                    directional_loss: bool = False,
                    level2_replay_weight: float = .5) -> dict:
    if level2_replay_weight <= 0.:
        raise ValueError('level2_replay_weight must be positive')
    obs, y, importance = demonstrations
    weights = np.minimum(8., np.sqrt(importance)).astype(np.float64)
    weights /= weights.sum()
    trainable = list(agent.network.correction.parameters())
    parameter_groups = [{'params': list(trainable), 'lr': learning_rate}]
    if train_context:
        context_parameters = list(agent.network.context_scene.parameters())
        trainable += context_parameters
        parameter_groups.append({'params': context_parameters,
                                 'lr': learning_rate * .2})
    optimizer = torch.optim.Adam(parameter_groups)
    agent.network.train()
    # Frozen context / old policy stay deterministic even in train() mode.
    losses = []
    for step in range(updates):
        idx = rng.choice(len(obs), size=batch_size, replace=True, p=weights)
        x = torch.as_tensor(obs[idx], dtype=torch.float32)
        labels = torch.as_tensor(y[idx], dtype=torch.float32)
        predicted = torch.tanh(agent.network(x)[0])
        clearance = None
        if directional_loss:
            # Quantile resists isolated min-range returns from 5% LiDAR dropout.
            rays = x[:, :360] * 11.88 + .12
            side_left = torch.quantile(rays[:, 55:126], .15, dim=-1)
            side_right = torch.quantile(rays[:, 235:306], .15, dim=-1)
            clearance = torch.minimum(side_left, side_right)
        loss = asymmetric_actor_loss(predicted, labels,
                                     speed_multiplier=3.5 if directional_loss else 2.,
                                     turn_multiplier=3. if directional_loss else 1.,
                                     clearance_m=clearance)
        context_loss = (F.cross_entropy(agent.network.context_scene(x),
                        torch.full((len(x),), 3, dtype=torch.long))
                        if train_context else None)
        if hard_turn_weight > 0.:
            teacher_turn = labels[:, 1]
            # Explicitly prevent mode-averaged zero-omega commands in the
            # high-curvature reactive maneuver. Retains smooth regression on
            # weaker teacher turns without inventing labels from geometry.
            hard = teacher_turn.abs() >= .65
            directional_margin = torch.relu(.65 - predicted[:, 1] * teacher_turn.sign())
            loss = loss + hard_turn_weight * (
                directional_margin.square() * hard).sum() / hard.sum().clamp_min(1)
        # Functional retention on actual L1/L2/L3/L5 trajectories.
        for level, (old_obs, old_actions) in replay.items():
            sample = rng.integers(0, len(old_obs), size=batch_size // 4)
            old_prediction = torch.tanh(agent.network(old_obs[sample])[0])
            coefficient = level2_replay_weight if level == 2 else .5
            loss = loss + coefficient * (old_prediction - old_actions[sample]).square().mean()
            if train_context:
                old_context = agent.network.context_scene(old_obs[sample])
                context_loss = context_loss + F.cross_entropy(
                    old_context, torch.full((len(sample),), level - 1, dtype=torch.long))
        if train_context:
            # Balanced scene supervision prevents L4 misclassification on the
            # student occupancy measure without erasing old-level scene IDs.
            loss = loss + context_loss_weight * context_loss / (len(replay) + 1)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(trainable, 1.)
        optimizer.step()
        if step % 25 == 0:
            losses.append(float(loss.detach()))
    agent.network.eval()
    return {'updates': updates, 'batch_size': batch_size,
            'context_finetuned': train_context,
            'mean_loss_over_sampled_steps': float(np.mean(losses)),
            'last_sampled_loss': losses[-1]}


def pilot(agent, episodes: int, seed: int, max_steps: int):
    reports = {str(level): evaluate_agent(agent, level, episodes,
                                         seed + level * 1000, True, max_steps)
               for level in range(1, 6)}
    # Explicit L2/L4 selection target. Other levels remain recorded and gated
    # at the independent release gate, never used as training targets here.
    l2, l4 = reports['2'], reports['4']
    score = ((l4['success_rate'] - 2.5 * l4['collision_rate']
              - 3. * l4['timeout_rate']) +
             2. * (l2['success_rate'] - 4. * l2['collision_rate']))
    return score, reports


def run(args):
    if min(args.rounds, args.episodes, args.replay_episodes, args.updates,
           args.batch_size, args.pilot_episodes) <= 0 or args.eval_episodes < 100:
        raise ValueError('Invalid budgets; gate requires >=100 episodes')
    if args.train_seed == args.pilot_seed or args.train_seed == args.eval_seed or args.pilot_seed == args.eval_seed:
        raise ValueError('Train, pilot, and gate seeds must be distinct')
    schedule = getattr(args, 'round_learning_rates', None)
    if schedule is not None and (len(schedule) != args.rounds or
                                 any(rate <= 0 for rate in schedule)):
        raise ValueError('Round learning rates must be positive, one per round')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.train_seed)
    torch.manual_seed(args.train_seed)
    torch.set_num_threads(1)
    student = initialise(args.resume, args.scene_checkpoint, args.conservative_gate,
                         args.train_context, args.directional_pool)
    reference = PPOAgent(load_config()['ppo'], 'cpu')
    reference.initialize_from(args.retention_reference)
    expert = ONNXAgent(args.level4_teacher)
    level2_expert = ONNXAgent(args.level2_teacher)
    replay = prepare_replay(student, reference, args.replay_episodes, args.train_seed,
                            args.max_steps, level2_teacher=level2_expert,
                            level2_episodes=args.level2_replay_episodes)
    trajectories = []
    experiments = []
    best_score, best_checkpoint = -np.inf, None
    for iteration in range(args.rounds):
        seeds = [args.train_seed + 200000 + iteration * 10000 + j
                 for j in range(args.episodes + iteration * args.extra_episodes)]
        teacher_probability = max(args.teacher_probability_min,
                                  args.teacher_probability_start - .1 * iteration)
        obs, labels, weights, _, collect_info = collect_dagger(
            expert, student, 4, seeds, args.max_steps, rng,
            perturb_probability=.15, stage=f'context_{iteration + 1}',
            teacher_probability=teacher_probability,
            risk_override_probability=args.risk_override_probability,
            level4_side_weight=args.level4_side_weight,
            flank_rescue=args.flank_rescue)
        trajectories.append((obs, labels, weights))
        merged = tuple(np.concatenate([chunk[k] for chunk in trajectories])
                       for k in range(3))
        round_lr = (schedule[iteration] if schedule is not None else args.learning_rate)
        update_info = update_residual(student, merged, replay, round_lr,
                                      args.updates, args.batch_size, rng,
                                      args.hard_turn_weight, args.train_context,
                                      args.context_loss_weight, args.directional_loss,
                                      args.level2_replay_weight)
        score, pilot_report = pilot(student, args.pilot_episodes,
                                    args.pilot_seed + iteration * 100000,
                                    args.max_steps)
        checkpoint = args.output_dir / f'candidate_round_{iteration + 1}.pth'
        student.save(checkpoint, 0, 5, method='context_residual_dagger_not_ppo',
                     independently_gated=False, eligible_for_real_robot=False)
        experiments.append({'round': iteration + 1, 'learning_rate': round_lr,
                            'collect': collect_info,
                            'train': update_info, 'pilot_score': score,
                            'pilot_not_acceptance': pilot_report,
                            'checkpoint': str(checkpoint)})
        if score > best_score:
            best_score, best_checkpoint = score, checkpoint
        (args.output_dir / 'training_trials.json').write_text(
            json.dumps(experiments, indent=2), encoding='utf-8')
        print(json.dumps({'round': iteration + 1, 'collection': collect_info,
                          'loss': update_info, 'pilot': {
                              k: (v['success_rate'], v['collision_rate'])
                              for k, v in pilot_report.items()},
                          'selected': str(best_checkpoint)}), flush=True)

    student.initialize_from(best_checkpoint)
    candidate = args.output_dir / 'retention_candidate.pth'
    student.save(candidate, 0, 5, method='context_residual_dagger_not_ppo',
                 independently_gated=False, eligible_for_real_robot=False)
    reports = {}
    for level in range(1, 6):
        result = evaluate(candidate, level, args.eval_episodes,
                          args.eval_seed + level * 1000, True, args.max_steps)
        reports[level] = result
        (args.output_dir / f'final_eval_l{level}.json').write_text(
            json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps({'acceptance_level': level, 'success': result['success_rate'],
                          'collision': result['collision_rate'],
                          'timeout': result['timeout_rate']}), flush=True)
    gate = assess(reports)
    gate_path = args.output_dir / 'single_actor_l1_to_l5_final_acceptance.json'
    gate_path.write_text(json.dumps(gate, indent=2), encoding='utf-8')
    passed = gate['simulation_gate_passed']
    if passed:
        student.save(candidate, 0, 5, method='context_residual_dagger_not_ppo',
                     independently_gated=True, eligible_for_real_robot=False)
    report = {'checkpoint': str(candidate), 'source': str(args.resume),
              'method': 'context_residual_DAgger_BC_not_PPO',
              'context_trained_on_simulator_levels': True,
              'no_external_controller_at_inference': True,
              'gate': {str(i): dict(reports[i], passed=gate['levels'][str(i)]['passed'])
                       for i in reports}, 'all_gates_passed': passed,
              'experiments': experiments,
              'scope': 'Simulation, fixed curriculum geometry; no Pi 4 validation'}
    (args.output_dir / 'retention_report.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'gate_passed': passed, 'report': str(gate_path),
                      'candidate': str(candidate)}), flush=True)
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', type=Path,
                        default=Path('ai_local_planner/checkpoints/single_model_l1_l5_pcgrad_20261018/retention_candidate.pth'))
    parser.add_argument('--scene-checkpoint', type=Path,
                        default=Path('ai_local_planner/checkpoints/scene_classifier_six_experimental.pth'))
    parser.add_argument('--retention-reference', type=Path,
                        default=Path('ai_local_planner/checkpoints/single_model_l1_l5_pcgrad_20261018/retention_candidate.pth'))
    parser.add_argument('--conservative-gate', action='store_true')
    parser.add_argument('--directional-pool', action='store_true',
                        help='Migrate conservative checkpoint to min+avg+directional LiDAR residual')
    parser.add_argument('--directional-loss', action='store_true')
    parser.add_argument('--flank-rescue', action='store_true')
    parser.add_argument('--risk-override-probability', type=float, default=1.)
    parser.add_argument('--level4-side-weight', type=float, default=1.)
    parser.add_argument('--hard-turn-weight', type=float, default=0.)
    parser.add_argument('--train-context', action='store_true',
                        help='Calibrate in-network scene classifier on DAgger/old replay')
    parser.add_argument('--context-loss-weight', type=float, default=.15)
    parser.add_argument('--teacher-probability-start', type=float, default=.6)
    parser.add_argument('--teacher-probability-min', type=float, default=.2)
    parser.add_argument('--level4-teacher', type=Path,
                        default=Path('ai_local_planner/exported/locked_scene_margin070_experimental/gap_level4_margin012.onnx'))
    parser.add_argument('--level2-teacher', type=Path,
                        default=Path('ai_local_planner/exported/locked_scene_margin070_experimental/ppo_levels12.onnx'))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--episodes', type=int, default=50)
    parser.add_argument('--extra-episodes', type=int, default=20)
    parser.add_argument('--replay-episodes', type=int, default=8)
    parser.add_argument('--level2-replay-episodes', type=int, default=40)
    parser.add_argument('--level2-replay-weight', type=float, default=2.)
    parser.add_argument('--updates', type=int, default=500)
    parser.add_argument('--batch-size', type=int, default=256)
    parser.add_argument('--learning-rate', type=float, default=0.0003)
    parser.add_argument('--round-learning-rates', type=float, nargs='+',
                        help='One learning rate per DAgger round (e.g. .00020 .00010 .00005)')
    parser.add_argument('--pilot-episodes', type=int, default=15)
    parser.add_argument('--eval-episodes', type=int, default=100)
    parser.add_argument('--max-steps', type=int, default=600)
    parser.add_argument('--train-seed', type=int, default=12000000)
    parser.add_argument('--pilot-seed', type=int, default=12200000)
    parser.add_argument('--eval-seed', type=int, default=12500000)
    args = parser.parse_args()
    raise SystemExit(0 if run(args) else 1)
