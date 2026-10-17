"""Benchmark ONNX single-sample CPU latency with p50/p95/p99 (run on Pi4)."""

import argparse
import json
import platform
from pathlib import Path
import time

import numpy as np
import onnxruntime as ort


def benchmark(model_path: Path, count: int = 1000, warmup: int = 100):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(model_path), sess_options=opts,
                                   providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    rng = np.random.default_rng(17)
    sample = rng.random((1, 365), dtype=np.float32)
    sample[0, 361:363] = [0., 1.]
    sample[0, 364] = 0.
    feed = {input_name: sample}
    for _ in range(warmup):
        session.run(None, feed)
    latencies = np.empty(count, dtype=np.float64)
    for i in range(count):
        begin = time.perf_counter_ns()
        session.run(None, feed)
        latencies[i] = (time.perf_counter_ns() - begin) / 1e6
    return {
        "host": platform.platform(), "machine": platform.machine(),
        "model": str(model_path), "inferences": count, "warmup": warmup,
        "p50_ms": float(np.percentile(latencies, 50)),
        "p95_ms": float(np.percentile(latencies, 95)),
        "p99_ms": float(np.percentile(latencies, 99)),
        "max_ms": float(latencies.max()), "target_p99_below_2ms": bool(np.percentile(latencies, 99) < 2.),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path,
                        default=Path("ai_local_planner/exported/local_planner.onnx"))
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations <= 0 or args.warmup < 0:
        parser.error("Iterations must be >0 and warmup >=0")
    result = benchmark(args.model, args.iterations, args.warmup)
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["target_p99_below_2ms"]:
        raise SystemExit("Benchmark failed: CPU p99 inference >= 2ms")


if __name__ == "__main__":
    main()
