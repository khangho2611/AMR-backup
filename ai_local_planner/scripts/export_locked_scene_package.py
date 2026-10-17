"""Build a six-model ONNXRuntime package for the stateful supervisor.

Each ONNX file preserves the 365-D input; specialist motion files output 2-D
physical commands. The scene classifier outputs six logits. The supervisor
adds five stationary frames and selects one model for the episode.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from ai_local_planner.scripts.export_onnx import export as export_actor
from ai_local_planner.scripts.export_reactive_onnx import export as export_gap
from ai_local_planner.scripts.export_scene_classifier_onnx import export as export_cls


def export(reference, corridor, pocket, classifier, output, dynamic_margin=.5):
    if not 0. <= dynamic_margin <= 1.:
        raise ValueError('dynamic_margin must be in [0,1]')
    output.parent.mkdir(parents=True, exist_ok=True)
    root = output.parent
    models = {'reference': 'ppo_levels12.onnx',
              'corridor': 'bc_level3.onnx',
              'pocket': 'bc_level5.onnx',
              'gap_level4': 'gap_level4_margin012.onnx',
              'gap_level6': f'gap_level6_margin{int(round(dynamic_margin * 100)):03d}.onnx',
              'classifier': 'scene_classifier.onnx'}
    checks = {}
    for key, checkpoint in [('reference', reference), ('corridor', corridor),
                            ('pocket', pocket)]:
        checks[key] = export_actor(checkpoint, root / models[key])['sha256']
    checks['gap_level4'] = export_gap(root / models['gap_level4'],
                                      margin=.12)['sha256']
    checks['gap_level6'] = export_gap(root / models['gap_level6'],
                                      margin=dynamic_margin)['sha256']
    checks['classifier'] = export_cls(classifier, root / models['classifier'])['sha256']
    package = {'architecture': 'stateful_scene_locked_multi_onnx',
               'trained_by_single_ppo': False, 'opset': 14,
               'models': models, 'sha256': checks,
               'calibration_frames': 5,
               'dynamic_inflation_margin_m': dynamic_margin,
               'created_utc': datetime.now(timezone.utc).isoformat(),
               'pi4_latency_verified': False, 'real_robot_approved': False,
               'limitations': ['Multiple ONNX sessions; not a single static PPO actor',
                               'Classifier is trained on fixed simulator map families',
                               'Hardware E-stop and LiDAR validity still require validation']}
    output.write_text(json.dumps(package, indent=2), encoding='utf-8')
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--corridor', type=Path, required=True)
    parser.add_argument('--pocket', type=Path, required=True)
    parser.add_argument('--classifier', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dynamic-margin', type=float, default=.5)
    args = parser.parse_args()
    print(json.dumps(export(args.reference, args.corridor, args.pocket,
                            args.classifier, args.output,
                            args.dynamic_margin), indent=2))
