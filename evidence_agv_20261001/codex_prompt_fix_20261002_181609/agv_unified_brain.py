#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# agv_unified_brain.py - BỘ NÃO ĐIỀU PHỐI TRUNG TÂM HỢP NHẤT XE AGV
# Tích hợp: ROS 2 Jazzy + SLAM Toolbox Map + RPLIDAR C1 + Điều khiển ESP32 Serial
# ==============================================================================

import os
import sys
import json
import time
import math
import serial
import threading
import heapq
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

PORT = 8080
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 115200

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class AGVSharedState:
    def __init__(self):
        self.lock = threading.Lock()
        # Trạng thái an toàn & chế độ
        self.auto_mode = False
        self.safety_status = "SAFE"
        self.hz = 10.0
        
        # Dữ liệu Radar 360 độ
        self.ranges = [0.0] * 360
        self.valid_points = 0
        self.min_dist_m = 9.99
        self.min_angle_deg = 0
        
        # Phân tích 8 hướng (cm)
        self.zones = {
            "front": 999, "front_right": 999, "right": 999, "back_right": 999,
            "back": 999, "back_left": 999, "left": 999, "front_left": 999
        }
        
        # Dữ liệu Bản đồ SLAM (/map)
        self.map_width = 0
        self.map_height = 0
        self.map_resolution = 0.05
        self.map_origin_x = 0.0
        self.map_origin_y = 0.0
        self.map_data = [] # Mảng nén pixel bản đồ
        self.map_received = False
        self.frontier_count = 0
        self.target_goal_x = 0.0
        self.target_goal_y = 0.0
        self.nav_mode = "FRONTIER" # "FRONTIER" hoặc "REACTIVE"
        self.explore_phase = "IDLE"
        
        # Telemetry từ ESP32
        self.robot_x = 0.0
        self.robot_y = 0.0
        self.robot_th = 0.0
        self.left_rpm = 0.0
        self.right_rpm = 0.0
        self.left_pwm = 0
        self.right_pwm = 0

state = AGVSharedState()

