#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_ai_mission_control.py - BỘ ĐIỀU KHIỂN & MÔ PHỎNG SONG HÀNH AI 1 VÀ AI 2 TRÊN WEB
====================================================================================
- Tích hợp trực tiếp 2 mô hình ONNX đã nghiệm thu:
  + AI 1: ai_local_planner/exported/local_planner.onnx (Local Motion Planner & Reactive Avoidance)
  + AI 2: models/coverage_model.onnx (Global Coverage DRL Planner)
- Cung cấp REST API & Giao diện Web Cyberpunk Mission Control (Port 8080)
- Chạy độc lập hoàn toàn trên Windows/Linux, không phụ thuộc phần cứng thật để nghiệm thu trực quan.
"""

import os
import sys
import json
import time
import math
import hashlib
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import deque
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_local_planner.environments.scenarios import create_scenario, Scenario, Circle
from ai_local_planner.environments.agv_motion_env import raycast, point_segment_distance
from ai_local_planner.runtime import build_observation, CommandSafetyFilter

PORT = 8080

# ==============================================================================
# 1. QUẢN LÝ MÔ HÌNH ONNX RUNTIME (AI 1 & AI 2)
# ==============================================================================
class DualModelManager:
    def __init__(self):
        self.ai1_path = ROOT / "ai_local_planner" / "exported" / "local_planner.onnx"
        self.ai1_json = ROOT / "ai_local_planner" / "exported" / "local_planner.json"
        self.ai2_path = ROOT / "models" / "coverage_model.onnx"
        self.ai2_json = ROOT / "models" / "manifest.json"

        # Tải AI 1
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        self.ai1_sess = ort.InferenceSession(str(self.ai1_path), sess_options=opts, providers=["CPUExecutionProvider"])
        self.ai1_input_name = self.ai1_sess.get_inputs()[0].name
        self.ai1_meta = json.loads(self.ai1_json.read_text(encoding="utf-8")) if self.ai1_json.exists() else {}
        self.ai1_sha = hashlib.sha256(self.ai1_path.read_bytes()).hexdigest()

        # Tải AI 2
        self.ai2_sess = ort.InferenceSession(str(self.ai2_path), sess_options=opts, providers=["CPUExecutionProvider"])
        self.ai2_map_name = self.ai2_sess.get_inputs()[0].name
        self.ai2_feat_name = self.ai2_sess.get_inputs()[1].name
        self.ai2_meta = json.loads(self.ai2_json.read_text(encoding="utf-8")) if self.ai2_json.exists() else {}
        self.ai2_sha = hashlib.sha256(self.ai2_path.read_bytes()).hexdigest()

        self.ai1_safety = CommandSafetyFilter(dt=0.1, stop_distance=0.46)

    def predict_ai1(self, raw_lidar_m, pose_xytheta, goal_xy, measured_v, measured_w):
        t0 = time.perf_counter()
        obs = build_observation(raw_lidar_m, pose_xytheta, goal_xy, measured_v, measured_w)
        pred = self.ai1_sess.run(None, {self.ai1_input_name: obs[None, :]})[0][0]
        # Qua bộ lọc an toàn phần cứng độc lập
        safe_cmd = self.ai1_safety.update(pred, raw_lidar_m)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return float(safe_cmd[0]), float(safe_cmd[1]), float(pred[0]), float(pred[1]), latency_ms

    def predict_ai2(self, local_map, features):
        t0 = time.perf_counter()
        q_vals = self.ai2_sess.run(None, {
            self.ai2_map_name: local_map[None, :],
            self.ai2_feat_name: features[None, :]
        })[0][0]
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return q_vals.tolist(), latency_ms


# ==============================================================================
# 2. GIẢ LẬP VẬT LÝ AI 1 (2D CONTINUOUS DIFFERENTIAL DRIVE & 360 LIDAR)
# ==============================================================================
class AI1SimulationState:
    def __init__(self, model_manager: DualModelManager):
        self.models = model_manager
        self.level = 1
        self.robot_radius = 0.20
        self.rng = np.random.default_rng(42)
        self.reset(level=1, seed=42)

    def reset(self, level=1, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.level = int(level)
        self.scenario = create_scenario(self.level, self.rng)
        self.pose = list(self.scenario.start) # [x, y, theta]
        self.goal = list(self.scenario.goal)  # [x, y]
        self.v = 0.0
        self.w = 0.0
        self.history = [list(self.pose[:2])]
        self.status = "RUNNING" # RUNNING, GOAL, COLLISION
        self.step_count = 0
        self.total_distance = 0.0
        self.last_latency_ms = 0.0
        self.min_clearance_m = 9.99
        self.min_clearance_deg = 0
        self.raw_lidar = raycast(np.array(self.pose[:2]), self.pose[2],
                                 self.scenario.all_walls(), self.scenario.obstacles, max_range=12.0)
        self._update_clearance()
        return self.get_state()

    def _update_clearance(self):
        self.min_clearance_m = float(np.min(self.raw_lidar))
        self.min_clearance_deg = int(np.argmin(self.raw_lidar))

    def step(self, dt=0.1):
        if self.status != "RUNNING":
            return self.get_state()

        # 1. Quét LiDAR 360 tia thực tế
        self.raw_lidar = raycast(np.array(self.pose[:2]), self.pose[2],
                                 self.scenario.all_walls(), self.scenario.obstacles, max_range=12.0)
        self._update_clearance()

        # 2. Suy luận bằng AI 1 ONNX
        v_cmd, w_cmd, raw_v, raw_w, latency = self.models.predict_ai1(
            self.raw_lidar, self.pose, self.goal, self.v, self.w
        )
        self.v = v_cmd
        self.w = w_cmd
        self.last_latency_ms = latency

        # 3. Động học Differential Drive AGV
        x, y, th = self.pose
        if abs(w_cmd) < 1e-4:
            nx = x + v_cmd * dt * math.cos(th)
            ny = y + v_cmd * dt * math.sin(th)
            nth = th
        else:
            nth = (th + w_cmd * dt + math.pi) % (2 * math.pi) - math.pi
            nx = x + (v_cmd / w_cmd) * (math.sin(nth) - math.sin(th))
            ny = y - (v_cmd / w_cmd) * (math.cos(nth) - math.cos(th))

        dist_moved = math.hypot(nx - x, ny - y)
        self.total_distance += dist_moved
        self.pose = [float(nx), float(ny), float(nth)]
        self.history.append([float(nx), float(ny)])
        if len(self.history) > 600:
            self.history.pop(0)
        self.step_count += 1

        # 4. Kiểm tra va chạm thực tế (Ground-truth Collision Check)
        cur_pos = np.array(self.pose[:2])
        # Tường
        walls = self.scenario.all_walls()
        wall_dists = point_segment_distance(cur_pos, walls)
        min_wall_dist = float(np.min(wall_dists)) if len(wall_dists) > 0 else 99.0

        # Vật cản tròn
        min_obs_dist = 99.0
        for obs in self.scenario.obstacles:
            d = math.hypot(cur_pos[0] - obs.x, cur_pos[1] - obs.y) - obs.radius
            if d < min_obs_dist:
                min_obs_dist = d

        real_clearance = min(min_wall_dist, min_obs_dist)
        if real_clearance <= self.robot_radius:
            self.status = "COLLISION"
            self.v = 0.0
            self.w = 0.0

        # 5. Kiểm tra đến đích
        dist_to_goal = math.hypot(self.pose[0] - self.goal[0], self.pose[1] - self.goal[1])
        if dist_to_goal <= 0.35 and self.status == "RUNNING":
            self.status = "GOAL"
            self.v = 0.0
            self.w = 0.0

        return self.get_state()

    def get_state(self):
        walls_list = [[float(v) for v in row] for row in self.scenario.all_walls()]
        obs_list = [{"x": float(o.x), "y": float(o.y), "radius": float(o.radius)} for o in self.scenario.obstacles]
        dist_to_goal = math.hypot(self.pose[0] - self.goal[0], self.pose[1] - self.goal[1])

        # Downsample lidar cho nhanh qua HTTP (360 tia float16)
        lidar_sampled = [round(float(r), 2) for r in self.raw_lidar]

        return {
            "level": self.level,
            "bounds": list(self.scenario.bounds),
            "pose": [round(v, 4) for v in self.pose],
            "goal": [round(v, 4) for v in self.goal],
            "v": round(self.v, 3),
            "w": round(self.w, 3),
            "status": self.status,
            "step_count": self.step_count,
            "total_distance": round(self.total_distance, 2),
            "dist_to_goal": round(dist_to_goal, 3),
            "latency_ms": round(self.last_latency_ms, 3),
            "min_clearance_m": round(self.min_clearance_m, 3),
            "min_clearance_deg": self.min_clearance_deg,
            "walls": walls_list,
            "obstacles": obs_list,
            "history": self.history[-150:], # 150 điểm gần nhất
            "lidar": lidar_sampled
        }


# ==============================================================================
# 3. GIẢ LẬP PHỦ KÍN SÀN AI 2 (GRID COVERAGE DRL AGENT)
# ==============================================================================
class AI2CoverageState:
    def __init__(self, model_manager: DualModelManager, size=32):
        self.models = model_manager
        self.size = size
        self.UNCOVERED = 1
        self.COVERED = 0
        self.OBSTACLE = 100
        # 0: Up (-1, 0), 1: Down (1, 0), 2: Left (0, -1), 3: Right (0, 1)
        self.actions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        self.action_names = ["LÊN (Up)", "XUỐNG (Down)", "TRÁI (Left)", "PHẢI (Right)"]
        self.rng = np.random.default_rng(42)
        self.padded_grid = np.full((self.size + 8, self.size + 8), self.OBSTACLE, dtype=np.int8)
        self.reset(preset="cluttered", seed=42)

    def reset(self, preset="cluttered", seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.preset = preset
        self.grid = np.full((self.size, self.size), self.UNCOVERED, dtype=np.int8)

        # Viền tường bao quanh
        self.grid[0, :] = self.OBSTACLE
        self.grid[self.size - 1, :] = self.OBSTACLE
        self.grid[:, 0] = self.OBSTACLE
        self.grid[:, self.size - 1] = self.OBSTACLE

        # Tạo vật cản theo preset
        if preset == "pillars":
            for r in range(5, self.size - 5, 6):
                for c in range(5, self.size - 5, 6):
                    self.grid[r:r+2, c:c+2] = self.OBSTACLE
        elif preset == "u_corridor":
            for c in range(6, self.size - 6): self.grid[8, c] = self.OBSTACLE
            for r in range(8, self.size - 10): self.grid[r, 6] = self.OBSTACLE
            for r in range(8, self.size - 10): self.grid[r, self.size - 7] = self.OBSTACLE
        elif preset == "cluttered":
            num_blocks = int(self.rng.integers(6, 12))
            for _ in range(num_blocks):
                bw = int(self.rng.integers(2, 5))
                bh = int(self.rng.integers(2, 5))
                bx = int(self.rng.integers(3, self.size - bw - 4))
                by = int(self.rng.integers(3, self.size - bh - 4))
                self.grid[by:by+bh, bx:bx+bw] = self.OBSTACLE

        # Tìm ô xuất phát an toàn
        self.rx, self.ry = 2, 2
        for r in range(2, self.size - 2):
            for c in range(2, self.size - 2):
                if self.grid[r, c] != self.OBSTACLE:
                    self.ry, self.rx = r, c
                    break
            if self.grid[self.ry, self.rx] != self.OBSTACLE:
                break

        self.grid[self.ry, self.rx] = self.COVERED
        self.steps = 0
        self.steps_without_new = 0
        self.last_action_idx = 1
        self.history = [(self.rx, self.ry)]
        self.status = "RUNNING"
        self.last_q_values = [0.0, 0.0, 0.0, 0.0]
        self.last_latency_ms = 0.0

        # Tính tổng số ô có thể đi đến (Reachable BFS)
        self.total_reachable = len(self._compute_reachable())
        self.covered_count = 1
        return self.get_state()

    def _compute_reachable(self):
        seen = {(self.ry, self.rx)}
        q = deque([(self.ry, self.rx)])
        while q:
            cy, cx = q.popleft()
            for dy, dx in self.actions:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < self.size and 0 <= nx < self.size:
                    if (ny, nx) not in seen and self.grid[ny, nx] != self.OBSTACLE:
                        seen.add((ny, nx))
                        q.append((ny, nx))
        return seen

    def _get_obs(self):
        self.padded_grid.fill(self.OBSTACLE)
        self.padded_grid[4:4+self.size, 4:4+self.size] = self.grid
        cy, cx = self.ry + 4, self.rx + 4
        patch = self.padded_grid[cy-4:cy+5, cx-4:cx+5]

        ch_uncov = (patch == self.UNCOVERED).astype(np.float32)
        ch_obs   = (patch == self.OBSTACLE).astype(np.float32)
        ch_cov   = (patch == self.COVERED).astype(np.float32)
        local_map = np.stack([ch_uncov, ch_obs, ch_cov], axis=0) # (3, 9, 9)

        # Geodesic target
        p_dx, p_dy, p_dist, has_tgt = self._find_geodesic_target()
        last_dy, last_dx = self.actions[self.last_action_idx]
        yaw = math.atan2(last_dy, last_dx)
        cov_frac = float(self.covered_count / max(1, self.total_reachable))
        no_prog = float(min(1.0, self.steps_without_new / 100.0))

        features = np.array([
            p_dx, p_dy, p_dist, 1.0 if has_tgt else 0.0,
            math.sin(yaw), math.cos(yaw), cov_frac, no_prog
        ], dtype=np.float32)

        return local_map, features

    def _find_geodesic_target(self):
        visited = bytearray(self.size * self.size)
        visited[self.ry * self.size + self.rx] = 1
        q = deque([(self.ry, self.rx, None, 0)])
        while q:
            cy, cx, first_act, d = q.popleft()
            if self.grid[cy, cx] == self.UNCOVERED:
                norm_d = min(1.0, float(d) / max(1.0, float(self.size * 2)))
                if first_act is not None:
                    dy, dx = self.actions[first_act]
                    return float(dx), float(dy), norm_d, True
                return 0.0, 0.0, norm_d, True
            for act_i, (dy, dx) in enumerate(self.actions):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < self.size and 0 <= nx < self.size:
                    idx = ny * self.size + nx
                    if not visited[idx] and self.grid[ny, nx] != self.OBSTACLE:
                        visited[idx] = 1
                        q.append((ny, nx, act_i if first_act is None else first_act, d + 1))
        return 0.0, 0.0, 0.0, False

    def step(self):
        if self.status != "RUNNING":
            return self.get_state()

        local_map, features = self._get_obs()
        q_vals, latency = self.models.predict_ai2(local_map, features)
        self.last_q_values = [round(v, 2) for v in q_vals]
        self.last_latency_ms = latency

        # Mask các ô đi vào tường
        masked_q = []
        for i, (dy, dx) in enumerate(self.actions):
            ny, nx = self.ry + dy, self.rx + dx
            if 0 <= ny < self.size and 0 <= nx < self.size and self.grid[ny, nx] != self.OBSTACLE:
                masked_q.append((q_vals[i], i))
            else:
                masked_q.append((-999999.0, i))

        best_q, best_act = max(masked_q, key=lambda x: x[0])
        self.last_action_idx = best_act
        dy, dx = self.actions[best_act]
        nry, nrx = self.ry + dy, self.rx + dx

        if 0 <= nry < self.size and 0 <= nrx < self.size and self.grid[nry, nrx] != self.OBSTACLE:
            self.ry, self.rx = nry, nrx
            if self.grid[self.ry, self.rx] == self.UNCOVERED:
                self.grid[self.ry, self.rx] = self.COVERED
                self.covered_count += 1
                self.steps_without_new = 0
            else:
                self.steps_without_new += 1
        else:
            self.steps_without_new += 1

        self.history.append((self.rx, self.ry))
        self.steps += 1

        if self.covered_count >= self.total_reachable:
            self.status = "COMPLETED"
        elif self.steps >= 1500:
            self.status = "TIMEOUT"

        return self.get_state()

    def get_state(self):
        cov_pct = round((self.covered_count / max(1, self.total_reachable)) * 100.0, 1)
        return {
            "preset": self.preset,
            "size": self.size,
            "robot": [int(self.rx), int(self.ry)],
            "status": self.status,
            "steps": self.steps,
            "covered_count": self.covered_count,
            "total_reachable": self.total_reachable,
            "coverage_pct": cov_pct,
            "q_values": self.last_q_values,
            "action_names": self.action_names,
            "last_action": self.last_action_idx,
            "latency_ms": round(self.last_latency_ms, 3),
            "grid": self.grid.tolist()
        }


# ==============================================================================
# 4. HTTP REQUEST HANDLER & REST API
# ==============================================================================
models_hub = DualModelManager()
sim_ai1 = AI1SimulationState(models_hub)
sim_ai2 = AI2CoverageState(models_hub)

class MissionControlHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Bỏ bớt log rác

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, code, data):
        payload = json.dumps(data, allow_nan=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self._cors()
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/', '/index.html'):
            html_file = ROOT / "index_cyberpunk.html"
            if not html_file.exists():
                html_file = ROOT / "ai_coverage_simulator.html"
            content = html_file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self._cors()
            self.end_headers()
            self.wfile.write(content)
            return

        elif path == '/api/models/info':
            info = {
                "ai1": {
                    "name": "Local Motion Planner (Obstacle Avoidance)",
                    "file": "ai_local_planner/exported/local_planner.onnx",
                    "sha256": models_hub.ai1_sha,
                    "opset": 14,
                    "input_dim": [1, 365],
                    "output_dim": [1, 2],
                    "status": "LOADED_ACTIVE",
                    "success_l1_l5": "99.6% (100-seed gated)"
                },
                "ai2": {
                    "name": "Global Coverage Planner (DRL Q-Net)",
                    "file": "models/coverage_model.onnx",
                    "sha256": models_hub.ai2_sha,
                    "input_dim": [[1, 3, 9, 9], [1, 8]],
                    "output_dim": [1, 4],
                    "status": "LOADED_ACTIVE",
                    "episodes_trained": 17851
                }
            }
            self._json(200, info)
            return

        elif path == '/api/ai1/state':
            self._json(200, sim_ai1.get_state())
            return

        elif path == '/api/ai2/state':
            self._json(200, sim_ai2.get_state())
            return

        self._json(404, {"error": "Not Found"})

    def do_POST(self):
        path = self.path.split('?')[0]
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode('utf-8')) if length > 0 else {}

        if path == '/api/ai1/reset':
            level = int(body.get('level', 1))
            seed = body.get('seed', None)
            res = sim_ai1.reset(level=level, seed=seed)
            self._json(200, res)
            return

        elif path == '/api/ai1/step':
            dt = float(body.get('dt', 0.1))
            res = sim_ai1.step(dt=dt)
            self._json(200, res)
            return

        elif path == '/api/ai2/reset':
            preset = body.get('preset', 'cluttered')
            seed = body.get('seed', None)
            res = sim_ai2.reset(preset=preset, seed=seed)
            self._json(200, res)
            return

        elif path == '/api/ai2/step':
            res = sim_ai2.step()
            self._json(200, res)
            return

        elif path == '/api/unified/step':
            # 1 bước AI 2 cấp goal, 1 bước AI 1 lái xe
            ai2_st = sim_ai2.step()
            # Ánh xạ tọa độ grid sang world của AI 1 nếu ở chế độ sandbox
            sim_ai1.goal = [float(sim_ai2.rx) * 0.25, float(sim_ai2.ry) * 0.25]
            ai1_st = sim_ai1.step(dt=0.1)
            self._json(200, {"ai1": ai1_st, "ai2": ai2_st})
            return

        self._json(404, {"error": "Not Found"})


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def run_server(port=PORT):
    # Ensure stdout handles UTF-8 on Windows
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    server = ThreadedServer(('0.0.0.0', port), MissionControlHandler)
    print("==================================================================", flush=True)
    print(f"[AGV MISSION CONTROL] SERVER DANG CHAY TAI: http://localhost:{port}", flush=True)
    print(f"  AI 1 Local Planner: {models_hub.ai1_path.name} (SHA: {models_hub.ai1_sha[:12]}...)", flush=True)
    print(f"  AI 2 Coverage:      {models_hub.ai2_path.name} (SHA: {models_hub.ai2_sha[:12]}...)", flush=True)
    print("==================================================================", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang tắt server...", flush=True)
    finally:
        server.server_close()


if __name__ == '__main__':
    run_server(PORT)
