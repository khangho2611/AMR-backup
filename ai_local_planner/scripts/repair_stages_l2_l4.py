"""Two-stage, single-actor DAgger repair with independent randomized gates.

Stage A: Level-2 hard-state rehearsal; retain L1/L3/L5.
Stage B: Level-4 perturbed student trajectories and old-level replay.
This is supervised DAgger fine tuning, not a PPO policy optimization run.
"""

import json
from pathlib import Path

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.scripts.acceptance_gate import assess
from ai_local_planner.scripts.corner_approach_dagger import split_frames
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.scripts.evaluate_policy import evaluate, evaluate_agent
from ai_local_planner.scripts.repair_retention import level5_trap_weights
from ai_local_planner.trainers.ppo_agent import PPOAgent


L2_HARD_SEEDS = (8302013, 8302017, 8302042, 8302049, 8302057,
                 8302060, 8302061, 8302064, 8302098)
TEACHER_PACKAGE = Path('ai_local_planner/exported/locked_scene_margin070_experimental')


def _ranges_from_observation(observations):
    if observations.ndim != 2 or observations.shape[1] != 365:
        raise ValueError('Expected observations [N,365]')
    return .12 + 11.88 * observations[:, :360]


def level2_approach_weights(observations, labels, student_actions,
                            approach_weight=5., disagreement_threshold=.15):
    """Weight the frontal 0.8–2.2m approach zone and teacher disagreement.

    Uses robust angular quantiles to suppress isolated LiDAR dropout returns.
    Disagreement is measured in the normalized [-1,1] actor action space.
    """
    scan = _ranges_from_observation(observations)
    front = np.concatenate((scan[:, :26], scan[:, 335:]), axis=1)
    distance = np.quantile(front, .15, axis=1)
    approach = (distance >= .8) & (distance <= 2.2)
    disagree = np.max(np.abs(labels - student_actions), axis=1) > disagreement_threshold
    return np.where(approach | disagree, approach_weight, 1.).astype(np.float32)


def level4_front_distance(observations):
    """Robust frontal +/-60 degree LiDAR distance in metres."""
    scan = _ranges_from_observation(observations)
    broad = np.concatenate((scan[:, :61], scan[:, 300:]), axis=1)
    return np.quantile(broad, .15, axis=1)


def level4_side_distance(observations):
    """Closest robust lateral-obstacle estimate across the two side arcs."""
    scan = _ranges_from_observation(observations)
    left = np.quantile(scan[:, 55:126], .15, axis=1)
    right = np.quantile(scan[:, 235:306], .15, axis=1)
    return np.minimum(left, right)


def _level4_side_clearance_torch(observations):
    """Same 15th-percentile side LiDAR clearance, in metres, on train device."""
    rays_m = .12 + 11.88 * observations[..., :360]
    left = torch.quantile(rays_m[..., 55:126], .15, dim=-1)
    right = torch.quantile(rays_m[..., 235:306], .15, dim=-1)
    return torch.minimum(left, right)


def level4_recovery_weights(observations, labels=None, student_actions=None,
                            approach_weight=5., critical_weight=6.,
                            disagreement_weight=5., disagreement_threshold=.15,
                            side_weight=1., side_trigger=.65):
    """Prioritize approach, imminent collision and teacher/student disagreement.

    Distance is a robust frontal quantile: random min-range dropout alone must
    not cause a spurious emergency classification. Multipliers compose.
    """
    distance = level4_front_distance(observations)
    weights = np.where(distance < .5, critical_weight,
                       np.where(distance <= 2.2, approach_weight, 1.))
    if side_weight < 1. or side_trigger <= 0:
        raise ValueError('Invalid lateral safety weighting')
    if side_weight > 1.:
        weights = weights * np.where(level4_side_distance(observations) < side_trigger,
                                    side_weight, 1.)
    if (labels is None) != (student_actions is None):
        raise ValueError('Provide both teacher labels and student actions')
    if labels is not None:
        if labels.shape != student_actions.shape or labels.shape != (len(distance), 2):
            raise ValueError('Expected teacher/student actions [N,2]')
        disagreement = np.max(np.abs(labels - student_actions), axis=1) > disagreement_threshold
        weights = weights * np.where(disagreement, disagreement_weight, 1.)
    return weights.astype(np.float32)