class AGVROSNode(Node):
    def __init__(self):
        super().__init__('agv_unified_brain')
        
        # 1. Quản lý Serial duy nhất (Không bao giờ bị tranh chấp)
        self.ser = None
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.05)
            self.get_logger().info(f'ĐÃ MỞ CỔNG SERIAL {SERIAL_PORT} THÀNH CÔNG!')
        except Exception as e:
            self.get_logger().error(f'LỖI MỞ SERIAL: {e}')

        # 1b. Khởi tạo TF Broadcaster cho SLAM Toolbox (odom -> base_footprint -> laser)
        self.tf_broadcaster = TransformBroadcaster(self)
        self.create_timer(0.05, self.broadcast_tf) # 20Hz

        # 2. Đăng ký LaserScan (/scan)
        qos_scan = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        self.create_subscription(LaserScan, '/scan', self.scan_cb, qos_scan)

        # 3. Đăng ký SLAM Map (/map)
        qos_map = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        self.create_subscription(OccupancyGrid, '/map', self.map_cb, qos_map)

        # 4. Timer định kỳ đọc Serial từ ESP32 (20Hz)
        self.create_timer(0.05, self.serial_read_loop)

        # 5. Timer vòng lặp tự hành né vật cản thông minh (10Hz)
        self.create_timer(0.10, self.auto_nav_loop)

        # 6. Biến trạng thái Frontier Exploration
        self.explore_state = "INITIAL_SPIN" # INITIAL_SPIN -> EXPLORING -> RETURNING_HOME -> COMPLETED
        self.spin_timer = 0.0
        self.stuck_counter = 0
        self.last_pos = (0.0, 0.0)
        self.home_x = 0.0
        self.home_y = 0.0
        self.home_th = 0.0

    def broadcast_tf(self):
        with state.lock:
            rx = state.robot_x
            ry = state.robot_y
            rth = state.robot_th

        now = self.get_clock().now().to_msg()

        # TF 1: odom -> base_footprint (theo Odometry thực tế của xe)
        t1 = TransformStamped()
        t1.header.stamp = now
        t1.header.frame_id = 'odom'
        t1.child_frame_id = 'base_footprint'
        t1.transform.translation.x = rx
        t1.transform.translation.y = ry
        t1.transform.translation.z = 0.0
        t1.transform.rotation.z = math.sin(rth / 2.0)
        t1.transform.rotation.w = math.cos(rth / 2.0)
        self.tf_broadcaster.sendTransform(t1)

        # TF 2: base_footprint -> laser (vị trí mắt LiDAR C1 đặt trước trục xe 5cm)
        t2 = TransformStamped()
        t2.header.stamp = now
        t2.header.frame_id = 'base_footprint'
        t2.child_frame_id = 'laser'
        t2.transform.translation.x = 0.05
        t2.transform.translation.y = 0.0
        t2.transform.translation.z = 0.12
        t2.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(t2)

    def send_cmd(self, cmd_str):
        if self.ser and self.ser.is_open:
            try:
                clean = cmd_str.strip()
                if clean.startswith(('S ', 's ', 'M ', 'm ', 'V ', 'v ')):
                    self.ser.write(bytes([65, 82, 77, 13, 10]))
                    time.sleep(0.01)
                msg = (clean + chr(13) + chr(10)).encode("utf-8")
                self.ser.write(msg)
            except Exception as e:
                self.get_logger().error(f'Lỗi gửi Serial: {e}')

    def serial_read_loop(self):
        if not self.ser or not self.ser.is_open:
            return
        try:
            while self.ser.in_waiting > 0:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        d = json.loads(line)
                        with state.lock:
                            if 'x' in d: state.robot_x = float(d.get('x', 0.0))
                            if 'y' in d: state.robot_y = float(d.get('y', 0.0))
                            if 'th' in d: state.robot_th = float(d.get('th', 0.0))
                            if 'l_rpm' in d: state.left_rpm = float(d.get('l_rpm', 0.0))
                            if 'r_rpm' in d: state.right_rpm = float(d.get('r_rpm', 0.0))
                            if 'l_pwm' in d: state.left_pwm = int(d.get('l_pwm', 0))
                            if 'r_pwm' in d: state.right_pwm = int(d.get('r_pwm', 0))
                    except Exception:
                        pass
        except Exception:
            pass

    def scan_cb(self, msg):
        angle = msg.angle_min
        step = msg.angle_increment
        points = [0.0] * 360
        valid_cnt = 0
        min_d = 99.0
        min_ang = 0
        zone_mins = {k: 99.0 for k in state.zones.keys()}

        for r in msg.ranges:
            if math.isfinite(r) and msg.range_min <= r <= msg.range_max:
                deg = int(math.degrees(angle)) % 360
                d = round(r, 3)
                if points[deg] == 0.0 or d < points[deg]:
                    points[deg] = d

                if 0.05 <= d <= 12.0:
                    valid_cnt += 1
                    if d < min_d:
                        min_d = d
                        min_ang = deg

                    # Phân bổ vào 8 vùng
                    if deg >= 338 or deg < 23: zone = "front"
                    elif 23 <= deg < 68: zone = "front_right"
                    elif 68 <= deg < 113: zone = "right"
                    elif 113 <= deg < 158: zone = "back_right"
                    elif 158 <= deg < 203: zone = "back"
                    elif 203 <= deg < 248: zone = "back_left"
                    elif 248 <= deg < 293: zone = "left"
                    else: zone = "front_left"

                    if d < zone_mins[zone]:
                        zone_mins[zone] = d

            angle += step

        with state.lock:
            state.ranges = points
            state.valid_points = valid_cnt
            state.min_dist_m = round(min_d if min_d < 90.0 else 9.99, 2)
            state.min_angle_deg = min_ang
            for k in state.zones.keys():
                state.zones[k] = int(zone_mins[k] * 100) if zone_mins[k] < 90.0 else 999

            if state.min_dist_m <= 0.35:
                state.safety_status = "DANGER_STOP"
            elif state.min_dist_m <= 0.70:
                state.safety_status = "WARNING"
            else:
                state.safety_status = "SAFE"

    def map_cb(self, msg):
        with state.lock:
            state.map_width = msg.info.width
            state.map_height = msg.info.height
            state.map_resolution = round(msg.info.resolution, 3)
            state.map_origin_x = round(msg.info.origin.position.x, 3)
            state.map_origin_y = round(msg.info.origin.position.y, 3)
            # Lấy mảng map thu gọn để truyền Web nhẹ nhàng
            state.map_data = list(msg.data)
            state.map_received = True

    def plan_astar_path(self, rx, ry, gx, gy):
        """
        Thuật toán A* Pathfinding kết hợp Costmap Inflation:
        Tìm đường di chuyển an toàn trong vùng trống (0), tránh xa tường/vật cản (>40).
        """
        with state.lock:
            w = state.map_width
            h = state.map_height
            res = state.map_resolution
            ox = state.map_origin_x
            oy = state.map_origin_y
            data = state.map_data

        if not data or w <= 0 or h <= 0:
            return None

        def w2m(wx, wy):
            mx = int((wx - ox) / res)
            my = int((wy - oy) / res)
            if 0 <= mx < w and 0 <= my < h:
                return (mx, my)
            return None

        def m2w(mx, my):
            return (ox + (mx + 0.5) * res, oy + (my + 0.5) * res)

        start_cell = w2m(rx, ry)
        goal_cell = w2m(gx, gy)
        if not start_cell or not goal_cell:
            return None

        # Vùng đệm an toàn 3 ô (~15cm) quanh tường
        def is_blocked(cx, cy):
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        v = data[ny * w + nx]
                        if v > 40: # Tường hoặc chướng ngại vật
                            return True
                    else:
                        return True
            return False

        # Nếu điểm goal bị cấn tường, tự dời ra ô trống gần nhất
        if is_blocked(goal_cell[0], goal_cell[1]):
            found_alt = False
            for r in range(1, 6):
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        cand = (goal_cell[0] + dx, goal_cell[1] + dy)
                        if 0 <= cand[0] < w and 0 <= cand[1] < h and not is_blocked(cand[0], cand[1]):
                            goal_cell = cand
                            found_alt = True
                            break
                    if found_alt: break
                if found_alt: break
            if not found_alt:
                return None

        pq = []
        start_h = math.hypot(goal_cell[0] - start_cell[0], goal_cell[1] - start_cell[1])
        heapq.heappush(pq, (start_h, 0, start_cell))
        came_from = {}
        cost_so_far = {start_cell: 0}
        dirs = [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]

        expanded = 0
        while pq and expanded < 2000:
            _, current_cost, current = heapq.heappop(pq)
            expanded += 1

            if current == goal_cell or math.hypot(current[0] - goal_cell[0], current[1] - goal_cell[1]) <= 1.5:
                path = []
                curr = current
                while curr in came_from:
                    path.append(m2w(curr[0], curr[1]))
                    curr = came_from[curr]
                path.reverse()
                return path

            for dx, dy in dirs:
                nx, ny = current[0] + dx, current[1] + dy
                if 0 <= nx < w and 0 <= ny < h:
                    if is_blocked(nx, ny):
                        continue
                    step_cost = 1.414 if (dx != 0 and dy != 0) else 1.0
                    new_cost = current_cost + step_cost
                    nxt = (nx, ny)
                    if nxt not in cost_so_far or new_cost < cost_so_far[nxt]:
                        cost_so_far[nxt] = new_cost
                        h_val = math.hypot(goal_cell[0] - nx, goal_cell[1] - ny)
                        priority = new_cost + h_val
                        heapq.heappush(pq, (priority, new_cost, nxt))
                        came_from[nxt] = current

        return None

    def find_best_frontier(self, rx, ry):
        """Thuật toán Frontier Exploration: Quét bản đồ tìm vùng chưa biết (-1) tiếp giáp ô thoáng (0)"""
        with state.lock:
            w = state.map_width
            h = state.map_height
            res = state.map_resolution
            ox = state.map_origin_x
            oy = state.map_origin_y
            data = state.map_data

        if not data or w == 0 or h == 0:
            return None

        frontiers = []
        step = 3
        for y in range(3, h - 3, step):
            for x in range(3, w - 3, step):
                idx = y * w + x
                val = data[idx]
                if val == 0:
                    # Kiểm tra ô này có xa tường không (> 3 ô ~ 15cm)
                    wall_near = False
                    for dy in range(-2, 3):
                        for dx in range(-2, 3):
                            if data[(y + dy) * w + (x + dx)] > 40:
                                wall_near = True
                                break
                        if wall_near: break
                    if wall_near:
                        continue

                    neighbors = [data[(y+1)*w + x], data[(y-1)*w + x], data[y*w + (x+1)], data[y*w + (x-1)]]
                    if -1 in neighbors:
                        wx = ox + x * res
                        wy = oy + y * res
                        dist = math.hypot(wx - rx, wy - ry)
                        if 0.4 <= dist <= 4.0:
                            frontiers.append((dist, wx, wy))

        with state.lock:
            state.frontier_count = len(frontiers)

        if not frontiers:
            return None
        frontiers.sort(key=lambda x: x[0])
        return (frontiers[0][1], frontiers[0][2])

    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            f_cm = state.zones["front"]
            fr_cm = state.zones["front_right"]
            fl_cm = state.zones["front_left"]
            l_cm = state.zones["left"]
            r_cm = state.zones["right"]
            rx = state.robot_x
            ry = state.robot_y
            rth = state.robot_th

        if not auto:
            self.explore_state = "INITIAL_SPIN"
            self.spin_timer = 0.0
            self.stuck_counter = 0
            with state.lock:
                state.explore_phase = "CHỜ LỆNH"
            return

        # 1. AN TOÀN PHẢN XẠ TUYỆT ĐỐI (Theo file Word: Hãm dừng 40cm)
        if f_cm < 40 or fr_cm < 32 or fl_cm < 32:
            # Chọn hướng trống nhất từ cảm biến Radar 360 để xoay thoát
            if l_cm >= r_cm:
                self.send_cmd("M -120 120") # Bẻ lái sang trái
            else:
                self.send_cmd("M 120 -120") # Bẻ lái sang phải
            return

        # 2. KHỞI TẠO BẢN ĐỒ: QUAY 360 ĐỘ
        if self.explore_state == "INITIAL_SPIN":
            with state.lock:
                state.explore_phase = "QUAY QUÉT KHUNG 360°"
            self.spin_timer += 0.10
            if self.spin_timer <= 6.0:
                self.send_cmd("M -120 120")
            else:
                self.send_cmd("STOP")
                self.home_x = rx
                self.home_y = ry
                self.home_th = rth
                self.explore_state = "EXPLORING"
                self.last_pos = (rx, ry)
            return

        # 3. FRONTIER EXPLORATION: TỰ ĐẾN VÙNG CHƯA BIẾT (-1)
        if self.explore_state == "EXPLORING":
            dist_moved = math.hypot(rx - self.last_pos[0], ry - self.last_pos[1])
            if dist_moved < 0.03:
                self.stuck_counter += 1
            else:
                self.stuck_counter = 0
            self.last_pos = (rx, ry)

            if self.stuck_counter >= 15:
                # Kẹt tại chỗ: Xoay tìm lối thoát mới
                if l_cm >= r_cm:
                    self.send_cmd("M -120 120")
                else:
                    self.send_cmd("M 120 -120")
                self.stuck_counter = 0
                return

            goal = self.find_best_frontier(rx, ry)
            if goal is None:
                self.explore_state = "RETURNING_HOME"
                return

            gx, gy = goal
            # DÙNG A* TÌM ĐƯỜNG ĐI TRÁNH TƯỜNG ĐẾN GOAL
            path = self.plan_astar_path(rx, ry, gx, gy)
            if path and len(path) > 1:
                # Lấy waypoint trung gian kế tiếp cách xe ít nhất 0.25m để bám theo đường cong
                target_wp = path[-1]
                for wp in path:
                    if math.hypot(wp[0] - rx, wp[1] - ry) >= 0.25:
                        target_wp = wp
                        break
                target_x, target_y = target_wp
            else:
                target_x, target_y = gx, gy

            with state.lock:
                state.target_goal_x = target_x
                state.target_goal_y = target_y
                state.explore_phase = f"A* ĐIỂM THOÁNG ({target_x:.1f}m, {target_y:.1f}m)"

            dx = target_x - rx
            dy = target_y - ry
            dist_to_goal = math.hypot(dx, dy)
            target_angle = math.atan2(dy, dx)
            angle_diff = (target_angle - rth + math.pi) % (2 * math.pi) - math.pi

            if abs(angle_diff) > 0.45:
                if angle_diff > 0:
                    self.send_cmd("M -125 125") # Xoay tại chỗ bám theo góc đường A*
                else:
                    self.send_cmd("M 125 -125")
            else:
                base_pwm = 125
                steer = int(angle_diff * 25.0)
                pwm_l = max(110, min(135, base_pwm - steer))
                pwm_r = max(110, min(135, base_pwm + steer))
                self.send_cmd(f"M {pwm_l} {pwm_r}")
            return

        # 4. TỰ ĐỘNG VỀ LẠI VỊ TRÍ XUẤT PHÁT
        if self.explore_state == "RETURNING_HOME":
            dx = self.home_x - rx
            dy = self.home_y - ry
            dist_home = math.hypot(dx, dy)

            if dist_home < 0.20:
                self.send_cmd("STOP")
                with state.lock:
                    state.explore_phase = "🏆 ĐÃ VỀ HOME THÀNH CÔNG!"
                    state.auto_mode = False
                return

            # DÙNG A* TÌM ĐƯỜNG TRÁNH VẬT CẢN ĐỂ VỀ HOME
            path_home = self.plan_astar_path(rx, ry, self.home_x, self.home_y)
            if path_home and len(path_home) > 1:
                target_wp = path_home[-1]
                for wp in path_home:
                    if math.hypot(wp[0] - rx, wp[1] - ry) >= 0.25:
                        target_wp = wp
                        break
                target_hx, target_hy = target_wp
            else:
                target_hx, target_hy = self.home_x, self.home_y

            with state.lock:
                state.explore_phase = f"QUÉT XONG! A* VỀ HOME ({dist_home:.2f}m)"

            target_angle = math.atan2(target_hy - ry, target_hx - rx)
            angle_diff = (target_angle - rth + math.pi) % (2 * math.pi) - math.pi
            if abs(angle_diff) > 0.45:
                if angle_diff > 0:
                    self.send_cmd("M -125 125")
                else:
                    self.send_cmd("M 125 -125")
            else:
                self.send_cmd("M 125 125")

