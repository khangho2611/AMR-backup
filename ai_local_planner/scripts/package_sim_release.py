"""Publish the validated single-actor ONNX under the deployment filename.

Only use after run_fast_gate finished both the five-level simulation gate and
host CPU latency check. The manifest deliberately withholds real-AGV approval.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil


DEFAULT_CHECKPOINT_DIR = Path(
    "ai_local_planner/checkpoints/single_actor_fast_gate_pass_20261018")
DEFAULT_EXPORT_DIR = Path("ai_local_planner/exported")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def publish(checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
            export_dir: Path = DEFAULT_EXPORT_DIR) -> dict:
    gate = _json(checkpoint_dir / "single_actor_l1_to_l5_final_acceptance.json")
    report = _json(checkpoint_dir / "retention_report.json")
    latency = _json(checkpoint_dir / "cpu_latency_benchmark.json")
    if not gate.get("simulation_gate_passed") or not report.get("all_gates_passed"):
        raise ValueError("Full independent L1-L5 simulation gate has not passed")
    if not latency.get("target_p99_below_2ms") or latency["p99_ms"] >= 2.:
        raise ValueError("Host CPU p99 must be below 2 ms")
    original_checkpoint = checkpoint_dir / "retention_candidate.pth"
    if _hash(original_checkpoint) != report["evaluated_checkpoint_sha256"]:
        raise ValueError("Checkpoint differs from independently evaluated weights")
    source = export_dir / "local_planner_single_actor_l1_l5.onnx"
    source_manifest = _json(source.with_suffix(".json"))
    if (_hash(source) != source_manifest["sha256"] or
            source_manifest.get("checkpoint_metadata", {}).get("verified_model_sha256") !=
            report["evaluated_model_sha256"]):
        raise ValueError("Official ONNX source does not match evaluated weights")

    destination = export_dir / "local_planner.onnx"
    temp = destination.with_name(destination.name + ".tmp")
    shutil.copyfile(source, temp)
    if _hash(temp) != _hash(source):
        temp.unlink(missing_ok=True)
        raise ValueError("Copied ONNX does not match the gated source")
    os.replace(temp, destination)
    onnx_manifest = {**source_manifest, "model": destination.name}
    _atomic_json(destination.with_suffix(".json"), onnx_manifest)

    metadata = {
        "model_name": "agv_local_planner_single_actor_l1_l5",
        "status": "SIMULATION_GATED_ONLY",
        "framework": "PyTorch -> ONNX",
        "opset_version": source_manifest["opset"],
        "date_exported": datetime.now(timezone.utc).isoformat(),
        "file": destination.name,
        "sha256": _hash(destination),
        "evaluated_checkpoint_sha256": report["evaluated_checkpoint_sha256"],
        "evaluated_weights_sha256": report["evaluated_model_sha256"],
        "input_signature": source_manifest["input"],
        "output_signature": source_manifest["output"],
        "hardware_constraints": {
            "v_min": 0., "v_max": .35, "w_min": -1.5, "w_max": 1.5,
            "near_field_shield_threshold_m": .22,
            "near_field_shield_max_v_m_s": .08,
            "minimum_contiguous_lidar_rays": 5,
            "independent_stm32_estop_verified": False,
            "jack_up_test_verified": False,
        },
        "evaluation_metrics": {
            "randomized_episodes_per_level": 100,
            "levels": gate["levels"],
            "host_cpu_p99_ms": latency["p99_ms"],
            "host_cpu_p99_below_2ms": latency["target_p99_below_2ms"],
            "raspberry_pi_4_p99_verified": False,
        },
        "scope": "Fixed simulator scenario geometry only; not real robot approval",
    }
    _atomic_json(export_dir / "manifest_template.json", metadata)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    args = parser.parse_args()
    result = publish(args.checkpoint_dir, args.export_dir)
    print(json.dumps({"status": result["status"], "file": result["file"],
                      "sha256": result["sha256"],
                      "host_cpu_p99_ms": result["evaluation_metrics"]["host_cpu_p99_ms"]}))


if __name__ == "__main__":
    main()
