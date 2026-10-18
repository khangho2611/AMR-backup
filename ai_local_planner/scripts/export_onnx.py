"""Export deterministic mean policy, validate ONNX parity and write manifest."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from ai_local_planner.models.actor_critic import (ActorCritic, ContextualResidualActorCritic,
                                                  ConservativeContextualResidualActorCritic,
                                                  DirectionalContextualResidualActorCritic, MeanPolicy,
                                                  is_legacy_state_dict)


def model_fingerprint(weights: dict) -> str:
    """Stable digest of the gated weights, independent of checkpoint metadata."""
    digest = hashlib.sha256()
    for name, tensor in sorted(weights.items()):
        if not isinstance(tensor, torch.Tensor):
            raise TypeError(f"Expected tensor for model key {name!r}")
        cpu = tensor.detach().cpu().contiguous()
        digest.update(json.dumps([name, str(cpu.dtype), list(cpu.shape)]).encode())
        # Version buffers such as directional_pool_version are 0-D int64;
        # PyTorch cannot reinterpret a 0-D Long tensor as uint8 directly.
        digest.update(cpu.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def export(checkpoint: Path, destination: Path) -> dict:
    torch.set_num_threads(1)
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    legacy = is_legacy_state_dict(state["model"])
    if destination.name == "local_planner_single_ppo.onnx":
        metadata = state.get("metadata", {})
        report = metadata.get("heldout_evaluation", {})
        prior = report.get("retention_levels", {})
        from ai_local_planner.scripts.run_train import passes_level_gate
        final_level = int(state.get("level", 0))
        if (legacy or final_level < 5 or
                metadata.get("full_l1_l5_gate") is not True or
                not report or not passes_level_gate(report, final_level) or
                any(str(level) not in prior or
                    not passes_level_gate(prior[str(level)], level)
                    for level in range(1, min(final_level, 6)))):
            raise ValueError("Official single PPO export requires passing the full randomized "
                             "100-episode L1-L5 checkpoint gate with 30-sector architecture")
    if destination.name == "local_planner_single_actor_l1_l5.onnx":
        from ai_local_planner.scripts.run_train import passes_level_gate

        report_file = checkpoint.parent / "retention_report.json"
        metadata = state.get("metadata", {})
        valid = (not legacy and int(state.get("level", 0)) >= 5 and
                 metadata.get("independently_gated") is True and
                 report_file.is_file())
        if valid:
            report = json.loads(report_file.read_text(encoding="utf-8"))
            gates = report.get("gate", {})
            valid = (report.get("all_gates_passed") is True and
                     Path(report.get("checkpoint", "")).resolve() == checkpoint.resolve() and
                     metadata.get("verified_model_sha256") == model_fingerprint(state["model"]) and
                     metadata.get("verified_model_sha256") == report.get("evaluated_model_sha256") and
                     metadata.get("evaluated_checkpoint_sha256") == report.get("evaluated_checkpoint_sha256") and
                     set(gates) == {str(i) for i in range(1, 6)} and
                     all(passes_level_gate(gates[str(i)], i) for i in range(1, 6)))
        if not valid:
            raise ValueError("Official L1-L5 single actor export requires passing the full randomized "
                             "100-episode five-level gate for this exact checkpoint")
    contextual = any(key.startswith('correction.') for key in state['model'])
    conservative = 'gate_min_probability' in state['model']
    directional = 'directional_pool_version' in state['model']
    network = (DirectionalContextualResidualActorCritic() if directional else
               ConservativeContextualResidualActorCritic() if conservative else
               ContextualResidualActorCritic() if contextual else ActorCritic(legacy=legacy)).eval()
    network.load_state_dict(state["model"])
    policy = MeanPolicy(network).eval()
    destination.parent.mkdir(parents=True, exist_ok=True)
    example = torch.zeros(1, 365, dtype=torch.float32)
    with torch.no_grad():
        torch.onnx.export(policy, example, str(destination), opset_version=14,
                          input_names=["lidar_and_goal_state"], output_names=["cmd_vel"],
                          dynamic_axes={"lidar_and_goal_state": {0: "batch"},
                                        "cmd_vel": {0: "batch"}},
                          do_constant_folding=True)
    onnx.checker.check_model(onnx.load(str(destination)))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(destination), sess_options=options,
                                   providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(91)
    samples = rng.uniform(0., 1., (32, 365)).astype(np.float32)
    samples[:, 361:363] = rng.uniform(-1, 1, (32, 2))
    samples[:, 364] = rng.uniform(-1, 1, 32)
    with torch.no_grad():
        reference = policy(torch.from_numpy(samples)).numpy()
    actual = session.run(["cmd_vel"], {"lidar_and_goal_state": samples})[0]
    maximum_error = float(np.max(np.abs(reference - actual)))
    if maximum_error >= 1e-5 or actual.shape != (32, 2):
        raise RuntimeError(f"ONNX parity failed: shape={actual.shape}, max_err={maximum_error}")
    sha = hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest = {
        "model": destination.name, "opset": 14, "sha256": sha,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_checkpoint": str(checkpoint), "training_steps": state.get("steps", 0),
        "curriculum_level": state.get("level"),
        "checkpoint_metadata": state.get("metadata", {}),
        "input": {"name": "lidar_and_goal_state", "shape": ["N", 365], "dtype": "float32",
                  "lidar_normalization": "clip((range_m-0.12)/11.88,0,1)",
                  "angles": "0..359 degrees, counterclockwise from forward"},
        "output": {"name": "cmd_vel", "shape": ["N", 2], "dtype": "float32",
                   "units": ["m/s", "rad/s"], "v_range": [0., .35], "w_range": [-1.5, 1.5]},
        "max_torch_onnx_error": maximum_error,
        "pi4_latency_verified": False, "real_robot_approved": False,
        "deployment_note": "Training quality, real LiDAR alignment, independent E-stop, and Pi4 p99<2ms require separate validation",
    }
    manifest_path = destination.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=Path("ai_local_planner/exported/local_planner.onnx"))
    args = parser.parse_args()
    report = export(args.checkpoint, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
