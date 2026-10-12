operator_control_config = False
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
from agv_navigation import GridPlanner, finite, slam_censored_ranges, twist_centres, valid_body_bounds
from agv_command_session import CommandSession
from agv_command_journal import CommandOutcomeJournal
from agv_preflight_static_collector import acquire_port_lock, cleanup_lock
from collections import deque
import rclpy
from rclpy.node import Node
try:
    from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
except Exception:
    ReentrantCallbackGroup = object
    MutuallyExclusiveCallbackGroup = object
try:
    from rclpy.executors import MultiThreadedExecutor
except Exception:
    MultiThreadedExecutor = object
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster, Buffer, TransformListener
from rclpy.time import Time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

PORT = 8080
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 115200
motion_window_s_config = None

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def __init__(self,*args,journal_path=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.command_journal=CommandOutcomeJournal(journal_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),'logs','command_outcomes.jsonl'))

class AGVSharedState:
    def __init__(self):
        self.lock = threading.RLock()
        # Trạng thái an toàn & chế độ
        self.auto_mode = False
        # Body radius is an enclosing measured radius, NOT half the wheel track.
        self.body_radius_m = 0.20
        self.body_bounds_m = None
        self.wall_margin_m = .15
        self.cruise_speed_mps = .20
        self.auto_target_speed_rpm = 30.0
        self.auto_target_turn_rpm = 22.0
        self.turn_w_rads = 0.88
        self.map_mono = 0.
        self.map_version = 0
        self.map_origin_yaw = 0.
        self.map_frame = ''
        self.scan_mono = 0.
        self.scan_frame = ''
        self.frontier_reachable = None
        self.unknown_cells = None
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
        
        # Finish ROS setup before opening hardware; constructor failures must
        # never leave an unmonitored UART or reader behind.
        self.ser = None
        self._port_lock = None
        self._port_lock_path = None
        self._rx_line = b''
        self.initialize_navigation()
        self._reader_stop = threading.Event()
        self._reader_thread = threading.Thread(target=self._reader_worker, daemon=True)
        self._watchdog_thread = threading.Thread(target=self._watchdog_worker, daemon=True)

        # 1b. Khởi tạo TF Broadcaster cho SLAM Toolbox (odom -> base_footprint -> laser)
        self.tf_broadcaster = TransformBroadcaster(self)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        try:
            radius = float(os.environ.get('AGV_BODY_RADIUS_M', '0.20'))
            if math.isfinite(radius) and radius > 0:
                state.body_radius_m = radius
            else:
                state.body_radius_m = 0.20
        except ValueError:
            pass
        try:
            bounds=tuple(float(v) for v in os.environ.get('AGV_BODY_BOUNDS_M','').split(','))
            if valid_body_bounds(bounds,state.body_radius_m):
                state.body_bounds_m=bounds
            else:
                state.body_bounds_m=(-0.16,-0.12,0.10,0.12)
        except ValueError:
            pass
        self.scan_max_age_s = float(os.environ.get('AGV_SCAN_MAX_AGE_S', '0.25'))
        self.progress_timeout_s = float(os.environ.get('AGV_PROGRESS_TIMEOUT_S', '1.5'))
        try:
            self.cb_group_sensors = ReentrantCallbackGroup() if ReentrantCallbackGroup is not object else None
            self.cb_group_nav = MutuallyExclusiveCallbackGroup() if MutuallyExclusiveCallbackGroup is not object else None
            self.cb_group_tf = MutuallyExclusiveCallbackGroup() if MutuallyExclusiveCallbackGroup is not object else None
        except Exception:
            self.cb_group_sensors, self.cb_group_nav, self.cb_group_tf = None, None, None

        kw_tf = {'callback_group': self.cb_group_tf} if self.cb_group_tf is not None else {}
        kw_sensors = {'callback_group': self.cb_group_sensors} if self.cb_group_sensors is not None else {}
        kw_nav = {'callback_group': self.cb_group_nav} if self.cb_group_nav is not None else {}

        try:
            self.create_timer(0.05, self.broadcast_tf, **kw_tf) # 20Hz
        except TypeError:
            self.create_timer(0.05, self.broadcast_tf)

        # 2. Đăng ký LaserScan (/scan)
        qos_scan = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        try:
            self.create_subscription(LaserScan, '/scan', self.scan_cb, qos_scan, **kw_sensors)
        except TypeError:
            self.create_subscription(LaserScan, '/scan', self.scan_cb, qos_scan)
        self.pub_slam_scan = self.create_publisher(LaserScan, '/scan_slam', qos_scan)

        # 3. Đăng ký SLAM Map (/map)
        qos_map = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        try:
            self.create_subscription(OccupancyGrid, '/map', self.map_cb, qos_map, **kw_sensors)
        except TypeError:
            self.create_subscription(OccupancyGrid, '/map', self.map_cb, qos_map)

        # 4. Timer định kỳ đọc Serial từ ESP32 (20Hz)
        # The sole reader has a separate thread; ROS callbacks never block it.

        # 5. Timer vòng lặp tự hành né vật cản thông minh (10Hz)
        try:
            self.create_timer(0.10, self.auto_nav_loop, **kw_nav)
        except TypeError:
            self.create_timer(0.10, self.auto_nav_loop)

        self._port_lock, self._port_lock_path = acquire_port_lock(SERIAL_PORT)
        try:
            # Setting these before OPEN reduces reset edges; it cannot prove
            # that every USB adapter avoids a reset. Startup still fails closed.
            self.ser = serial.Serial(port=None, baudrate=BAUDRATE, timeout=.05,
                                     write_timeout=.2, exclusive=True)
            self.ser.rts = False
            self.ser.dtr = False
            self.ser.port = SERIAL_PORT
            self.ser.open()
            is_op = globals().get('operator_control_config', False)
            strict = not is_op
            self.control = CommandSession(self.ser, motion_window_s=motion_window_s_config,
                                          require_transport_sync=strict,
                                          operator_idle_lease_s=5. if (motion_window_s_config is None and strict) else 0.,
                                          strict_preflight=strict)
            self.control.autonomy_allowed = False
            self.control.arc_validator = self._forward_arc_clear
            self.control.escape_validator = self._escape_clear
            self._reader_thread.start()
            self._watchdog_thread.start()
            self.get_logger().info(f'ĐÃ MỞ CỔNG SERIAL {SERIAL_PORT}; DISARMED, KHÔNG AUTO ARM')
        except Exception:
            self._reader_stop.set()
            for thread in (self._reader_thread,self._watchdog_thread):
                if thread.ident is not None: thread.join(.5)
            if self.ser is not None: self.ser.close()
            cleanup_lock(self._port_lock,self._port_lock_path)
            self._port_lock = None
            raise

    def broadcast_tf(self):
        with self.control.lock:
            if self.control.last_d0 is None or not 0 <= self.control.clock()-self.control.last_d0 <= .25:
                return
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

        # The measured LiDAR mounting TF must be supplied by robot_state_publisher
        # or a calibrated static transform. Do not invent offsets from a drawing.

    def send_cmd(self, cmd_str, autonomous=False):
        clean = cmd_str.strip()
        if clean == 'STOP':
            with state.lock:
                state.auto_mode = False
            self.explore_state = 'IDLE'
            return self.control.request_stop()
        if clean in ('RESET', 'CLEAR_FAULT'):
            ok_write = True
            if self.ser and self.ser.is_open:
                ok_write = self.control.send_raw(b'CLEAR_FAULT\nARM\n')
            if not ok_write:
                return False, 'SERIAL_WRITE_FAILED'
            with self.control.lock:
                self.control.fault = None
                self.control.latched = False
                if not self.control.strict_preflight:
                    self.control.armed = True
                self.control.generation += 1
                self.control.arm_sent = None
                self.control.stop_deadline = None
                self.control.stop_confirmed = True
                self.control.clear_fault_until = self.control.clock() + 1.2
                self.control.stable_start = self.control.clock()
                self.control.stable_count = 80
            with state.lock:
                state.auto_mode = False
                state.explore_phase = 'SẴN SÀNG'
            return True, 'RESET_OK'
        if clean == 'ARM':
            if not self.control.strict_preflight:
                ok_write = True
                if self.ser and self.ser.is_open:
                    ok_write = self.control.send_raw(b'ARM\n')
                if not ok_write:
                    return False, 'SERIAL_WRITE_FAILED'
                with self.control.lock:
                    self.control.armed = True
                    self.control.latched = False
                    self.control.fault = None
                return True, 'ARM_CONFIRMED'
            return self.control.request_arm()
        if not autonomous and (clean.startswith('M ') or (clean.startswith('V ') and clean != 'V 0.000 0.000')):
            now = self.control.clock()
            if not self.control.strict_preflight:
                if self.ser and self.ser.is_open and (self.control.fault or not self.control.armed or (self.control.latest and self.control.latest.get('safety') != 'ARMED')):
                    self.control.send_raw(b'CLEAR_FAULT\nARM\n')
                with self.control.lock:
                    self.control.fault = None
                    self.control.latched = False
                    self.control.armed = True
                    self.control.clear_fault_until = now + 1.2
            elif not self.control.armed:
                self.control.request_arm()
        return self.control.drive(clean, autonomous=autonomous)

    def _reader_worker(self):
        while not self._reader_stop.is_set():
            self.serial_read_loop()
            self._reader_stop.wait(.01)

    def _watchdog_worker(self):
        last_heal = 0
        while not self._reader_stop.wait(.02):
            self.control.watchdog_tick()
            if self.control.latched:
                with state.lock:
                    state.auto_mode = False
            is_faulted = bool(self.control.fault) or (self.control.latest and self.control.latest.get('safety') == 'FAULT')
            if not self.control.strict_preflight and is_faulted and not self.control.motion:
                now = time.monotonic()
                if now - last_heal > 0.20:
                    last_heal = now
                    if self.ser and self.ser.is_open:
                        self.control.send_raw(b'CLEAR_FAULT\nARM\n')

    def serial_read_loop(self):
        if not self.ser or not self.ser.is_open:
            return
        latest = None
        try:
            self._rx_line = getattr(self,'_rx_line',b'')
            # Bulk reads avoid pyserial.readline's Python loop per byte under
            # HTTP/JSON CPU load. Bound work while retaining incomplete frames.
            for _ in range(40):
                if b'\n' not in self._rx_line:
                    waiting=self.ser.in_waiting
                    if waiting <= 0:break
                    self._rx_line += self.ser.read(min(waiting,4096))
                if b'\n' not in self._rx_line:
                    if len(self._rx_line)>1024:
                        self._rx_line=b''
                        self.control.request_stop('SERIAL_LINE_TOO_LONG',wait=False)
                    break
                raw,self._rx_line=self._rx_line.split(b'\n',1)
                if len(raw)>1024:
                    self._rx_line=b''
                    self.control.request_stop('SERIAL_LINE_TOO_LONG',wait=False)
                    break
                if not raw.strip():continue
                packet=self.control.ingest_line(raw.strip())
                if packet is not None and packet == self.control.latest:latest=packet
            # Dashboard consumers may wait on each other; never make UART
            # freshness depend on the dashboard mutex. Next sample refreshes it.
            if latest is not None and state.lock.acquire(blocking=False):
                try:
                    state.robot_x,state.robot_y,state.robot_th=latest['x'],latest['y'],latest['th']
                    state.left_rpm,state.right_rpm=latest['l_rpm'],latest['r_rpm']
                    state.left_pwm,state.right_pwm=latest['l_pwm'],latest['r_pwm']
                finally:state.lock.release()
        except Exception as exc:
            self.control.request_stop('READER_ERROR:' + type(exc).__name__,wait=False)

    def _scan_unavailable(self, reason):
        with self.control.lock:
            self.control.scan_time=None
            active=(self.control.armed or self.control.motion or self.control.arm_sent is not None)
            needs_scan=self.control.autonomy_allowed is not False
        with state.lock:
            state.scan_mono=0.
            state.explore_phase='CHỜ LIDAR: '+reason
        if active and needs_scan:self.control.request_stop(reason,wait=False)

    def scan_cb(self, msg):
        if not self._fresh_ros_header(msg.header, getattr(self, 'scan_max_age_s', .25)):
            self._scan_unavailable('STALE_SCAN_STAMP')
            return
        if (not finite(msg.angle_min) or not finite(msg.angle_increment) or msg.angle_increment == 0 or
                not finite(msg.range_min) or not finite(msg.range_max) or msg.range_min < 0 or
                msg.range_max <= msg.range_min):
            self._scan_unavailable('INVALID_SCAN')
            return
        angle = msg.angle_min
        step = msg.angle_increment
        if msg.header.frame_id == 'base_footprint':
            mount_x, mount_y, mount_yaw = 0., 0., 0.
        else:
            try:
                mount = self.tf_buffer.lookup_transform('base_footprint',msg.header.frame_id,Time())
                mount_x, mount_y = mount.transform.translation.x,mount.transform.translation.y
                mount_yaw = self._yaw(mount.transform.rotation)
                if not finite(mount_x) or not finite(mount_y):
                    raise ValueError('Invalid scan TF')
                stamp = mount.header.stamp.sec+mount.header.stamp.nanosec*1e-9
                # Static TF stamp zero is timeless; dynamic transforms expire.
                if stamp and not 0 <= self.get_clock().now().nanoseconds*1e-9-stamp <= .25:
                    raise ValueError('Stale scan TF')
            except Exception:
                self._scan_unavailable('MISSING_SCAN_TF')
                return
        if hasattr(self,'pub_slam_scan'):
            import copy
            filtered = copy.deepcopy(msg)
            try:
                filtered.ranges = slam_censored_ranges(msg.ranges,msg.range_min,msg.range_max)
            except ValueError:
                self._scan_unavailable('INVALID_SLAM_SCAN_LIMITS')
                return
            self.pub_slam_scan.publish(filtered)
        points = [0.0] * 360
        valid_cnt = 0
        min_d = 99.0
        min_ang = 0
        zone_mins = {k: 99.0 for k in state.zones.keys()}

        for r in msg.ranges:
            # A positive infinite beam is a no-return ray up to range_max;
            # NaN/negative infinity is invalid, never treated as free space.
            if r == math.inf:
                r = msg.range_max
            if math.isfinite(r) and msg.range_min <= r <= msg.range_max:
                x = mount_x + r*math.cos(angle+mount_yaw)
                y = mount_y + r*math.sin(angle+mount_yaw)
                deg = round(math.degrees(math.atan2(y,x))) % 360
                d = math.hypot(x,y)
                if points[deg] == 0.0 or d < points[deg]:
                    points[deg] = d

                if 0.05 <= d <= 12.0:
                    valid_cnt += 1
                    if d < min_d:
                        min_d = d
                        min_ang = deg

                    # Phân bổ vào 8 vùng
                    if deg >= 338 or deg < 23: zone = "front"
                    elif 23 <= deg < 68: zone = "front_left"
                    elif 68 <= deg < 113: zone = "left"
                    elif 113 <= deg < 158: zone = "back_left"
                    elif 158 <= deg < 203: zone = "back"
                    elif 203 <= deg < 248: zone = "back_right"
                    elif 248 <= deg < 293: zone = "right"
                    else: zone = "front_right"

                    if d < zone_mins[zone]:
                        zone_mins[zone] = d

            angle += step

        with state.lock:
            state.scan_mono = time.monotonic()
            state.scan_frame = msg.header.frame_id
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

        rotation_clear = self._rotation_clear()
        with self.control.lock:
            self.control.scan_time = self.control.clock()
            # Front drive needs actual returns in the forward cone. Unknown rays
            # do not become an artificial 999cm free direction.
            forward = [points[d % 360] for d in range(-22,23)]
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            min_pts = 10 if is_op else 30
            min_dist = .35 if is_op else .40
            self.control.scan_clear = sum(d > 0 for d in forward) >= min_pts and min(d for d in forward if d > 0) >= min_dist
            self.control.rotation_clear = rotation_clear
        # Forward/rotation commands are independently guarded at write time.
        # The navigator may HOLD and select another goal while the scan is fresh.

    @staticmethod
    def _yaw(q):
        vals = (q.x,q.y,q.z,q.w)
        if not all(finite(v) for v in vals) or abs(sum(v*v for v in vals)-1.) > .01:
            raise ValueError('Invalid orientation')
        # This planner only accepts planar grids/transforms.
        if abs(q.x) > 1e-5 or abs(q.y) > 1e-5:
            raise ValueError('Non-planar transform')
        return math.atan2(2*q.w*q.z, 1-2*q.z*q.z)

    def _fresh_ros_header(self, header, max_age):
        try:
            stamp = header.stamp.sec+header.stamp.nanosec*1e-9
            now = self.get_clock().now().nanoseconds*1e-9
            return finite(stamp) and -0.10 <= now-stamp <= max_age
        except (TypeError,AttributeError):
            return False

    def map_cb(self, msg):
        try:
            yaw = self._yaw(msg.info.origin.orientation)
            w,h,res = msg.info.width,msg.info.height,msg.info.resolution
            ox,oy = msg.info.origin.position.x,msg.info.origin.position.y
            data = list(msg.data)
            frame = msg.header.frame_id
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            max_map_age = 15.0 if is_op else 2.0
            valid = (type(w) is int and type(h) is int and 0 < w*h <= 2_000_000 and
                     w > 0 and h > 0 and finite(res) and .001 <= res <= 1. and
                     finite(ox) and finite(oy) and isinstance(frame,str) and bool(frame) and
                     len(data) == w*h and all(type(v) is int and -1 <= v <= 100 for v in data) and
                     self._fresh_ros_header(msg.header,max_map_age))
            if not valid:
                raise ValueError('Invalid OccupancyGrid')
        except (ValueError, TypeError, AttributeError):
            with state.lock: state.map_received = False
            return
        with state.lock:
            identity = (frame,w,h,res,ox,oy,yaw)
            old = (state.map_frame,state.map_width,state.map_height,state.map_resolution,
                   state.map_origin_x,state.map_origin_y,state.map_origin_yaw)
            if state.map_frame and state.map_frame != frame:
                self.initialize_navigation()
                # Reframed map cannot silently move the captured home.
                state.auto_mode = False
            state.map_width,state.map_height,state.map_resolution = w,h,res
            state.map_origin_x,state.map_origin_y,state.map_origin_yaw = ox,oy,yaw
            state.map_frame = frame
            if state.map_data != data or old != identity:
                state.map_version += 1
            state.map_data,state.map_received,state.map_mono = data,True,time.monotonic()

    def initialize_navigation(self):
        self.explore_state = 'IDLE'
        self.home = None
        self.goal = None
        self.blocked_goals = []
        self.blocked_regions = []
        self.progress = deque()
        self._planner_key,self._planner = None,None
        self._planners = {}
        self._home_stop_sent = False
        self._cautious = False
        self._normal_clear_since = None

    def _grid(self, margin=None):
        with state.lock:
            now = time.monotonic()
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            max_map_age = 15.0 if is_op else 2.0
            if not state.map_received or not 0 <= now-state.map_mono <= max_map_age:
                return None
            if margin is None:
                margin = .03 if getattr(self,'_cautious',False) else state.wall_margin_m
            key = (state.map_version,state.body_radius_m,margin)
            args = (state.map_width,state.map_height,state.map_resolution,
                    (state.map_origin_x,state.map_origin_y,state.map_origin_yaw),
                    tuple(state.map_data),state.body_radius_m,margin)
        cache=getattr(self,'_planners',{})
        cache={k:p for k,p in cache.items() if k[:2]==key[:2]}
        if key not in cache:
            try:
                planner = GridPlanner(*args, budget_s=.5)
            except (ValueError,TypeError,TimeoutError):
                return None
            cache[key]=planner
        self._planners=cache
        self._planner_key,self._planner=key,cache[key]
        return cache[key]

    def _enter_cautious(self, pose):
        """Yellow corridor: keep the enclosing body, reduce only the slow buffer."""
        if getattr(self,'_cautious',False):return False
        grid = self._grid(margin=.03)
        if grid is None or not grid.swept_clear(pose,0.,0.):return False
        self._cautious=True
        self._normal_clear_since=None
        self.blocked_regions=[]
        self.progress.clear()
        with state.lock:state.explore_phase='VÙNG VÀNG: đi chậm theo khoảng trống đủ thân xe'
        return True

    def _restore_normal_clearance(self, pose):
        if not getattr(self,'_cautious',False):return
        grid=self._grid(margin=state.wall_margin_m)
        clear=grid is not None and grid.swept_clear(pose,.20,0.)
        if self.goal is not None and grid is not None:
            if not grid.traversable(grid.world_to_cell(*self.goal)) or grid.path((pose[0],pose[1]), self.goal) is None:
                clear = False
        now=time.monotonic()
        if not clear:self._normal_clear_since=None
        elif self._normal_clear_since is None:self._normal_clear_since=now
        elif now-self._normal_clear_since>=2.:
            self._cautious=False
            self._normal_clear_since=None

    def plan_astar_path(self, rx,ry,gx,gy):
        grid = self._grid()
        return None if grid is None else grid.path((rx,ry),(gx,gy))

    def find_best_frontier(self, rx,ry):
        grid = self._grid()
        if grid is None:
            with state.lock: state.frontier_reachable = None
            return None
        now = time.monotonic()
        self.blocked_goals = [b for b in getattr(self,'blocked_goals',[]) if b[3] > now]
        self.blocked_regions = [b for b in getattr(self,'blocked_regions',[]) if b[3] > now]
        summary = grid.frontiers((rx,ry),[b[:3] for b in self.blocked_goals],
                                [b[:3] for b in self.blocked_regions])
        with state.lock:
            state.frontier_reachable = None if summary is None else summary['reachable_frontiers']
            state.frontier_count = 0 if summary is None else len(summary['goals'])
            state.unknown_cells = None if summary is None else summary['unknown_cells']
        if not summary or not summary['goals']:
            return None
        pose = self._pose_map()
        yaw = pose[2] if pose is not None else None
        best_goal = None
        best_score = float('inf')
        for g in summary['goals']:
            path = grid.path((rx, ry), g)
            if path is None:
                continue
            path_len = len(path) * grid.res
            if yaw is not None:
                dx, dy = g[0] - rx, g[1] - ry
                target_heading = math.atan2(dy, dx)
                heading_err = abs((target_heading - yaw + math.pi) % (2 * math.pi) - math.pi)
                score = path_len + 0.35 * heading_err
            else:
                score = path_len
            if score < best_score:
                best_score = score
                best_goal = g
        return best_goal if best_goal is not None else summary['goals'][0]

    def _pose_map(self):
        try:
            with state.lock:
                frame = state.map_frame
            t = self.tf_buffer.lookup_transform(frame,'base_footprint',Time())
            stamp = t.header.stamp.sec+t.header.stamp.nanosec*1e-9
            age = self.get_clock().now().nanoseconds*1e-9-stamp
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            max_tf_age = 20.00 if is_op else .25
            if not 0 <= age <= max_tf_age:
                self._last_pose_error = f'TF_AGE_{age:.3f}_MAX_{max_tf_age:.3f}'
                return None
            p,q = t.transform.translation,t.transform.rotation
            yaw = self._yaw(q)
            self._last_pose_error = None
            return (p.x,p.y,yaw) if finite(p.x) and finite(p.y) else None
        except Exception as exc:
            self._last_pose_error = f'EXC_{type(exc).__name__}'
            return None

    def _forward_arc_clear(self, v, w):
        def failed(reason):
            self._last_arc_reason=reason
            if getattr(self,'control',None) is not None:
                self.control._event('arc_rejected',reason=reason,v=v,w=w)
            return False
        self._last_arc_reason=None
        if getattr(self,'_cautious',False) and finite(v) and v>.040001:
            return failed('CAUTIOUS_SPEED_LIMIT')
        grid,pose=self._grid(),self._pose_map()
        if grid is None or pose is None:return failed('MAP_OR_TF_UNAVAILABLE')
        if not finite(v) or v <= 0:return failed('INVALID_TWIST')
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        with state.lock:
            epoch=(state.map_version,state.map_frame,state.body_radius_m,state.wall_margin_m,state.scan_mono)
            points=list(state.ranges)
            max_age = max(1.20, getattr(self, 'scan_max_age_s', 1.20)) if is_op else getattr(self, 'scan_max_age_s', .25)
            if not -0.10 <= time.monotonic()-state.scan_mono <= max_age:return failed('SCAN_STALE')
        samples=twist_centres(v,w)
        if samples is None:return failed('INVALID_TWIST')
        clear,reason=grid.swept_clear_result(pose,v,w)
        if not clear:
            if is_op and reason == 'UNKNOWN_SWEEP':
                pass
            else:
                return failed(reason)
        centres,padding=samples
        # Map and fresh scan must both clear the moving enclosing body. Missing
        # rear bins are not invented as free rays: the full footprint there
        # must be known-free in the map. Front coverage remains a writer gate.
        for deg,d in enumerate(points):
            if not finite(d) or d <= 0:continue
            angle=math.radians(deg)
            px,py=d*math.cos(angle),d*math.sin(angle)
            # Account for the half-degree rounding used by scan_cb.
            radius=grid.radius+padding+d*math.sin(math.radians(.5))
            if any(math.hypot(px-x,py-y) <= radius for x,y in centres):return failed('SCAN_BODY_CLEARANCE')
        with state.lock:
            valid=(epoch==(state.map_version,state.map_frame,state.body_radius_m,state.wall_margin_m,state.scan_mono)
                    and -0.10 <= time.monotonic()-state.scan_mono <= max_age
                    and 0 <= time.monotonic()-state.map_mono <= (15.0 if is_op else 2.0))
        return True if valid else failed('INPUT_CHANGED_DURING_SWEEP')

    def _escape_clear(self, v, w):
        grid,pose=self._grid(),self._pose_map()
        if grid is None or pose is None:return False
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        max_map_age = 15.0 if is_op else 2.0
        with state.lock:
            epoch=(state.map_version,state.map_frame,state.body_radius_m,state.body_bounds_m,state.wall_margin_m,state.scan_mono)
            bounds=state.body_bounds_m
            points=list(state.ranges)
            max_age = max(1.20, getattr(self, 'scan_max_age_s', 1.20)) if is_op else getattr(self, 'scan_max_age_s', .25)
            if not -0.10 <= time.monotonic()-state.scan_mono <= max_age:return False
        samples=twist_centres(v,w)
        if samples is None or not grid.escape_swept_clear(pose,v,w,bounds=bounds):return False
        centres,padding=samples
        obstacles=[(d*math.cos(math.radians(deg)),d*math.sin(math.radians(deg)),d)
                   for deg,d in enumerate(points) if finite(d) and 0<d<16.]
        if not obstacles:return False
        if abs(v) < 1e-9:
            body_margin = min(abs(b) for b in bounds) if bounds else grid.body_radius
            for px,py,d in obstacles:
                gap=math.hypot(px,py)-d*math.sin(math.radians(.5))
                if gap<=body_margin+padding:return False
            with state.lock:
                return (epoch==(state.map_version,state.map_frame,state.body_radius_m,state.body_bounds_m,state.wall_margin_m,state.scan_mono)
                        and -0.10 <= time.monotonic()-state.scan_mono <= max_age
                        and 0 <= time.monotonic()-state.map_mono <= max_map_age)
        if bounds is not None:
            for i, (bx, by) in enumerate(centres):
                if i == 0 and len(centres) > 1: continue
                angle = w * .5 * i / max(1, len(centres)-1)
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                for ox_b, oy_b, d in obstacles:
                    dx, dy = ox_b - bx, oy_b - by
                    lx = cos_a * dx + sin_a * dy
                    ly = -sin_a * dx + cos_a * dy
                    if (bounds[0] - 0.02 <= lx <= bounds[2] + 0.02 and
                        bounds[1] - 0.02 <= ly <= bounds[3] + 0.02):
                        return False
        else:
            distances=[]
            for x,y in centres:
                clearance=math.inf
                for px,py,d in obstacles:
                    gap=math.hypot(px-x,py-y)-d*math.sin(math.radians(.5))
                    if gap<=grid.body_radius+padding:return False
                    clearance=min(clearance,gap)
                if distances and clearance<distances[-1]-1e-7:return False
                distances.append(clearance)
            if v < 0:
                if distances[-1] < distances[0] - 1e-7: return False
            else:
                if distances[-1] <= distances[0] + .0001: return False
        with state.lock:
            return (epoch==(state.map_version,state.map_frame,state.body_radius_m,state.body_bounds_m,state.wall_margin_m,state.scan_mono)
                    and -0.10 <= time.monotonic()-state.scan_mono <= max_age
                    and 0 <= time.monotonic()-state.map_mono <= max_map_age)

    def _try_escape(self):
        # Ordered recovery candidates: candidate list starts from current escape phase index
        with state.lock:
            min_ang = getattr(state, 'min_angle_deg', 0)
            min_d = getattr(state, 'min_dist_m', 9.99)
        front_obstacle = (min_d <= 0.35 and abs((min_ang + 180) % 360 - 180) <= 60)
        if front_obstacle:
            candidates = ((-.04, 0.), (-.04, -.35), (-.04, .35), (0., .35), (0., -.35), (.04, -.35), (.04, .35), (.04, 0.))
        else:
            candidates = ((.04,0.),(.04,-.35),(.04,.35),(-.04,0.),(-.04,-.35),(-.04,.35),(0.,.35),(0.,-.35))
        idx = getattr(self, '_escape_index', 0) % len(candidates)
        ordered = candidates[idx:] + candidates[:idx]
        for v,w in ordered:
            if self._escape_clear(v,w):
                ok,reason=self.control.drive(f'V {v:.3f} {w:.3f}',autonomous=True,escape=True)
                if ok:
                    self._last_escape_vw = (v, w)
                    self.control._event('navigation_red_escape',v=v,w=w,reason='CLEARANCE_INCREASING')
                    with state.lock:
                        if v>0: state.explore_phase='NÉ VÙNG ĐỎ: tiến ra xa vật cản'
                        elif v<0: state.explore_phase='NÉ VÙNG ĐỎ: lùi theo hành lang trống'
                        else: state.explore_phase='NÉ VÙNG ĐỎ: xoay chỉnh góc thoát kẹt'
                return ok
        return False

    def start_auto(self):
        """Expose each failed START gate at the moment of the decision."""
        if not self.control.strict_preflight:
            with state.lock:
                if not (isinstance(state.body_radius_m, float) and state.body_radius_m > 0):
                    state.body_radius_m = 0.20
            if self.ser and self.ser.is_open:
                self.control.send_raw(b'CLEAR_FAULT\nARM\n')
            with self.control.lock:
                self.control.fault = None
                self.control.latched = False
                self.control.armed = True
                self.control.autonomy_allowed = True
                self.control.generation += 1
                self.control.last_command = self.control.clock()
            blockers = []
            self.initialize_navigation()
            with state.lock:
                self.home = self._pose_map()
                self.explore_state = 'EXPLORING'
                state.auto_mode = True
            self._auto_start_time = time.monotonic()
            self.send_cmd('V 0.000 0.000', autonomous=True)
            with state.lock:
                _radius = state.body_radius_m
            with self.control.lock:
                _gen = self.control.generation
            return True, 'STARTED', [], dict(body_radius_m=_radius, auto=True, generation=_gen)
        pose,grid=self._pose_map(),self._grid()
        with state.lock,self.control.lock:
            now=self.control.clock()
            ages=self.control._ages(now)
            map_age=time.monotonic()-state.map_mono
            checks=(('NOT_ARMED',self.control.strict_preflight and not self.control.armed),
                    ('LATCHED',self.control.strict_preflight and self.control.latched),
                    ('FAULT',self.control.strict_preflight and self.control.fault is not None),
                    ('D0_STALE',self.control.strict_preflight and (ages['d0_age_s'] is None or not 0 <= ages['d0_age_s'] <= .25)),
                    ('SCAN_STALE',ages['scan_age_s'] is None or not -0.10 <= ages['scan_age_s'] <= getattr(self, 'scan_max_age_s', .25)),
                    ('CALLER_STALE',self.control.strict_preflight and self.control.armed and (ages['caller_age_s'] is None or not 0 <= ages['caller_age_s'] <= .2)),
                    ('TRIAL_EXPIRED',self.control.trial_deadline is not None and now >= self.control.trial_deadline),
                    ('BODY_RADIUS_UNCONFIGURED',not finite(state.body_radius_m) or state.body_radius_m <= 0),
                    ('MAP_NOT_READY',grid is None),('TF_NOT_READY',pose is None))
            blockers=[name for name,blocked in checks if blocked]
            snapshot=dict(**ages,map_age_s=map_age,map_frame=state.map_frame,
                          body_radius_m=state.body_radius_m,pose=pose,generation=self.control.generation)
            if not blockers:
                self.initialize_navigation()
                self.control.autonomy_allowed = True
                self.control.generation += 1
                self.control.last_command = now
                self.home=pose;self.explore_state='EXPLORING';state.auto_mode=True
            self.control._event('auto_gate',accepted=not blockers,blockers=blockers,gate=snapshot)
            if not blockers:
                self.send_cmd('V 0.000 0.000', autonomous=True)
            return not blockers,('STARTED' if not blockers else 'EXPLICIT_ARM_FRESH_MAP_TF_AND_BODY_RADIUS_REQUIRED'),blockers,snapshot
    def _hold(self, phase):
        with state.lock: state.explore_phase = phase
        # V0 keeps a valid explicit session without asserting physical STOP.
        self.send_cmd('V 0.000 0.000',autonomous=True)

    def _exclude_goal(self, now, failed=True):
        if self.goal is not None:
            radius = max(.30,state.map_resolution*3)
            target = self.blocked_regions if failed else self.blocked_goals
            target.append((*self.goal,radius,now+30.))
            self.goal = None
        self.progress.clear()

    def _follow(self, pose, goal):
        self._last_arc_reason=None
        self._follow_transient=False
        grid = self._grid()
        path = None if grid is None else grid.path(pose[:2],goal)
        if not path:
            if getattr(self,'control',None) is not None:
                self.control._event('navigation_blocked',reason='NO_SAFE_PATH',pose=pose,goal=goal)
            return False
        # Extend the carrot only along one straight run of A*. Do not skip a
        # bend; the writer still checks the actual swept body before each TX.
        wp = path[1] if len(path) > 1 else path[0]
        if len(path)>2:
            direction=(path[2][0]-wp[0],path[2][1]-wp[1])
            for candidate in path[2:]:
                offset=(candidate[0]-wp[0],candidate[1]-wp[1])
                if abs(direction[0]*offset[1]-direction[1]*offset[0])>1e-8:break
                if math.hypot(candidate[0]-pose[0],candidate[1]-pose[1])>.25:break
                wp=candidate
        dx,dy = wp[0]-pose[0],wp[1]-pose[1]
        error = (math.atan2(dy,dx)-pose[2]+math.pi)%(2*math.pi)-math.pi
        w_max = getattr(state, 'turn_w_rads', 0.88)
        if abs(error) > 1.57:
            v = 0.
        elif abs(error) > .25:
            v_crawl = .03 if not getattr(self,'_cautious',False) else .02
            v = min(v_crawl, state.cruise_speed_mps,
                    math.hypot(dx,dy)/.5, math.hypot(goal[0]-pose[0],goal[1]-pose[1])/.5)
        else:
            v = min(state.cruise_speed_mps,
                    math.hypot(dx,dy)/.5, math.hypot(goal[0]-pose[0],goal[1]-pose[1])/.5)
        if getattr(self,'_cautious',False):v=min(v,.04)
        if v == 0 and abs(error) > .04:
            w_min = min(0.60, w_max)
            w = math.copysign(max(w_min, min(w_max, abs(error))), error)
        else:
            w = max(-w_max, min(w_max, error))
        if v == 0 and abs(w) > 0 and not self._rotation_clear():
            # Prefer a slow, geometrically checked escape over a blind spin.
            # The writer repeats this validation with fresh map/TF/scan.
            scan_clear = bool(getattr(self.control,'scan_clear',False))
            v = min(.02, math.hypot(dx,dy))
            w = max(-.12,min(.12,error))
            if scan_clear and self._forward_arc_clear(v,w):
                self.control._event('navigation_yellow_escape',reason='FORWARD_SWEEP_CLEAR',
                                    pose=pose,goal=goal,v=v,w=w)
            else:
                if getattr(self,'control',None) is not None:
                    self.control._event('navigation_blocked',reason='NO_SAFE_FORWARD_SWEEP',pose=pose,goal=goal)
                return False
        ok, reason = self.send_cmd(f'V {v:.3f} {w:.3f}',autonomous=True)
        if ok:return True
        if reason in ('WRITER_BUSY','TRANSPORT_BUSY','SCAN_STALE','D0_STALE','CALLER_STALE') or \
           getattr(self,'_last_arc_reason',None) in ('INPUT_CHANGED_DURING_SWEEP','SWEEP_BUDGET','SCAN_STALE','MAP_OR_TF_UNAVAILABLE'):
            self._follow_transient=True
            return False
        # An A* segment can be valid while a curved shortcut cuts its corner.
        # Align inside the current cleared footprint before advancing again.
        if v>0 and abs(error)>.04 and self._rotation_clear():
            return self.send_cmd(f'V 0.000 {math.copysign(w_max,error):.3f}',autonomous=True)[0]
        return False

    def _rotation_clear(self):
        with state.lock:
            radius = state.body_radius_m
            points = list(state.ranges)
            age = time.monotonic()-state.scan_mono
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        max_age = max(1.20, getattr(self, 'scan_max_age_s', 1.20)) if is_op else .25
        min_clear = (radius + 0.02) if is_op else (radius + (.03 if getattr(self,'_cautious',False) else state.wall_margin_m))
        returns=[p for p in points if finite(p) and 0<p<16.]
        if not (radius is not None and 0<=age<=max_age and len(returns)>=(15 if is_op else 30) and
                min(returns)>min_clear):return False
        if is_op:
            return True
        grid,pose=self._grid(),self._pose_map()
        # A missing rounded radar bin is not an obstacle. The complete known-
        # free map footprint covers those directions; unknown cells still block.
        return grid is not None and pose is not None and grid.swept_clear(pose,0.,.35)

    def auto_nav_loop(self):
        if self.explore_state == 'WAIT_STOP':
            health = self.control.health()
            with state.lock:
                state.explore_phase = 'HOME: đã xác nhận D0 dừng' if health['stop_confirmed'] else 'HOME: chờ xác nhận dừng'
                if health['stop_confirmed']:
                    state.auto_mode = False
                    self.explore_state = 'COMPLETED'
            return
        with state.lock:
            auto = state.auto_mode
            scan_age = time.monotonic()-state.scan_mono
        if not getattr(self, '_initial_pid_tuned', False) and getattr(self, 'control', None) is not None:
            if hasattr(self.control, 'preflight_ready') and self.control.preflight_ready(self.control.clock()) and not getattr(self.control, 'armed', False):
                try:
                    res = self.control.tuning(1.00, 3.20, 0.010, kf=1.80)
                    if res.get('status') == 'APPLIED':
                        self._initial_pid_tuned = True
                        if hasattr(self, 'get_logger'):
                            self.get_logger().info('ĐÃ TỰ ĐỘNG NẠP BỘ THÔNG SỐ PID TỐI ƯU (kp=1.0, ki=3.2, kd=0.01, kf=1.80)')
                except Exception:
                    pass
        if not auto:
            return
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        pose = self._pose_map()
        if pose is None:
            self._hold(f'HOLD: chờ TF ({getattr(self, "_last_pose_error", "None")})')
            return
        grid = self._grid()
        if grid is None:
            self._hold(f'HOLD: chờ bản đồ (map_age={time.monotonic()-state.map_mono:.2f}s, recvd={state.map_received})')
            return
        max_scan_age = max(1.20, getattr(self, 'scan_max_age_s', 1.20)) if is_op else getattr(self, 'scan_max_age_s', .25)
        if not -0.10 <= scan_age <= max_scan_age:
            self._hold(f'HOLD: chờ scan (scan_age={scan_age:.2f}s, max={max_scan_age:.2f}s)')
            return
        if self.home is None:
            self.home = pose
            self.explore_state = 'EXPLORING'
        self._restore_normal_clearance(pose)
        grid=self._grid()
        if grid is None:
            self._hold('HOLD: chờ bản đồ mới')
            return
        now = time.monotonic()
        if getattr(self, 'control', None) is not None and getattr(self.control, 'armed', False):
            if not is_op and self.control.clock() - (self.control.last_command or 0) > 0.15:
                self.send_cmd('V 0.000 0.000', autonomous=True)
        self.progress.append((now,pose))
        while self.progress and now-self.progress[0][0] > 2.:
            self.progress.popleft()

        # Phát hiện kẹt bánh động cơ thực tế qua telemetry ESP32
        wheel_stalled = False
        control = getattr(self, 'control', None)
        latest_d0 = getattr(control, 'latest', None) if control is not None else None
        if latest_d0:
            l_rpm = abs(latest_d0.get('l_rpm', 0.0))
            r_rpm = abs(latest_d0.get('r_rpm', 0.0))
            l_tgt = abs(latest_d0.get('l_tgt', 0.0))
            r_tgt = abs(latest_d0.get('r_tgt', 0.0))
            is_stalling = (
                (l_tgt >= 5.0 and l_rpm < 1.5) or
                (r_tgt >= 5.0 and r_rpm < 1.5) or
                (max(l_tgt, r_tgt) >= 5.0 and min(l_rpm, r_rpm) < 1.5 and max(l_rpm, r_rpm) >= 15.0)
            )
            if is_stalling:
                if getattr(self, '_stall_start', None) is None:
                    self._stall_start = now
                elif now - self._stall_start > (3.5 if is_op else 1.8):
                    wheel_stalled = True
            else:
                self._stall_start = None
        else:
            self._stall_start = None

        if wheel_stalled:
            self._escape_index = (getattr(self, '_escape_index', 0) + 1) % 8
            self._stall_start = None
            if self.goal is not None:
                self._exclude_goal(now)
            if not self._try_escape():
                self._hold('Né kẹt: phát hiện kẹt bánh động cơ, chuyển hướng')
            return

        with state.lock:
            danger_close = (state.safety_status == 'DANGER_STOP' or (state.min_dist_m is not None and state.min_dist_m <= 0.35))
        if danger_close:
            if not self._try_escape():
                self._escape_index = (getattr(self, '_escape_index', 0) + 1) % 8
                if self.goal is not None:
                    self._exclude_goal(now)
                self._hold('HOLD: vật cản quá gần, chưa có đường thoát an toàn')
            return

        if not grid.traversable(grid.world_to_cell(*pose[:2])) or not grid.swept_clear(pose,0.,0.):
            if (self.progress and now-self.progress[0][0] >= getattr(self, 'progress_timeout_s', 1.5) and
                    math.hypot(pose[0]-self.progress[0][1][0],pose[1]-self.progress[0][1][1]) < .02 and
                    abs((pose[2]-self.progress[0][1][2]+math.pi)%(2*math.pi)-math.pi) < .10):
                self._escape_index = (getattr(self, '_escape_index', 0) + 1) % 8
                self._exclude_goal(now)
                if not self._try_escape():
                    self._hold('Đổi vùng: kẹt trong vùng đỏ không tiến triển')
                return
            if self._enter_cautious(pose):
                self._hold('VÙNG VÀNG: chọn đường chậm đủ thân xe')
            elif not self._try_escape():
                self._escape_index = (getattr(self, '_escape_index', 0) + 1) % 8
                self._hold('HOLD: chưa có đường thoát vùng đỏ đủ thân xe')
            return
        else:
            self._escape_index = 0
        if self.goal is not None and (self.progress and now-self.progress[0][0] >= getattr(self, 'progress_timeout_s', 1.5) and
                math.hypot(pose[0]-self.progress[0][1][0],pose[1]-self.progress[0][1][1]) < .02 and
                abs((pose[2]-self.progress[0][1][2]+math.pi)%(2*math.pi)-math.pi) < .10):
            self._exclude_goal(now)
            self._hold('Đổi vùng khám phá: mục tiêu không có tiến triển')
            return
        if self.explore_state == 'RETURNING_HOME':
            if is_op and (now - getattr(self, '_auto_start_time', 0) < 15.0):
                self.explore_state = 'EXPLORING'
                return
            dist = math.hypot(pose[0]-self.home[0],pose[1]-self.home[1])
            if dist <= .04:
                angle = (self.home[2]-pose[2]+math.pi)%(2*math.pi)-math.pi
                if abs(angle) > .08:
                    if self._rotation_clear():
                        self.send_cmd(f'V 0.000 {max(-.35,min(.35,angle)):.3f}',autonomous=True)
                    else:
                        self._hold('HOME: chưa đủ khoảng trống để chỉnh hướng')
                else:
                    self.control.request_stop('HOME_STOP',wait=False)
                    self.explore_state = 'WAIT_STOP'
                return
            if not self._follow(pose,self.home[:2]):
                self._enter_cautious(pose)
                self._hold('HOLD: chưa có đường an toàn về home')
            return
        if self.goal is None or math.hypot(pose[0]-self.goal[0],pose[1]-self.goal[1]) < .06:
            if self.goal is not None:
                self._exclude_goal(now,failed=False)
            self.goal = self.find_best_frontier(*pose[:2])
            self.progress.clear()
        if self.goal is None:
            if not is_op:
                if self._enter_cautious(pose):
                    self._hold('VÙNG VÀNG: tìm frontier qua hành lang hẹp')
                    return
                with state.lock:
                    remaining = state.frontier_reachable
                    blocked_count = len(self.blocked_regions)
                if remaining == 0 and blocked_count == 0:
                    self.explore_state = 'RETURNING_HOME'
                    self._hold('Hết frontier reachable; nghiệm thu toàn phòng và về Home')
                elif remaining == 0 and blocked_count > 0:
                    self._active_spin_start = getattr(self, '_active_spin_start', None)
                    if self._active_spin_start is None:
                        self._active_spin_start = now
                        self._spin_fail_count = 0
                    if now - self._active_spin_start < 3.0:
                        turn_w = getattr(state, 'turn_w_rads', 0.88)
                        ok, reason = self.send_cmd(f'V 0.000 {turn_w:.3f}', autonomous=True)
                        if ok:
                            with state.lock: state.explore_phase = 'TỰ HÀNH: xoay quét mở rộng góc nhìn'
                        else:
                            self._spin_fail_count = getattr(self, '_spin_fail_count', 0) + 1
                            with state.lock: state.explore_phase = f'HOLD: xoay quét bị chặn ({reason})'
                            if self._spin_fail_count >= 3:
                                self._active_spin_start = now - 10.0
                    else:
                        self.blocked_regions = [b for b in self.blocked_regions if b[3] > now + 20.]
                        self._active_spin_start = None
                        self._hold('HOLD: giải phóng vùng chờ để tìm lại frontier')
                else:
                    self._hold('HOLD: frontier còn nhưng chưa có mục tiêu an toàn mới')
                return

            # CHẾ ĐỘ VẬN HÀNH: Vừa chạy vừa quét bằng Reactive Open-Space Navigation theo LiDAR 360
            with state.lock:
                ranges = list(state.ranges)
                cruise_speed = state.cruise_speed_mps
            
            f_pts = [ranges[d % 360] for d in range(-25, 26) if ranges[d % 360] > 0]
            f_dist = min(f_pts) if f_pts else 9.99
            l_pts = [ranges[d % 360] for d in range(25, 90) if ranges[d % 360] > 0]
            l_dist = min(l_pts) if l_pts else 9.99
            r_pts = [ranges[d % 360] for d in range(-90, -25) if ranges[d % 360] > 0]
            r_dist = min(r_pts) if r_pts else 9.99

            if f_dist >= 0.40:
                v = cruise_speed if state.auto_target_speed_rpm > 30 else min(0.12, cruise_speed)
                w = 0.0
                if l_dist < 0.35 and l_dist < r_dist:
                    w = -0.18
                elif r_dist < 0.35 and r_dist < l_dist:
                    w = 0.18
                ok, reason = self.send_cmd(f'V {v:.3f} {w:.3f}', autonomous=True)
                if not ok:
                    w_turn = 0.45 if l_dist >= r_dist else -0.45
                    ok_turn, r_turn = self.send_cmd(f'V 0.000 {w_turn:.3f}', autonomous=True)
                    if not ok_turn:
                        self._try_escape()
                    with state.lock:
                        state.explore_phase = 'TỰ HÀNH: đổi hướng tránh cản' if ok_turn else f'TỰ HÀNH: cản phía trước ({r_turn})'
                else:
                    with state.lock:
                        state.explore_phase = 'TỰ HÀNH: tiến mở rộng vùng quét'
            elif f_dist >= 0.28:
                v = max(0.06, min(0.18, cruise_speed * 0.45)) if state.auto_target_speed_rpm > 30 else 0.04
                w = 0.45 if l_dist >= r_dist else -0.45
                ok, reason = self.send_cmd(f'V {v:.3f} {w:.3f}', autonomous=True)
                if not ok:
                    w_turn = 0.45 if l_dist >= r_dist else -0.45
                    ok_turn, _ = self.send_cmd(f'V 0.000 {w_turn:.3f}', autonomous=True)
                    if not ok_turn:
                        self._try_escape()
                    with state.lock:
                        state.explore_phase = 'TỰ HÀNH: rẽ tránh cản' if ok_turn else f'TỰ HÀNH: rẽ ({reason})'
                else:
                    with state.lock:
                        state.explore_phase = 'TỰ HÀNH: rẽ tìm khoảng trống mở rộng map'
            else:
                if not self._try_escape():
                    w = 0.45 if l_dist >= r_dist else -0.45
                    ok, reason = self.send_cmd(f'V 0.000 {w:.3f}', autonomous=True)
                    with state.lock:
                        state.explore_phase = 'TỰ HÀNH: xoay tại chỗ tìm hướng thoáng' if ok else f'HOLD: phía trước bị cản ({reason})'
            return
        else:
            self._active_spin_start = None
        with state.lock:
            state.target_goal_x,state.target_goal_y = self.goal
            state.explore_phase = 'EXPLORING: bám đường A* known-free'
        if not self._follow(pose,self.goal):
            if getattr(self,'_follow_transient',False):
                self._hold('CHỜ MẪU MỚI: '+str(getattr(self,'_last_arc_reason','BUSY_OR_STALE')))
                return
            if self._enter_cautious(pose):
                self._hold('VÙNG VÀNG: giữ mục tiêu, tính lại đường chậm')
                return
            self._goal_retries = getattr(self, '_goal_retries', 0) + 1
            if self._goal_retries < 5:
                if is_op:
                    dx, dy = self.goal[0] - pose[0], self.goal[1] - pose[1]
                    target_heading = math.atan2(dy, dx)
                    heading_err = (target_heading - pose[2] + math.pi) % (2 * math.pi) - math.pi
                    with state.lock:
                        ranges = list(state.ranges)
                    f_pts = [ranges[d % 360] for d in range(-25, 26) if ranges[d % 360] > 0]
                    f_dist = min(f_pts) if f_pts else 9.99
                    if f_dist >= 0.38 and abs(heading_err) < 0.6:
                        self.send_cmd(f'V 0.060 {max(-0.35, min(0.35, heading_err)):.3f}', autonomous=True)
                        with state.lock: state.explore_phase = 'TỰ HÀNH: tiến nhẹ hướng mục tiêu'
                        return
                    elif abs(heading_err) >= 0.6:
                        w_turn = 0.40 if heading_err > 0 else -0.40
                        ok, reason = self.send_cmd(f'V 0.000 {w_turn:.3f}', autonomous=True)
                        if not ok:
                            self._try_escape()
                        with state.lock: state.explore_phase = 'TỰ HÀNH: xoay hướng mục tiêu' if ok else f'HOLD: xoay bị chặn ({reason})'
                        return
                self._hold(f'TÍNH LẠI ĐƯỜNG ({self._goal_retries}/5): chờ cơ hội lượn')
                return
            self._goal_retries = 0
            self._exclude_goal(now)
            self._hold('Đổi mục tiêu: đường bị chặn hoặc dữ liệu không hợp lệ')
        else:
            self._goal_retries = 0

    def close_control(self):
        self.control.request_stop('SHUTDOWN',wait=False)
        self.control.stop_event.wait(.25)
        self._reader_stop.set()
        for thread in (self._reader_thread,self._watchdog_thread):
            thread.join(.5)
        ok = not self._reader_thread.is_alive() and not self._watchdog_thread.is_alive()
        try:
            if self.ser: self.ser.close()
        except Exception:
            ok = False
        if ok:
            cleanup_lock(getattr(self,'_port_lock',None),getattr(self,'_port_lock_path',None))
            self._port_lock = None
        return ok and self.control.stop_confirmed and self.control.stop_write_ok


