"""Export frozen six-level hybrid and verify real PyTorch/ONNX parity."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.models.actor_critic import ActorCritic
from ai_local_planner.models.scene_classifier import SceneClassifier
from ai_local_planner.models.scene_routed import SceneRoutedMeanPolicy


def export(reference: Path, corridor: Path, pocket: Path,
           classifier: Path, destination: Path):
    torch.set_num_threads(1)
    experts = []
    for checkpoint in (reference, corridor, pocket):
        state = torch.load(checkpoint, map_location='cpu', weights_only=True)
        model = ActorCritic().eval()
        model.load_state_dict(state['model'])
        experts.append(model)
    cdata = torch.load(classifier, map_location='cpu', weights_only=True)
    class_net = SceneClassifier().eval()
    class_net.load_state_dict(cdata['model'])
    policy = SceneRoutedMeanPolicy(*experts, class_net).eval()

    destination.parent.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(policy, torch.zeros(1, 365), str(destination),
                          opset_version=14,
                          input_names=['lidar_and_goal_state'],
                          output_names=['cmd_vel'],
                          dynamic_axes={'lidar_and_goal_state': {0: 'batch'},
                                        'cmd_vel': {0: 'batch'}},
                          do_constant_folding=True)
    onnx.checker.check_model(onnx.load(str(destination)))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(destination), sess_options=options,
                                   providers=['CPUExecutionProvider'])

    rng = np.random.default_rng(1188)
    samples = [rng.random((30, 365), dtype=np.float32)]
    for level in range(1, 7):
        env = AGVMotionEnv(level=level, randomize=True)
        try:
            for seed in range(3):
                observation, _ = env.reset(seed=1100000 + 100 * level + seed)
                samples.append(observation[None, :])
        finally:
            env.close()
    obs = np.concatenate(samples).astype(np.float32)
    with torch.no_grad():
        expected = policy(torch.from_numpy(obs)).numpy()
        categories = class_net(torch.from_numpy(obs)).argmax(-1).numpy()
    actual = session.run(['cmd_vel'], {'lidar_and_goal_state': obs})[0]
    error = float(np.max(np.abs(actual - expected)))
    if actual.shape != expected.shape or not np.isfinite(actual).all() or error > 2e-5:
        raise RuntimeError(f'Hybrid ONNX parity failed: {error}, {actual.shape}')

    manifest = {
        'model': destination.name,
        'architecture': 'six_scene_classifier_hybrid_frozen_experts',
        'trained_by_ppo': False,
        'components': {'reference_ppo': str(reference),
                       'corridor_bc_dagger': str(corridor),
                       'pocket_bc': str(pocket),
                       'scene_classifier': str(classifier),
                       'level4_gap_margin_m': .12,
                       'level6_gap_margin_m': .36},
        'classification_validation_accuracy': cdata['validation_accuracy'],
        'opset': 14,
        'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'input': {'name': 'lidar_and_goal_state', 'shape': ['N', 365],
                  'dtype': 'float32'},
        'output': {'name': 'cmd_vel', 'shape': ['N', 2], 'dtype': 'float32',
                   'units': ['m/s', 'rad/s']},
        'max_torch_onnx_error': error,
        'parity_scene_classes': sorted(set(int(c) for c in categories)),
        'pi4_latency_verified': False,
        'real_robot_approved': False,
        'status': 'experimental_pending_six_level_closed_loop_acceptance',
    }
    destination.with_suffix('.json').write_text(
        json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--corridor', type=Path, required=True)
    parser.add_argument('--pocket', type=Path, required=True)
    parser.add_argument('--classifier', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.reference, args.corridor, args.pocket,
                            args.classifier, args.output), indent=2))


if __name__ == '__main__':
    main()
