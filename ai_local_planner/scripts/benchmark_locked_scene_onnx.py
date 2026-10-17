"""Benchmark actual Python supervisor + ONNXRuntime CPU inference on this host."""

import argparse
import json
from pathlib import Path
import platform
import time

import numpy as np

from ai_local_planner.environments.agv_motion_env import AGVMotionEnv
from ai_local_planner.models.locked_scene_onnx_agent import LockedSceneONNXAgent


def quantiles(samples):
    return {'p50_ms': float(np.percentile(samples, 50)),
            'p95_ms': float(np.percentile(samples, 95)),
            'p99_ms': float(np.percentile(samples, 99)),
            'max_ms': float(np.max(samples)),
            'p99_below_2ms_on_this_host': bool(np.percentile(samples, 99) < 2.)}


def benchmark(package, iterations, warmup):
    agent = LockedSceneONNXAgent(package)
    results = {}
    for level in range(1, 7):
        env = AGVMotionEnv(level=level, randomize=True)
        try:
            obs, _ = env.reset(seed=1940000 + level)
        finally:
            env.close()
        agent.locked_category = level - 1
        for _ in range(warmup):
            agent.act(obs)
        samples = []
        for _ in range(iterations):
            start = time.perf_counter_ns()
            agent.act(obs)
            samples.append((time.perf_counter_ns() - start) / 1e6)
        results[str(level)] = quantiles(samples)
    agent.reset()
    obs = np.zeros(365, dtype=np.float32)
    samples = []
    for _ in range(iterations):
        agent.reset()
        start = time.perf_counter_ns()
        agent.act(obs)
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return {'platform': platform.platform(), 'machine': platform.machine(),
            'package': str(package), 'iterations_per_mode': iterations,
            'warmup': warmup, 'models': results,
            'classifier_calibration_frame': quantiles(samples),
            'pi4_latency_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--warmup', type=int, default=100)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0:
        parser.error('Invalid counts')
    report = benchmark(args.package, args.iterations, args.warmup)
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