ros_node = None

class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        p = self.path.split('?')
        path = p[0]
        q = p[1] if len(p) > 1 else ''

        if path == '/api/telemetry':
            with state.lock:
                d = {
                    "auto": state.auto_mode,
                    "status": state.safety_status,
                    "hz": state.hz,
                    "min_m": state.min_dist_m,
                    "min_ang": state.min_angle_deg,
                    "zones": state.zones,
                    "ranges": state.ranges,
                    "robot": {
                        "x": state.robot_x, "y": state.robot_y, "th": state.robot_th,
                        "l_rpm": state.left_rpm, "r_rpm": state.right_rpm,
                        "l_pwm": state.left_pwm, "r_pwm": state.right_pwm
                    },
                    "map_info": {
                        "has_map": state.map_received,
                        "w": state.map_width, "h": state.map_height,
                        "res": state.map_resolution,
                        "ox": state.map_origin_x, "oy": state.map_origin_y,
                        "frontiers": state.frontier_count,
                        "goal_x": state.target_goal_x, "goal_y": state.target_goal_y,
                        "phase": state.explore_phase
                    }
                }
            payload = json.dumps(d).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == '/api/map_full':
            with state.lock:
                d = {
                    "w": state.map_width, "h": state.map_height,
                    "res": state.map_resolution,
                    "ox": state.map_origin_x, "oy": state.map_origin_y,
                    "data": state.map_data
                }
            payload = json.dumps(d).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == '/api/cmd':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            val = params.get('val', [''])[0]
            if ros_node:
                ros_node.send_cmd(val)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return

        elif path == '/api/pid':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            kp = params.get('kp', ['0.5'])[0]
            ki = params.get('ki', ['1.5'])[0]
            kd = params.get('kd', ['0.01'])[0]
            kf = params.get('kf', ['0.45'])[0]
            cmd = f"TUNING {kp} {ki} {kd} {kf}"
            if ros_node:
                ros_node.send_cmd(cmd)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"status":"ok", "cmd": cmd}).encode('utf-8'))
            return

        elif path == '/api/auto':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            act = params.get('act', [''])[0].upper()
            with state.lock:
                if act == 'START':
                    state.auto_mode = True
                else:
                    state.auto_mode = False
                    if ros_node: ros_node.send_cmd('STOP')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"status":"ok", "auto": state.auto_mode}).encode('utf-8'))
            return

        else:
            # Phục vụ giao diện Dashboard chuẩn Cyberpunk Pro
            html_file = '/home/khangho/rplidar_c1_test/bridge/web/index_cyberpunk.html'
            if os.path.exists(html_file):
                with open(html_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self._cors()
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, 'File Not Found')

def main():
    global ros_node
    rclpy.init()
    ros_node = AGVROSNode()

    # Chạy ROS2 spin ở background thread
    ros_thread = threading.Thread(target=rclpy.spin, args=(ros_node,), daemon=True)
    ros_thread.start()

    server = ThreadedHTTPServer(('0.0.0.0', PORT), WebHandler)
    print(f'=== AGV UNIFIED BRAIN RUNNING ON PORT {PORT} ===')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if ros_node:
            ros_node.send_cmd('STOP')
        server.shutdown()
        rclpy.shutdown()

if __name__ == '__main__':
    main()