"""Read-only AI2 evaluation on actual previously recorded SLAM maps.

No ROS, UART or motor commands. The selected pose and unvisited cells are
synthetic, and results must not be described as physical coverage validation.
"""

import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np


def probe(map_file, model_root):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(model_root))
    from agv_navigation import GridPlanner
    from agv_ai_bridge import ai2_observation, ai2_ranked_candidates
    import onnxruntime as ort

    data = json.loads(map_file.read_text(encoding='utf-8-sig'))
    grid = GridPlanner(data['w'], data['h'], data['res'],
                       (data['ox'], data['oy'], data['yaw']), data['data'],
                       body_radius=.20, margin=.10, budget_s=2.)
    safe_cells = [(x, y) for y in range(grid.h) for x in range(grid.w)
                  if grid.traversable((x, y))]
    if not safe_cells:
        raise ValueError('No traversable cells in recorded map')
    pose_cell = safe_cells[len(safe_cells) // 2]
    pose_world = grid.cell_to_world(*pose_cell)

    candidates = []
    for cell in safe_cells:
        target = grid.cell_to_world(*cell)
        dist = math.dist(pose_world, target)
        if .35 <= dist <= 1.5:
            path = grid.path(pose_world, target)
            if path is not None and len(path) > 1:
                candidates.append((dist, target))
    if len(candidates) < 5:
        raise ValueError('Insufficient reachable candidate cells in captured map')
    candidates.sort(key=lambda item: item[0])

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    sess = ort.InferenceSession(str(model_root / 'models/coverage_model.onnx'),
                                sess_options=opts, providers=['CPUExecutionProvider'])
    feeds = sess.get_inputs()

    def infer_once():
        start_ns = time.perf_counter_ns()
        obs = ai2_observation(grid, pose_cell, candidates, set(), pose_world,
                              data['yaw'], 0, sum(v == 0 for v in data['data']))
        if obs is None:
            raise ValueError('Failed to construct a reachable AI2 observation')
        patch, feat = obs
        result = sess.run(None, {feeds[0].name: patch[None], feeds[1].name: feat[None]})
        action, ranked = ai2_ranked_candidates(candidates, result[0].reshape(-1),
                                                *pose_world, map_yaw=grid.origin[2])
        ms = (time.perf_counter_ns() - start_ns) / 1e6
        return action, ranked, result, patch, feat, ms

    for _ in range(10):
        infer_once()
    measurements = [infer_once() for _ in range(100)]
    action, ranked, result, patch, feat, ms = measurements[-1]
    times = [entry[-1] for entry in measurements]
    return dict(map_file=map_file.name, map_dimensions=[grid.w, grid.h],
                map_resolution=grid.res, safe_cells=len(safe_cells),
                robot_pose_source='synthetic_pose_on_recorded_real_slam_map',
                robot_cell=pose_cell, candidates=len(candidates),
                ai2_input_map=list(patch.shape), ai2_input_features=list(feat.shape),
                finite_q=bool(np.isfinite(result[0]).all()),
                q_values=result[0].reshape(-1).tolist(), action=int(action),
                baseline_nearest=list(candidates[0][1]),
                ai2_ranked_goal=list(ranked[0][1]),
                pipeline_p50_ms=round(float(np.percentile(times, 50)), 4),
                pipeline_p99_ms=round(float(np.percentile(times, 99)), 4),
                notes='Recorded occupancy map, synthetic position and unvisited state; no live SLAM/motion')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-root', type=pathlib.Path, required=True)
    ap.add_argument('maps', nargs='+', type=pathlib.Path)
    args = ap.parse_args()
    print(json.dumps([probe(path, args.model_root) for path in args.maps],
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
