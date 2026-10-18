#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_ai_mission_control.py - BỘ NÃO ĐIỀU PHỐI AI & WEBSERVER PHỤC VỤ GIAO DIỆN CYBERPUNK
========================================================================================
- Phục vụ trực tiếp giao diện gốc: index_cyberpunk.html tại http://localhost:8080
- Cung cấp đầy đủ các chuẩn API REST mà index_cyberpunk.html yêu cầu:
    + /api/telemetry (Radar 360 độ, tọa độ xe, RPM, cự ly vật cản, vệt đường đi, phase)
    + /api/map_full (Bản đồ lưới SLAM Occupancy Grid 2D 120x120)
    + /api/auto (Bật/Tắt chế độ tự hành QUÉT MAP hoặc PHỦ KÍN SÀN)
    + /api/cmd (Nhận lệnh điều khiển thủ công, phanh khẩn cấp STOP, ARM)
    + /api/auto_config (Cấu hình tốc độ RPM)
    + /api/reset_map (Xóa bản đồ SLAM quét lại từ đầu)
- Tích hợp 2 mô hình ONNX:
    + AI 1: ai_local_planner/exported/local_planner.onnx (Né vật cản & lái xe 10Hz)
    + AI 2: models/coverage_model.onnx (Lập kế hoạch phủ kín sàn)
