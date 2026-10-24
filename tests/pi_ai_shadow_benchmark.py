"""CPU-only Pi model benchmark: no ROS, UART, serial, or motor commands.

Run from an isolated staged source tree, passing the existing model directory:
    python3 -B tests/pi_ai_shadow_benchmark.py /path/to/installed/agv
"""

import hashlib
import json
import pathlib
import platform
import socket
import sys
import time

import numpy as np
import onnxruntime as ort


def measure(label, fn, warmup=100, samples=1000):
    for _ in range(warmup):
        fn()
    durations = np.empty(samples, dtype=np.float64)
    for i in range(samples):
        t0 = time.perf_counter_ns()
        fn()
        durations[i] = (time.perf_counter_ns() - t0) / 1_000_000
    return {
        "name": label,
        "samples": samples,
        "p50_ms": round(float(np.percentile(durations, 50)), 4),
        "p95_ms": round(float(np.percentile(durations, 95)), 4),
        "p99_ms": round(float(np.percentile(durations, 99)), 4),
        "max_ms": round(float(np.max(durations)), 4),
    }


def main(model_root):
    # Import only the model runtime; deliberately do not import the robot brain.
    sys.path.insert(0, str(model_root))
    from ai_local_planner.runtime import LocalPlannerRuntime

    ai1_path = model_root / "ai_local_planner/exported/local_planner.onnx"
    ai2_path = model_root / "models/coverage_model.onnx"
    runtime = LocalPlannerRuntime(ai1_path)
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    ai2_session = ort.InferenceSession(str(ai2_path), sess_options=opts,
                                       providers=["CPUExecutionProvider"])
    assert len(ai2_session.get_inputs()) == 2

    scan = np.full(360, 3.0, dtype=np.float64)
    obs = np.zeros((1, 365), dtype=np.float32)
    obs[0, :360] = (3.0 - .12) / (12.0 - .12)
    obs[0, 360] = .2
    obs[0, 362] = 1.0
    input1 = {runtime.input_name: obs}

    local_map = np.zeros((1, 3, 9, 9), dtype=np.float32)
    local_map[0, 0] = 1.0
    features = np.array([[.0, .0, 1.0, .0, .2, .0, .0, .0]], dtype=np.float32)
    input2 = {ai2_session.get_inputs()[0].name: local_map,
              ai2_session.get_inputs()[1].name: features}

    ai1_raw = runtime.session.run(None, input1)[0]
    ai1_safe = runtime.predict_from_sensors(scan, (0., 0., 0.), (2., 0.), 0., 0.)
    ai2_q = ai2_session.run(None, input2)[0]
    assert ai1_raw.shape == (1, 2) and np.isfinite(ai1_raw).all()
    assert ai1_safe.shape == (2,) and np.isfinite(ai1_safe).all()
    assert 0.0 <= float(ai1_safe[0]) <= .35 and abs(float(ai1_safe[1])) <= 1.5
    assert ai2_q.shape == (1, 4) and np.isfinite(ai2_q).all()

    result = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "onnxruntime": ort.__version__,
        "model_sha256": {str(p.relative_to(model_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (ai1_path, ai2_path)},
        "model_outputs": {"ai1_raw": ai1_raw[0].tolist(),
                          "ai1_filtered": ai1_safe.tolist(),
                          "ai2_q": ai2_q[0].tolist()},
        "benchmarks": [
            measure("ai1_onnx_only", lambda: runtime.session.run(None, input1)),
            measure("ai1_sensor_to_filtered_action", lambda: runtime.predict_from_sensors(
                scan, (0., 0., 0.), (2., 0.), 0., 0.)),
            measure("ai2_onnx_only", lambda: ai2_session.run(None, input2)),
        ],
        "scope": "synthetic stationary inputs; CPU inference only; no ROS/UART/motors",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: pi_ai_shadow_benchmark.py /absolute/model/root")
    main(pathlib.Path(sys.argv[1]).resolve())
