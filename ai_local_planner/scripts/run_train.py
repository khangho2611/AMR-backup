"""Train PPO, log per-episode statistics, promote six curriculum levels."""

import argparse
from collections import deque
import csv
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.scripts.acceptance_gate import MIN_SUCCESS, MAX_COLLISION
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.trainers.ppo_agent import PPOAgent
from ai_local_planner.trainers.rollout_buffer import RolloutBuffer


def passes_level_gate(report: dict, level: int, min_episodes: int = 100) -> bool:
    """Accept deterministic policy only after a full randomized test batch."""
    return (report.get("domain_randomization") is True and
            int(report["level"]) == level and
            int(report["episodes"]) >= min_episodes and
            float(report["success_rate"]) >= MIN_SUCCESS[level] - 1e-9 and
            float(report["collision_rate"]) <= MAX_COLLISION[level] + 1e-9)


def can_promote(report: dict, retention_enabled: bool = True) -> bool:
    """Require current-level acceptance and zero regressions in earlier levels."""
    if not report["current_passed"]:
        return False
    return not retention_enabled or report["retention_passed"]


def restore_episode_history(log_path: Path, history: dict[int, deque]) -> int:
    """Continue per-level rolling statistics and episode IDs on resume."""
    if not log_path.is_file() or log_path.stat().st_size == 0:
        return 0
    completed = 0
    with log_path.open("r", newline="", encoding="utf-8") as stream:
        for entry in csv.DictReader(stream):
            level = int(entry["level"])
            if level not in history:
                raise ValueError(f"Invalid logged level {level}: {log_path}")
            history[level].append(float(entry["success"]))
            completed = max(completed, int(entry["episode"]))
    return completed


