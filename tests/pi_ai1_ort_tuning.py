"""CPU-only comparison of ONNX Runtime thread counts for the released AI1 model.

Measurements are synthetic model inference alone; they cannot certify any
real-time robot control or collision safety requirement.
"""

import argparse
import json
import pathlib
import time

import numpy as np
import onnxruntime as ort


def measure(model_path, threads, samples=500):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(str(model_path), sess_options=opts,
                                providers=['CPUExecutionProvider'])
    obs = np.full((1, 365), .5, dtype=np.float32)
    feeds = {sess.get_inputs()[0].name: obs}
    for _ in range(100):
        sess.run(None, feeds)
    times = []
    for _ in range(samples):
        t0 = time.perf_counter_ns()
        output = sess.run(None, feeds)[0]
        times.append((time.perf_counter_ns() - t0) / 1e6)
    if output.shape != (1, 2) or not np.isfinite(output).all():
        raise ValueError('Invalid AI1 output')
    return dict(threads=threads, samples=samples,
                p50_ms=round(float(np.percentile(times, 50)), 4),
                p95_ms=round(float(np.percentile(times, 95)), 4),
                p99_ms=round(float(np.percentile(times, 99)), 4),
                max_ms=round(float(np.max(times)), 4))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model', type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps([measure(args.model, n) for n in [1, 2, 3, 4]], indent=2))