ros_node = None
observe_only = False

class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data,allow_nan=False).encode('utf8'))

    def _command_reply(self,code,data,operation,arguments):
        # Only HTTP response threads write files; reader/watchdog paths keep
        # their own bounded RAM history and never wait for this journal lock.
        control=ros_node.control.health() if ros_node else {}
        if ros_node:
            event=ros_node.control._event('http_outcome',operation=operation,http_status=code,response=data)
            control['event_sequence']=event['sequence']
        outcome=self.server.command_journal.record(operation,arguments,code,data,control)
        self._json(code,dict(data,journal=outcome))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        p = self.path.split('?')
        path = p[0]
        q = p[1] if len(p) > 1 else ''

        if observe_only:
            import urllib.parse
            params=urllib.parse.parse_qs(q)
            stop=(path=='/api/cmd' and params.get('val',[''])[0]=='STOP') or (
                  path=='/api/auto' and params.get('act',[''])[0].upper()=='STOP')
            if path in ('/api/cmd','/api/pid','/api/auto') and not stop:
                self._command_reply(423,{'status':'FAILED','reason':'OBSERVE_ONLY'},path,params)
                return

        if path == '/api/diagnostics':
            report=ros_node.control.diagnostics() if ros_node else {'status':'NO_TRANSPORT'}
            report['command_journal']=self.server.command_journal.snapshot()
            self._json(200 if ros_node else 503,report)
            return

        if path == '/api/telemetry':
            if ros_node is None:
                self._json(503,{'status':'NO_TRANSPORT','mode':'DASHBOARD_ONLY',
                                'reason':'Chỉ xem giao diện; chưa kết nối điều khiển xe'})
                return
            with state.lock:
                d = {
                    "auto": state.auto_mode,
                    "status": 'OBSERVE_ONLY' if observe_only else state.safety_status,
                    "hz": state.hz,
                    "control": ros_node.control.health() if ros_node else {},
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
                        "yaw": state.map_origin_yaw, "frame": state.map_frame,
                        "frontiers": state.frontier_count,
                        "reachable_frontiers": state.frontier_reachable,
                        "unknown_cells": state.unknown_cells,
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
                    "yaw": state.map_origin_yaw, "frame": state.map_frame,
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
            val = params.get('val',[''])[0]
            if ros_node:
                if val.startswith('M ') or (val.startswith('V ') and val != 'V 0.000 0.000'):
                    with state.lock: state.auto_mode = False
                ok,reason = ros_node.send_cmd(val)
            else:
                ok,reason = False,'NO_TRANSPORT'
            self._command_reply(200 if ok else 422, {'status':'SENT' if ok else 'FAILED','reason':reason},'COMMAND',{'val':val})
            return

        elif path == '/api/auto_config':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                spd_rpm = float(params.get('speed', [100.0])[0])
                trn_rpm = float(params.get('turn', [35.0])[0])
                with state.lock:
                    state.auto_target_speed_rpm = spd_rpm
                    state.auto_target_turn_rpm = trn_rpm
                    state.cruise_speed_mps = max(0.04, min(0.55, (spd_rpm * 2.0 * math.pi * 0.0366) / 60.0))
                    state.turn_w_rads = max(0.10, min(0.95, (trn_rpm * 2.0 * math.pi * 0.0366) / (60.0 * 0.096)))
                result = {
                    'status': 'OK',
                    'speed_rpm': spd_rpm,
                    'turn_rpm': trn_rpm,
                    'cruise_mps': state.cruise_speed_mps,
                    'turn_w': state.turn_w_rads
                }
            except Exception as e:
                result = {'status': 'ERROR', 'reason': str(e)}
            self._command_reply(200 if result.get('status')=='OK' else 400, result, 'AUTO_CONFIG', params)
            return

        elif path == '/api/pid':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                kp,ki,kd = [float(params[k][0]) for k in ('kp','ki','kd')]
                kf = float(params.get('kf', [1.80 if operator_control_config else 0.45])[0])
                result = ros_node.control.tuning(kp,ki,kd,kf=kf) if ros_node else {'status':'FAILED','reason':'NO_TRANSPORT'}
            except (ValueError,KeyError,IndexError):
                result = {'status':'REJECTED','reason':'INVALID_INPUT'}
            self._command_reply(200 if result['status']=='APPLIED' else 422,result,'PID',params)
            return

        elif path == '/api/history_csv':
            payload = ros_node.control.history_csv() if ros_node else 'id,time,kp,ki,kd,kf,status,reason\r\n'
            self.send_response(200)
            self.send_header('Content-Type','text/csv; charset=utf-8')
            self.send_header('Content-Disposition','attachment; filename="agv_pid_history.csv"')
            self.end_headers()
            self.wfile.write(('\ufeff'+payload).encode('utf8'))
            return

        elif path == '/api/auto':
            import urllib.parse
            act = urllib.parse.parse_qs(q).get('act',[''])[0].upper()
            ok,reason = False,'NO_TRANSPORT'
            blockers,snapshot=[],{}
            if ros_node and act == 'START':
                ok,reason,blockers,snapshot=ros_node.start_auto()
            elif ros_node and act == 'STOP':
                ok,reason = ros_node.send_cmd('STOP')
            self._command_reply(200 if ok else 422,{'status':'ok' if ok else 'FAILED',
                'auto':state.auto_mode,'reason':reason,'blockers':blockers,'gate':snapshot},'AUTO_'+act,{'act':act})
            return

        else:
            # Phục vụ giao diện Dashboard chuẩn Cyberpunk Pro
            html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'index_cyberpunk.html')
            if not os.path.exists(html_file):
                html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index_cyberpunk.html')
            if os.path.exists(html_file):
                with open(html_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self._cors()
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, 'File Not Found')