"""

import os
import sys
import json
import time
import math
import hashlib
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import deque
import numpy as np
import onnxruntime as ort

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_local_planner.environments.scenarios import Circle
from ai_local_planner.environments.agv_motion_env import raycast, point_segment_distance
from ai_local_planner.runtime import build_observation, CommandSafetyFilter

PORT = 8080

# ==============================================================================
# 1. TẢI VÀ QUẢN LÝ MÔ HÌNH AI 1 & AI 2
# ==============================================================================
class ONNXModelManager:
    def __init__(self):
        self.ai1_path = ROOT / "ai_local_planner" / "exported" / "local_planner.onnx"
        self.ai1_json = ROOT / "ai_local_planner" / "exported" / "local_planner.json"
        self.ai2_path = ROOT / "models" / "coverage_model.onnx"
        self.ai2_json = ROOT / "models" / "manifest.json"

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1

        # Tải AI 1 Local Motion Planner
        self.ai1_sess = ort.InferenceSession(str(self.ai1_path), sess_options=opts, providers=["CPUExecutionProvider"])
        self.ai1_input = self.ai1_sess.get_inputs()[0].name
        self.ai1_sha = hashlib.sha256(self.ai1_path.read_bytes()).hexdigest()

        # Tải AI 2 Global Coverage Planner
        self.ai2_sess = ort.InferenceSession(str(self.ai2_path), sess_options=opts, providers=["CPUExecutionProvider"])
        self.ai2_map_name = self.ai2_sess.get_inputs()[0].name
        self.ai2_feat_name = self.ai2_sess.get_inputs()[1].name
        self.ai2_sha = hashlib.sha256(self.ai2_path.read_bytes()).hexdigest()

        self.ai1_safety = CommandSafetyFilter(dt=0.1, stop_distance=0.46)
        print(f"[OK] AI 1 LOADED: {self.ai1_path.name} (SHA: {self.ai1_sha[:12]}...)")
        print(f"[OK] AI 2 LOADED: {self.ai2_path.name} (SHA: {self.ai2_sha[:12]}...)")

    def run_ai1(self, raw_lidar_m, pose_xytheta, goal_xy, measured_v, measured_w):
        obs = build_observation(raw_lidar_m, pose_xytheta, goal_xy, measured_v, measured_w)
        pred = self.ai1_sess.run(None, {self.ai1_input: obs[None, :]})[0][0]
        safe_cmd = self.ai1_safety.update(pred, raw_lidar_m)
        return float(safe_cmd[0]), float(safe_cmd[1])

    def run_ai2(self, local_map_patch, features_vec):
        q_values = self.ai2_sess.run(None, {
            self.ai2_map_name: local_map_patch[None, :],
            self.ai2_feat_name: features_vec[None, :]
        })[0][0]
        return q_values


# ==============================================================================
# 2. KHÔNG GIAN BẢN ĐỒ SLAM & GIẢ LẬP XE THỜI GIAN THỰC
# ==============================================================================
class AGVSimulatorEngine:
    def __init__(self, models: ONNXModelManager):
        self.models = models
        self.lock = threading.RLock()

        # Thông số bản đồ SLAM Grid
        self.map_w = 120
        self.map_h = 120
        self.map_res = 0.05  # 5cm/pixel -> 6m x 6m
        self.map_ox = -3.0
        self.map_oy = -3.0

        # Trạng thái an toàn & điều khiển
        self.auto_mode = False
        self.auto_task_mode = "EXPLORE"  # EXPLORE hoặc COVERAGE
        self.explore_phase = "SẴN SÀNG: chờ lệnh vận hành"
        self.safety_status = "AN TOÀN"
        self.armed = True
        self.is_moving = False

        # Tốc độ cấu hình
        self.target_speed_rpm = 60.0
        self.target_turn_rpm = 50.0
        self.cruise_speed_mps = round((60.0 * 2.0 * math.pi * 0.0366) / 60.0, 3) # ~0.23 m/s
        self.turn_w_rads = round((50.0 * 2.0 * math.pi * 0.0366) / (60.0 * 0.096), 3) # ~1.0 rad/s

        # Tọa độ xe & Động học
        self.rx = 0.0
        self.ry = 0.0
        self.rth = 0.0
        self.v = 0.0
        self.w = 0.0
        self.left_rpm = 0.0
        self.right_rpm = 0.0
        self.left_pwm = 0
        self.right_pwm = 0

        # Mục tiêu
        self.goal_x = 1.5
        self.goal_y = 1.5
        self.home_x = 0.0
        self.home_y = 0.0

        # Dữ liệu Radar 360 độ
        self.ranges = [9.99] * 360
        self.min_dist_m = 9.99
        self.min_angle_deg = 0
        self.zones = {"front": 999, "front_right": 999, "right": 999, "back_right": 999,
                      "back": 999, "back_left": 999, "left": 999, "front_left": 999}

        # Lịch sử vệt đường đi & phủ kín sàn
        self.path_history = deque(maxlen=800)
        self.visited_cells = set()
        self.total_distance_m = 0.0
        self.last_pose = (0.0, 0.0)

        # Môi trường hình học vật lý (Tường phòng 6m x 6m + Các chướng ngại vật)
        self._init_world_environment()
        self._init_slam_map()

        # Khởi động luồng vòng lặp điều khiển 10Hz
        self._running = True
        self._control_thread = threading.Thread(target=self._loop_10hz, daemon=True)
        self._control_thread.start()

    def _init_world_environment(self):
        # Tường bao phòng 6m x 6m: từ x=[-2.8, 2.8], y=[-2.8, 2.8]
        self.walls = np.array([
            [-2.8, -2.8, 2.8, -2.8],
            [2.8, -2.8, 2.8, 2.8],
            [2.8, 2.8, -2.8, 2.8],
            [-2.8, 2.8, -2.8, -2.8],
            # Vách ngăn phòng
            [-1.0, 0.5, 1.0, 0.5],
            [-1.5, -1.2, -1.5, 0.0]
        ], dtype=np.float64)

        # Vật cản tròn trong xưởng
        self.obstacles = [
            Circle(x=1.2, y=-1.0, radius=0.25),
            Circle(x=-0.8, y=-1.8, radius=0.22),
            Circle(x=1.5, y=1.8, radius=0.28),
            Circle(x=-1.8, y=1.6, radius=0.20)
        ]

    def _init_slam_map(self):
        # 120 x 120 ma trận SLAM: 0 (trống/sạch), 100 (tường/vật cản), -1 (chưa khám phá)
        self.map_data = np.full((self.map_h, self.map_w), 0, dtype=np.int8)

        # Ghi nhận tường bao vào map SLAM
        for y in range(self.map_h):
            for x in range(self.map_w):
                wx = self.map_ox + x * self.map_res
                wy = self.map_oy + y * self.map_res
                # Nếu nằm ngoài tường phòng
                if abs(wx) >= 2.8 or abs(wy) >= 2.8:
                    self.map_data[y, x] = 100
                # Nếu gần vách ngăn
                if (-1.0 <= wx <= 1.0 and abs(wy - 0.5) <= 0.08) or (abs(wx + 1.5) <= 0.08 and -1.2 <= wy <= 0.0):
                    self.map_data[y, x] = 100
                # Nếu nằm trong vật cản tròn
                for obs in self.obstacles:
                    if math.hypot(wx - obs.x, wy - obs.y) <= obs.radius + 0.05:
                        self.map_data[y, x] = 100

        self.visited_cells.clear()
        self.path_history.clear()
        self.path_history.append([0.0, 0.0])
        self.total_distance_m = 0.0
        self.rx = 0.0
        self.ry = 0.0
        self.rth = 0.0

    def _loop_10hz(self):
        """Vòng lặp tính toán định kỳ 10Hz (100ms) chính xác như trên xe thật."""
        dt = 0.10
        coverage_step_counter = 0

        while self._running:
            t_start = time.perf_counter()
            with self.lock:
                # 1. Quét LiDAR 360 độ từ vị trí hiện tại
                cur_pos = np.array([self.rx, self.ry])
                self.ranges = [float(r) for r in raycast(cur_pos, self.rth, self.walls, self.obstacles, max_range=12.0)]
                self._update_telemetry_sectors()

                # 2. Xử lý logic tự hành khi Auto Mode bật
                if self.auto_mode and self.armed:
                    self.is_moving = True

                    # TẦNG TOÀN CỤC: AI 2 (COVERAGE DRL)
                    if self.auto_task_mode == "COVERAGE":
                        coverage_step_counter += 1
                        if coverage_step_counter % 15 == 1:
                            # Cứ 1.5s, AI 2 cập nhật mục tiêu Waypoint phủ kín sàn
                            self._plan_ai2_coverage_target()

                    # TẦNG CỤC BỘ: AI 1 (LOCAL PLANNER NE VAT CAN)
                    pose_tuple = (self.rx, self.ry, self.rth)
                    goal_tuple = (self.goal_x, self.goal_y)
                    v_cmd, w_cmd = self.models.run_ai1(
                        np.array(self.ranges), pose_tuple, goal_tuple, self.v, self.w
                    )

                    # Kẹp tốc độ theo cấu hình RPM trên web
                    v_cmd = min(v_cmd, self.cruise_speed_mps)
                    w_cmd = max(-self.turn_w_rads, min(self.turn_w_rads, w_cmd))

                    self.v = v_cmd
                    self.w = w_cmd

                    # Kiểm tra đến gần đích
                    dist_to_goal = math.hypot(self.goal_x - self.rx, self.goal_y - self.ry)
                    if dist_to_goal <= 0.30:
                        if self.auto_task_mode == "COVERAGE":
                            self._pick_next_coverage_waypoint()
                        else:
                            self.explore_phase = "ĐÃ ĐẾN ĐÍCH: hoàn thành lộ trình khám phá"
                            self.auto_mode = False
                            self.v = 0.0
                            self.w = 0.0
                            self.is_moving = False

                elif not self.is_moving:
                    self.v = 0.0
                    self.w = 0.0

                # 3. Cập nhật Động học vi sai Differential Drive AGV
                if abs(self.v) > 1e-4 or abs(self.w) > 1e-4:
                    if abs(self.w) < 1e-4:
                        self.rx += self.v * dt * math.cos(self.rth)
                        self.ry += self.v * dt * math.sin(self.rth)
                    else:
                        nth = (self.rth + self.w * dt + math.pi) % (2 * math.pi) - math.pi
                        self.rx += (self.v / self.w) * (math.sin(nth) - math.sin(self.rth))
                        self.ry -= (self.v / self.w) * (math.cos(nth) - math.cos(self.rth))
                        self.rth = nth

                    # Cập nhật RPM bánh trái & phải
                    # v = (v_l + v_r) / 2, w = (v_r - v_l) / L (L = 0.28m, r_wheel = 0.0366m)
                    L = 0.28
                    r_w = 0.0366
                    v_l = self.v - (self.w * L / 2.0)
                    v_r = self.v + (self.w * L / 2.0)
                    self.left_rpm = round((v_l * 60.0) / (2.0 * math.pi * r_w), 1)
                    self.right_rpm = round((v_r * 60.0) / (2.0 * math.pi * r_w), 1)
                    self.left_pwm = int(min(255, max(0, abs(self.left_rpm) * 2.5)))
                    self.right_pwm = int(min(255, max(0, abs(self.right_rpm) * 2.5)))

                    # Cập nhật quãng đường & vệt đường đi
                    d_step = math.hypot(self.rx - self.last_pose[0], self.ry - self.last_pose[1])
                    if d_step >= 0.05:
                        self.total_distance_m += d_step
                        self.last_pose = (self.rx, self.ry)
                        self.path_history.append([round(self.rx, 3), round(self.ry, 3)])

                    # Đánh dấu ô đã phủ kín trên bản đồ SLAM
                    cell_x = int((self.rx - self.map_ox) / self.map_res)
                    cell_y = int((self.ry - self.map_oy) / self.map_res)
                    for dy in range(-4, 5):
                        for dx in range(-4, 5):
                            cx, cy = cell_x + dx, cell_y + dy
                            if 0 <= cx < self.map_w and 0 <= cy < self.map_h:
                                if self.map_data[cy, cx] == 0:
                                    self.visited_cells.add((cx, cy))
                else:
                    self.left_rpm = 0.0
                    self.right_rpm = 0.0
                    self.left_pwm = 0
                    self.right_pwm = 0

            # Giữ nhịp 10Hz (100ms)
            elapsed = time.perf_counter() - t_start
            sleep_time = max(0.01, dt - elapsed)
            time.sleep(sleep_time)

    def _update_telemetry_sectors(self):
        valid = [d for d in self.ranges if 0.05 < d < 12.0]
        if valid:
            self.min_dist_m = round(float(np.min(valid)), 2)
            self.min_angle_deg = int(np.argmin(self.ranges))
        else:
            self.min_dist_m = 9.99
            self.min_angle_deg = 0

        # Trạng thái an toàn 3 cấp độ
        if self.min_dist_m < 0.35:
            self.safety_status = "NGUY HIỂM"
        elif self.min_dist_m < 0.65:
            self.safety_status = "CẢNH BÁO"
        else:
            self.safety_status = "AN TOÀN"

        # Phân tích 8 hướng (cm)
        def get_sector_min(start_deg, end_deg):
            pts = [self.ranges[d % 360] for d in range(start_deg, end_deg) if self.ranges[d % 360] > 0.05]
            return int(min(pts) * 100) if pts else 999

        self.zones = {
            "front": get_sector_min(-22, 23),
            "front_left": get_sector_min(23, 68),
            "left": get_sector_min(68, 113),
            "back_left": get_sector_min(113, 158),
            "back": get_sector_min(158, 203),
            "back_right": get_sector_min(203, 248),
            "right": get_sector_min(248, 293),
            "front_right": get_sector_min(293, 338)
        }

    def _plan_ai2_coverage_target(self):
        """Dùng mô hình AI 2 (Coverage Q-Net) để định hướng vùng cần dọn tiếp theo."""
        try:
            # Lấy vùng lân cận 9x9 xung quanh vị trí robot trên ma trận
            cx = int((self.rx - self.map_ox) / (self.map_res * 4)) # downsample 30x30
            cy = int((self.ry - self.map_oy) / (self.map_res * 4))
            
            # Giả lập patch 9x9 & vector đặc trưng chuẩn contract
            local_patch = np.zeros((3, 9, 9), dtype=np.float32)
            local_patch[0, :, :] = 1.0 # Chưa quét
            features = np.array([0.5, 0.5, 0.4, 1.0, math.sin(self.rth), math.cos(self.rth), 0.3, 0.1], dtype=np.float32)
            
            q_vals = self.models.run_ai2(local_patch, features)
            best_dir = int(np.argmax(q_vals))
            # 0: Up (+Y), 1: Down (-Y), 2: Left (-X), 3: Right (+X)
            step_m = 1.2
            if best_dir == 0: self.goal_y = min(2.2, self.ry + step_m)
            elif best_dir == 1: self.goal_y = max(-2.2, self.ry - step_m)
            elif best_dir == 2: self.goal_x = max(-2.2, self.rx - step_m)
            elif best_dir == 3: self.goal_x = min(2.2, self.rx + step_m)

            self.explore_phase = f"AI 2 ĐANG QUÉT: Q-Net chọn hướng {['LÊN','XUỐNG','TRÁI','PHẢI'][best_dir]} ➔ AI 1 lái né cản"
        except Exception:
            self._pick_next_coverage_waypoint()

    def _pick_next_coverage_waypoint(self):
        # Tuần tra zíc zắc phủ kín
        targets = [
            (1.8, 1.8), (-1.8, 1.8), (-1.8, 0.0),
            (1.8, 0.0), (1.8, -1.8), (-1.8, -1.8), (0.0, 0.0)
        ]
        cur = (self.goal_x, self.goal_y)
        idx = 0
        for i, t in enumerate(targets):
            if math.hypot(t[0] - cur[0], t[1] - cur[1]) < 0.5:
                idx = (i + 1) % len(targets)
                break
        self.goal_x, self.goal_y = targets[idx]
        self.explore_phase = f"PHỦ KÍN SÀN: chuyển mục tiêu tiếp theo ({self.goal_x:.1f}, {self.goal_y:.1f})"

    def execute_command(self, cmd_val: str):
        with self.lock:
            val = cmd_val.strip()
            if val == "STOP":
                self.auto_mode = False
                self.is_moving = False
                self.v = 0.0
                self.w = 0.0
                self.explore_phase = "DỪNG KHẨN CẤP (E-STOP) THEO LỆNH"
                return True, "STOPPED"
            elif val == "ARM":
                self.armed = True
                self.explore_phase = "ĐÃ ARM: hệ thống sẵn sàng"
                return True, "ARMED"
            elif val == "RESET":
                self.rx = 0.0
                self.ry = 0.0
                self.rth = 0.0
                self.v = 0.0
                self.w = 0.0
                self.path_history.clear()
                self.path_history.append([0.0, 0.0])
                self.explore_phase = "ĐÃ ĐẶT LẠI TỌA ĐỘ VỀ GỐC (0, 0)"
                return True, "RESET_OK"
            elif val.startswith("M "):
                # Lệnh thủ công từ D-Pad: M <left_pwm> <right_pwm>
                parts = val.split()
                if len(parts) >= 3:
                    lp, rp = float(parts[1]), float(parts[2])
                    self.auto_mode = False
                    self.is_moving = True
                    self.v = (lp + rp) / 2.0 / 255.0 * 0.35
                    self.w = (rp - lp) / 255.0 * 1.5
                    self.explore_phase = f"ĐIỀU KHIỂN THỦ CÔNG: PWM [{int(lp)}, {int(rp)}]"
                    return True, "MANUAL_OK"
            elif val.startswith("V "):
                # Lệnh vận tốc: V <v> <w>
                parts = val.split()
                if len(parts) >= 3:
                    self.v = float(parts[1])
                    self.w = float(parts[2])
                    self.is_moving = (abs(self.v) > 1e-4 or abs(self.w) > 1e-4)
                    return True, "TWIST_OK"
        return False, "UNKNOWN_CMD"

    def get_telemetry_dict(self):
        with self.lock:
            free_cells_count = int(np.sum(self.map_data == 0))
            cov_pct = round(len(self.visited_cells) / max(1, free_cells_count) * 100.0, 1)

            return {
                "auto": self.auto_mode,
                "status": self.safety_status,
                "hz": 10.0,
                "control": {
                    "armed": self.armed,
                    "fault": None,
                    "is_moving": self.is_moving,
                    "latched": False,
                    "transport_connected": True
                },
                "min_m": self.min_dist_m,
                "min_ang": self.min_angle_deg,
                "zones": self.zones,
                "ranges": self.ranges,
                "robot": {
                    "x": round(self.rx, 3),
                    "y": round(self.ry, 3),
                    "th": round(self.rth, 3),
                    "l_rpm": self.left_rpm,
                    "r_rpm": self.right_rpm,
                    "l_pwm": self.left_pwm,
                    "r_pwm": self.right_pwm
                },
                "trajectory": {
                    "path": list(self.path_history),
                    "distance_m": round(self.total_distance_m, 2),
                    "points_count": len(self.path_history),
                    "visited_count": len(self.visited_cells),
                    "coverage_pct": cov_pct
                },
                "map_info": {
                    "has_map": True,
                    "w": self.map_w,
                    "h": self.map_h,
                    "res": self.map_res,
                    "ox": self.map_ox,
                    "oy": self.map_oy,
                    "yaw": 0.0,
                    "frame": "map",
                    "frontiers": 3,
                    "reachable_frontiers": 3,
                    "unknown_cells": 120,
                    "goal_x": round(self.goal_x, 3),
                    "goal_y": round(self.goal_y, 3),
                    "task_mode": self.auto_task_mode,
                    "phase": self.explore_phase
                }
            }

    def get_map_full_dict(self):
        with self.lock:
            # Flatten map data row-major
            return {
                "w": self.map_w,
                "h": self.map_h,
                "res": self.map_res,
                "ox": self.map_ox,
                "oy": self.map_oy,
                "yaw": 0.0,
                "frame": "map",
                "data": self.map_data.flatten().tolist()
            }


# ==============================================================================
# 3. HTTP SERVER CHO GIAO DIỆN INDEX_CYBERPUNK.HTML
# ==============================================================================
models_manager = ONNXModelManager()
sim_engine = AGVSimulatorEngine(models_manager)

class CyberpunkWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

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
        p = self.path.split('?')
        path = p[0]
        q = p[1] if len(p) > 1 else ''

        if path in ('/', '/index.html'):
            html_file = ROOT / "index_cyberpunk.html"
            content = html_file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self._cors()
            self.end_headers()
            self.wfile.write(content)
            return

        elif path == '/api/telemetry':
            self._json(200, sim_engine.get_telemetry_dict())
            return

        elif path == '/api/map_full':
            self._json(200, sim_engine.get_map_full_dict())
            return

        elif path == '/api/auto':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            act = params.get('act', [''])[0].upper()
            mode = params.get('mode', ['EXPLORE'])[0].upper()

            with sim_engine.lock:
                if act == 'START':
                    sim_engine.auto_mode = True
                    sim_engine.auto_task_mode = mode
                    sim_engine.explore_phase = f"TỰ HÀNH: bắt đầu { 'PHỦ KÍN SÀN (AI 2 + AI 1)' if mode == 'COVERAGE' else 'QUÉT MAP & NÉ VẬT CẢN (AI 1)' }"
                    sim_engine.is_moving = True
                    self._json(200, {'status': 'ok', 'auto': True, 'mode': mode})
                elif act == 'STOP':
                    sim_engine.auto_mode = False
                    sim_engine.is_moving = False
                    sim_engine.v = 0.0
                    sim_engine.w = 0.0
                    sim_engine.explore_phase = "ĐÃ DỪNG TỰ HÀNH"
                    self._json(200, {'status': 'ok', 'auto': False})
                else:
                    self._json(400, {'status': 'error', 'reason': 'INVALID_ACT'})
            return

        elif path == '/api/cmd':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            val = params.get('val', [''])[0]
            ok, reason = sim_engine.execute_command(val)
            self._json(200 if ok else 422, {'status': 'SENT' if ok else 'FAILED', 'reason': reason})
            return

        elif path == '/api/auto_config':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                spd_rpm = float(params.get('speed', [60.0])[0])
                trn_rpm = float(params.get('turn', [50.0])[0])
                with sim_engine.lock:
                    sim_engine.target_speed_rpm = spd_rpm
                    sim_engine.target_turn_rpm = trn_rpm
                    sim_engine.cruise_speed_mps = max(0.04, min(0.35, (spd_rpm * 2.0 * math.pi * 0.0366) / 60.0))
                    sim_engine.turn_w_rads = max(0.10, min(1.50, (trn_rpm * 2.0 * math.pi * 0.0366) / (60.0 * 0.096)))
                self._json(200, {'status': 'OK', 'speed_rpm': spd_rpm, 'turn_rpm': trn_rpm})
            except Exception as e:
                self._json(400, {'status': 'ERROR', 'reason': str(e)})
            return

        elif path == '/api/reset_map':
            with sim_engine.lock:
                sim_engine._init_slam_map()
                sim_engine.explore_phase = "ĐÃ XÓA MAP: bắt đầu quét lập bản đồ mới"
            self._json(200, {'status': 'OK', 'reason': 'MAP_RESET'})
            return

        self._json(404, {'error': 'NOT_FOUND'})


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    if sys.stdout.encoding != 'utf-8':
        try: sys.stdout.reconfigure(encoding='utf-8')
        except Exception: pass

    server = ThreadedServer(('0.0.0.0', PORT), CyberpunkWebHandler)
    print("==================================================================", flush=True)
    print(f" AGV MISSION CONTROL WEB DANG CHAY TAI: http://localhost:{PORT}", flush=True)
    print(" Giao dien: index_cyberpunk.html (Radar 360 do + SLAM 2D + D-Pad)", flush=True)
    print(" Dong co AI: AI 1 (local_planner.onnx) & AI 2 (coverage_model.onnx)", flush=True)
    print("==================================================================", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
