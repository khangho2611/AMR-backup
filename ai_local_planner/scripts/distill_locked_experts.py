"""Offline 1→6 expert imitation to warm-start ONE ActorCritic for later PPO.

The teacher is a separately verified ONNX specialist per level. The student
sees ONLY the 365-D observation, never ground-truth level or obstacle geometry.
Teacher labels are produced offline; held-out MSE is split by whole episodes.
This process is behavioral cloning, NOT PPO, and does not confer safety approval.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.models.locked_scene_onnx_agent import LockedSceneONNXAgent
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.scripts.pretrain_obstacle_expert import episode_split
from ai_local_planner.scripts.run_train import passes_level_gate
from ai_local_planner.trainers.ppo_agent import PPOAgent


def collect(expert, level: int, episodes: int, seed: int, max_steps: int,
            actor: PPOAgent | None = None):
    """Run teacher or student, always label with that level's ONNX specialist."""
    env = AGVMotionEnv(level=level, randomize=True, max_steps=max_steps)
    observations, labels, groups = [], [], []
    successes = collisions = 0
    try:
        for episode in range(episodes):
            obs, _ = env.reset(seed=seed + episode)
            for _ in range(max_steps):
                label, _, _ = expert.act(obs, deterministic=True)
                command = (actor.act(obs, deterministic=True)[0]
                           if actor is not None else label)
                observations.append(obs)
                labels.append(label)
                groups.append(episode)
                obs, _, terminated, truncated, info = env.step(command)
                if terminated or truncated:
                    successes += int(info["success"])
                    collisions += int(info["collision"])
                    break
    finally:
        env.close()
    return (np.asarray(observations, dtype=np.float32),
            np.asarray(labels, dtype=np.float32),
            np.asarray(groups, dtype=np.int32),
            {"episodes": episodes, "success_rate": successes / episodes,
             "collision_rate": collisions / episodes})


def build_balanced_split(by_level: dict, seed: int, frames_per_level: int):
    """Keep disjoint episode groups and equally capped data from each level."""
    train_obs, train_act, valid_obs, valid_act = [], [], [], []
    distribution = {}
    for level, (obs, actions, groups) in sorted(by_level.items()):
        train_ids, valid_ids = episode_split(groups, seed + level)
        rng = np.random.default_rng(seed + level * 2017)
        if len(train_ids) > frames_per_level:
            train_ids = rng.choice(train_ids, frames_per_level, replace=False)
        if len(valid_ids) > max(1, frames_per_level // 10):
            valid_ids = rng.choice(valid_ids, max(1, frames_per_level // 10),
                                   replace=False)
        train_obs.append(obs[train_ids])
        train_act.append(actions[train_ids])
        valid_obs.append(obs[valid_ids])
        valid_act.append(actions[valid_ids])
        distribution[level] = {"train_frames": len(train_ids),
                               "heldout_frames": len(valid_ids),
                               "episodes": int(np.unique(groups).size)}
    return (np.concatenate(train_obs), np.concatenate(train_act),
            np.concatenate(valid_obs), np.concatenate(valid_act), distribution)


def distill(args):
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(1)
    package = LockedSceneONNXAgent(args.package)
    agent = PPOAgent(load_config()["ppo"], device=args.device)
    if args.resume:
        agent.load(args.resume)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    optimizer = torch.optim.Adam(agent.network.parameters(), lr=args.learning_rate)
    by_level = {}
    summaries = []
    for level in range(1, args.max_level + 1):
        expert = package.experts[level - 1]
        obs, acts, groups, teacher_report = collect(
            expert, level, args.episodes_per_level, args.seed + level * 10000,
            args.max_steps)
        if args.dagger_episodes:
            dobs, dacts, dgroups, student_report = collect(
                expert, level, args.dagger_episodes,
                args.seed + level * 10000 + 5000, args.max_steps, actor=agent)
            obs = np.concatenate((obs, dobs))
            acts = np.concatenate((acts, dacts))
            groups = np.concatenate((groups, dgroups + args.episodes_per_level))
        else:
            student_report = None
        by_level[level] = obs, acts, groups
        train_obs, train_actions, valid_obs, valid_actions, balance = (
            build_balanced_split(by_level, args.seed, args.frames_per_level))
        device = agent.device
        x = torch.as_tensor(train_obs, device=device)
        y = torch.as_tensor(train_actions, device=device)
        vx = torch.as_tensor(valid_obs, device=device)
        vy = torch.as_tensor(valid_actions, device=device)
        for epoch in range(args.epochs_per_level):
            agent.network.train()
            order = torch.randperm(len(x), device=device)
            for indices in order.split(args.batch_size):
                prediction = torch.tanh(agent.network(x[indices])[0])
                loss = F.mse_loss(prediction, y[indices])
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(agent.network.parameters(), 1.)
                optimizer.step()
        agent.network.eval()
        with torch.no_grad():
            validation_mse = float(F.mse_loss(torch.tanh(agent.network(vx)[0]), vy))
        # Restore the standard PPO optimizer; BC optimizer state is not PPO state.
        agent.optimizer = torch.optim.Adam(agent.network.parameters(),
                                           lr=agent.config["learning_rate"], eps=1e-5)
        checkpoint = output / f"candidate_level_{level}.pth"
        agent.save(checkpoint, steps=0, level=level,
                   method="offline_expert_behavioral_cloning",
                   validation_episode_split=True, validation_mse=validation_mse,
                   independently_gated=False, eligible_for_real_robot=False)
        evaluations = {}
        for tested_level in range(1, level + 1):
            if args.eval_episodes:
                report = evaluate_agent(agent, tested_level, args.eval_episodes,
                                        seed=args.seed + 100000 + tested_level * 1000,
                                        max_steps=args.max_steps)
                report["passed"] = passes_level_gate(report, tested_level)
                evaluations[str(tested_level)] = report
        summary = {"candidate": str(checkpoint), "stage": level,
                   "student_type": "one_actor_critic", "algorithm": "BC_warmstart_not_PPO",
                   "teacher_rollout": teacher_report, "dagger_rollout": student_report,
                   "validation_mse": validation_mse, "balanced_frames": balance,
                   "evaluations": evaluations,
                   "all_gates_passed": bool(evaluations) and
                                       all(v["passed"] for v in evaluations.values())}
        summaries.append(summary)
        print(json.dumps({"stage": level, "teacher_success": teacher_report["success_rate"],
                          "heldout_mse": validation_mse,
                          "gates_passed": summary["all_gates_passed"]}), flush=True)
        (output / "distillation_report.json").write_text(
            json.dumps(summaries, indent=2), encoding="utf-8")
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-level", type=int, choices=range(1, 7), default=6)
    parser.add_argument("--episodes-per-level", type=int, default=40)
    parser.add_argument("--dagger-episodes", type=int, default=20)
    parser.add_argument("--frames-per-level", type=int, default=15000)
    parser.add_argument("--epochs-per-level", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=0.00003)
    parser.add_argument("--max-steps", type=int, default=600)
    parser.add_argument("--eval-episodes", type=int, default=0,
                        help="Evaluate each new candidate on ALL stages so far")
    parser.add_argument("--seed", type=int, default=4700000)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if (args.episodes_per_level < 2 or args.dagger_episodes < 0 or
            args.frames_per_level < 1 or args.epochs_per_level < 1 or
            args.batch_size < 1 or args.learning_rate <= 0 or
            args.max_steps < 1 or args.eval_episodes < 0):
        parser.error("Invalid training settings")
    distill(args)


if __name__ == "__main__":
    main()
