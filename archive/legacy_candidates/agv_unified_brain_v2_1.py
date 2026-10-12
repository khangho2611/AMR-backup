#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# agv_unified_brain.py - BỘ NÃO ĐIỀU PHỐI TRUNG TÂM HỢP NHẤT XE AGV V2.1
# Tích hợp: ROS 2 Jazzy + TF Broadcaster (odom -> base_footprint -> laser)
#          + SLAM Toolbox Map + RPLIDAR C1 + ESP32 Closed-loop Heading PID
# ==============================================================================

import os
import sys
import json
import time
import math
import serial
import threading
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
        self.auto_mode = False
        self.auto_slam_scan = False
        self.continuous_slam_nav = False
        self.slam_scan_timer = 0.0
        self.target_heading = 0.0
        self.target_speed = 0.22
        self.kp_heading = 1.15
        
        self.safety_status = "SAFE"
        self.hz = 10.0
        self.ranges = [0.0] * 360
        self.valid_points = 0
        self.min_dist_m = 9.99
        self.min_angle_deg = 0
        
        self.zones = {
            "front": 999, "front_right": 999, "right": 999, "back_right": 999,
            "back": 999, "back_left": 999, "left": 999, "front_left": 999
        }
        
        self.map_width = 0
        self.map_height = 0
        self.map_resolution = 0.05
        self.map_origin_x = 0.0
        self.map_origin_y = 0.0
        self.map_data = []
        self.map_received = False
        
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
        
        self.ser = None
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.05)
            self.get_logger().info(f'ĐÃ MỞ CỔNG SERIAL {SERIAL_PORT} THÀNH CÔNG!')
        except Exception as e:
            self.get_logger().error(f'LỖI MỞ SERIAL: {e}')

        # 1. TF Broadcaster phát dynamic transform cho SLAM Toolbox
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

        # 4. Timer định kỳ đọc Serial ESP32 (20Hz)
        self.create_timer(0.05, self.serial_read_loop)

        # 5. Timer vòng lặp tự hành & bù lệch hướng góc Odometry (10Hz)
        self.create_timer(0.10, self.auto_nav_loop)

    def broadcast_tf(self):
        with state.lock:
            rx = state.robot_x
            ry = state.robot_y
            rth = state.robot_th

        now = self.get_clock().now().to_msg()

        # TF 1: odom -> base_footprint
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

        # TF 2: base_footprint -> laser
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
                msg = (cmd_str.strip() + '\r\n').encode('utf-8')
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
            state.map_data = list(msg.data)
            state.map_received = True

    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            auto_slam = state.auto_slam_scan
            cont_slam = state.continuous_slam_nav
            cur_th = state.robot_th
            tgt_th = state.target_heading
            kp = state.kp_heading
            base_v = state.target_speed
            f_cm = state.zones["front"]
            fr_cm = state.zones["front_right"]
            fl_cm = state.zones["front_left"]
            l_cm = state.zones["left"]
            r_cm = state.zones["right"]

        # 1. CHẾ ĐỘ QUÉT 360 ĐỘ TỰ ĐỘNG (Xoay 0.35 rad/s trong 18s)
        if auto_slam:
            with state.lock:
                state.slam_scan_timer += 0.10
                t = state.slam_scan_timer
            if t <= 18.0:
                self.send_cmd("V 0.0 0.35")
            else:
                with state.lock:
                    state.auto_slam_scan = False
                    state.slam_scan_timer = 0
                self.send_cmd("STOP")
            return

        # 2. CHẾ ĐỘ CHẠY BÌNH THƯỜNG & QUÉT MAP LIÊN TỤC (TỐC ĐỘ 0.22 m/s, BÙ SAI SỐ GÓC THỜI GIAN THỰC)
        if cont_slam or auto:
            # VẬT CẢN GẦN TRƯỚC MẶT (< 38cm): PHANH & ĐỔI HƯỚNG
            if f_cm < 38 or fr_cm < 32 or fl_cm < 32:
                self.send_cmd("V -0.10 0.0")
                time.sleep(0.12)
                turn_dir = 1.0 if l_cm > r_cm else -1.0
                with state.lock:
                    state.target_heading = cur_th + turn_dir * 0.785
                self.send_cmd(f"V 0.0 {turn_dir * 0.85:.2f}")
                time.sleep(0.2)

            # VÙNG ĐIỀU CHỈNH HƯỚNG (38cm - 75cm)
            elif f_cm < 75 or fr_cm < 60 or fl_cm < 60:
                v = max(0.14, base_v * 0.70)
                turn_dir = 1.0 if l_cm > r_cm else -1.0
                ratio = (75 - f_cm) / 37.0
                w = turn_dir * 0.60 * ratio
                with state.lock:
                    state.target_heading = cur_th
                self.send_cmd(f"V {v:.2f} {w:.2f}")

            # ĐƯỜNG THOÁNG (> 75cm): CHẠY TỐC ĐỘ 0.22 m/s VÀ DÙNG CLOSED-LOOP PID BÙ GÓC LỆCH CASTER
            else:
                err_th = tgt_th - cur_th
                err_th = (err_th + math.pi) % (2 * math.pi) - math.pi
                w_correction = max(-0.45, min(0.45, kp * err_th))
                
                if l_cm < 42: w_correction -= 0.15
                elif r_cm < 42: w_correction += 0.15
                
                self.send_cmd(f"V {base_v:.2f} {w_correction:.2f}")
            return

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
                    "auto_slam": state.auto_slam_scan,
                    "cont_slam": state.continuous_slam_nav,
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
                        "ox": state.map_origin_x, "oy": state.map_origin_y
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

        elif path == '/api/continuous_slam':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            act = params.get('act', [''])[0].upper()
            spd = float(params.get('speed', [0.22])[0])
            with state.lock:
                if act == 'START':
                    state.continuous_slam_nav = True
                    state.auto_mode = True
                    state.target_speed = spd
                    state.target_heading = state.robot_th
                else:
                    state.continuous_slam_nav = False
                    state.auto_mode = False
                    if ros_node: ros_node.send_cmd('STOP')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"status":"ok", "continuous_slam": state.continuous_slam_nav}).encode('utf-8'))
            return

        elif path == '/api/slam_auto':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            act = params.get('act', [''])[0].upper()
            with state.lock:
                if act == 'START':
                    state.auto_slam_scan = True
                    state.slam_scan_timer = 0
                    state.auto_mode = False
                else:
                    state.auto_slam_scan = False
                    state.slam_scan_timer = 0
                    if ros_node: ros_node.send_cmd('STOP')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"status":"ok", "auto_slam": state.auto_slam_scan}).encode('utf-8'))
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

        elif path == '/api/auto':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            act = params.get('act', [''])[0].upper()
            with state.lock:
                if act == 'START':
                    state.auto_mode = True
                else:
                    state.auto_mode = False
                    state.continuous_slam_nav = False
                    if ros_node: ros_node.send_cmd('STOP')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"status":"ok", "auto": state.auto_mode}).encode('utf-8'))
            return

        else:
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

    ros_thread = threading.Thread(target=rclpy.spin, args=(ros_node,), daemon=True)
    ros_thread.start()

    server = ThreadedHTTPServer(('0.0.0.0', PORT), WebHandler)
    print(f'=== AGV UNIFIED BRAIN V2.1 WITH TF RUNNING ON PORT {PORT} ===')
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
