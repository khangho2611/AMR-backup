"""Read-only audit of the current V1 contract; never trains or controls hardware."""
from pathlib import Path
import hashlib
import json
import random
import sys
import time
from collections import deque

import numpy as np
import onnx
import onnxruntime as ort
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from train_coverage_20000 import FastGridCoverageEnv, DRLCoverageCNN


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reachable(env):
    seen = {(env.ry, env.rx)}
    queue = deque(seen)
    while queue:
        y, x = queue.popleft()
        for dy, dx in env.actions:
            p = (y + dy, x + dx)
            if (0 <= p[0] < env.size and 0 <= p[1] < env.size
                    and p not in seen and env.grid[p] != env.OBSTACLE):
                seen.add(p)
                queue.append(p)
    return len(seen)


def nearest_uncovered_action(env):
    start = (env.ry, env.rx)
    queue = deque([(start, None)])
    seen = {start}
    while queue:
        (y, x), first = queue.popleft()
        if env.grid[y, x] == env.UNCOVERED:
            return first
        for action, (dy, dx) in enumerate(env.actions):
            p = (y + dy, x + dx)
            if (0 <= p[0] < env.size and 0 <= p[1] < env.size
                    and p not in seen and env.grid[p] != env.OBSTACLE):
                seen.add(p)
                queue.append((p, action if first is None else first))
    return None


def main():
    torch.set_num_threads(1)
    paths = [ROOT / 'train_coverage_20000.py', ROOT / 'run_train_20000.bat',
             ROOT / 'models/coverage_model.pth', ROOT / 'models/coverage_model.onnx']
    before = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    model = DRLCoverageCNN().eval()
    model.load_state_dict(torch.load(paths[2], map_location='cpu', weights_only=True))
    graph = onnx.load(str(paths[3]), load_external_data=False)
    onnx.checker.check_model(graph)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    # Loading bytes proves the tested model doesn't need an adjacent .data file.
    session = ort.InferenceSession(paths[3].read_bytes(), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    input_name = session.get_inputs()[0].name
    rows = []
    max_error = 0.0
    disagreement = 0
    mismatch_details = []
    allclose_failures = 0
    start = time.perf_counter()
    samples = []
    for seed in range(10000, 10100):
        random.seed(seed)
        np.random.seed(seed)
        env = FastGridCoverageEnv()
        obs = env._get_obs()
        total = env.total_free
        connected = reachable(env)
        visited = {(env.ry, env.rx)}
        repeats = 0
        samples.append(obs[None])
        for _ in range(350):
            data = obs[None]
            with torch.inference_mode():
                pt = model(torch.from_numpy(data)).numpy()
            ox = session.run(None, {input_name: data})[0]
            max_error = max(max_error, float(np.max(np.abs(pt - ox))))
            disagreement += int(pt.argmax() != ox.argmax())
            allclose_failures += int(not np.allclose(pt, ox, rtol=1e-4, atol=1e-5))
            if pt.argmax() != ox.argmax():
                sorted_q = np.sort(pt[0])
                mismatch_details.append(dict(seed=seed, step=env.steps,
                    torch_q=pt[0].tolist(), onnx_q=ox[0].tolist(),
                    torch_top_two_gap=float(sorted_q[-1] - sorted_q[-2])))
            obs, _, done, info = env.step(int(pt.argmax()))
            point = (env.ry, env.rx)
            repeats += int(point in visited and not info['hit_wall'])
            visited.add(point)
            if done:
                break
        rows.append(dict(seed=seed, total_free=total, reachable=connected,
                         covered=env.covered_count, steps=env.steps,
                         coverage=env.covered_count / total,
                         hit_wall=info['hit_wall'], repeats=repeats))
    baselines = []
    for seed in range(10000, 10100):
        random.seed(seed)
        env = FastGridCoverageEnv()
        for _ in range(350):
            action = nearest_uncovered_action(env)
            if action is None:
                break
            _, _, done, _ = env.step(action)
            if done:
                break
        baselines.append(env.covered_count / env.total_free)
    sample = samples[0]
    for _ in range(100):
        session.run(None, {input_name: sample})
    timings = []
    for _ in range(1000):
        t = time.perf_counter_ns()
        session.run(None, {input_name: sample})
        timings.append((time.perf_counter_ns() - t) / 1e6)
    coverages = [r['coverage'] for r in rows]
    after = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    assert before == after, 'Audited source/model changed during evaluation'
    result = dict(
        scope='Current V1 point-robot environment; 100 fixed audit seeds; no claim these were unseen during original training',
        sha256=before, versions=dict(torch=torch.__version__, onnx=onnx.__version__, ort=ort.__version__),
        parameters=sum(p.numel() for p in model.parameters()),
        onnx_bytes=paths[3].stat().st_size,
        external_initializers=[v.name for v in graph.graph.initializer if v.data_location == onnx.TensorProto.EXTERNAL],
        onnx_load_from_bytes=True, inputs=[dict(name=i.name, shape=i.shape) for i in session.get_inputs()],
        coverage_mean=float(np.mean(coverages)), coverage_median=float(np.median(coverages)),
        coverage_min=float(min(coverages)), coverage_max=float(max(coverages)),
        success_ge_95=sum(c >= .95 for c in coverages),
        collision_episodes=sum(r['hit_wall'] for r in rows),
        steps_mean=float(np.mean([r['steps'] for r in rows])),
        disconnected_maps=sum(r['reachable'] != r['total_free'] for r in rows),
        nearest_uncovered_bfs_mean=float(np.mean(baselines)),
        pytorch_onnx_max_abs_error=max_error, pytorch_onnx_argmax_disagreements=disagreement,
        allclose_failures_rtol_1e_4_atol_1e_5=allclose_failures,
        mismatch_details=mismatch_details,
        pc_only_ort_ms_p50_p95_p99=np.percentile(timings, [50, 95, 99]).tolist(),
        elapsed_seconds=time.perf_counter() - start, episodes=rows)
    output = Path(__file__).with_name('audit_current.json')
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'episodes'}, indent=2))


if __name__ == '__main__':
    main()
