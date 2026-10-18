"""Publication is refused on failed gates and keeps the ONNX hash verifiable."""

import hashlib
import json

import pytest

from ai_local_planner.scripts.package_sim_release import publish


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_release_only_after_simulation_and_latency_gates(tmp_path):
    checkpoint = tmp_path / "checkpoints"
    exported = tmp_path / "exported"
    checkpoint.mkdir()
    exported.mkdir()
    candidate = checkpoint / "retention_candidate.pth"
    candidate.write_bytes(b"checked student")
    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    model = exported / "local_planner_single_actor_l1_l5.onnx"
    model.write_bytes(b"validated ONNX")
    model_hash = hashlib.sha256(model.read_bytes()).hexdigest()
    _write(model.with_suffix(".json"), {
        "sha256": model_hash, "opset": 14,
        "input": {"shape": ["N", 365]}, "output": {"shape": ["N", 2]},
        "checkpoint_metadata": {"verified_model_sha256": "w" * 64}})
    _write(checkpoint / "single_actor_l1_to_l5_final_acceptance.json", {
        "simulation_gate_passed": False,
        "levels": {str(i): {"passed": True} for i in range(1, 6)}})
    _write(checkpoint / "retention_report.json", {
        "all_gates_passed": True, "evaluated_checkpoint_sha256": candidate_hash,
        "evaluated_model_sha256": "w" * 64})
    _write(checkpoint / "cpu_latency_benchmark.json", {
        "target_p99_below_2ms": True, "p99_ms": 1.5})
    with pytest.raises(ValueError, match="simulation gate"):
        publish(checkpoint, exported)
    assert not (exported / "local_planner.onnx").exists()
    _write(checkpoint / "single_actor_l1_to_l5_final_acceptance.json", {
        "simulation_gate_passed": True,
        "levels": {str(i): {"passed": True} for i in range(1, 6)}})
    manifest = publish(checkpoint, exported)
    assert manifest["status"] == "SIMULATION_GATED_ONLY"
    assert (exported / "local_planner.onnx").read_bytes() == model.read_bytes()
    assert json.loads((exported / "local_planner.json").read_text())["sha256"] == model_hash
    assert json.loads((exported / "manifest_template.json").read_text())["sha256"] == model_hash
    assert manifest["evaluation_metrics"]["raspberry_pi_4_p99_verified"] is False
