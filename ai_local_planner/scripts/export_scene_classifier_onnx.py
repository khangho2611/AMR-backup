"""Export scene classifier logits to ONNX opset 14 with SHA manifest."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from ai_local_planner.models.scene_classifier import SceneClassifier


def export(checkpoint: Path, output: Path):
    torch.set_num_threads(1)
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)
    model = SceneClassifier().eval()
    model.load_state_dict(state['model'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(model, torch.zeros((1, 365)), str(output),
                          opset_version=14,
                          input_names=['lidar_and_goal_state'],
                          output_names=['scene_logits'],
                          dynamic_axes={'lidar_and_goal_state': {0: 'batch'},
                                        'scene_logits': {0: 'batch'}})
    onnx.checker.check_model(onnx.load(str(output)))
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    sess = ort.InferenceSession(str(output), sess_options=opts,
                                providers=['CPUExecutionProvider'])
    samples = np.random.default_rng(388).random((45, 365), dtype=np.float32)
    with torch.no_grad():
        expected = model(torch.from_numpy(samples)).numpy()
    actual = sess.run(['scene_logits'], {'lidar_and_goal_state': samples})[0]
    error = float(np.max(np.abs(actual - expected)))
    if (actual.shape != (45, 6) or error > 1e-4 or
            not np.array_equal(actual.argmax(-1), expected.argmax(-1))):
        raise RuntimeError(f'Classifier ONNX parity failed {error}')
    manifest = {'model': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                'architecture': 'six_level_scene_classifier', 'trained_by_ppo': False,
                'source_checkpoint': str(checkpoint), 'opset': 14,
                'input': {'name': 'lidar_and_goal_state', 'shape': ['N', 365],
                          'dtype': 'float32'},
                'output': {'name': 'scene_logits', 'shape': ['N', 6],
                           'dtype': 'float32'},
                'max_torch_onnx_error': error,
                'validation_accuracy': state['validation_accuracy'],
                'pi4_latency_verified': False, 'real_robot_approved': False}
    output.with_suffix('.json').write_text(json.dumps(manifest, indent=2),
                                           encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.checkpoint, args.output), indent=2))
