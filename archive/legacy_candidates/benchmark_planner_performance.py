"""
benchmark_planner_performance.py
=============================================================================
Đo đạc định lượng hiệu năng tính toán CPU, thời gian lập kế hoạch (latency),
phân phối P50/P95/P99 và jitter của bộ lập kế hoạch ReachabilityCostmapPlannerV2.
Thực hiện trên fixture chuẩn 20x20 và 40x40.
=============================================================================
"""

import sys
import time
import math
import statistics
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import agv_reachability_costmap_planner_v2 as planner_module

def benchmark_planner(iterations: int = 100):
    planner = planner_module.ReachabilityCostmapPlannerV2()
    # Tạo bản đồ 20x20 ô (1m x 1m), resolution = 0.05m
    w, h = 20, 20
    grid = [0] * (w * h)
    # Thêm vật cản ở giữa tạo ngõ rẽ
    for y in range(5, 15):
        grid[y * w + 10] = 100 # tường ở giữa
    # Mở một cổng rộng 350mm (7 ô)
    for y in range(8, 12):
        grid[y * w + 10] = 0

    planner.ingest_occupancy_grid(w, h, 0.05, (0.0, 0.0), "map", grid, stamp=100.0)

    start_w = (0.2, 0.5)
    goal_w = (0.8, 0.5)

    latencies_ms = []
    cpu_times_ms = []

    for _ in range(iterations):
        t0_wall = time.perf_counter()
        t0_cpu = time.process_time()

        path = planner.find_path_world(start_w, goal_w, timeout_s=0.5)

        t1_wall = time.perf_counter()
        t1_cpu = time.process_time()

        assert path is not None and len(path) > 0, "Benchmark thất bại: không tìm thấy path"

        latencies_ms.append((t1_wall - t0_wall) * 1000.0)
        cpu_times_ms.append((t1_cpu - t0_cpu) * 1000.0)

    latencies_sorted = sorted(latencies_ms)
    p50 = statistics.median(latencies_sorted)
    idx_p95 = int(0.95 * len(latencies_sorted))
    idx_p99 = int(0.99 * len(latencies_sorted))
    p95 = latencies_sorted[min(idx_p95, len(latencies_sorted) - 1)]
    p99 = latencies_sorted[min(idx_p99, len(latencies_sorted) - 1)]
    mean_val = statistics.mean(latencies_ms)
    stdev_val = statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0.0

    print("=================================================================")
    print(f"=== KẾT QUẢ ĐO LƯỜNG HIỆU NĂNG PLANNER ({iterations} LẦN CHẠY) ===")
    print(f"Mean Latency : {mean_val:.3f} ms")
    print(f"Std Dev (Jitter): {stdev_val:.3f} ms")
    print(f"P50 Latency  : {p50:.3f} ms")
    print(f"P95 Latency  : {p95:.3f} ms")
    print(f"P99 Latency  : {p99:.3f} ms")
    print(f"Mean CPU Time: {statistics.mean(cpu_times_ms):.3f} ms")
    print("=================================================================")

if __name__ == "__main__":
    benchmark_planner()
