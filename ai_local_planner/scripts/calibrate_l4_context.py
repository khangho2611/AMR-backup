"""Experimental calibration of the in-network L4 scene gate.

Use only new development seeds here. This is a hyperparameter search, never
an independent acceptance gate or evidence of deployment readiness.
"""

import argparse
import json
from pathlib import Path

import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.scripts.evaluate_policy import evaluate_agent
from ai_local_planner.trainers.ppo_agent import PPOAgent


def score_reports(reports):
    l2, l4 = reports["2"], reports["4"]
    return ((l4["success_rate"] - 2.5 * l4["collision_rate"]
             - 3.0 * l4["timeout_rate"])
            + 2.0 * (l2["success_rate"] - 4.0 * l2["collision_rate"]))


def load_with_l4_bias(source: Path, shift: float):
    agent = PPOAgent(load_config()["ppo"], "cpu")
    state = agent.initialize_from(source)
    if not hasattr(agent.network, "context_scene"):
        raise ValueError("Source must contain a contextual ActorCritic")
    with torch.no_grad():
        agent.network.context_scene.head[-1].bias[3].add_(shift)
    agent.network.eval()
    return agent, state


def run(args):
    if args.episodes < 1 or args.retention_episodes < 1:
        raise ValueError("Episode budgets must be positive")
    if not args.source.is_file():
        raise FileNotFoundError(args.source)
    if not args.shifts or len(set(args.shifts)) != len(args.shifts):
        raise ValueError("Provide distinct shifts including zero")
    if 0.0 not in args.shifts:
        raise ValueError("A zero-shift baseline is required")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    trials = []
    for shift in args.shifts:
        agent, _ = load_with_l4_bias(args.source, shift)
        reports = {str(level): evaluate_agent(
            agent, level, args.episodes,
            args.dev_seed + level * 1000, True, args.max_steps)
            for level in (2, 4)}
        entry = {"l4_bias_shift": shift, "score": score_reports(reports),
                 "development_not_acceptance": reports}
        trials.append(entry)
        print(json.dumps({"shift": shift, "score": entry["score"],
                          "l2": [reports["2"]["success_rate"], reports["2"]["collision_rate"]],
                          "l4": [reports["4"]["success_rate"], reports["4"]["collision_rate"],
                                 reports["4"]["timeout_rate"]]}), flush=True)
        (args.output_dir / "calibration_trials.json").write_text(
            json.dumps(trials, indent=2), encoding="utf-8")

    baseline = next(t for t in trials if t["l4_bias_shift"] == 0.0)
    # A shift that provides no measurable benefit should not replace the
    # unmodified source. Preserve the original policy on exact score ties.
    selected = max(trials, key=lambda t: (t["score"], -abs(t["l4_bias_shift"])))
    selected_agent, _ = load_with_l4_bias(args.source, selected["l4_bias_shift"])
    retention = {str(level): evaluate_agent(
        selected_agent, level, args.retention_episodes,
        args.dev_seed + 100000 + level * 1000, True, args.max_steps)
        for level in (1, 3, 5)}
    # Never overwrite an existing candidate and never mark this as gated.
    destination = args.output_dir / "experimental_candidate.pth"
    if destination.exists():
        raise FileExistsError(destination)
    selected_agent.save(destination, 0, 5,
                        method="experimental_l4_context_bias_calibration",
                        independently_gated=False, eligible_for_real_robot=False)
    summary = {"source": str(args.source), "candidate": str(destination),
               "selected_shift": selected["l4_bias_shift"],
               "selected_score": selected["score"],
               "zero_shift_score": baseline["score"],
               "development_only": True, "acceptance_gate_passed": False,
               "retention_development": retention, "trials": trials}
    (args.output_dir / "calibration_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"candidate": str(destination),
                      "selected_shift": selected["l4_bias_shift"],
                      "score": selected["score"], "baseline_score": baseline["score"],
                      "retention": {k: v["success_rate"] for k, v in retention.items()}}),
          flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--shifts", type=float, nargs="*",
                        default=[-.75, -.35, 0., .35, .75, 1.25, 2.])
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--retention-episodes", type=int, default=30)
    parser.add_argument("--dev-seed", type=int, default=19200000)
    parser.add_argument("--max-steps", type=int, default=600)
    run(parser.parse_args())
