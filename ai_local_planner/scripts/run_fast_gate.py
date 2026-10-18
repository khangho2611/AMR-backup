"""Independent five-level gate; conditionally export the single actor ONNX.

The checkpoint must already have been trained. Evaluation uses disjoint seeds
and randomized, deterministic mean-policy, closed-loop simulator episodes.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

import torch

from ai_local_planner.scripts.acceptance_gate import assess
from ai_local_planner.scripts.benchmark_latency import benchmark
from ai_local_planner.scripts.evaluate_policy import evaluate
from ai_local_planner.scripts.export_onnx import export, model_fingerprint


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_heldout_seeds(provenance_file: Path, gate_seed: int, episodes: int) -> None:
    """Reject overlap with collection, replay and pilot episodes of this run."""
    if episodes > 1000:
        raise ValueError("The per-level seed windows must not overlap")
    if not provenance_file.is_file():
        raise ValueError("Missing training provenance; cannot certify held-out seeds")
    provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
    config = provenance["config"]
    train_seed = int(config["train_seed"])
    pilot_seed = int(config["pilot_seed"])
    intervals = []
    intervals.append((4, train_seed + 200000, train_seed + 200000 + int(config["episodes"]) - 1))
    for level in (1, 2, 3, 5):
        count = int(config["level2_replay_episodes"] if level == 2 else config["replay_episodes"])
        intervals.append((level, train_seed + level * 10000, train_seed + level * 10000 + count - 1))
    for level in range(1, 6):
        intervals.append((level, pilot_seed + level * 1000,
                          pilot_seed + level * 1000 + int(config["pilot_episodes"]) - 1))
    for level in range(1, 6):
        start = gate_seed + level * 1000
        stop = start + episodes - 1
        for _, historical_start, historical_stop in intervals:
            if start <= historical_stop and historical_start <= stop:
                raise ValueError(f"Level {level} gate seeds overlap training/pilot seeds")
        # Newer DAgger solvers record exact seed sets, including any
        # development-failure seeds subsequently used for local refinements.
        # Never accept a release gate on an episode observed during selection.
        for kind, by_level in provenance.get("seed_sets", {}).items():
            if kind not in ("training", "development", "refinement"):
                raise ValueError(f"Unrecognized provenance seed category: {kind}")
            for values in by_level.values():
                if any(start <= int(value) <= stop for value in values):
                    raise ValueError(f"Level {level} gate seeds overlap {kind} seeds")


def run(checkpoint: Path, seed: int = 20100000, episodes: int = 100):
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)
    if episodes < 100:
        raise ValueError("Independent release gate requires >= 100 episodes/level")
    verify_heldout_seeds(checkpoint.parent / "provenance.json", seed, episodes)
    torch.set_num_threads(1)
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if state.get("metadata", {}).get("independently_gated") is True:
        raise ValueError("Expected unpromoted experimental checkpoint")
    model_sha = sha256(checkpoint)
    weights_sha = model_fingerprint(state["model"])
    reports = {}
    for level in range(1, 6):
        result = evaluate(checkpoint, level, episodes, seed + level * 1000,
                          randomize=True, max_steps=600)
        if sha256(checkpoint) != model_sha:
            raise RuntimeError("Checkpoint changed during independent evaluation")
        result["evaluated_checkpoint_sha256"] = model_sha
        result["evaluated_model_sha256"] = weights_sha
        reports[level] = result
        (checkpoint.parent / f"final_eval_l{level}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"gate_level": level,
                          "success": result["success_rate"],
                          "collision": result["collision_rate"],
                          "timeout": result["timeout_rate"]}), flush=True)

    gate = assess(reports, min_episodes=100)
    (checkpoint.parent / "single_actor_l1_to_l5_final_acceptance.json").write_text(
        json.dumps(gate, indent=2), encoding="utf-8")
    approved = gate["simulation_gate_passed"]
    report = {"checkpoint": str(checkpoint),
              "method": "micro_DAgger_BC_not_PPO",
              "evaluated_checkpoint_sha256": model_sha,
              "evaluated_model_sha256": weights_sha,
              "gate": {str(i): dict(reports[i],
                                     passed=gate["levels"][str(i)]["passed"])
                       for i in range(1, 6)},
              "all_gates_passed": approved,
              "scope": "fixed simulation geometry; real robot and Pi4 not verified"}
    (checkpoint.parent / "retention_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    if not approved:
        print("SIMULATION_GATE_FAILED; official ONNX not exported", flush=True)
        return False

    if sha256(checkpoint) != model_sha:
        raise RuntimeError("Checkpoint changed after evaluation; refusing release")
    # Prepare and validate EVERYTHING in a private staging directory first.
    # The evaluated candidate remains byte-for-byte immutable.
    staging = checkpoint.parent / "verified_release_checkpoint"
    staging.mkdir(exist_ok=False)
    destination = Path("ai_local_planner/exported/local_planner_single_actor_l1_l5.onnx")
    try:
        staged_checkpoint = staging / "gated_model.pth"
        metadata = dict(state.get("metadata", {}))
        metadata.update(independently_gated=True, eligible_for_real_robot=False,
                        evaluated_checkpoint_sha256=model_sha,
                        verified_model_sha256=weights_sha)
        state["metadata"] = metadata
        torch.save(state, staged_checkpoint)
        verified_state = torch.load(staged_checkpoint, map_location="cpu", weights_only=True)
        if model_fingerprint(verified_state["model"]) != weights_sha:
            raise RuntimeError("Staged checkpoint weights differ from evaluated weights")
        staged_report = dict(report, checkpoint=str(staged_checkpoint))
        (staging / "retention_report.json").write_text(
            json.dumps(staged_report, indent=2), encoding="utf-8")
        staged_onnx = staging / destination.name
        manifest = export(staged_checkpoint, staged_onnx)
        latency = benchmark(staged_onnx)
        (checkpoint.parent / "cpu_latency_benchmark.json").write_text(
            json.dumps(latency, indent=2), encoding="utf-8")
        if not latency["target_p99_below_2ms"]:
            print("CPU_P99_GATE_FAILED; official ONNX not exported", flush=True)
            shutil.rmtree(staging)
            return False
        if sha256(checkpoint) != model_sha:
            raise RuntimeError("Evaluated candidate changed before official promotion")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Manifest last: any interrupted promotion fails SHA validation at runtime.
        os.replace(staged_onnx, destination)
        os.replace(staged_onnx.with_suffix(".json"), destination.with_suffix(".json"))
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    print(json.dumps({"gate_passed": True, "onnx": str(destination),
                      "onnx_sha256": manifest["sha256"],
                      "cpu_p99_ms": latency["p99_ms"],
                      "pi4_verified": False}), flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20100000)
    parser.add_argument("--episodes", type=int, default=100)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.checkpoint, args.seed, args.episodes) else 1)


if __name__ == "__main__":
    main()
