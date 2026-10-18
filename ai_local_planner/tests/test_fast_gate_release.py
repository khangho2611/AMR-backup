"""A failing CPU release gate must leave the evaluated candidate untouched."""

import hashlib
import json
from pathlib import Path

import pytest
import torch

from ai_local_planner.scripts import run_fast_gate


def _provenance(folder: Path):
    data = {"config": {"train_seed": 22300000, "pilot_seed": 22400000,
                       "episodes": 40, "replay_episodes": 10,
                       "level2_replay_episodes": 40, "pilot_episodes": 20}}
    (folder / "provenance.json").write_text(json.dumps(data), encoding="utf-8")


def test_refuse_overlapping_collection_and_pilot_seeds(tmp_path):
    _provenance(tmp_path)
    with pytest.raises(ValueError, match="overlap"):
        # L4 collection seeds: 22500000..22500039.
        run_fast_gate.verify_heldout_seeds(tmp_path / "provenance.json",
                                           22496000, 100)
    run_fast_gate.verify_heldout_seeds(tmp_path / "provenance.json",
                                       20100000, 100)


def test_latency_failure_never_promotes_model(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    checkpoint = tmp_path / "candidate.pth"
    torch.save({"model": {"weight": torch.tensor([1., 2.])},
                "metadata": {"independently_gated": False}, "level": 5}, checkpoint)
    _provenance(tmp_path)
    original_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()

    def fake_evaluate(path, level, episodes, seed, randomize, max_steps):
        assert path == checkpoint and episodes == 100 and randomize is True
        return {"checkpoint": str(path), "level": level, "episodes": episodes,
                "seed_start": seed, "domain_randomization": True,
                "success_rate": 1., "collision_rate": 0., "timeout_rate": 0.}

    def fake_export(source, destination):
        assert source.name == "gated_model.pth"
        assert torch.load(source, weights_only=True)["metadata"]["independently_gated"] is True
        destination.write_bytes(b"mock candidate ONNX")
        destination.with_suffix(".json").write_text("{}", encoding="utf-8")
        return {"sha256": "test"}

    def fake_benchmark(path):
        assert path.name == "local_planner_single_actor_l1_l5.onnx"
        assert "verified_release_checkpoint" in str(path)
        return {"p99_ms": 2.5, "target_p99_below_2ms": False}

    monkeypatch.setattr(run_fast_gate, "evaluate", fake_evaluate)
    monkeypatch.setattr(run_fast_gate, "export", fake_export)
    monkeypatch.setattr(run_fast_gate, "benchmark", fake_benchmark)

    assert run_fast_gate.run(checkpoint, seed=20100000, episodes=100) is False
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == original_hash
    assert not (tmp_path / "ai_local_planner/exported/local_planner_single_actor_l1_l5.onnx").exists()
    assert not (tmp_path / "verified_release_checkpoint").exists()