def perturb_student_action(action, rng, probability=.15):
    """Apply at most 0.3 rad/s angular perturbation (normalized by 1.5)."""
    result = np.asarray(action, np.float32).copy()
    if rng.random() < probability:
        result[1] = np.clip(result[1] + rng.uniform(-.3, .3) / 1.5, -1., 1.)
    return result


def choose_level4_rollout(student_action, teacher_action, distance, rng,
                         teacher_probability=.5, perturb_probability=.15,
                         risk_override_probability=1., side_distance=None,
                         flank_rescue=False):
    """Use teacher recovery when a collision is likely, otherwise mix policies."""
    student = np.clip(np.asarray(student_action, np.float32), -1., 1.)
    teacher = np.clip(np.asarray(teacher_action, np.float32), -1., 1.)
    if student.shape != (2,) or teacher.shape != (2,) or not np.isfinite(student).all() or not np.isfinite(teacher).all():
        raise ValueError('Rollout actions must be finite vectors of length two')
    # Normalized velocity increases with physical forward speed.
    if side_distance is not None and (not np.isfinite(side_distance) or side_distance < 0.):
        raise ValueError('side_distance must be finite and nonnegative')
    if flank_rescue:
        unsafe = ((distance < 1.2 or (side_distance is not None and side_distance < .55))
                  and (student[0] > teacher[0] + .08 or
                       abs(student[1]) + .15 < abs(teacher[1])))
    else:
        unsafe = (distance < 1. and
                  (student[0] > teacher[0] + .1 or
                   abs(student[1]) + .1 < abs(teacher[1])))
    if not 0 <= risk_override_probability <= 1.:
        raise ValueError('risk_override_probability must be in [0,1]')
    # Flank rescue expands the definition of danger; the override probability
    # still controls how often to intervene so DAgger can observe off-policy
    # recovery states instead of always hiding them behind teacher actions.
    risk_rescue = bool(unsafe and (risk_override_probability == 1. or
                                  rng.random() < risk_override_probability))
    use_teacher = bool(risk_rescue or rng.random() < teacher_probability)
    action = (teacher.copy() if use_teacher else
              perturb_student_action(student, rng, perturb_probability))
    return np.clip(action, -1., 1.), use_teacher


def asymmetric_actor_loss(prediction, labels, speed_multiplier=3.5,
                          turn_multiplier=3., clearance_m=None,
                          clearance_penalty=2., coupled_penalty=1.5):
    """Teacher-relative joint speed/turn imitation near tight flank geometry.

    Both actions use normalized [-1, 1] channels, not SI units: physical
    v = (a_v + 1) * 0.35 / 2 m/s and omega = a_w * 1.5 rad/s. The coupled
    term applies only inside 0.40 m when the teacher commands >0.4 rad/s,
    and only for simultaneous student overspeed and insufficient signed turn.
    There is no fixed creep-speed target; all targets are teacher-relative.
    """
    if (speed_multiplier < 1. or turn_multiplier < 1. or
            clearance_penalty < 0. or coupled_penalty < 0.):
        raise ValueError('Invalid safety loss multipliers')
    square = (prediction - labels).square()
    if clearance_m is not None and clearance_m.shape != prediction.shape[:-1]:
        raise ValueError('Expected one clearance measurement per sample')
    flank_risk = ((clearance_m < .50).to(square.dtype)
                  if clearance_m is not None else torch.zeros_like(square[..., 0]))
    sharp_turn = labels[..., 1].abs() > .4
    overspeed = ((prediction[..., 0] > labels[..., 0]) &
                 (sharp_turn | (flank_risk > 0.)))
    velocity_weight = 1. + (speed_multiplier - 1.) * overspeed.to(square.dtype)
    understeer = (sharp_turn &
                  (prediction[..., 1].abs() < labels[..., 1].abs() - .10))
    turn_weight = (1. + (turn_multiplier - 1.) * understeer.to(square.dtype)
                   + clearance_penalty * flank_risk)
    loss = torch.stack((square[..., 0] * velocity_weight,
                        square[..., 1] * turn_weight), dim=-1).mean()
    if clearance_m is not None and coupled_penalty:
        # Physical SI units: x[0] maps [-1,1] -> [0,.35] m/s, while x[1]
        # maps [-1,1] -> [-1.5,1.5] rad/s. A hardcoded 0.4 threshold on
        # normalized omega would incorrectly require 0.6 rad/s.
        teacher_omega = labels[..., 1] * 1.5
        student_omega = prediction[..., 1] * 1.5
        excess_velocity = torch.relu((prediction[..., 0] - labels[..., 0]) * .175)
        # Signed steering gap penalizes understeer and wrong-way turning,
        # but does not penalize same-direction oversteer as "understeer".
        missing_steering = torch.relu(teacher_omega.abs() -
                                      teacher_omega.sign() * student_omega)
        dangerous = ((clearance_m < .40) & (teacher_omega.abs() > .4))
        loss = loss + coupled_penalty * (excess_velocity * missing_steering *
                                        dangerous.to(square.dtype)).mean()
    return loss


