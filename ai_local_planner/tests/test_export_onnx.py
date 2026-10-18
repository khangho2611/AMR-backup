"""Export contract must be self-contained and loadable by the Pi4 runtime."""

import json
import numpy as np
import pytest
import torch

from ai_local_planner.configs.settings import load_config
from ai_local_planner.runtime import LocalPlannerRuntime
from ai_local_planner.scripts.export_onnx import export, model_fingerprint


def test_fingerprint_supports_scalar_version_buffers_and_catches_changes():
    weights = {"version": torch.tensor(1, dtype=torch.int64),
               "head": torch.tensor([1., 2.], dtype=torch.float32)}
    original = model_fingerprint(weights)
    assert original == model_fingerprint(dict(reversed(list(weights.items()))))
    assert original != model_fingerprint({**weights, "version": torch.tensor(2)})
from ai_local_planner.trainers.ppo_agent import PPOAgent


def test_export_and_guarded_onnx_inference(tmp_path):
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    checkpoint = tmp_path / "test_model.pth"
    agent.save(checkpoint, 123, 1)
    exported = tmp_path / "local_planner.onnx"
    metadata = export(checkpoint, exported)
    assert metadata["training_steps"] == 123
    assert metadata["max_torch_onnx_error"] < 1e-5
    assert metadata["real_robot_approved"] is False
    runtime = LocalPlannerRuntime(exported)
    raw = np.full(360, 5., dtype=np.float32)
    cmd = runtime.predict_from_sensors(raw, (1., 2., 0.), (4., 2.), 0., 0.)
    assert cmd.shape == (2,) and 0. <= cmd[0] <= .05
    danger = raw.copy()
    danger[22] = .13
    assert np.all(runtime.predict_from_sensors(danger, (1., 2., 0.),
                                               (4., 2.), 0., 0.) == 0.)
    # Any accidental partial update to the model is rejected by SHA integrity.
    with open(exported, "ab") as stream:
        stream.write(b"invalid")
    with pytest.raises(ValueError, match="SHA256"):
        LocalPlannerRuntime(exported)


def test_official_single_ppo_export_requires_full_l1_l5_gate(tmp_path):
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    candidate = tmp_path / "partial.pth"
    agent.save(candidate, 5000, 2)
    output = tmp_path / "local_planner_single_ppo.onnx"
    with pytest.raises(ValueError, match="full randomized"):
        export(candidate, output)
    assert not output.exists()


def test_official_single_actor_l1_l5_export_rejects_ungated_candidate(tmp_path):
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    candidate = tmp_path / "retention_candidate.pth"
    agent.save(candidate, 0, 5, method="five_level_constrained_dagger_distillation",
               independently_gated=False)
    output = tmp_path / "local_planner_single_actor_l1_l5.onnx"
    with pytest.raises(ValueError, match="full randomized"):
        export(candidate, output)
    assert not output.exists()


def test_official_single_actor_export_checks_full_evidence(tmp_path):
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    candidate = tmp_path / "retention_candidate.pth"
    agent.save(candidate, 0, 5, independently_gated=True)
    state = torch.load(candidate, map_location="cpu", weights_only=True)
    weights_sha = model_fingerprint(state["model"])
    evaluated_checkpoint_sha = "b" * 64
    state["metadata"].update(verified_model_sha256=weights_sha,
                             evaluated_checkpoint_sha256=evaluated_checkpoint_sha)
    torch.save(state, candidate)
    gates = {str(i): {"level": i, "episodes": 100, "success_rate": 1.,
                      "collision_rate": 0., "domain_randomization": True}
             for i in range(1, 6)}
    report_file = tmp_path / "retention_report.json"
    report_file.write_text(json.dumps({"checkpoint": str(candidate),
                                        "all_gates_passed": True, "gate": gates,
                                        "evaluated_model_sha256": weights_sha,
                                        "evaluated_checkpoint_sha256": evaluated_checkpoint_sha}),
                           encoding="utf-8")
    output = tmp_path / "local_planner_single_actor_l1_l5.onnx"
    assert export(candidate, output)["opset"] == 14
    # L4 is the advanced slalom: .12 is allowed; .13 must refuse export.
    gates["4"]["collision_rate"] = .13
    report_file.write_text(json.dumps({"checkpoint": str(candidate),
                                        "all_gates_passed": True, "gate": gates,
                                        "evaluated_model_sha256": weights_sha,
                                        "evaluated_checkpoint_sha256": evaluated_checkpoint_sha}),
                           encoding="utf-8")
    output.unlink()
    with pytest.raises(ValueError, match="full randomized"):
        export(candidate, output)
    assert not output.exists()


def test_official_export_detects_tampered_weights(tmp_path):
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    candidate = tmp_path / "gated.pth"
    agent.save(candidate, 0, 5, independently_gated=True)
    state = torch.load(candidate, map_location="cpu", weights_only=True)
    initial_digest = model_fingerprint(state["model"])
    state["metadata"]["verified_model_sha256"] = initial_digest
    state["metadata"]["evaluated_checkpoint_sha256"] = "a" * 64
    gates = {str(i): {"level": i, "episodes": 100, "success_rate": 1.,
                      "collision_rate": 0., "domain_randomization": True}
             for i in range(1, 6)}
    (tmp_path / "retention_report.json").write_text(json.dumps({
        "checkpoint": str(candidate), "all_gates_passed": True, "gate": gates,
        "evaluated_model_sha256": initial_digest,
        "evaluated_checkpoint_sha256": "a" * 64}), encoding="utf-8")
    first_weight = next(value for value in state["model"].values() if value.is_floating_point())
    first_weight.reshape(-1)[0] += .1
    torch.save(state, candidate)
    output = tmp_path / "local_planner_single_actor_l1_l5.onnx"
    with pytest.raises(ValueError, match="full randomized"):
        export(candidate, output)
    assert not output.exists()
