"""Constrained DAgger repair with old-skill rehearsal and independent gates.

Teacher on visited Level-1 states: previously gated PPO Level-1/2 student.
Output constraints on visited Level-2/3 states: current Level-3 DAgger.
This is experimental policy distillation, NOT proof of PPO acceptance.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.scripts.corner_approach_dagger import split_frames
from ai_local_planner.scripts.distill_locked_experts import collect
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.scripts.evaluate_onnx import ONNXAgent
from ai_local_planner.scripts.acceptance_gate import MIN_SUCCESS, MAX_COLLISION
from ai_local_planner.scripts.run_train import passes_level_gate
from ai_local_planner.trainers.ppo_agent import PPOAgent


def sample_task(batch, samples, rng, device):
    obs, acts, weights = batch
    p = weights / weights.sum()
    ix = rng.choice(len(obs), samples, replace=True, p=p)
    return (torch.as_tensor(obs[ix], device=device),
            torch.as_tensor(acts[ix], device=device))


def level2_safety_weights(observations: np.ndarray, near_weight: float = 3.,
                          approach_weight: float = 1.) -> np.ndarray:
    """Prioritize both early obstacle avoidance and close-range corrections.

    Early steering can decide which side of a small obstacle the robot takes.
    A frontal 10th percentile detects narrow targets around 2.8 m while
    suppressing isolated minimum-range points caused by 5% LiDAR dropout.
    The original broader +/-45-degree, 1.2 m near-obstacle weighting remains.
    Only policy observations are used; no privileged pose or level ID is input.
    """
    if observations.ndim != 2 or observations.shape[1] != 365:
        raise ValueError("Expected observations [N,365]")
    near_scan = np.concatenate((observations[:, :46],
                                observations[:, 315:360]), axis=1)
    approach_scan = np.concatenate((observations[:, :26],
                                    observations[:, 335:360]), axis=1)
    near = np.quantile(near_scan, .15, axis=1) < (1.2 - .12) / (12. - .12)
    approach = np.quantile(approach_scan, .10, axis=1) < (2.8 - .12) / (12. - .12)
    return np.maximum(np.where(near, near_weight, 1.),
                      np.where(approach, approach_weight, 1.)).astype(np.float32)


def level4_safety_weights(observations: np.ndarray, near_weight: float = 3.) -> np.ndarray:
    """Oversample close slalom approaches without triggering on isolated dropout.

    5th percentile of a 180-degree forward hemisphere needs many nearby rays;
    single bad returns from the randomized LiDAR are intentionally suppressed.
    Distances use the observation contract's [0.12, 12] metre normalization.
    """
    if observations.ndim != 2 or observations.shape[1] != 365:
        raise ValueError("Expected observations [N,365]")
    scan = np.concatenate((observations[:, :91], observations[:, 270:360]), axis=1)
    close = np.quantile(scan, .10, axis=1) < (.5 - .12) / 11.88
    return np.where(close, near_weight, 1.).astype(np.float32)


def level5_trap_weights(observations: np.ndarray, trap_weight: float = 3.) -> np.ndarray:
    """Emphasize stopped/turning states with a wall in front and on both sides."""
    if observations.ndim != 2 or observations.shape[1] != 365:
        raise ValueError("Expected observations [N,365]")
    front = np.concatenate((observations[:, :26], observations[:, 334:360]), axis=1)
    left = observations[:, 60:121]
    right = observations[:, 239:300]
    trap = (np.quantile(front, .15, axis=1) < (.6 - .12) / 11.88)
    trap &= np.quantile(left, .20, axis=1) < (.7 - .12) / 11.88
    trap &= np.quantile(right, .20, axis=1) < (.7 - .12) / 11.88
    return np.where(trap, trap_weight, 1.).astype(np.float32)


def five_level_budgets(budgets: list[int]) -> dict[int, tuple[int, int]]:
    """Split each level's total demonstration budget across expert and DAgger.

    Expert trajectories come first, remaining episodes visit student states.
    """
    if len(budgets) != 5 or any(episode < 2 for episode in budgets):
        raise ValueError("Exactly five episode budgets >=2 are required")
    return {level: ((count + 1) // 2, count // 2)
            for level, count in enumerate(budgets, start=1)}


def task_loss_weights(max_level: int) -> dict[int, float]:
    """Reserve majority of gradient budget for the verified L1-L3 policy."""
    if max_level != 5:
        raise ValueError("Five-level weighting requires --max-level 5")
    return {1: .15, 2: .18, 3: .19, 4: .25, 5: .23}


def _pilot_score(gates: dict[int, dict]) -> float:
    """Select a candidate without treating a short pilot as acceptance."""
    return sum(2. * min(0., data["success_rate"] - MIN_SUCCESS[level])
               - 3. * max(0., data["collision_rate"] - MAX_COLLISION[level])
               + .05 * data["success_rate"] for level, data in gates.items())


def train_five(args):
    """Train ONE 30-sector policy against 5 specialist teachers, then gate it.

    Fixed held-out test seeds never overlap the demonstration/DAgger seeds.
    Candidate and per-epoch checkpoints remain experimental on gate failure.
    """
    torch.manual_seed(args.seed)
    torch.set_num_threads(1)
    rng = np.random.default_rng(args.seed)
    config = load_config()["ppo"]
    student = PPOAgent(config, "cpu")
    student.initialize_from(args.init_from)
    anchor = PPOAgent(config, "cpu")
    anchor.initialize_from(args.init_from)
    anchor.network.eval().requires_grad_(False)
    experts = {1: anchor, 2: anchor, 3: anchor}
    for level, path in ((4, args.level4_teacher_checkpoint),
                        (5, args.level5_teacher_checkpoint)):
        onnx_path = (args.level4_teacher_onnx if level == 4
                     else args.level5_teacher_onnx)
        if onnx_path is not None:
            if not onnx_path.is_file():
                raise FileNotFoundError(f"Level {level} ONNX teacher missing: {onnx_path}")
            experts[level] = ONNXAgent(onnx_path)
            continue
        if path is None or not path.is_file():
            raise FileNotFoundError(f"Level {level} expert checkpoint missing: {path}")
        teacher = PPOAgent(config, "cpu")
        teacher.initialize_from(path)  # Migrates historical 10-sector experts.
        teacher.network.eval().requires_grad_(False)
        experts[level] = teacher

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    budgets = five_level_budgets(args.episode_budgets)
    frames, descriptions = {}, {}
    for level, (teacher_count, dagger_count) in budgets.items():
        teacher = experts[level]
        base_seed = args.seed + level * 20000
        e_obs, e_actions, e_groups, expert_report = collect(
            teacher, level, teacher_count, base_seed, args.max_steps)
        d_obs, d_actions, d_groups, dagger_report = collect(
            teacher, level, dagger_count, base_seed + 5000, args.max_steps,
            actor=student)
        obs = np.concatenate((e_obs, d_obs))
        actions = np.concatenate((e_actions, d_actions))
        groups = np.concatenate((e_groups, d_groups + teacher_count))
        frames[level] = split_frames((obs, actions, np.ones(len(obs), np.float32), groups),
                                     args.seed + level)
        training, valid = frames[level]
        if level == 4:
            weights = level4_safety_weights(training[0], args.level4_obstacle_weight)
            frames[level] = ((training[0], training[1], weights), valid)
        elif level == 5:
            weights = level5_trap_weights(training[0], args.level5_trap_weight)
            frames[level] = ((training[0], training[1], weights), valid)
        descriptions[str(level)] = {
            "expert": expert_report, "student_initial": dagger_report,
            "teacher_checkpoint": str(args.init_from if level <= 3 else
                                      (getattr(args, f"level{level}_teacher_onnx") or
                                       getattr(args, f"level{level}_teacher_checkpoint"))),
            "teacher_episodes": teacher_count, "dagger_episodes": dagger_count,
            "train_frames": len(frames[level][0][0]),
            "holdout_frames": len(frames[level][1][0]),
        }
        print(json.dumps({"collected_level": level, **descriptions[str(level)]}),
              flush=True)

    weights = task_loss_weights(5)
    optimizer = torch.optim.Adam(student.network.parameters(), lr=args.learning_rate)
    trials = []
    best_score, best_epoch = -float("inf"), 0
    for epoch in range(1, args.epochs + 1):
        student.network.train()
        for _ in range(args.updates_per_epoch):
            optimizer.zero_grad(set_to_none=True)
            total = 0.
            for level, weight in weights.items():
                x, y = sample_task(frames[level][0], args.batch_size, rng,
                                   student.device)
                predicted = torch.tanh(student.network(x)[0])
                scale = args.old_skill_loss_scale if level <= 3 else 1.
                total = total + weight * scale * (predicted - y).square().mean()
            total.backward()
            torch.nn.utils.clip_grad_norm_(student.network.parameters(), 1.)
            optimizer.step()
        student.network.eval()
        with torch.no_grad():
            mse = {}
            for level in range(1, 6):
                x, y, _ = frames[level][1]
                prediction = torch.tanh(student.network(torch.as_tensor(x))[0])
                mse[str(level)] = float((prediction - torch.as_tensor(y)).square().mean())
        epoch_checkpoint = output / f"candidate_epoch_{epoch}.pth"
        student.save(epoch_checkpoint, steps=0, level=5,
                     method="five_level_constrained_dagger_distillation",
                     independently_gated=False, eligible_for_real_robot=False)
        pilot = {}
        if args.pilot_episodes:
            for level in range(1, 6):
                result = evaluate_agent(student, level, args.pilot_episodes,
                                        args.pilot_seed + level * 1000, True,
                                        args.max_steps)
                pilot[level] = result
        score = _pilot_score(pilot) if pilot else -sum(mse.values())
        if score > best_score:
            best_score, best_epoch = score, epoch
        trials.append({"epoch": epoch, "checkpoint": str(epoch_checkpoint),
                       "validation_mse": mse,
                       "pilot_not_acceptance": {str(k): v for k, v in pilot.items()},
                       "pilot_score": score})
        print(json.dumps({"epoch": epoch, "validation_mse": mse,
                          "pilot_success_rates": {str(i): r["success_rate"]
                                                  for i, r in pilot.items()},
                          "best_epoch": best_epoch}), flush=True)
        (output / "training_trials.json").write_text(
            json.dumps(trials, indent=2), encoding="utf-8")

    # Load the selected snapshot and use a disjoint, full 100-seed gate.
    chosen = output / f"candidate_epoch_{best_epoch}.pth"
    student.initialize_from(chosen)
    gate = {}
    for level in range(1, 6):
        result = evaluate_agent(student, level, args.eval_episodes,
                                args.eval_seed + level * 1000, True, args.max_steps)
        result["passed"] = passes_level_gate(result, level)
        gate[str(level)] = result
        print(json.dumps({"gate": level, **result}), flush=True)
    passed = all(result["passed"] for result in gate.values())
    student.optimizer = torch.optim.Adam(student.network.parameters(),
                                         lr=config["learning_rate"], eps=1e-5)
    checkpoint = output / "retention_candidate.pth"
    student.save(checkpoint, steps=0, level=5,
                 method="five_level_constrained_dagger_distillation",
                 selected_epoch=best_epoch, independently_gated=passed,
                 eligible_for_real_robot=False)
    report = {"checkpoint": str(checkpoint), "source": str(args.init_from),
              "architecture": "lidar30_fusion128", "method": "DAgger_BC_not_PPO",
              "teacher_checkpoint_level4": str(args.level4_teacher_checkpoint),
              "teacher_checkpoint_level5": str(args.level5_teacher_checkpoint),
              "effective_teacher_level4": str(args.level4_teacher_onnx or args.level4_teacher_checkpoint),
              "effective_teacher_level5": str(args.level5_teacher_onnx or args.level5_teacher_checkpoint),
              "old_skill_loss_scale": args.old_skill_loss_scale,
              "sample_report": descriptions, "task_loss_weights": weights,
              "selected_epoch": best_epoch, "validation_trials": trials,
              "gate": gate, "all_gates_passed": passed,
              "scope": "Domain-randomized simulation only, fixed curriculum geometry"}
    (output / "retention_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"all_gates_passed": passed, "checkpoint": str(checkpoint)}),
          flush=True)
    return report


def episode_counts(level: int, teacher: int, dagger: int,
                   level2_teacher: int | None, level2_dagger: int | None) -> tuple[int, int]:
    """Increase Level-2 coverage without inflating Level-1/3 rehearsal costs."""
    if level == 2:
        return (level2_teacher if level2_teacher is not None else teacher,
                level2_dagger if level2_dagger is not None else dagger)
    return teacher, dagger


def train(args):
    if args.max_level == 5:
        return train_five(args)
    torch.manual_seed(args.seed)
    torch.set_num_threads(1)
    rng = np.random.default_rng(args.seed)
    config = load_config()["ppo"]
    student = PPOAgent(config, "cpu")
    student.initialize_from(args.init_from)
    old = PPOAgent(config, "cpu")
    old.initialize_from(args.gated_old_checkpoint)
    old.network.eval()
    # Freeze the reference of the Level-2/3 behaviour before optimization.
    anchor = PPOAgent(config, "cpu")
    anchor.initialize_from(args.init_from)
    anchor.network.eval()
    frames = {}
    descriptions = {}
    for level in (1, 2, 3):
        n_teacher, n_dagger = episode_counts(level, args.teacher_episodes,
                                             args.dagger_episodes,
                                             args.level2_teacher_episodes,
                                             args.level2_dagger_episodes)
        label_policy = old if level == 1 or (level == 2 and args.repair_level2) else anchor
        expert_obs, expert_act, expert_groups, expert_report = collect(
            label_policy, level, n_teacher,
            args.seed + level * 20000, args.max_steps)
        online_obs, online_act, online_groups, student_report = collect(
            label_policy, level, n_dagger,
            args.seed + level * 20000 + 5000, args.max_steps, actor=student)
        obs = np.concatenate((expert_obs, online_obs))
        acts = np.concatenate((expert_act, online_act))
        groups = np.concatenate((expert_groups,
                                 online_groups + n_teacher))
        frames[level] = split_frames((obs, acts, np.ones(len(obs), np.float32), groups),
                                     args.seed + level)
        if level == 2 and args.level2_hard_seeds:
            targeted = [collect(old, 2, 1, hard_seed, args.max_steps, actor=student)
                        for hard_seed in args.level2_hard_seeds]
            training, validation = frames[level]
            hard_obs = np.concatenate([item[0] for item in targeted])
            hard_actions = np.concatenate([item[1] for item in targeted])
            training = (np.concatenate((training[0], hard_obs)),
                        np.concatenate((training[1], hard_actions)),
                        np.ones(len(training[0]) + len(hard_obs), np.float32))
            frames[level] = (training, validation)
            print(json.dumps({"hard_seeds": args.level2_hard_seeds,
                              "student_hard_rollouts": [item[3] for item in targeted]}),
                  flush=True)
        if level == 2 and (args.level2_obstacle_weight > 1. or
                           args.level2_approach_weight > 1.):
            training, valid = frames[level]
            weights = level2_safety_weights(training[0], args.level2_obstacle_weight,
                                            args.level2_approach_weight)
            frames[level] = ((training[0], training[1], weights), valid)
        descriptions[str(level)] = dict(expert=expert_report, student=student_report,
                                        train_frames=len(frames[level][0][0]),
                                        holdout_frames=len(frames[level][1][0]))
        print(json.dumps({"collected_level": level, **descriptions[str(level)]}), flush=True)

    optimizer = torch.optim.Adam(student.network.parameters(), lr=args.learning_rate)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    losses = []
    for epoch in range(args.epochs):
        student.network.train()
        for _ in range(args.updates_per_epoch):
            optimizer.zero_grad(set_to_none=True)
            total = 0.
            for level, weight in ((1, args.level1_weight), (2, args.level2_weight),
                                  (3, 1. - args.level1_weight - args.level2_weight)):
                x, y = sample_task(frames[level][0], args.batch_size, rng, student.device)
                predicted = torch.tanh(student.network(x)[0])
                total = total + weight * (predicted - y).square().mean()
            total.backward()
            torch.nn.utils.clip_grad_norm_(student.network.parameters(), 1.)
            optimizer.step()
        student.network.eval()
        with torch.no_grad():
            mse = {}
            for level in (1, 2, 3):
                x, y, _ = frames[level][1]
                prediction = torch.tanh(student.network(torch.as_tensor(x))[0])
                mse[str(level)] = float((prediction - torch.as_tensor(y)).square().mean())
        losses.append(mse)
        print(json.dumps({"epoch": epoch + 1, "validation_mse": mse}), flush=True)
    student.optimizer = torch.optim.Adam(student.network.parameters(),
                                         lr=config["learning_rate"], eps=1e-5)
    checkpoint = output / "retention_candidate.pth"
    student.save(checkpoint, steps=0, level=3, method="constrained_retention_distillation",
                 independently_gated=False, eligible_for_real_robot=False)
    gate = {}
    for level in (1, 2, 3):
        result = evaluate_agent(student, level, args.eval_episodes,
                                args.eval_seed + level * 1000, True, args.max_steps)
        result["passed"] = passes_level_gate(result, level)
        gate[str(level)] = result
        print(json.dumps({"gate": level, **result}), flush=True)
    report = dict(checkpoint=str(checkpoint), source=str(args.init_from),
                  old_teacher=str(args.gated_old_checkpoint), sample_report=descriptions,
                  validation=losses, gate=gate,
                  all_gates_passed=all(x["passed"] for x in gate.values()))
    (output / "retention_report.json").write_text(json.dumps(report, indent=2),
                                                   encoding="utf-8")
    print(json.dumps({"all_gates_passed": report["all_gates_passed"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-from", type=Path, required=True)
    parser.add_argument("--gated-old-checkpoint", type=Path,
                        help="Previously verified L1/L2 teacher for legacy --max-level 3")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-level", type=int, choices=(3, 5), default=3,
                        help="5: five-level DAgger with legacy-expert migration")
    parser.add_argument("--level4-teacher-checkpoint", type=Path,
                        default=Path("ai_local_planner/checkpoints/level4_dagger_reactive_experimental.pth"))
    parser.add_argument("--level5-teacher-checkpoint", type=Path,
                        default=Path("ai_local_planner/checkpoints/level5_bc_reactive_experimental.pth"))
    parser.add_argument("--level4-teacher-onnx", type=Path,
                        help="Verified specialist alternative when legacy L4 teacher is weak")
    parser.add_argument("--level5-teacher-onnx", type=Path,
                        help="Optional verified Level-5 ONNX specialist")
    parser.add_argument("--old-skill-loss-scale", type=float, default=6.,
                        help="Multiply L1-L3 imitation loss to protect retained behavior")
    parser.add_argument("--episode-budgets", type=int, nargs=5,
                        default=[15, 25, 25, 40, 35],
                        metavar="N", help="Total expert+DAgger episodes for L1..L5")
    parser.add_argument("--level4-obstacle-weight", type=float, default=3.)
    parser.add_argument("--level5-trap-weight", type=float, default=3.)
    parser.add_argument("--pilot-episodes", type=int, default=15,
                        help="Per-epoch model selection only, NEVER acceptance")
    parser.add_argument("--pilot-seed", type=int, default=7900000)
    parser.add_argument("--teacher-episodes", type=int, default=20)
    parser.add_argument("--dagger-episodes", type=int, default=20)
    parser.add_argument("--level2-teacher-episodes", type=int,
                        help="Use a larger Level-2 teacher dataset; other levels unchanged")
    parser.add_argument("--level2-dagger-episodes", type=int,
                        help="Use more Level-2 student-visited states; other levels unchanged")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--updates-per-epoch", type=int, default=90)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=0.000008)
    parser.add_argument("--level1-weight", type=float, default=.55)
    parser.add_argument("--level2-weight", type=float, default=.225)
    parser.add_argument("--repair-level2", action="store_true",
                        help="Use the previously gated Level-2 checkpoint as teacher")
    parser.add_argument("--level2-hard-seeds", type=int, nargs="*", default=[],
                        help="Known failure seeds for training only; use different gate seeds")
    parser.add_argument("--level2-obstacle-weight", type=float, default=1.)
    parser.add_argument("--level2-approach-weight", type=float, default=1.,
                        help="Sample weight for Level-2 frontal obstacles visible within 2.8m")
    parser.add_argument("--max-steps", type=int, default=600)
    parser.add_argument("--eval-episodes", type=int, default=100)
    parser.add_argument("--eval-seed", type=int, default=7000000)
    parser.add_argument("--seed", type=int, default=5600000)
    args = parser.parse_args()
    if args.max_level == 5:
        try:
            five_level_budgets(args.episode_budgets)
        except ValueError as err:
            parser.error(str(err))
        if (args.epochs <= 0 or args.updates_per_epoch <= 0 or args.batch_size <= 0
                or args.max_steps <= 0 or args.eval_episodes < 100 or
                args.learning_rate <= 0 or args.pilot_episodes < 0 or
                args.old_skill_loss_scale < 1. or
                min(args.level4_obstacle_weight, args.level5_trap_weight) < 1. or
                args.pilot_seed == args.eval_seed):
            parser.error("Invalid five-level settings (full gate requires >=100 episodes)")
        train_five(args)
        return
    if args.gated_old_checkpoint is None:
        parser.error("--gated-old-checkpoint is required for --max-level 3")
    if (min(args.teacher_episodes, args.dagger_episodes,
            args.epochs,
            args.updates_per_epoch, args.batch_size, args.max_steps,
            args.eval_episodes) <= 0 or args.learning_rate <= 0 or
            min(args.level2_obstacle_weight, args.level2_approach_weight) < 1. or
            any(n is not None and n <= 0 for n in (
                args.level2_teacher_episodes, args.level2_dagger_episodes)) or
            args.level1_weight <= 0 or args.level2_weight <= 0 or
            args.level1_weight + args.level2_weight >= 1):
        parser.error("Invalid retention repair settings")
    train(args)


if __name__ == "__main__":
    main()