def collect_dagger(expert, actor, level, seeds, max_steps, rng,
                   perturb_probability=0., stage='A',
                   level2_weight=5., level4_weight=5., teacher_probability=.5,
                   risk_override_probability=1., level4_side_weight=1.,
                   flank_rescue=False):
    """Observe ACTUAL student states; get teacher labels before any perturbation.

    Episode IDs remain disjoint for validation. Test seeds must be separate.
    """
    obs_all, y_all, a_all, groups = [], [], [], []
    successes = collisions = teacher_steps = total_steps = 0
    env = AGVMotionEnv(level=level, randomize=True, max_steps=max_steps)
    try:
        for group, seed in enumerate(seeds):
            obs, _ = env.reset(seed=int(seed))
            for _ in range(max_steps):
                target = expert.act(obs, deterministic=True)[0]
                original = actor.act(obs, deterministic=True)[0]
                obs_all.append(obs)
                y_all.append(target)
                a_all.append(original)
                groups.append(group)
                if level == 4:
                    distance = float(level4_front_distance(np.asarray(obs)[None, :])[0])
                    side_distance = (float(level4_side_distance(np.asarray(obs)[None, :])[0])
                                     if flank_rescue else None)
                    action, used_teacher = choose_level4_rollout(
                        original, target, distance, rng, teacher_probability,
                        perturb_probability, risk_override_probability,
                        side_distance=side_distance, flank_rescue=flank_rescue)
                    teacher_steps += int(used_teacher)
                else:
                    action = original
                total_steps += 1
                obs, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    successes += int(info['success'])
                    collisions += int(info['collision'])
                    break
    finally:
        env.close()
    observations = np.asarray(obs_all, np.float32)
    labels = np.asarray(y_all, np.float32)
    actions = np.asarray(a_all, np.float32)
    if level == 2:
        weights = level2_approach_weights(observations, labels, actions,
                                          approach_weight=level2_weight)
    elif level == 4:
        weights = level4_recovery_weights(observations, labels, actions,
                                          approach_weight=level4_weight,
                                          side_weight=level4_side_weight)
    elif level == 5:
        weights = level5_trap_weights(observations)
    else:
        weights = np.ones(len(observations), np.float32)
    report = {'level': level, 'stage': stage, 'episodes': len(seeds),
              'frames': len(observations), 'success_rate': successes / len(seeds),
              'collision_rate': collisions / len(seeds),
              'fraction_disagreement_gt_015': float(np.mean(
                  np.max(np.abs(labels - actions), axis=1) > .15)),
              'fraction_weighted': float(np.mean(weights > 1.)),
              'perturbation_probability': perturb_probability,
              'teacher_rollout_fraction': teacher_steps / max(total_steps, 1),
              'mean_teacher_normalized_speed': float(labels[:, 0].mean()),
              'mean_student_normalized_speed': float(actions[:, 0].mean())}
    return observations, labels, weights, np.asarray(groups, np.int32), report


