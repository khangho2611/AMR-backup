"""Export experimental rule-based LiDAR baseline to ONNX Opset 14.

This artifact is intentionally distinct from the PPO local planner and must
never be represented as a PPO-trained checkpoint.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from ai_local_planner.models.reactive_lidar import ReactiveLiDARPolicy
from ai_local_planner.models.reactive_onnx import ReactiveONNXPolicy


def export(path: Path, margin: float = .36) -> dict:
    torch.set_num_threads(1)
    model = ReactiveONNXPolicy(margin=margin).eval()
    path.parent.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(model, torch.zeros(1, 365), str(path), opset_version=14,
                          input_names=['lidar_and_goal_state'], output_names=['cmd_vel'],
                          dynamic_axes={'lidar_and_goal_state': {0: 'batch'},
                                        'cmd_vel': {0: 'batch'}},
                          do_constant_folding=True)
    onnx.checker.check_model(onnx.load(str(path)))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(path), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    rng = np.random.default_rng(78341)
    obs = rng.random((48, 365), dtype=np.float32)
    obs[:, 361:363] = rng.uniform(-1., 1., size=(48, 2))
    obs[:, 364] = rng.uniform(-1., 1., size=48)
    obs[4:8, 361:363] = [0., -1.]
    obs[8:12, 361:363] = [0., 1.]
    # Avoid an artificial plateau of 90 identical returns, which creates
    # exact argmax ties and can flip turn direction across float32/float64.
    obs[12:24, 0:90] = rng.uniform(.01, .06, size=(12, 90))
    with torch.no_grad():
        reference = model(torch.from_numpy(obs)).numpy()
    obtained = session.run(['cmd_vel'], {'lidar_and_goal_state': obs})[0]
    pytorch_parity = float(np.max(np.abs(reference - obtained)))
    numpy_expert = ReactiveLiDARPolicy(margin=margin)
    numpy_output = np.stack([np.array([
        (numpy_expert.act(row)[0][0] + 1.) * .175,
        numpy_expert.act(row)[0][1] * 1.5]) for row in obs])
    numpy_parity = float(np.max(np.abs(numpy_output - obtained)))
    if (obtained.shape != (48, 2) or not np.isfinite(obtained).all()
            or pytorch_parity > 2e-5 or numpy_parity > 2e-5):
        raise RuntimeError(f'ONNX parity failure torch={pytorch_parity}, numpy={numpy_parity}')
    manifest = {
        'model': path.name, 'architecture': 'rule_based_lidar_gap_reference',
        'trained_by_ppo': False, 'opset': 14,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'input': {'name': 'lidar_and_goal_state', 'shape': ['N', 365], 'dtype': 'float32'},
        'output': {'name': 'cmd_vel', 'shape': ['N', 2], 'dtype': 'float32',
                   'units': ['m/s', 'rad/s']},
        'margin_m': margin, 'max_torch_onnx_error': pytorch_parity,
        'max_numpy_onnx_error': numpy_parity,
        'pi4_latency_verified': False, 'real_robot_approved': False,
    }
    path.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--margin', type=float, default=.36)
    args = parser.parse_args()
    print(json.dumps(export(args.output, margin=args.margin), indent=2))
