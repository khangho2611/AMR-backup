"""Level-3 corner DAgger with episode-disjoint validation and Level-1/2 replay.

The specialist supervises observations visited by the shared student actor.
Privileged pose is used only to weight training samples, never as model input.
Candidates remain experimental until a separate 100-seed acceptance gate.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.models.locked_scene_onnx_agent import LockedSceneONNXAgent
from ai_local_planner.scripts.distill_locked_experts import collect
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.scripts.pretrain_obstacle_expert import episode_split
from ai_local_planner.scripts.run_train import passes_level_gate
from ai_local_planner.trainers.ppo_agent import PPOAgent


CORNER_XY = np.array([3.65, 1.85], dtype=np.float64)


def corner_weight(pose_xy, scan, corner_xy=CORNER_XY) -> float:
    """3x if near the 90-degree turn OR any true frontal +/-15 ray <1.2m."""
    ranges = np.asarray(scan)
    if ranges.shape != (360,):
        raise ValueError("Expected 360 LiDAR rays")
    distance = float(np.linalg.norm(np.asarray(pose_xy) - corner_xy))
    front = float(np.min(np.concatenate((ranges[-15:], ranges[:16]))))
    return 3. if distance < 1.5 or front < 1.2 else 1.


def weighted_actor_mse(prediction, labels, weights):
    """Normalize by total weights, so larger corner weights stay 3x."""
    return ((prediction - labels).square().mean(dim=-1) * weights).sum() / weights.sum()


def mixed_rehearsal_loss(prediction, labels, weights, is_replay,
                         rehearsal_fraction=.35):
    """Reserve exactly 35% gradient budget for old levels, after 3x weighting.

    Corner weights apply inside the corner partition, without reducing the
    contribution from Levels 1-2. Minibatches contain both partitions.
    """
    if not bool(is_replay.any()) or not bool((~is_replay).any()):
        raise ValueError("Mixed minibatch requires both replay and corner frames")
    replay_loss = weighted_actor_mse(
        prediction[is_replay], labels[is_replay], weights[is_replay])
    corner_loss = weighted_actor_mse(
        prediction[~is_replay], labels[~is_replay], weights[~is_replay])
    return rehearsal_fraction * replay_loss + (1. - rehearsal_fraction) * corner_loss


def collect_corner(expert, actor, episodes: int, seed: int, max_steps: int,
                   group_offset: int = 0):
    """Collect expert-labelled frames under either expert or student actions."""
    env = AGVMotionEnv(level=3, randomize=True, max_steps=max_steps)
    obs_data, labels, weights, groups = [], [], [], []
    success = collisions = brake_labels = corner_frames = 0
    try:
        for episode in range(episodes):
            obs, _ = env.reset(seed=seed + episode)
            for _ in range(max_steps):
                label, _, _ = expert.act(obs, deterministic=True)
                weight = corner_weight(env.pose[:2], env._true_scan)
                obs_data.append(obs)
                labels.append(label)
                weights.append(weight)
                groups.append(group_offset + episode)
                corner_frames += int(weight == 3.)
                # Normalized policy action -1 => v=0; -0.7142857 => v=.05.
                brake_labels += int(weight == 3. and label[0] <= (2. * .05 / .35 - 1.))
                command = actor.act(obs, deterministic=True)[0] if actor is not None else label
                obs, _, done, truncated, info = env.step(command)
                if done or truncated:
                    success += int(info["success"])
                    collisions += int(info["collision"])
                    break
    finally:
        env.close()
    return (np.asarray(obs_data, dtype=np.float32),
            np.asarray(labels, dtype=np.float32),
            np.asarray(weights, dtype=np.float32),
            np.asarray(groups, dtype=np.int32),
            {"episodes": episodes, "success_rate": success / episodes,
             "collision_rate": collisions / episodes, "corner_frames": corner_frames,
             "brake_teacher_labels_at_corner": brake_labels,
             "braking_label_fraction": brake_labels / max(1, corner_frames)})


def split_frames(data, seed: int):
    obs, labels, weights, groups = data
    train, valid = episode_split(groups, seed)
    return ((obs[train], labels[train], weights[train]),
            (obs[valid], labels[valid], weights[valid]))


def fit_round(agent, replay, corner, epochs, batch_size, learning_rate, seed,
              rehearsal_fraction=.35):
    """35% replay frames, 65% corner frames per epoch, weighted 3x on corner."""
    rng = np.random.default_rng(seed)
    optimizer = torch.optim.Adam(agent.network.parameters(), lr=learning_rate)
    old_a, old_y, old_w = replay
    corner_a, corner_y, corner_w = corner
    epoch_size = max(len(corner_a), batch_size)
    prior_n = round(epoch_size * rehearsal_fraction)
    corner_n = epoch_size - prior_n
    if min(len(old_a), len(corner_a)) == 0:
        raise ValueError("Both replay and corner training frames are required")
    for _ in range(epochs):
        indices_old = rng.choice(len(old_a), size=prior_n, replace=True)
        indices_corner = rng.choice(len(corner_a), size=corner_n, replace=True)
        obs = np.concatenate((old_a[indices_old], corner_a[indices_corner]))
        labels = np.concatenate((old_y[indices_old], corner_y[indices_corner]))
        weights = np.concatenate((old_w[indices_old], corner_w[indices_corner]))
        replay_mask = np.concatenate((np.ones(prior_n, dtype=bool),
                                      np.zeros(corner_n, dtype=bool)))
        perm = rng.permutation(len(obs))
        agent.network.train()
        for inds in np.array_split(perm, max(1, int(np.ceil(len(perm) / batch_size)))):
            x = torch.as_tensor(obs[inds], device=agent.device)
            y = torch.as_tensor(labels[inds], device=agent.device)
            w = torch.as_tensor(weights[inds], device=agent.device)
            mask = torch.as_tensor(replay_mask[inds], device=agent.device)
            pred = torch.tanh(agent.network(x)[0])
            if not bool(mask.any()) or not bool((~mask).any()):
                continue
            loss = mixed_rehearsal_loss(pred, y, w, mask, rehearsal_fraction)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(agent.network.parameters(), 1.)
            optimizer.step()
    # PPO requires fresh Adam moments for its own clipped objective.
    agent.optimizer = torch.optim.Adam(agent.network.parameters(),
                                       lr=agent.config["learning_rate"], eps=1e-5)
    agent.network.eval()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path(
        "ai_local_planner/exported/locked_scene_margin070_experimental/package.json"))
    parser.add_argument("--init-from", type=Path, required=True)
    parser.add_argument("--replay-checkpoint", type=Path,
                        help="Gate-passed student policy to label and drive Level 1/2 replay")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--teacher-episodes", type=int, default=24)
    parser.add_argument("--replay-episodes", type=int, default=16)
    parser.add_argument("--dagger-episodes", type=int, default=24)
    parser.add_argument("--dagger-rounds", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=.00002)
    parser.add_argument("--rehearsal-fraction", type=float, default=.35)
    parser.add_argument("--max-steps", type=int, default=600)
    parser.add_argument("--eval-episodes", type=int, default=100)
    parser.add_argument("--eval-seed", type=int, default=5100000)
    parser.add_argument("--seed", type=int, default=4800000)
    args = parser.parse_args()
    if (args.teacher_episodes < 2 or args.replay_episodes < 2 or
            args.dagger_episodes < 2 or args.dagger_rounds < 1 or args.epochs < 1 or
            args.batch_size < 1 or args.learning_rate <= 0 or
            not 0. < args.rehearsal_fraction < 1. or args.eval_episodes < 1):
        parser.error("Invalid DAgger configuration")
    torch.manual_seed(args.seed)
    torch.set_num_threads(1)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    package = LockedSceneONNXAgent(args.package)
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    agent.initialize_from(args.init_from)
    replay_expert = None
    if args.replay_checkpoint:
        replay_expert = PPOAgent(load_config()["ppo"], device="cpu")
        replay_expert.initialize_from(args.replay_checkpoint)
        replay_expert.network.eval()
    replay_train_parts, replay_valid_parts = [], []
    for level in (1, 2):
        source = replay_expert if replay_expert is not None else package.experts[level - 1]
        obs, labels, groups, report = collect(source, level,
            args.replay_episodes, args.seed + level * 10000, args.max_steps)
        training, validation = split_frames((obs, labels,
              np.ones(len(obs), np.float32), groups), args.seed + level * 10)
        replay_train_parts.append(training)
        replay_valid_parts.append(validation)
        print(json.dumps({"replay_level": level, **report}), flush=True)
    # Equal representation of old levels within the fixed 35% replay budget;
    # otherwise long Level-2 episodes dwarf the easier Level-1 corridor.
    rng = np.random.default_rng(args.seed)
    n_train = min(len(part[0]) for part in replay_train_parts)
    n_valid = min(len(part[0]) for part in replay_valid_parts)
    def balanced(parts, n):
        indexes = [rng.choice(len(p[0]), n, replace=False) for p in parts]
        return tuple(np.concatenate([p[k][ind] for p, ind in zip(parts, indexes)])
                     for k in range(3))
    replay_train = balanced(replay_train_parts, n_train)
    replay_valid = balanced(replay_valid_parts, n_valid)

    expert = package.experts[2]
    initial = collect_corner(expert, None, args.teacher_episodes, args.seed + 30000,
                             args.max_steps)
    corner_data = list(initial[:4])
    report = {"teacher": initial[4], "rounds": [], "starting_checkpoint": str(args.init_from),
              "replay_teacher": str(args.replay_checkpoint) if args.replay_checkpoint else str(args.package),
              "training": {"corner_weight": 3., "rehearsal_fraction": args.rehearsal_fraction,
                           "rehearsal_fraction_of_loss": args.rehearsal_fraction,
                           "max_steps": args.max_steps}}
    print(json.dumps({"teacher_level3": initial[4]}), flush=True)
    for iteration in range(args.dagger_rounds):
        student_data = collect_corner(expert, agent, args.dagger_episodes,
            args.seed + 40000 + iteration * 2000, args.max_steps,
            group_offset=(iteration + 1) * 100000)
        for j in range(4):
            corner_data[j] = np.concatenate((corner_data[j], student_data[j]))
        corner_train, corner_valid = split_frames(corner_data, args.seed + 103)
        fit_round(agent, replay_train, corner_train, args.epochs, args.batch_size,
                  args.learning_rate, args.seed + iteration, args.rehearsal_fraction)
        with torch.no_grad():
            validation = {}
            for name, dataset in (("replay", replay_valid), ("corner", corner_valid)):
                xo, ya, wa = dataset
                x = torch.as_tensor(xo, device=agent.device)
                y = torch.as_tensor(ya, device=agent.device)
                w = torch.as_tensor(wa, device=agent.device)
                validation[name] = float(weighted_actor_mse(
                    torch.tanh(agent.network(x)[0]), y, w))
        checkpoint = output / f"dagger_round_{iteration + 1}.pth"
        agent.save(checkpoint, steps=0, level=3, method="weighted_corner_DAgger",
                   teacher= str(args.package), validation=validation,
                   independently_gated=False, eligible_for_real_robot=False)
        item = {"round": iteration + 1, "student_rollout": student_data[4],
                "validation_mse": validation, "checkpoint": str(checkpoint),
                "train_frames_replay": len(replay_train[0]),
                "train_frames_corner": len(corner_train[0])}
        report["rounds"].append(item)
        print(json.dumps(item), flush=True)
        (output / "corner_dagger_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")

    evaluations = {}
    for level in (1, 2, 3):
        result = evaluate_agent(agent, level=level, episodes=args.eval_episodes,
                                seed=args.eval_seed + level * 1000, randomize=True,
                                max_steps=args.max_steps)
        result["passed"] = passes_level_gate(result, level)
        evaluations[str(level)] = result
        print(json.dumps({"gate": level, **result}), flush=True)
    report["acceptance_gate"] = evaluations
    report["all_gates_passed"] = all(x["passed"] for x in evaluations.values())
    (output / "corner_dagger_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"all_gates_passed": report["all_gates_passed"]}), flush=True)


if __name__ == "__main__":
    main()