def _weighted_sample(data, rng, batch_size, device):
    obs, labels, weight = data
    # Importance weighting is confined within a level; the stage mixing
    # coefficients below separately control cross-level gradient allocation.
    indices = rng.choice(len(obs), batch_size, replace=True,
                         p=weight / weight.sum())
    return (torch.as_tensor(obs[indices], device=device),
            torch.as_tensor(labels[indices], device=device))


def _project_conflicting_gradient(old_grads, new_grads, relaxation=1.):
    """Partially remove component of the new-task gradient opposing old skill.

    Operates on full flattened parameter gradients, including zero slots for
    unused critic parameters. relaxation=1 yields a nonnegative dot product;
    relaxation=.5 retains half of the conflicting component for L4 learning.
    """
    dot = sum((a * b).sum() for a, b in zip(old_grads, new_grads))
    if float(dot) >= 0.:
        return new_grads, False
    norm_sq = sum((a * a).sum() for a in old_grads)
    factor = dot / (norm_sq + 1e-12)
    return [b - relaxation * factor * a for a, b in zip(old_grads, new_grads)], True


def _stage_train(student, datasets, stage, weights, output, args, rng,
                 pilot_levels, epochs):
    optimizer = torch.optim.Adam(student.network.parameters(), lr=args.learning_rate)
    trials, best_score, best_path = [], -1.e30, None
    parameters = list(student.network.parameters())
    for epoch in range(1, epochs + 1):
        student.network.train()
        conflicts = 0
        for _ in range(args.updates_per_epoch):
            old_loss = 0.
            new_loss = 0.
            optimizer.zero_grad(set_to_none=True)
            for level, coefficient in weights.items():
                x, y = _weighted_sample(datasets[level][0], rng, args.batch_size,
                                        student.device)
                prediction = torch.tanh(student.network(x)[0])
                term = coefficient * (asymmetric_actor_loss(
                    prediction, y, clearance_m=_level4_side_clearance_torch(x))
                                      if level == 4 else (prediction - y).square().mean())
                if level == 4:
                    new_loss = new_loss + term
                else:
                    old_loss = old_loss + term
            if stage == 'B' and getattr(args, 'gradient_surgery', True):
                def gradients(loss, retain):
                    found = torch.autograd.grad(loss, parameters,
                                                retain_graph=retain,
                                                allow_unused=True)
                    return [g if g is not None else torch.zeros_like(p)
                            for g, p in zip(found, parameters)]
                old_grads = gradients(old_loss, True)
                new_grads = gradients(new_loss, False)
                if float(old_loss.detach()) >= getattr(args, 'old_loss_threshold', 0.):
                    new_grads, conflict = _project_conflicting_gradient(
                        old_grads, new_grads,
                        getattr(args, 'gradient_projection_relaxation', .5))
                else:
                    conflict = False
                conflicts += int(conflict)
                for p, a, b in zip(parameters, old_grads, new_grads):
                    p.grad = a + b
            else:
                (old_loss + new_loss).backward()
            torch.nn.utils.clip_grad_norm_(student.network.parameters(), 1.)
            optimizer.step()
        student.network.eval()
        pilot = {}
        for level in pilot_levels:
            pilot[level] = evaluate_agent(student, level, args.pilot_episodes,
                                          args.pilot_seed + (1 if stage == 'A' else 2) * 100000
                                          + level * 1000, True, args.max_steps)
        # Constrained selection rewards only improvement without old-level
        # losses; independent gate is withheld until training is complete.
        deviations = {level: max(0., threshold - pilot[level]['success_rate'])
                      for level, threshold in ((1, .98), (2, .98), (3, .98),
                                               (4, .9), (5, .98)) if level in pilot}
        score = (-sum((4. if level in (1, 2, 3, 5) else 2.) * deficit
                      for level, deficit in deviations.items())
                 - sum(pilot[level]['collision_rate'] for level in pilot)
                 + .01 * sum(pilot[level]['success_rate'] for level in pilot))
        checkpoint = output / f'stage_{stage}_epoch_{epoch}.pth'
        student.save(checkpoint, 0, 5, method=f'dagger_stage_{stage}',
                     independently_gated=False, eligible_for_real_robot=False)
        if score > best_score:
            best_score, best_path = score, checkpoint
        trials.append({'stage': stage, 'epoch': epoch, 'checkpoint': str(checkpoint),
                       'gradient_conflict_updates': conflicts,
                       'pilot_score': score,
                       'pilot_not_acceptance': {str(k): v for k, v in pilot.items()}})
        print(json.dumps({'stage': stage, 'epoch': epoch, 'score': score,
                          'gradient_conflict_updates': conflicts,
                          'pilot_success': {k: v['success_rate'] for k,v in pilot.items()},
                          'best_checkpoint': str(best_path)}), flush=True)
        (output / f'stage_{stage}_trials.json').write_text(
            json.dumps(trials, indent=2), encoding='utf-8')
    student.initialize_from(best_path)
    return trials, best_path