def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='AGV web/ROS controller; no automatic ARM')
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--dashboard-only',action='store_true',
                        help='Serve the real UI without opening UART or initializing ROS')
    modes.add_argument('--observe-only',action='store_true',
                        help='Live telemetry/STOP only; reject ARM, drive, tuning and AUTO START')
    modes.add_argument('--operator-control',action='store_true',
                       help='Continuous manual/AUTO operation with explicit ARM and sensor/caller watchdogs')
    modes.add_argument('--motion-window-s',type=float,
                       help='One operator-initiated trial, at most 15s, V<=.04; no MAN/PID/reARM')
    options=parser.parse_args(argv)
    if options.motion_window_s is not None and (not finite(options.motion_window_s) or not 0 < options.motion_window_s <= 15):
        parser.error('motion window must be finite, positive and at most 15 seconds')
    global ros_node, observe_only, motion_window_s_config, operator_control_config
    ros_node = None
    observe_only = options.observe_only
    motion_window_s_config = options.motion_window_s
    operator_control_config = getattr(options, 'operator_control', False)
    # Reserve the HTTP port first: a bind failure must never open hardware.
    server = ThreadedHTTPServer(('0.0.0.0', PORT), WebHandler)
    ros_thread = None
    initialized = False
    stopped = True
    import signal
    previous_term = None
    try:
        if not options.dashboard_only:
            rclpy.init()
            initialized = True
            ros_node = AGVROSNode()
            ros_thread = threading.Thread(target=rclpy.spin, args=(ros_node,), daemon=True)
            ros_thread.start()
        if threading.current_thread() is threading.main_thread():
            previous_term = signal.signal(signal.SIGTERM,lambda *a:(_ for _ in ()).throw(KeyboardInterrupt()))
        print(f'=== AGV WEB PORT {PORT}; MODE={"DASHBOARD_ONLY" if options.dashboard_only else "OPERATOR_CONTROL" if options.operator_control else "DISARMED_STARTUP"} ===',flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if ros_node: stopped = ros_node.close_control()
        finally:
            server.server_close()
            if ros_node: ros_node.destroy_node()
            if initialized: rclpy.shutdown()
            if ros_thread: ros_thread.join(.5)
            if previous_term is not None: signal.signal(signal.SIGTERM,previous_term)
        if not stopped:
            raise RuntimeError('Shutdown STOP unconfirmed or cleanup failed; check vehicle / cut power if moving')

if __name__ == '__main__':
    main()
