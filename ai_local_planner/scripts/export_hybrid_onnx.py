"""Export the two-specialist experimental model as a standalone ONNX 14 file.

Inference computes both specialists, so this model MUST be timed separately
on a Raspberry Pi 4. It is not a drop-in real-robot safety approval.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from ai_local_planner.models.actor_critic import ActorCritic
from ai_local_planner.models.hybrid_policy import (CorridorRoutedMeanPolicy,
                                                   RANGE_THRESHOLD_NORMALIZED,
                                                   MIN_CLOSE_RAYS)


def export(reference: Path, specialist: Path, destination: Path) -> dict:
    torch.set_num_threads(1)
    networks = []
    for path in (reference, specialist):
        state = torch.load(path, map_location="cpu", weights_only=True)
        network = ActorCritic().eval()
        network.load_state_dict(state["model"])
        networks.append(network)
    policy = CorridorRoutedMeanPolicy(*networks).eval()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(policy, torch.zeros(1, 365), str(destination),
                          opset_version=14, input_names=["lidar_and_goal_state"],
                          output_names=["cmd_vel"],
                          dynamic_axes={"lidar_and_goal_state": {0: "batch"},
                                        "cmd_vel": {0: "batch"}},
                          do_constant_folding=True)
    onnx.checker.check_model(onnx.load(str(destination)))

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    session = ort.InferenceSession(str(destination), sess_options=opts,
                                   providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(7788)
    # Exercise both branches AND the decision boundary; random LiDAR values
    # alone almost never look like the narrow Level 3 corridor.
    samples = rng.uniform(.15, 1., size=(64, 365)).astype(np.float32)
    samples[:, 361:363] = rng.uniform(-1., 1., size=(64, 2))
    samples[:, 364] = rng.uniform(-1., 1., size=64)
    samples[16:48, 55:125] = .02
    samples[16:48, 235:305] = .02
    samples[48:, 55:55 + MIN_CLOSE_RAYS] = RANGE_THRESHOLD_NORMALIZED - .001
    samples[48:, 235:235 + MIN_CLOSE_RAYS - 1] = RANGE_THRESHOLD_NORMALIZED - .001
    with torch.no_grad():
        torch_out = policy(torch.from_numpy(samples)).numpy()
    ort_out = session.run(["cmd_vel"], {"lidar_and_goal_state": samples})[0]
    max_error = float(np.max(np.abs(torch_out - ort_out)))
    if ort_out.shape != (64, 2) or max_error > 1e-5:
        raise RuntimeError(f"Hybrid ONNX parity failed: {max_error}, shape={ort_out.shape}")

    manifest = {
        "model": destination.name, "opset": 14,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_checkpoint": str(reference),
        "specialist_checkpoint": str(specialist),
        "architecture": "frozen_two_policy_lidar_router",
        "input": {"name": "lidar_and_goal_state", "shape": ["N", 365],
                  "dtype": "float32", "angles": "0..359 CCW from forward",
                  "lidar_normalization": "clip((range_m-0.12)/11.88,0,1)"},
        "output": {"name": "cmd_vel", "shape": ["N", 2], "dtype": "float32",
                   "units": ["m/s", "rad/s"], "v_range": [0., .35],
                   "w_range": [-1.5, 1.5]},
        "routing": {"range_threshold_m": .72, "min_close_rays_per_side": MIN_CLOSE_RAYS,
                    "left_slice": [55, 125], "right_slice": [235, 305]},
        "max_torch_onnx_error": max_error,
        "pi4_latency_verified": False, "real_robot_approved": False,
        "deployment_note": "Experimental multi-policy routing on fixed L corridor. "
                           "Pi4 p99<2ms, varied corridor geometry, LiDAR dropouts, "
                           "and independent hardware E-stop not validated.",
    }
    destination.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--specialist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.reference, args.specialist, args.output), indent=2))


if __name__ == "__main__":
    main()