def _collect_levels(experts, student, levels, args, rng, stage,
                    perturb_level4=False):
    datasets, summaries = {}, {}
    for level, episodes in levels.items():
        seeds = [args.seed + (1 if stage == 'A' else 2) * 1000000
                 + level * 10000 + i for i in range(episodes)]
        if stage == 'A' and level == 2:
            # Previously discovered failures are development seeds, NOT gate.
            seeds.extend(L2_HARD_SEEDS)
        data = collect_dagger(experts[level], student, level, seeds,
                              args.max_steps, rng,
                              args.perturbation_prob if perturb_level4 and level == 4 else 0.,
                              stage, args.level2_weight, args.level4_weight,
                              args.teacher_probability)
        obs, labels, weights, groups, report = data
        datasets[level] = split_frames((obs, labels, weights, groups),
                                      args.seed + level + (1 if stage == 'A' else 2) * 200)
        summaries[str(level)] = report
        print(json.dumps({'collection': report}), flush=True)
    return datasets, summaries


def run(args):
    if args.device != 'cpu':
        raise ValueError('Current DAgger repair is CPU only')
    if args.eval_episodes < 100 or args.pilot_episodes < 1 or args.max_steps <= 0:
        raise ValueError('Invalid evaluation budgets; independent gate needs >=100')
    if (args.level2_weight < 1 or args.level4_weight < 1 or
            not 0 <= args.perturbation_prob <= 1 or args.epochs < 1 or
            args.updates_per_epoch < 1 or args.batch_size < 1 or args.learning_rate <= 0):
        raise ValueError('Invalid training hyperparameters')
    if (not 0 <= args.teacher_probability <= 1 or
            not 0 <= args.gradient_projection_relaxation <= 1 or
            args.old_loss_threshold < 0):
        raise ValueError('Invalid mixed-rollout or gradient-balancing settings')
    collection_seed_ranges = [(args.seed + stage * 1000000 + level * 10000,
                               args.seed + stage * 1000000 + level * 10000 + 100)
                              for stage in (1, 2) for level in range(1, 6)]
    for start, end in collection_seed_ranges:
        if any(start <= seed < end for seed in
               (args.eval_seed + l * 1000 + i
                for l in range(1, 6) for i in range(args.eval_episodes))):
            raise ValueError('Acceptance seeds overlap training seeds')
    torch.manual_seed(args.seed)
    torch.set_num_threads(1)
    rng = np.random.default_rng(args.seed)
    cfg = load_config()['ppo']
    student = PPOAgent(cfg, 'cpu')
    student.initialize_from(args.resume)
    baseline = PPOAgent(cfg, 'cpu')
    baseline.initialize_from(args.gated_old_checkpoint)
    baseline.network.eval().requires_grad_(False)
    prior = PPOAgent(cfg, 'cpu')
    prior.initialize_from(args.resume)
    prior.network.eval().requires_grad_(False)
    experts = {1: baseline, 2: ONNXAgent(args.level2_teacher_onnx),
               3: baseline, 4: ONNXAgent(args.level4_teacher_onnx), 5: prior}
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    if getattr(args, 'stage_b_only', False):
        a_collected, a_best = {}, args.resume
    else:
        a_data, a_collected = _collect_levels(experts, student,
                                               {1: 15, 2: 40, 3: 20, 5: 20},
                                               args, rng, 'A')
        a_trials, a_best = _stage_train(student, a_data, 'A',
                                        {1: .17, 2: .48, 3: .17, 5: .18}, out, args,
                                        rng, (1, 2, 3, 5), args.epochs)
    # Do not advance to Stage B until Level 2 is repaired while L1/L3/L5
    # remain above the requested retention threshold.
    a_gate = {str(i): evaluate_agent(student, i, 100,
                                     args.stage_a_eval_seed + i * 1000,
                                     True, args.max_steps) for i in (1, 2, 3, 5)}
    for level, result in a_gate.items():
        result['passed'] = (result['success_rate'] >= (.98 - 1e-9) and
                            result['collision_rate'] <= .02 + 1e-9)
        print(json.dumps({'stage_A_gate': level, **result}), flush=True)
    (out / 'stage_A_gate.json').write_text(json.dumps(a_gate, indent=2),
                                           encoding='utf-8')
    if not all(result['passed'] for result in a_gate.values()):
        checkpoint = out / 'stage_A_candidate.pth'
        student.save(checkpoint, 0, 5, method='dagger_stage_A_only',
                     independently_gated=False, eligible_for_real_robot=False)
        summary = {'stage_A_passed': False, 'stage_A_checkpoint': str(checkpoint),
                   'stage_A_training': a_collected, 'stage_A_gate': a_gate,
                   'all_gates_passed': False,
                   'note': 'Stage B blocked by Stage A retention gate; official ONNX not allowed.'}
        (out / 'retention_report.json').write_text(json.dumps(summary, indent=2),
                                                   encoding='utf-8')
        print(json.dumps({'stage_A_gate_passed': False,
                          'stage_B_executed': False}), flush=True)
        return summary
    b_data, b_collected = _collect_levels(experts, student,
                                           {1: 15, 2: 40, 3: 20, 4: 50, 5: 20},
                                           args, rng, 'B', perturb_level4=True)
    b_trials, b_best = _stage_train(student, b_data, 'B',
                                    {1: .12, 2: .28, 3: .12, 4: .31, 5: .17},
                                    out, args, rng, (1, 2, 3, 4, 5), args.epochs)
    # Save exactly one candidate, with the same weights used for the gate.
    candidate = out / 'retention_candidate.pth'
    student.save(candidate, steps=0, level=5, method='dagger_perturbation_rehearsal',
                 independently_gated=False, eligible_for_real_robot=False)
    log_dir = Path('ai_local_planner/logs')
    log_dir.mkdir(parents=True, exist_ok=True)
    reports = {}
    for level in range(1, 6):
        report = evaluate(candidate, level, args.eval_episodes,
                          args.eval_seed + level * 1000, True, args.max_steps)
        reports[level] = report
        (log_dir / f'final_eval_l{level}.json').write_text(
            json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({'final_gate': level,
                          'success_rate': report['success_rate'],
                          'collision_rate': report['collision_rate']}), flush=True)
    final_gate = assess(reports)
    gate_path = log_dir / 'single_actor_l1_to_l5_final_acceptance.json'
    gate_path.write_text(json.dumps(final_gate, indent=2), encoding='utf-8')
    passed = final_gate['simulation_gate_passed']
    if passed:
        # Metadata promotion only after the independent full gate.
        student.save(candidate, 0, 5, method='dagger_perturbation_rehearsal',
                     independently_gated=True, eligible_for_real_robot=False)
    summary = {'checkpoint': str(candidate), 'source': str(args.resume),
               'stage_A_checkpoint': str(a_best), 'stage_B_checkpoint': str(b_best),
               'stage_A_training': a_collected, 'stage_B_training': b_collected,
               'stage_A_gate': a_gate, 'gate': {
                   str(i): dict(reports[i], passed=final_gate['levels'][str(i)]['passed'])
                   for i in reports}, 'all_gates_passed': passed,
               'selected_stage': 'B', 'method': 'DAgger_BC_not_PPO',
               'note': 'Simulation only. Stage-A and Stage-B validation are separate from final seeds.'}
    (out / 'retention_report.json').write_text(
        json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({'final_gate_passed': passed, 'candidate': str(candidate),
                      'gate_file': str(gate_path)}), flush=True)
    return summary