def train(args):
    config = load_config(args.config)
    p = config["ppo"]
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    agent = PPOAgent(p, device=args.device)
    # Tiny Conv1D batches are generally faster without many CPU threads.
    if agent.device.type == "cpu":
        torch.set_num_threads(1)
    start_step, level = 0, args.level
    if args.init_from:
        state = agent.initialize_from(args.init_from)
        print(f"Initialized 30-sector student from {args.init_from} "
              f"(source level={state.get('level')}; fresh optimizer)", flush=True)
    if args.resume:
        state = agent.load(args.resume)
        start_step, level = int(state["steps"]), int(state["level"])
    if level > args.max_level:
        raise ValueError(f"Checkpoint starts at Level {level}, above --max-level {args.max_level}")
    if args.learning_rate is not None:
        if args.learning_rate <= 0:
            raise ValueError("--learning-rate must be positive")
        for group in agent.optimizer.param_groups:
            group["lr"] = args.learning_rate
    default_teacher = (Path("ai_local_planner/exported/") /
                       "locked_scene_margin070_experimental/package.json")
    reference = args.reference_checkpoint or args.reference_package
    if reference is None and not args.no_teacher and default_teacher.is_file():
        reference = default_teacher
    if reference is not None and not args.no_teacher:
        agent.set_reference_policy(reference, args.reference_coef)
        print(f"PPO teacher anchor: {reference} (coef={args.reference_coef})", flush=True)
    env = AGVMotionEnv(level=level, randomize=True, max_steps=args.max_episode_steps,
                       config=config)
    obs, _ = env.reset(seed=args.seed)
    buffer = RolloutBuffer()
    history = {i: deque(maxlen=config["curriculum"]["eval_window_episodes"])
               for i in range(1, 7)}
    # Compare both success and quality; retain a strong BC warm start even
    # when early PPO exploration temporarily damages the deterministic actor.
    best_score = (-1., float("-inf"))
    best_retained_score = (-1., float("-inf"))
    episode_reward = 0.
    run_dir = Path(args.output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "episodes.csv"
    episode_count = restore_episode_history(log_path, history)
    log_file = open(log_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(log_file,
                            fieldnames=["episode", "timesteps", "level", "reward", "steps",
                                        "success", "collision", "success_rate_100"])
    if log_path.stat().st_size == 0:
        writer.writeheader()
    timesteps = start_step
    awaiting_bootstrap = False
    start_time = time.perf_counter()

    def record_evaluation(step: int):
        nonlocal best_score, best_retained_score
        report = evaluate_agent(agent, level=level, episodes=args.eval_episodes,
                                seed=args.eval_seed, randomize=True,
                                max_steps=args.max_episode_steps)
        retention = {}
        retention_passed = True
        if args.retention_eval and level > 1:
            for earlier in range(1, level):
                prior = evaluate_agent(agent, level=earlier,
                                       episodes=args.eval_episodes,
                                       seed=args.eval_seed + earlier * 1000,
                                       randomize=True,
                                       max_steps=args.max_episode_steps)
                prior['passed'] = passes_level_gate(prior, earlier)
                retention[str(earlier)] = prior
                retention_passed &= prior['passed']
        report['retention_levels'] = retention
        report['retention_passed'] = retention_passed
        current_passed = passes_level_gate(report, level)
        report['current_passed'] = current_passed
        report["training_steps"] = step
        print(f"heldout_eval {json.dumps(report)}", flush=True)
        with open(run_dir / "evaluations.jsonl", "a", encoding="utf-8") as stream:
            stream.write(json.dumps(report) + "\n")
        score = (report["success_rate"], report["mean_reward"])
        if score > best_score:
            best_score = score
            agent.save(run_dir / f"best_level_{level}.pth", step,
                       level, heldout_evaluation=report)
        if step > 0 and retention_passed and current_passed and score > best_retained_score:
            best_retained_score = score
            accepted_levels = sorted([level, *map(int, retention.keys())])
            agent.save(run_dir / "best_model.pth", step, level,
                       heldout_evaluation=report,
                       accepted_levels=accepted_levels,
                       full_l1_l5_gate=(level >= 5 and args.retention_eval and
                                        all(i in accepted_levels for i in range(1, 6))),
                       reference_teacher=str(reference) if reference else None)
        return report

    try:
        if args.eval_on_start:
            record_evaluation(timesteps)
        while timesteps < (args.steps if args.steps is not None else p["total_timesteps"]):
            batch_steps = min(args.rollout_steps or p["rollout_steps"],
                              (args.steps if args.steps is not None else p["total_timesteps"]) - timesteps)
            for _ in range(batch_steps):
                action, value, logp = agent.act(obs)
                reference_action = agent.reference_action(obs, env.level)
                if awaiting_bootstrap:
                    buffer.finish_last(value)
                    awaiting_bootstrap = False
                next_obs, reward, terminated, truncated, info = env.step(action)
                # Next step's actor pass supplies V(s') without a second forward.
                # TimeLimit needs its terminal observation value before reset.
                next_value = (agent.value(next_obs) if truncated else 0.)
                buffer.add(obs, action, logp, reward, value, next_value,
                           terminated, truncated, reference_action=reference_action)
                awaiting_bootstrap = not (terminated or truncated)
                episode_reward += reward
                timesteps += 1
                obs = next_obs
                if terminated or truncated:
                    episode_count += 1
                    level_history = history[env.level]
                    level_history.append(float(info["success"]))
                    success_rate = sum(level_history) / len(level_history)
                    record = dict(episode=episode_count, timesteps=timesteps, level=env.level,
                                  reward=round(episode_reward, 3), steps=info["steps"],
                                  success=info["success"], collision=info["collision"],
                                  success_rate_100=round(success_rate, 4))
                    writer.writerow(record)
                    log_file.flush()
                    print(json.dumps(record, ensure_ascii=False), flush=True)
                    episode_reward = 0.
                    if level > 1 and random.random() < args.rehearsal_prob:
                        env.set_level(random.randrange(1, level))
                    else:
                        env.set_level(level)
                    obs, _ = env.reset()
            if awaiting_bootstrap:
                buffer.finish_last(agent.value(obs))
                awaiting_bootstrap = False
            statistics = agent.update(buffer, epochs=args.epochs, batch_size=args.batch_size)
            print(f"update steps={timesteps} level={level} "+
                  " ".join(f"{k}={v:.4f}" for k, v in statistics.items()), flush=True)
            if (args.eval_every and
                    (timesteps // args.eval_every > (timesteps - batch_steps) // args.eval_every or
                     timesteps == (args.steps if args.steps is not None else p["total_timesteps"]))):
                report = record_evaluation(timesteps)
                if (args.early_stop_success_floor is not None and
                        report["success_rate"] < args.early_stop_success_floor):
                    print(f"EARLY STOP: Level {level} success {report['success_rate']:.1%} "
                          f"below {args.early_stop_success_floor:.1%}; best_model retained",
                          flush=True)
                    break
                # Promotion relies on held-out deterministic successes, not noisy
                # exploratory training episodes. The fixed eval has 100 seeds.
                if (can_promote(report, retention_enabled=args.retention_eval) and
                        level < args.max_level):
                    level += 1
                    if args.curriculum_warmstart_dir:
                        candidate = (args.curriculum_warmstart_dir /
                                     f"candidate_level_{level}.pth")
                        if not candidate.is_file():
                            raise FileNotFoundError(f"Missing offline Level {level} candidate: {candidate}")
                        resumed = agent.load(candidate)
                        if int(resumed["level"]) != level:
                            raise ValueError(f"Offline checkpoint level mismatch: {candidate}")
                        print(f"Loaded offline warm start for Level {level}: {candidate}",
                              flush=True)
                    best_score = (-1., float("-inf"))
                    best_retained_score = (-1., float("-inf"))
                    history[level].clear()
                    env.set_level(level)
                    obs, _ = env.reset()
                    print(f"CURRICULUM PROMOTED -> {level} after independent evaluation", flush=True)
            if timesteps // args.save_every > (timesteps - batch_steps) // args.save_every:
                agent.save(run_dir / f"checkpoint_step_{timesteps}.pth", timesteps,
                           level, episodes=episode_count)
        agent.save(run_dir / "latest_model.pth", timesteps, level,
                   episodes=episode_count, elapsed_seconds=time.perf_counter() - start_time)
    except KeyboardInterrupt:
        # A long simulator training job can be interrupted at the console.
        # Preserve an exact continuation point rather than losing unfinished PPO.
        agent.save(run_dir / "interrupted_model.pth", timesteps, level,
                   episodes=episode_count, elapsed_seconds=time.perf_counter() - start_time)
        print(f"Interrupted: recover using --resume {run_dir / 'interrupted_model.pth'}",
              flush=True)
        raise
    finally:
        log_file.close()
        env.close()
    print(f"Training checkpoint: {run_dir / 'latest_model.pth'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--steps", type=int, help="Absolute total timesteps (default: config 5M)")
    parser.add_argument("--rollout-steps", type=int)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--level", type=int, choices=range(1, 7), default=1)
    parser.add_argument("--max-level", type=int, choices=range(1, 7), default=6,
                        help="Highest curriculum level to train (use 2 to refine Level 2)")
    parser.add_argument("--max-episode-steps", type=int, default=600)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--init-from", type=Path,
                        help="Initialize actor weights from prior checkpoint without its level, steps or optimizer")
    parser.add_argument("--learning-rate", type=float,
                        help="Override Adam LR even after restoring optimizer state")
    parser.add_argument("--reference-checkpoint", type=Path,
                        help="Verified policy to constrain PPO via action imitation")
    parser.add_argument("--reference-package", type=Path,
                        help="Multi-level teacher package.json; dispatch offline by simulator episode level")
    parser.add_argument("--no-teacher", action="store_true",
                        help="Opt out of automatic locked_scene_margin070 teacher anchor")
    parser.add_argument("--reference-coef", type=float, default=10.,
                        help="Coefficient for reference-policy action MSE on rollout states")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("ai_local_planner/checkpoints"))
    parser.add_argument("--save-every", type=int, default=10_000,
                        help="Save a resumable PPO checkpoint periodically (default 10k steps)")
    parser.add_argument("--eval-every", type=int, default=25_000,
                        help="Steps between held-out deterministic evaluations (0 disables)")
    parser.add_argument("--eval-episodes", type=int, default=100)
    parser.add_argument("--eval-seed", type=int, default=100000)
    parser.add_argument("--eval-on-start", action="store_true",
                        help="Evaluate and preserve the initial/resumed policy before PPO updates")
    parser.add_argument("--rehearsal-prob", type=float, default=0.,
                        help="Probability of training each new episode on a previously passed level")
    parser.add_argument("--curriculum-warmstart-dir", type=Path,
                        help="Optional offline candidate_level_N.pth loaded only after passing Level N-1")
    parser.add_argument("--retention-eval", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Require prior levels to meet acceptance thresholds before promotion")
    parser.add_argument("--early-stop-success-floor", type=float,
                        help="Stop PPO when a held-out evaluation falls below this success rate")
    args = parser.parse_args()
    if args.rollout_steps is not None and args.rollout_steps < 1:
        parser.error("--rollout-steps must be positive")
    if args.save_every <= 0:
        parser.error("--save-every must be positive")
    if args.eval_every < 0 or args.eval_episodes < 1:
        parser.error("--eval-every cannot be negative and --eval-episodes must be positive")
    if args.reference_checkpoint and args.reference_coef <= 0:
        parser.error("--reference-coef must be positive with --reference-checkpoint")
    if args.reference_package and args.reference_checkpoint:
        parser.error("Choose either --reference-package or --reference-checkpoint")
    if args.resume and args.init_from:
        parser.error("Choose either --resume or --init-from")
    if (args.reference_package or not args.no_teacher) and args.reference_coef <= 0:
        parser.error("--reference-coef must be positive for teacher anchoring")
    if args.epochs is not None and args.epochs < 1:
        parser.error("--epochs must be positive")
    if args.batch_size is not None and args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if (args.early_stop_success_floor is not None and
            not 0. <= args.early_stop_success_floor <= 1.):
        parser.error("--early-stop-success-floor must be in [0,1]")
    if not 0. <= args.rehearsal_prob < 1.:
        parser.error("--rehearsal-prob must be in [0,1)")
    train(args)


if __name__ == "__main__":
    main()
