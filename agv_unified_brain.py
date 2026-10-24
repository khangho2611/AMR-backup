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

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
import math
import serial
import threading
from agv_navigation import GridPlanner, finite, slam_censored_ranges, twist_centres, valid_body_bounds
from agv_command_session import CommandSession
from agv_speed_profile import (NORMAL_RPM, SLOW_RPM, rpm_to_speed, rpm_to_turn,
                               twist_to_wheels, running_wheels, wheels_to_twist)
from agv_command_journal import CommandOutcomeJournal
from agv_preflight_static_collector import acquire_port_lock, cleanup_lock
from agv_ai_bridge import (ai1_prepare_scan, measured_twist, ai1_velocity, ai2_observation,
                           ai2_ranked_candidates, ai2_valid_action_mask,
                           reproject_visited_cells)
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
SERIAL_PORT = '/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'  # ESP32 CH340, 115200 baud
BAUDRATE = 115200
STEER_DEADBAND_RAD = 0.035  # ~2 deg; matched to 0.5 RPM wheel quantization setpoint
motion_window_s_config = None

class PathTarget(tuple):
    """Stable lookahead target carrying segment orientation and cross-track offset."""
    def __new__(cls, x, y, path_yaw=None, e_lat=0.0, *args, **kwargs):
        obj = super().__new__(cls, (float(x), float(y)))
        obj.path_yaw = path_yaw
        obj.e_lat = e_lat
        for k, v in kwargs.items():
            setattr(obj, k, v)
        return obj

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
        self.wall_margin_m = float(os.environ.get('AGV_WALL_MARGIN_M', '0.00' if globals().get('operator_control_config', False) else '.15'))
        default_speed = float(os.environ.get('AGV_AUTO_SPEED_RPM', '40.0' if globals().get('operator_control_config', False) else str(NORMAL_RPM)))
        self.auto_target_speed_rpm = default_speed
        self.cruise_speed_mps = rpm_to_speed(self.auto_target_speed_rpm)
        default_turn = 35.0 if globals().get('operator_control_config', False) else NORMAL_RPM
        self.auto_target_turn_rpm = float(os.environ.get('AGV_AUTO_TURN_RPM', default_turn))
        self.turn_w_rads = rpm_to_turn(self.auto_target_turn_rpm)
        self.map_mono = 0.
        self.map_version = 0
        self.map_origin_yaw = 0.
        self.map_frame = ''
        self.scan_mono = 0.
        self.scan_frame = ''
        self.frontier_reachable = None
        self.frontier_selectable = 0
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

        # Vết bánh xe (Breadcrumbs / Trajectory lưu tạm trong RAM)
        self.path_history = deque(maxlen=2000)
        self.total_distance_m = 0.0
        self.last_path_pose = None
        self.visited_cells = set()

state = AGVSharedState()

class AGVROSNode(Node):
    _is_pure_spinning = False
    _spin_start_time = None
    _locked_spin_wp = None
    _locked_spin_goal = None
    _spin_timeout_until = 0.0
    _active_path = None
    _active_path_goal = None
    _active_path_map_ver = None

    @property
    def _follow_spinning(self):
        return getattr(self, '_is_pure_spinning', False)

    @_follow_spinning.setter
    def _follow_spinning(self, v):
        self._is_pure_spinning = bool(v)

    @property
    def _follow_spin_start(self):
        return getattr(self, '_spin_start_time', None)

    @_follow_spin_start.setter
    def _follow_spin_start(self, v):
        self._spin_start_time = v

    @property
    def _follow_spin_locked_wp(self):
        return getattr(self, '_locked_spin_wp', None)

    @_follow_spin_locked_wp.setter
    def _follow_spin_locked_wp(self, v):
        self._locked_spin_wp = v

    @property
    def _follow_spin_goal(self):
        return getattr(self, '_locked_spin_goal', None)

    @_follow_spin_goal.setter
    def _follow_spin_goal(self, v):
        self._locked_spin_goal = v

    @property
    def _follow_spin_cooldown_until(self):
        return getattr(self, '_spin_timeout_until', 0.0)

    @_follow_spin_cooldown_until.setter
    def _follow_spin_cooldown_until(self, v):
        self._spin_timeout_until = float(v) if v is not None else 0.0

    def __init__(self):
        super().__init__('agv_unified_brain')
        
        # Finish ROS setup before opening hardware; constructor failures must
        # never leave an unmonitored UART or reader behind.
        self.ser = None
        self._port_lock = None
        self._port_lock_path = None
        self._rx_line = b''
        self.initialize_navigation()
        checkpoint = os.environ.pop('AGV_NAV_RESTART_CHECKPOINT', None)
        if checkpoint:
            self._restore_restart_checkpoint(checkpoint)
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
        # C1 reports at ~10 Hz. Allow a bounded two-frame scheduling gap,
        # while retaining the fail-closed watchdog and per-command scan gate.
        self.scan_max_age_s = float(os.environ.get('AGV_SCAN_MAX_AGE_S', '0.65'))
        self.progress_timeout_s = float(os.environ.get('AGV_PROGRESS_TIMEOUT_S', '3.5'))
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
            self.control.operator_rpm_profile = is_op and motion_window_s_config is None
            if is_op:
                state.auto_target_speed_rpm = float(os.environ.get('AGV_AUTO_SPEED_RPM', '40.0'))
                state.cruise_speed_mps = rpm_to_speed(state.auto_target_speed_rpm)
                self.control.auto_speed_rpm = state.auto_target_speed_rpm
                state.auto_target_turn_rpm = float(os.environ.get('AGV_AUTO_TURN_RPM', '35.0'))
                state.turn_w_rads = rpm_to_turn(state.auto_target_turn_rpm)
                self.control.auto_turn_rpm = state.auto_target_turn_rpm
            else:
                self.control.auto_speed_rpm = state.auto_target_speed_rpm
                self.control.auto_turn_rpm = state.auto_target_turn_rpm
            self.control.slow_speed_requested = lambda: getattr(self, '_cautious', False)
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
        # The LiDAR may still stream when the MCU telemetry is disconnected.
        # Never publish the last odometry pose under a new ROS timestamp:
        # slam_toolbox would mistake a frozen robot for a valid moving base.
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

    def send_cmd(self, cmd_str, autonomous=False, planned_turn=False):
        clean = cmd_str.strip()
        if clean == 'STOP':
            with state.lock:
                state.auto_mode = False
            self.explore_state = 'IDLE'
            return self.control.request_stop()
        if clean in ('RESET', 'CLEAR_FAULT'):
            # Explicit recovery requires a separate MCU ACK. A reset cannot
            # manufacture ARMED or STOP_CONFIRMED state on the Pi.
            ok, reason = self.control.request_clear_fault()
            if not ok:
                return False, reason
            with state.lock:
                state.auto_mode = False
                state.explore_phase = 'RESET: chờ MCU ACK và telemetry dừng'
            return True, reason
        if clean == 'RESET_MAP':
            return self.reset_slam_map()
        if clean == 'ARM':
            return self.control.request_arm()
        if not autonomous and self.control.strict_preflight and (clean.startswith('M ') or (clean.startswith('V ') and clean != 'V 0.000 0.000')) and not self.control.armed:
            ok, reason = self.control.request_arm()
            if not ok:return False, reason
        return self.control.drive(clean, autonomous=autonomous)

    def reset_slam_map(self):
        """Xóa trắng bản đồ và vết đường đi để bắt đầu quét lại từ đầu."""
        # Resetting map coordinates during autonomous motion invalidates every
        # planned path and HOME. Require fresh proof of a stationary MCU.
        with state.lock:
            if state.auto_mode:
                return False, 'AUTO_ACTIVE_STOP_FIRST'
        control = getattr(self, 'control', None)
        if control is None:
            return False, 'MCU_HEALTH_UNAVAILABLE'
        health = control.health()
        d0 = health.get('latest_d0') or {}
        age = health.get('d0_age_s')
        if age is None or not 0 <= age <= .25:
            return False, 'D0_STALE_CANNOT_CONFIRM_STATIONARY'
        keys = ('l_rpm', 'r_rpm', 'l_tgt', 'r_tgt')
        try:
            readings = [float(d0[k]) for k in keys]
        except (KeyError, TypeError, ValueError, OverflowError):
            return False, 'MCU_STATIONARITY_UNKNOWN'
        if not all(math.isfinite(v) for v in readings):
            return False, 'MCU_STATIONARITY_UNKNOWN'
        if any(abs(v) > .5 for v in readings):
            return False, 'MCU_MOVING_STOP_FIRST'
        now = time.monotonic()
        if now - getattr(self, '_last_slam_reset_at', float('-inf')) < 1.0:
            return False, 'RESET_COOLDOWN'
        # Launch first. The launcher's --start branch can exit zero even when
        # slam_toolbox failed; verify both exit status and the actual node.
        # Never clear the map/mission on an unconfirmed restart.
        try:
            import subprocess
            cmd = ['bash', '/home/khangho/slam_calibration_tools/run_slam_tuned.sh', '--start']
            started = subprocess.run(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, timeout=12, check=False)
            if started.returncode != 0:
                self.get_logger().warn('SLAM launcher failed: ' +
                                       started.stderr.decode('utf-8', errors='replace')[-300:])
                return False, 'SLAM_RESTART_SCRIPT_FAILED'
            # ros2 launch starts the lifecycle node asynchronously. A single
            # immediate pgrep creates a false RESET failure on a slow Pi.
            # Bound the wait and keep the previous map on genuine failures.
            deadline = time.monotonic() + 6.0
            while True:
                alive = subprocess.run(
                    ['pgrep', '-f', '^/opt/ros/jazzy/lib/slam_toolbox/async_slam_toolbox_node( |$)'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=2, check=False)
                if alive.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(.25)
            if alive.returncode != 0:
                return False, 'SLAM_RESTART_NODE_NOT_RUNNING'
        except Exception as exc:
            self.get_logger().warn(f'EXCEPTION GỌI RESET: {exc}')
            return False, 'SLAM_RESTART_FAILED_' + type(exc).__name__
        self._last_slam_reset_at = now
        with state.lock:
            state.path_history.clear()
            state.visited_cells.clear()
            state.total_distance_m = 0.0
            state.last_path_pose = None
            state.map_received = False
            state.map_data = []
            state.target_goal_x = 0.0
            state.target_goal_y = 0.0
            state.explore_phase = 'ĐÃ RESET BẢN ĐỒ: Đang quét lại từ đầu'
        self.goal = None
        self.home = None  # A new SLAM session has a new map origin/TF trajectory.
        self.explore_state = 'IDLE'
        self._goal_type = 'FRONTIER'
        self._ai2_last_visited_count = None
        self._ai2_no_progress_steps = 0
        self._explore_partial = False
        self._planners = {}
        self._planner = self._planner_key = None
        self.blocked_goals = []
        self.blocked_regions = []
        self.progress.clear()
        self.get_logger().info('ĐÃ GỬI LỆNH KHỞI TẠO LẠI SLAM; CHỜ BẢN ĐỒ MỚI')
        return True, 'SLAM_RESTART_REQUESTED'

    def _reader_worker(self):
        while not self._reader_stop.is_set():
            self.serial_read_loop()
            self._reader_stop.wait(.01)

    def _watchdog_worker(self):
        while not self._reader_stop.wait(.02):
            self.control.watchdog_tick()
            if self.control.latched:
                with state.lock:
                    state.auto_mode = False

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
                    state.robot_x,state.robot_y,state.robot_th=self._continuous_odom_pose(latest)
                    state.left_rpm,state.right_rpm=latest['l_rpm'],latest['r_rpm']
                    state.left_pwm,state.right_pwm=latest['l_pwm'],latest['r_pwm']
                finally:state.lock.release()
        except Exception as exc:
            self.control.request_stop('READER_ERROR:' + type(exc).__name__,wait=False)

    def _scan_unavailable(self, reason):
        self._scan_tf_valid = False
        with self.control.lock:
            self.control.scan_time=None
            active=(self.control.armed or self.control.motion or self.control.arm_sent is not None)
            needs_scan=self.control.autonomy_allowed is not False
        with state.lock:
            state.scan_mono=0.
            state.explore_phase='CHỜ LIDAR: '+reason
        if active and needs_scan:
            self.control.hold_for_scan(reason)

    def scan_cb(self, msg):
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        scan_max_age = max(.65, getattr(self, 'scan_max_age_s', .25)) if is_op else getattr(self, 'scan_max_age_s', .25)
        if not self._fresh_ros_header(msg.header, scan_max_age):
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
            mount_valid = True
        else:
            try:
                mount = self.tf_buffer.lookup_transform('base_footprint',msg.header.frame_id,Time())
                mount_x, mount_y = mount.transform.translation.x,mount.transform.translation.y
                mount_yaw = self._yaw(mount.transform.rotation)
                if not finite(mount_x) or not finite(mount_y):
                    raise ValueError('Invalid scan TF')
                stamp = mount.header.stamp.sec+mount.header.stamp.nanosec*1e-9
                # Static TF stamp zero is timeless; dynamic transforms expire.
                if stamp and not 0 <= self.get_clock().now().nanoseconds*1e-9-stamp <= .50:
                    raise ValueError('Stale scan TF')
                mount_valid = True
            except Exception:
                if is_op:
                    # Keep radar visualization available, but block AUTO because
                    # the physical sensor mounting geometry is unverified.
                    mount_x, mount_y, mount_yaw = 0., 0., 0.
                    mount_valid = False
                else:
                    self._scan_unavailable('MISSING_SCAN_TF')
                    return
        bounds = state.body_bounds_m
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        if hasattr(self,'pub_slam_scan'):
            import copy
            filtered = copy.deepcopy(msg)
            try:
                clean_ranges = list(msg.ranges)
                angle_cur = msg.angle_min
                for idx, r in enumerate(clean_ranges):
                    if math.isfinite(r) and msg.range_min <= r < min(msg.range_max, 16.0):
                        x = mount_x + r*math.cos(angle_cur+mount_yaw)
                        y = mount_y + r*math.sin(angle_cur+mount_yaw)
                        if bounds is not None:
                            if (bounds[0] - 0.01 <= x <= bounds[2] + 0.01 and
                                bounds[1] - 0.01 <= y <= bounds[3] + 0.01):
                                clean_ranges[idx] = float('inf')
                            elif is_op and x <= 0.02 and math.hypot(x, y) <= 0.25:
                                clean_ranges[idx] = float('inf')
                        elif math.hypot(x, y) <= (state.body_radius_m or 0.20) * (0.85 if is_op else 0.75):
                            clean_ranges[idx] = float('inf')
                    angle_cur += step
                filtered.ranges = slam_censored_ranges(clean_ranges, msg.range_min, msg.range_max)
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
            # Inf and saturated readings mean no measured return. Leave their
            # bins unknown (0), especially in the 45-degree forward safety
            # cone. A max-range placeholder must not enable forward motion.
            if math.isfinite(r) and msg.range_min <= r < min(msg.range_max, 16.0):
                x = mount_x + r*math.cos(angle+mount_yaw)
                y = mount_y + r*math.sin(angle+mount_yaw)
                is_self = False
                if bounds is not None:
                    if (bounds[0] - 0.01 <= x <= bounds[2] + 0.01 and
                        bounds[1] - 0.01 <= y <= bounds[3] + 0.01):
                        is_self = True
                    elif is_op and x <= 0.02 and math.hypot(x, y) <= 0.25:
                        is_self = True
                elif math.hypot(x, y) <= (state.body_radius_m or 0.20) * (0.85 if is_op else 0.75):
                    is_self = True

                if not is_self:
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

            f_cone = [points[d % 360] for d in range(-25, 26) if points[d % 360] > 0]
            f_cone_min = min(f_cone, default=9.99)
            if f_cone_min < 0.25 or state.min_dist_m <= 0.15:
                state.safety_status = "DANGER_STOP"
            elif f_cone_min < 0.50 or state.min_dist_m <= 0.35:
                state.safety_status = "WARNING"
            else:
                state.safety_status = "SAFE"

        rotation_clear = self._rotation_clear()
        self._scan_tf_valid = mount_valid
        with self.control.lock:
            self.control.scan_time = self.control.clock() if mount_valid else None
            # Front drive needs actual returns in the forward cone. Unknown rays
            # do not become an artificial 999cm free direction.
            forward = [points[d % 360] for d in range(-22,23)]
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            min_pts = 30
            # Use the same enclosing body and margin as the swept validator.
            # A fixed 40 cm gate vetoed valid cautious A* corridors forever.
            min_dist = (state.body_radius_m or .20) + (.03 if getattr(self, '_cautious', False)
                                                       else state.wall_margin_m)
            self.control.scan_clear = sum(d > 0 for d in forward) >= min_pts and min(d for d in forward if d > 0) >= min_dist
            self.control.rotation_clear = rotation_clear
        if not mount_valid:
            with self.control.lock:
                active = self.control.armed or self.control.motion
                auto = self.control.autonomy_allowed is True
            if active and auto:
                self.control.hold_for_scan('MISSING_SCAN_TF')
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
        frame_changed = False
        with state.lock:
            identity = (frame,w,h,res,ox,oy,yaw)
            old = (state.map_frame,state.map_width,state.map_height,state.map_resolution,
                   state.map_origin_x,state.map_origin_y,state.map_origin_yaw)
            if state.map_frame and state.map_frame != frame:
                frame_changed = True
                # Avoid reloading ONNX models while holding the map lock.
                self._invalidate_map_navigation()
                # Reframed map cannot silently move the captured home.
                state.auto_mode = False
            if state.map_data != data or old != identity:
                state.visited_cells = reproject_visited_cells(
                    state.visited_cells, old, identity, data)
            state.map_width,state.map_height,state.map_resolution = w,h,res
            state.map_origin_x,state.map_origin_y,state.map_origin_yaw = ox,oy,yaw
            state.map_frame = frame
            if state.map_data != data or old != identity:
                state.map_version += 1
            state.map_data,state.map_received,state.map_mono = data,True,time.monotonic()
        if frame_changed and getattr(self, 'control', None) is not None:
            # A new frame invalidates all world-frame goals. The previous
            # drive must be stopped even after AUTO has been cancelled.
            self.control.request_stop('MAP_FRAME_CHANGED', wait=False)

    @staticmethod
    def _slam_process_token(pid):
        with open(f'/proc/{int(pid)}/stat', encoding='utf-8') as stream:
            # PID reuse must not make an old map mission appear current.
            return stream.read().split(') ', 1)[1].split()[19]

    def _continuous_odom_pose(self, packet):
        """Retain odom->base continuity when reopening UART resets MCU odometry."""
        resume = getattr(self, '_odom_resume_pose', None)
        if resume is not None:
            yaw = resume[2] - packet['th']
            c, s = math.cos(yaw), math.sin(yaw)
            self._odom_restart_offset = (resume[0] - c*packet['x'] + s*packet['y'],
                                         resume[1] - s*packet['x'] - c*packet['y'], yaw)
            self._odom_resume_pose = None
        offset = getattr(self, '_odom_restart_offset', None)
        if offset is None:
            return packet['x'], packet['y'], packet['th']
        dx, dy, yaw = offset
        c, s = math.cos(yaw), math.sin(yaw)
        return (dx + c*packet['x'] - s*packet['y'],
                dy + s*packet['x'] + c*packet['y'], packet['th'] + yaw)

    def _restore_restart_checkpoint(self, path):
        """One-shot controller migration; never restore AUTO/ARM or stale SLAM."""
        try:
            with open(path, encoding='utf-8') as stream:
                saved = json.load(stream)
            if self._slam_process_token(saved['slam_pid']) != saved['slam_token']:
                return False
            home = saved['home']
            m, trace = saved['map_info'], saved['trajectory']
            if (len(home) != 3 or not all(finite(v) for v in home) or
                    not isinstance(m['frame'], str) or
                    type(m['w']) is not int or type(m['h']) is not int or
                    not 0 < m['w'] * m['h'] <= 2_000_000 or
                    not all(finite(m[k]) for k in ('res', 'ox', 'oy', 'yaw')) or
                    not .001 <= m['res'] <= 1. or
                    not finite(trace['distance_m']) or trace['distance_m'] < 0 or
                    len(trace['path']) > 5000 or
                    any(len(p) != 2 or not all(finite(v) for v in p) for p in trace['path'])):
                return False
            self.home = tuple(home)
            self._cautious = saved.get('cautious') is True
            odom = saved.get('odom_pose') or {}
            if all(finite(odom.get(k)) for k in ('x', 'y', 'th')):
                self._odom_resume_pose = (odom['x'], odom['y'], odom['th'])
            with state.lock:
                state.map_width, state.map_height = m['w'], m['h']
                state.map_resolution = m['res']
                state.map_origin_x, state.map_origin_y, state.map_origin_yaw = m['ox'], m['oy'], m['yaw']
                state.map_frame = m['frame']
                state.path_history.clear()
                state.path_history.extend(trace['path'])
                state.last_path_pose = tuple(trace['path'][-1]) if trace['path'] else None
                state.total_distance_m = trace['distance_m']
                state.visited_cells = {tuple(c) for c in saved.get('visited_cells', [])
                                       if len(c) == 2 and all(type(v) is int for v in c)
                                       and 0 <= c[0] < m['w'] and 0 <= c[1] < m['h']}
            return True
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            return False
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def initialize_navigation(self):
        self.explore_state = 'IDLE'
        self.home = None
        self.goal = None
        self._goal_type = 'FRONTIER'
        self.blocked_goals = []
        self.blocked_regions = []
        self.progress = deque()
        self._planner_key,self._planner = None,None
        self._planners = {}
        self._home_stop_sent = False
        self._cautious = False
        self._normal_clear_since = None
        self._is_pure_spinning = False
        self._spin_start_time = None
        self._locked_spin_wp = None
        self._locked_spin_goal = None
        self._spin_timeout_until = 0.0
        self.ai1_runtime = None
        self.ai2_session = None
        # Models are still unapproved for the real robot. In shadow mode their
        # predictions are observable, but conventional navigation keeps control.
        self.ai1_mode = os.environ.get('AGV_AI1_MODE', 'shadow').lower()
        self.ai2_mode = os.environ.get('AGV_AI2_MODE', 'shadow').lower()
        if self.ai1_mode not in ('off', 'shadow', 'control'):
            self.ai1_mode = 'shadow'
        if self.ai2_mode not in ('off', 'shadow', 'control'):
            self.ai2_mode = 'shadow'
        self._ai1_active = False
        self._ai1_v = None
        self._ai1_w = None
        self._ai1_shadow_cmd = None
        self._ai1_error = None
        self._ai2_shadow_goal = None
        self._ai2_error = None
        self._ai2_best_action = None
        self._ai2_q_vals = None
        self._ai2_last_visited_count = None
        self._ai2_no_progress_steps = 0
        self._explore_partial = False
        try:
            from ai_local_planner.runtime import LocalPlannerRuntime
            ai1_model = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ai_local_planner', 'exported', 'local_planner.onnx')
            if os.path.exists(ai1_model):
                self.ai1_runtime = LocalPlannerRuntime(ai1_model)
                print(f"[OK] ĐÃ NẠP MÔ HÌNH AI 1 (NÉ CẢN): {ai1_model}", flush=True)
        except Exception as e:
            self.ai1_runtime = None
            print(f"[CẢNH BÁO] Không nạp được AI 1: {e}", flush=True)

        try:
            import onnxruntime as ort
            ai2_model = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'coverage_model.onnx')
            if os.path.exists(ai2_model):
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                self.ai2_session = ort.InferenceSession(ai2_model, sess_options=opts, providers=["CPUExecutionProvider"])
                self.ai2_map_name = self.ai2_session.get_inputs()[0].name
                self.ai2_feat_name = self.ai2_session.get_inputs()[1].name
                print(f"[OK] ĐÃ NẠP MÔ HÌNH AI 2 (PHỦ KÍN SÀN): {ai2_model}", flush=True)
        except Exception as e:
            self.ai2_session = None
            print(f"[CẢNH BÁO] Không nạp được AI 2: {e}", flush=True)

        with state.lock:
            state.path_history.clear()
            state.total_distance_m = 0.0
            state.last_path_pose = None
            state.visited_cells.clear()
            state.target_goal_x = 0.0
            state.target_goal_y = 0.0

    def _invalidate_map_navigation(self):
        """Invalidate routes after a TF frame change, retaining AI runtimes."""
        with state.lock:
            self.home = None
            self.goal = None
            self.explore_state = 'IDLE'
            self._goal_type = 'FRONTIER'
            self.blocked_goals = []
            self.blocked_regions = []
            self.progress = deque()
            self._is_pure_spinning = False
            self._spin_start_time = None
            self._locked_spin_wp = None
            self._locked_spin_goal = None
            self._spin_timeout_until = 0.0
            self._active_path = None
            self._active_path_goal = None
            self._active_path_map_ver = None
            self._planner_key, self._planner = None, None
            self._planners = {}
            self._home_stop_sent = False
            self._ai1_active = False
            self._ai1_shadow_cmd = None
            self._ai2_shadow_goal = None
            self._ai2_last_visited_count = None
            self._ai2_no_progress_steps = 0
            self._explore_partial = False
            state.path_history.clear()
            state.total_distance_m = 0.0
            state.last_path_pose = None
            state.target_goal_x = state.target_goal_y = 0.0

    def _grid(self, margin=None):
        with state.lock:
            now = time.monotonic()
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            max_map_age = 15.0 if is_op else 2.0
            if not state.map_received or not 0 <= now-state.map_mono <= max_map_age:
                return None
            if margin is None:
                is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
                margin = float(os.environ.get('AGV_WALL_MARGIN_M', '0.00' if is_op else (.03 if getattr(self,'_cautious',False) else state.wall_margin_m)))
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
        if grid is None: return False
        bounds = state.body_bounds_m
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        if is_op and bounds is not None and hasattr(grid, 'box_swept_clear'):
            clear = grid.box_swept_clear(pose, 0., 0., bounds, allow_start_overlap=True)
        else:
            clear = grid.swept_clear(pose, 0., 0.)
        if not clear: return False
        self._cautious=True
        self._normal_clear_since=None
        self.blocked_regions=[]
        if hasattr(self, 'progress') and hasattr(self.progress, 'clear'):
            self.progress.clear()
        with state.lock:state.explore_phase='VÙNG VÀNG: đi chậm theo khoảng trống đủ thân xe'
        return True

    def _restore_normal_clearance(self, pose):
        if not getattr(self,'_cautious',False):return
        grid=self._grid(margin=state.wall_margin_m)
        clear=grid is not None and grid.swept_clear(pose,.20,0.)
        with state.lock:
            returns = [d for d in state.ranges if finite(d) and 0 < d < 16.]
        clear = clear and bool(returns) and min(returns) > grid.radius
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
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)

        # Nới lỏng điểm xuất phát: nếu robot đứng sát tường, tìm ô lân cận trống gần nhất
        qx, qy = rx, ry
        start_cell = grid.world_to_cell(rx, ry)
        if start_cell is None:
            with state.lock:
                state.frontier_reachable = None
                state.frontier_count = 0
                state.frontier_selectable = 0
                state.unknown_cells = None
            return None
        if not grid.traversable(start_cell):
            best_start = None
            best_dist = float('inf')
            for ddx in range(-4, 5):
                for ddy in range(-4, 5):
                    cand = (start_cell[0] + ddx, start_cell[1] + ddy)
                    if grid.traversable(cand):
                        d = math.hypot(ddx, ddy)
                        if d < best_dist:
                            best_dist = d
                            best_start = cand
            if best_start is not None:
                qx, qy = grid.cell_to_world(*best_start)

        summary = grid.frontiers((qx,qy),[b[:3] for b in self.blocked_goals],
                                [b[:3] for b in self.blocked_regions])
        # Failed goals have a bounded cooldown. Clearing all exclusions when
        # they hide every candidate would immediately reselect the same
        # unreachable goal and lock AUTO into an endless HOLD/retry cycle.
        with state.lock:
            state.frontier_reachable = None if summary is None else summary['reachable_frontiers']
            state.frontier_selectable = 0 if summary is None else len(summary['goals'])
            state.frontier_count = 0 if summary is None else len(summary['goals'])
            state.unknown_cells = None if summary is None else summary['unknown_cells']
        if not summary or not summary['goals']:
            return None
        pose = self._pose_map()
        yaw = pose[2] if pose is not None else None
        best_goal = None
        best_score = float('inf')
        cand_goals = list(summary['goals'])
        # Lọc các mục tiêu có khoảng cách đủ an toàn để AGV di chuyển và mở rộng tầm nhìn lidar (>= 0.55m).
        # Loại trừ các điểm quá gần chân xe (< 0.55m) trừ khi không còn mục tiêu nào khác.
        far_candidates = [g for g in cand_goals if math.hypot(g[0] - rx, g[1] - ry) >= 0.55]
        eval_candidates = far_candidates if far_candidates else cand_goals
        if len(eval_candidates) > 10:
            eval_candidates.sort(key=lambda g: math.hypot(g[0] - rx, g[1] - ry))
            eval_candidates = eval_candidates[:10]

        for g in eval_candidates:
            euclid_dist = math.hypot(g[0] - rx, g[1] - ry)
            path = grid.path((qx, qy), g)
            if path is None:
                continue
            path_len = len(path) * grid.res
            heading_err = 0.0
            if yaw is not None:
                dx, dy = g[0] - rx, g[1] - ry
                target_heading = math.atan2(dy, dx)
                heading_err = abs((target_heading - yaw + math.pi) % (2 * math.pi) - math.pi)

            # Phạt các điểm quá gần (< 0.80m) để xe đi dứt khoát 1 đoạn đường mở rộng map
            dist_pen = 0.0
            if euclid_dist < 0.80:
                dist_pen = (0.80 - euclid_dist) * 2.5
            elif euclid_dist > 2.50:
                dist_pen = (euclid_dist - 2.50) * 0.6

            # Điểm ưu tiên: Chiều dài đường đi thực tế + ưu tiên hướng trước mặt xe + phạt cự ly
            score = path_len * 1.0 + heading_err * 1.0 + dist_pen
            if score < best_score:
                best_score = score
                best_goal = g
        # Every exported frontier must be reachable through known-free space.
        # A timed-out or disconnected candidate must not become a drive goal.
        return best_goal

    def _get_safe_home_target(self, pose=None):
        """Find a free HOME connected to the current robot pose."""
        if self.home is None:
            return None
        grid = self._grid()
        if (grid is None or not hasattr(grid, 'world_to_cell') or
                not hasattr(grid, 'traversable')):
            return None
        if pose is None:
            pose = self._pose_map()
        if pose is None or not hasattr(grid, 'path'):
            return None
        start = grid.world_to_cell(pose[0], pose[1])
        if not grid.traversable(start):
            return None

        def reachable(xy):
            # A geometrically free cell may be separated by a wall. Never
            # select such a home just because the target cell is traversable.
            return grid.path(pose[:2], xy) is not None

        h_cell = grid.world_to_cell(self.home[0], self.home[1])
        if h_cell is not None and grid.traversable(h_cell) and reachable(self.home[:2]):
            return (self.home[0], self.home[1])
        # Nếu vị trí ban đầu nằm sát vật cản (do bán kính lạm phát robot), tìm ô traversable lân cận gần nhất
        if h_cell is not None and hasattr(grid, 'cell_to_world'):
            offsets = sorted(((dx, dy) for dx in range(-5, 6) for dy in range(-5, 6)),
                             key=lambda p: p[0] * p[0] + p[1] * p[1])
            checked = 0
            for dx, dy in offsets:
                c = (h_cell[0] + dx, h_cell[1] + dy)
                if grid.traversable(c):
                    checked += 1
                    xy = grid.cell_to_world(*c)
                    if reachable(xy):
                        return xy
                    if checked >= 12:  # Bound planning work on Raspberry Pi.
                        break
        # An occupied or unknown HOME must never silently become a goal.
        return None

    def _get_safe_point_target(self, x, y, pose=None):
        """Find a safe, reachable target cell near (x, y) connected to the current robot pose."""
        grid = self._grid()
        if (grid is None or not hasattr(grid, 'world_to_cell') or
                not hasattr(grid, 'traversable')):
            return None
        if pose is None:
            pose = self._pose_map()
        if pose is None or not hasattr(grid, 'path'):
            return None

        def reachable(xy):
            return grid.path(pose[:2], xy) is not None

        # Check if point has comfortable clearance from walls (~0.28m, margin=0.08)
        safe_grid = self._grid(margin=0.08)
        if safe_grid is not None and hasattr(safe_grid, 'traversable'):
            sc = safe_grid.world_to_cell(x, y)
            if sc is not None and safe_grid.traversable(sc) and reachable((x, y)):
                return (float(x), float(y))
            # If clicked close to a wall, search nearby cells that give safe wall clearance
            t_cell = grid.world_to_cell(x, y)
            if t_cell is not None and hasattr(safe_grid, 'cell_to_world'):
                offsets = sorted(((dx, dy) for dx in range(-8, 9) for dy in range(-8, 9)),
                                 key=lambda p: p[0] * p[0] + p[1] * p[1])
                for dx, dy in offsets:
                    c = (t_cell[0] + dx, t_cell[1] + dy)
                    if safe_grid.traversable(c):
                        xy = safe_grid.cell_to_world(*c)
                        if reachable(xy):
                            return xy

        t_cell = grid.world_to_cell(x, y)
        if t_cell is not None and grid.traversable(t_cell) and reachable((x, y)):
            return (float(x), float(y))

        # Search nearby traversable cells within ~0.4m (8 cells)
        if t_cell is not None and hasattr(grid, 'cell_to_world'):
            offsets = sorted(((dx, dy) for dx in range(-8, 9) for dy in range(-8, 9)),
                             key=lambda p: p[0] * p[0] + p[1] * p[1])
            checked = 0
            for dx, dy in offsets:
                c = (t_cell[0] + dx, t_cell[1] + dy)
                if grid.traversable(c):
                    checked += 1
                    xy = grid.cell_to_world(*c)
                    if reachable(xy):
                        return xy
                    if checked >= 20:
                        break

        # If still not found, check cautious grid (margin=0.03)
        narrow = self._grid(margin=0.03)
        if narrow is not None and hasattr(narrow, 'traversable') and hasattr(narrow, 'path'):
            nc = narrow.world_to_cell(x, y)
            if nc is not None and narrow.traversable(nc) and narrow.path(pose[:2], (x, y)) is not None:
                return (float(x), float(y))
        return None

    def navigate_to_point(self, x, y):
        """Start auto-navigation towards a specific point (x, y) on the SLAM map."""
        if not finite(x) or not finite(y):
            return False, 'INVALID_COORDINATES', ['INVALID_COORDINATES'], {}
        pose = self._pose_map()
        grid = self._grid()
        if grid is None:
            return False, 'MAP_NOT_READY', ['MAP_NOT_READY'], {}
        if pose is None:
            return False, 'TF_NOT_READY', ['TF_NOT_READY'], {}

        safe_target = self._get_safe_point_target(x, y, pose)
        if safe_target is None:
            return False, 'TARGET_UNREACHABLE_OR_BLOCKED', ['TARGET_UNREACHABLE_OR_BLOCKED'], {}

        ok, reason, blockers, snapshot = self.start_auto(mode='NAV_TO_GOAL', target=safe_target)
        return ok, reason, blockers, snapshot

    def find_best_coverage_goal(self, rx, ry, world_yaw=None):
        """Tìm mục tiêu là ô sàn trống chưa được thân xe lăn qua (Physical Coverage).
        Được kích hoạt khi toàn bộ Unknown Frontiers đã khám phá hết (remaining_frontiers == 0).
        """
        self._ai2_shadow_goal = None
        self._ai2_best_action = None
        self._ai2_q_vals = None
        self._ai2_error = None
        grid = self._grid()
        if grid is None:
            return None

        gw = getattr(grid, 'w', 0)
        gh = getattr(grid, 'h', 0)
        gres = getattr(grid, 'res', 0.05)
        if gw <= 0 or gh <= 0 or not hasattr(grid, 'cell_to_world') or not hasattr(grid, 'world_to_cell'):
            return None

        with state.lock:
            v_cells = set(state.visited_cells) if state.visited_cells else set()

        start_cell = grid.world_to_cell(rx, ry)
        qx, qy = rx, ry
        if start_cell is not None and hasattr(grid, 'traversable') and not grid.traversable(start_cell):
            best_start = None
            best_dist = float('inf')
            for ddx in range(-4, 5):
                for ddy in range(-4, 5):
                    cand = (start_cell[0] + ddx, start_cell[1] + ddy)
                    if grid.traversable(cand):
                        d = math.hypot(ddx, ddy)
                        if d < best_dist:
                            best_dist = d
                            best_start = cand
            if best_start is not None:
                qx, qy = grid.cell_to_world(*best_start)
                start_cell = best_start

        now = time.monotonic()
        blocked_pts = [b for b in getattr(self, 'blocked_goals', []) if b[3] > now] + \
                      [b for b in getattr(self, 'blocked_regions', []) if b[3] > now]

        # Quét lưới với stride ~ 0.25m (kích thước thân xe AGV) để tối ưu CPU Pi 4
        stride = max(3, int(round(0.25 / max(0.01, gres))))
        candidates = []
        for gy in range(stride // 2, gh, stride):
            for gx in range(stride // 2, gw, stride):
                if (gx, gy) in v_cells:
                    continue
                if hasattr(grid, 'traversable') and not grid.traversable((gx, gy)):
                    continue
                wx, wy = grid.cell_to_world(gx, gy)
                is_blocked = False
                for b in blocked_pts:
                    if math.hypot(wx - b[0], wy - b[1]) < b[2]:
                        is_blocked = True
                        break
                if is_blocked:
                    continue
                d = math.hypot(wx - rx, wy - ry)
                if d >= 0.35:
                    candidates.append((d, (wx, wy)))

        if not candidates:
            return None

        # Sắp xếp và định hướng theo mô hình AI 2 (Coverage Q-Net)
        if (getattr(self, 'ai2_mode', 'shadow') != 'off' and
                getattr(self, 'ai2_session', None) is not None and candidates and start_cell is not None):
            try:
                import numpy as np
                total_free = sum(1 for v in state.map_data if v == 0) if state.map_data else 1
                # The pose from TF is in the same map frame as the coverage goal.
                # ESP32 odometry yaw may be relative to a different frame.
                yaw = float(getattr(self, '_coverage_tf_yaw', state.robot_th)
                            if world_yaw is None else world_yaw)
                obs = ai2_observation(grid, start_cell, candidates, v_cells,
                                      (qx, qy), yaw,
                                      getattr(self, '_ai2_no_progress_steps', 0), total_free)
                if obs is None:
                    raise ValueError('No reachable AI2 observation target')
                patch, feat = obs
                outputs = self.ai2_session.run(None, {self.ai2_map_name: patch[None, :],
                                                       self.ai2_feat_name: feat[None, :]})
                action, ranked = ai2_ranked_candidates(
                    candidates, np.asarray(outputs[0]).reshape(-1), rx, ry,
                    float(getattr(grid, 'origin', (0., 0., 0.))[2]),
                    valid_actions=ai2_valid_action_mask(grid, start_cell))
                self._ai2_best_action = action
                self._ai2_q_vals = [round(float(q), 3) for q in np.asarray(outputs[0]).reshape(-1)]
                self._ai2_shadow_goal = ranked[0][1]
                self._ai2_error = None
                if getattr(self, 'ai2_mode', 'shadow') == 'control':
                    candidates = ranked
                else:
                    candidates.sort(key=lambda c: c[0])
            except Exception as exc:
                self._ai2_error = type(exc).__name__ + ': ' + str(exc)
                self._ai2_shadow_goal = None
                self._ai2_best_action = None
                self._ai2_q_vals = None
                candidates.sort(key=lambda c: c[0])
        else:
            candidates.sort(key=lambda c: c[0])

        # Kiểm tra đường đi A* tới tối đa 10 ứng viên gần nhất
        if hasattr(grid, 'path'):
            for _, goal_world in candidates[:10]:
                path = grid.path((qx, qy), goal_world)
                if path is not None and len(path) > 1:
                    return goal_world

            # AI2's directional vote can put unreachable points in its top 10.
            # Keep the original reachable, nearest-first goal as a fallback.
            if getattr(self, 'ai2_mode', 'shadow') == 'control':
                for _, goal_world in sorted(candidates, key=lambda c: c[0])[:10]:
                    path = grid.path((qx, qy), goal_world)
                    if path is not None and len(path) > 1:
                        return goal_world

        return None

    def _pose_map(self):
        try:
            with state.lock:
                frame = state.map_frame
            t = self.tf_buffer.lookup_transform(frame,'base_footprint',Time())
            stamp = t.header.stamp.sec+t.header.stamp.nanosec*1e-9
            age = self.get_clock().now().nanoseconds*1e-9-stamp
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            max_tf_age = .80 if is_op else .50
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

    def _cautious_speed_limit(self):
        # RPM mode already validates the final 40-RPM wheel targets. Applying
        # the legacy 0.04 m/s cap first exaggerates curvature during conversion
        # and turns small heading corrections into one-wheel pivots.
        return (rpm_to_speed(SLOW_RPM)
                if getattr(getattr(self, 'control', None), 'operator_rpm_profile', False)
                else .04)

    def _forward_arc_clear(self, v, w):
        def failed(reason):
            self._last_arc_reason=reason
            if getattr(self,'control',None) is not None:
                self.control._event('arc_rejected',reason=reason,v=v,w=w)
            return False
        self._last_arc_reason=None
        cautious_max = self._cautious_speed_limit()
        if getattr(self,'_cautious',False) and finite(v) and v>cautious_max+1e-6:
            return failed('CAUTIOUS_SPEED_LIMIT')
        grid,pose=self._grid(),self._pose_map()
        if grid is None or pose is None:return failed('MAP_OR_TF_UNAVAILABLE')
        if not finite(v) or v <= 0:return failed('INVALID_TWIST')
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        with state.lock:
            epoch=(state.map_version,state.map_frame,state.body_radius_m,state.wall_margin_m,state.scan_mono)
            bounds=state.body_bounds_m
            points=list(state.ranges)
            max_age = max(.65, getattr(self, 'scan_max_age_s', .25)) if is_op else getattr(self, 'scan_max_age_s', .25)
            if not -0.10 <= time.monotonic()-state.scan_mono <= max_age:return failed('SCAN_STALE')
        samples=twist_centres(v,w)
        if samples is None:return failed('INVALID_TWIST')
        clear,reason=grid.swept_clear_result(pose,v,w)
        if not clear:
            if is_op and reason == 'UNKNOWN_SWEEP':
                # Exploration requires driving towards unmapped space; real-time LiDAR below guards collision
                clear = True
            elif is_op and reason == 'OCCUPIED_SWEEP':
                narrow = self._grid(margin=.03)
                if narrow is not None:
                    if bounds is not None and hasattr(narrow, 'box_swept_clear') and narrow.box_swept_clear(pose, v, w, bounds, allow_start_overlap=True):
                        clear = True
                    elif narrow.swept_clear(pose, v, w):
                        clear = True
            if not clear:
                return failed(reason)
        centres,padding=samples
        if is_op and bounds is not None:
            lat_limit = max(abs(bounds[1]), abs(bounds[3])) + 0.015
            f_limit = max(bounds[2] + 0.03, 0.22)
            for i, (bx, by) in enumerate(centres):
                if i == 0 and len(centres) > 1: continue
                angle = w * .5 * i / max(1, len(centres) - 1)
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                for deg, d in enumerate(points):
                    if not finite(d) or d <= 0 or d >= 16.0: continue
                    if is_op and 100 <= deg <= 260 and d <= 0.25: continue
                    a_rad = math.radians(deg)
                    px, py = d * math.cos(a_rad), d * math.sin(a_rad)
                    dx, dy = px - bx, py - by
                    lx = cos_a * dx + sin_a * dy
                    ly = -sin_a * dx + cos_a * dy
                    if (bounds[0] - 0.03 <= lx <= f_limit and abs(ly) <= lat_limit):
                        return failed('SCAN_BODY_CLEARANCE')
        else:
            for deg,d in enumerate(points):
                if not finite(d) or d <= 0:continue
                angle=math.radians(deg)
                px,py=d*math.cos(angle),d*math.sin(angle)
                # Account for the half-degree rounding used by scan_cb.
                radius = grid.radius+padding+d*math.sin(math.radians(.5))
                if any(math.hypot(px-x,py-y) <= radius for x,y in centres):return failed('SCAN_BODY_CLEARANCE')
        with state.lock:
            valid=(epoch==(state.map_version,state.map_frame,state.body_radius_m,state.wall_margin_m,state.scan_mono)
                    and -0.10 <= time.monotonic()-state.scan_mono <= max_age
                    and 0 <= time.monotonic()-state.map_mono <= 5.0)
        return True if valid else failed('INPUT_CHANGED_DURING_SWEEP')

    def _escape_clear(self, v, w):
        grid,pose=self._grid(),self._pose_map()
        if grid is None or pose is None:return False
        max_map_age = 5.0
        with state.lock:
            epoch=(state.map_version,state.map_frame,state.body_radius_m,state.body_bounds_m,state.wall_margin_m,state.scan_mono)
            bounds=state.body_bounds_m
            points=list(state.ranges)
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            max_age = max(.65, getattr(self, 'scan_max_age_s', .25)) if is_op else getattr(self, 'scan_max_age_s', .25)
            if not -0.10 <= time.monotonic()-state.scan_mono <= max_age:return False
        samples=twist_centres(v,w)
        if samples is None:
            return False
        escape_swept = getattr(grid, 'escape_swept_clear', None)
        if callable(escape_swept):
            if not escape_swept(pose, v, w, bounds=bounds,
                                require_progress=not getattr(getattr(self, 'control', None), 'strict_preflight', True)):
                return False
        elif hasattr(grid, 'swept_clear'):
            if not grid.swept_clear(pose, v, w):
                return False
        centres,padding=samples
        obstacles=[(d*math.cos(math.radians(deg)),d*math.sin(math.radians(deg)),d)
                   for deg,d in enumerate(points) if finite(d) and 0<d<16.]
        if not obstacles:return False
        if abs(v) < 1e-9:
            grid_r = getattr(grid, 'body_radius', getattr(grid, 'radius', state.body_radius_m or 0.20))
            body_margin = min(abs(b) for b in bounds) if bounds else grid_r
            for px,py,d in obstacles:
                if is_op and px <= 0.02 and math.hypot(px, py) <= 0.25:
                    continue
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
                    grid_r = getattr(grid, 'body_radius', getattr(grid, 'radius', state.body_radius_m or 0.20))
                    if gap<=grid_r+padding:return False
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

    def _spin_recovery_allows_turn(self, record=False, pose=None):
        """One bounded turn episode, renewed only by real translation, not a latch."""
        control = getattr(self, 'control', None)
        latest = getattr(control, 'latest', None) if control is not None else None
        current = None
        if isinstance(latest, dict):
            try:
                current = (float(latest['x']), float(latest['y']), float(latest['th']))
            except (KeyError, TypeError, ValueError):
                pass
        if current is None or not all(math.isfinite(x) for x in current):
            pose_map = getattr(self, '_pose_map', None)
            if callable(pose_map):
                try:
                    current = pose_map()
                except Exception:
                    pass
        if current is None and pose is not None and all(math.isfinite(x) for x in pose):
            current = pose
        if current is None:
            return True

        now = time.monotonic()
        recovery = getattr(self, '_spin_recovery', None)
        # Bounded turn can only be renewed when real physical translation (>= 0.12m) occurs
        if recovery and math.dist(current[:2], recovery['anchor']) >= 0.12:
            self._spin_recovery = None
            recovery = None

        if recovery is None:
            if record:
                self._spin_recovery = dict(anchor=current[:2], yaw=current[2], angle=0.0, started=now, failed=False)
            return True

        if recovery.get('failed', False):
            return False

        delta = (current[2] - recovery['yaw'] + math.pi) % (2 * math.pi) - math.pi
        recovery['angle'] += abs(delta)
        recovery['yaw'] = current[2]

        allowed = (now - recovery['started'] < 4.0 and recovery['angle'] < math.pi + 0.35)
        if not allowed:
            recovery['failed'] = True
        return allowed

    def _shared_checked_recovery(self, pose, reason='RECOVERY'):
        """One shared checked recovery handler for both blocked-start and frontal danger.

        1. Prefer safe translational exit or real detour;
        2. If unavailable, evaluate left/right swept footprint using actual RPM converted rotation,
           commit to one direction, stop on measured angle/progress/time bound;
        3. Replan validated exit, no reentry until meaningful translation change;
        4. If complete rotation footprint doesn't fit, HOLD correctly without weakening validators.
        """
        if pose is None:
            return False

        grid = self._grid()
        is_op = getattr(self.control, 'operator_rpm_profile', False) or not getattr(self.control, 'strict_preflight', True)
        now = time.monotonic()

        with state.lock:
            ranges = list(state.ranges) if state.ranges else []
            min_ang = getattr(state, 'min_angle_deg', 0)
            min_d = getattr(state, 'min_dist_m', 9.99)

        front_obstacle = (min_d <= 0.38 and abs((min_ang + 180) % 360 - 180) <= 60)
        speed = self._cautious_speed_limit()

        direction = 1.0
        goal = getattr(self, 'goal', None)
        if goal is not None:
            along = ((goal[0] - pose[0]) * math.cos(pose[2]) +
                     (goal[1] - pose[1]) * math.sin(pose[2]))
            direction = 1.0 if along >= 0.0 else -1.0

        # For operator mode facing front obstacle: prefer evaluated clean rotation before translation
        if is_op and front_obstacle and self._rotation_clear() and self._spin_recovery_allows_turn(record=False):
            turn_w = max(0.40, min(1.80, getattr(state, 'turn_w_rads', 1.00)))
            l_pts = [ranges[d % 360] for d in range(25, 90) if ranges and ranges[d % 360] > 0]
            r_pts = [ranges[d % 360] for d in range(-90, -25) if ranges and ranges[d % 360] > 0]
            l_dist = min(l_pts, default=9.99)
            r_dist = min(r_pts, default=9.99)

            primary_w = turn_w if l_dist >= r_dist else -turn_w
            turn_rpm = min(35.0, float(getattr(self.control, 'auto_turn_rpm', 35.0)))
            for w in (primary_w, -primary_w):
                checked = (0.0, w)
                if getattr(self.control, 'operator_rpm_profile', False):
                    checked = wheels_to_twist(*running_wheels(*twist_to_wheels(0.0, w), normal_rpm=turn_rpm))
                if self._escape_clear(*checked):
                    ok, drive_reason = self.control.drive(f'V 0.000 {w:.3f}', autonomous=True, escape=True)
                    if ok:
                        self._spin_recovery_allows_turn(record=True)
                        with state.lock:
                            state.explore_phase = f'QUAY ĐẦU: xoay có kiểm soát ({math.degrees(w):.0f}°/s)'
                        self.control._event('navigation_red_escape', v=0.0, w=checked[1], reason='BOUNDED_CHECKED_TURN')
                        return True

        # Step 1: Prefer safe translational exit or real detour
        if is_op:
            trans_candidates = ((0.090, 0.0), (0.090, -0.60), (0.090, 0.60), (-0.090, 0.0)) if not front_obstacle else ((-0.090, 0.0), (0.090, 0.0))
        elif front_obstacle:
            trans_candidates = ((-0.090, 0.0), (-0.090, -0.60), (-0.090, 0.60), (0.090, 0.0), (0.090, -0.60), (0.090, 0.60))
        else:
            trans_candidates = ((0.090, 0.0), (0.090, -0.60), (0.090, 0.60), (-0.090, 0.0), (-0.090, -0.60), (-0.090, 0.60))

        for v, w in trans_candidates:
            checked = (v, w)
            if getattr(self.control, 'operator_rpm_profile', False):
                checked = wheels_to_twist(*running_wheels(*twist_to_wheels(v, w), slow=True))

            end = (pose[0] + v * 0.5 * math.cos(pose[2]), pose[1] + v * 0.5 * math.sin(pose[2]))
            connect = (v > 0 and grid is not None and
                       hasattr(grid, 'world_to_cell') and
                       not grid.traversable(grid.world_to_cell(*pose[:2])) and
                       grid.traversable(grid.world_to_cell(*end)) and
                       grid.swept_clear(pose, v, 0.) and self._forward_arc_clear(v, 0.))

            escape_ok = False
            if not connect:
                try:
                    escape_ok = self._escape_clear(*checked)
                except Exception:
                    escape_ok = False

            if connect or escape_ok:
                is_connect = (connect and reason == 'BLOCKED_START')
                drive_kw = dict(autonomous=True) if is_connect else dict(autonomous=True, escape=True)
                ok, drive_reason = self.control.drive(f'V {v:.3f} {w:.3f}', **drive_kw)
                if ok:
                    self._front_blocked_count = 0
                    if getattr(self, '_spin_recovery', None) is not None:
                        anchor = self._spin_recovery.get('anchor')
                        if anchor and math.dist(pose[:2], anchor) >= 0.12:
                            self._spin_recovery = None
                    if is_connect:
                        phase = ('PHỤC HỒI VỊ TRÍ: tiến theo lối đã kiểm tra' if v > 0 else
                                 'PHỤC HỒI VỊ TRÍ: lùi theo lối đã kiểm tra')
                    else:
                        phase = ('NÉ VÙNG ĐỎ: tiến ra xa vật cản' if v > 0 else
                                 'NÉ VÙNG ĐỎ: lùi theo hành lang trống')
                    with state.lock:
                        state.explore_phase = phase
                    if is_connect:
                        self.control._event('navigation_clearance_translation', v=v, w=w)
                    else:
                        self.control._event('navigation_red_escape', v=checked[0], w=checked[1], reason='TRANSLATIONAL_EXIT')
                    return True

        # Step 2: Translational exit unavailable; evaluate left/right rotation if full swept footprint permits
        if not self._rotation_clear():
            if not getattr(self, '_cautious', False) and self._enter_cautious(pose):
                if not self._rotation_clear():
                    return False
            else:
                return False

        if not self._spin_recovery_allows_turn(record=False):
            return False

        turn_w = max(0.40, min(1.80, getattr(state, 'turn_w_rads', 1.40)))
        l_pts = [ranges[d % 360] for d in range(25, 90) if ranges and ranges[d % 360] > 0]
        r_pts = [ranges[d % 360] for d in range(-90, -25) if ranges and ranges[d % 360] > 0]
        l_dist = min(l_pts, default=9.99)
        r_dist = min(r_pts, default=9.99)

        primary_w = turn_w if l_dist >= r_dist else -turn_w
        for w in (primary_w, -primary_w):
            checked = (0.0, w)
            if getattr(self.control, 'operator_rpm_profile', False):
                checked = wheels_to_twist(*running_wheels(*twist_to_wheels(0.0, w), slow=True))
            if self._escape_clear(*checked):
                ok, drive_reason = self.control.drive(f'V 0.000 {w:.3f}', autonomous=True, escape=True)
                if ok:
                    self._spin_recovery_allows_turn(record=True)
                    with state.lock:
                        state.explore_phase = f'QUAY ĐẦU: xoay có kiểm soát ({math.degrees(w):.0f}°/s)'
                    self.control._event('navigation_red_escape', v=0.0, w=checked[1], reason='BOUNDED_CHECKED_TURN')
                    return True

        return False

    def _try_operator_clearance_recovery(self, pose):
        """Leave an inflated start with checked translation or bounded turn."""
        return self._shared_checked_recovery(pose, reason='BLOCKED_START')

    def _try_escape(self):
        # Frontal danger escape
        pose = self._pose_map()
        return self._shared_checked_recovery(pose, reason='FRONTAL_DANGER')

    def start_auto(self, mode='EXPLORE', target=None):
        """Expose each failed START gate at the moment of the decision."""
        task_mode = mode.upper() if mode else 'EXPLORE'
        self._auto_task_mode = task_mode
        pose,grid=self._pose_map(),self._grid()
        # SLAM's map->odom TF can appear shortly after /map is published.
        # Wait for localization to initialize without opening the motor gate.
        if pose is None and grid is not None:
            deadline = time.monotonic() + 1.2
            while pose is None and time.monotonic() < deadline:
                time.sleep(.10)
                pose = self._pose_map()
        with state.lock,self.control.lock:
            now=self.control.clock()
            ages=self.control._ages(now)
            map_age=time.monotonic()-state.map_mono
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            max_scan_age = max(.65, getattr(self, 'scan_max_age_s', .25)) if is_op else getattr(self, 'scan_max_age_s', .25)
            checks=(('NOT_ARMED',not self.control.armed),
                    ('LATCHED',self.control.latched),
                    ('FAULT',self.control.fault is not None or (self.control.latest is not None and self.control.latest.get('safety') == 'FAULT')),
                    ('D0_STALE',ages['d0_age_s'] is None or not 0 <= ages['d0_age_s'] <= .25),
                    ('SCAN_STALE',ages['scan_age_s'] is None or not -0.10 <= ages['scan_age_s'] <= max_scan_age),
                    ('CALLER_STALE',self.control.strict_preflight and self.control.armed and (ages['caller_age_s'] is None or not 0 <= ages['caller_age_s'] <= .2)),
                    ('TRIAL_EXPIRED',self.control.trial_deadline is not None and now >= self.control.trial_deadline),
                    ('BODY_RADIUS_UNCONFIGURED',not finite(state.body_radius_m) or state.body_radius_m <= 0),
                    ('MAP_NOT_READY',grid is None),('TF_NOT_READY',pose is None),
                    ('SCAN_MOUNT_TF_NOT_READY',not getattr(self, '_scan_tf_valid', False)))
            blockers=[name for name,blocked in checks if blocked]
            snapshot=dict(**ages,map_age_s=map_age,map_frame=state.map_frame,
                          body_radius_m=state.body_radius_m,pose=pose,
                          tf_error=getattr(self, '_last_pose_error', None),
                          generation=self.control.generation)
            if not blockers:
                # Resume the existing map mission without reloading models,
                # erasing the trace, or moving HOME to the current position.
                self.blocked_goals, self.blocked_regions = [], []
                self.progress = deque()
                self._escape_latch_until = self._turn_latch_until = 0.
                self._spin_recovery = None
                self._last_escape_cmd = None
                self._stall_start = self._spin_start_time = None
                self._is_pure_spinning = False
                self._locked_spin_wp = None
                self._locked_spin_goal = None
                self._spin_timeout_until = 0.0
                self._last_smooth_v = 0.
                if getattr(self, 'home', None) is None:
                    self.home = pose
                if not hasattr(self, '_auto_start_time'):
                    self._auto_start_time = time.monotonic()
                self.control.autonomy_allowed = True
                self.control.generation += 1
                self.control.last_command = now
                if task_mode in ('NAV_TO_GOAL', 'POINT') and target is not None:
                    self.goal = tuple(target)
                    self._goal_type = 'POINT'
                    self._goal_progress = None
                    self._last_announced_goal = None
                    self._goal_time = now
                    self._goal_retries = 0
                    self._goal_blocked_count = 0
                    self.explore_state = 'NAVIGATING_TO_GOAL'
                    state.target_goal_x, state.target_goal_y = self.goal
                    state.explore_phase = f'TỰ HÀNH: Đang chạy tới điểm ({self.goal[0]:.2f}, {self.goal[1]:.2f})'
                elif task_mode == 'COVERAGE':
                    self.goal = None
                    self._goal_type = 'COVERAGE'
                    self._goal_progress = None
                    self._last_announced_goal = None
                    self.explore_state = 'COVERAGE_PATROL'
                    state.explore_phase = 'TỰ HÀNH: bắt đầu phủ kín sàn'
                else:
                    self.goal = None
                    self._goal_type = 'FRONTIER'
                    self._goal_progress = None
                    self._last_announced_goal = None
                    self.explore_state = 'EXPLORING'
                    state.explore_phase = 'TỰ HÀNH: bắt đầu quét mở rộng map'
                state.auto_mode=True
            self.control._event('auto_gate',accepted=not blockers,blockers=blockers,gate=snapshot)
            if not blockers:
                self.send_cmd('V 0.000 0.000', autonomous=True)
            return not blockers,('STARTED' if not blockers else 'EXPLICIT_ARM_FRESH_MAP_TF_AND_BODY_RADIUS_REQUIRED'),blockers,snapshot
    def _hold(self, phase):
        with state.lock: state.explore_phase = phase
        # V0 keeps a valid explicit session without asserting physical STOP.
        self.send_cmd('V 0.000 0.000',autonomous=True)

    def _request_home_completion(self, description):
        """Latch STOP; report completion only after post-STOP MCU telemetry."""
        self._home_completion_phase = description
        with state.lock:
            state.explore_phase = 'HOME: đang chờ MCU xác nhận STOP'
            state.target_goal_x = state.target_goal_y = 0.0
        self.goal = None
        self.explore_state = 'WAIT_STOP'
        self._home_stop_started = time.monotonic()
        self.control.request_stop('HOME_STOP', wait=False)

    def _exclude_goal(self, now, failed=True, reason=None):
        if self.goal is not None:
            self._last_goal_change = dict(goal=list(self.goal), failed=failed,
                                          reason=reason or ('BLOCKED' if failed else 'ARRIVED'))
            if callable(getattr(getattr(self, 'control', None), '_event', None)):
                self.control._event('navigation_goal_released', **self._last_goal_change)
            is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
            radius = max(.35, state.map_resolution * 4)
            duration = (60.0 if failed else 90.0) if is_op else 30.0
            target = self.blocked_regions if failed else self.blocked_goals
            target.append((*self.goal, radius, now + duration))
            self.goal = None
        self._goal_progress = None
        self._last_announced_goal = None
        self._goal_just_excluded = True
        with state.lock:
            state.target_goal_x = 0.0
            state.target_goal_y = 0.0
        self.progress.clear()
        self._is_pure_spinning = False
        self._spin_start_time = None
        self._locked_spin_wp = None
        self._locked_spin_goal = None
        self._spin_timeout_until = 0.0

    @staticmethod
    def _local_path_target(grid, pose, goal, max_lookahead=.25):
        """Pick a stable short lookahead entirely within inflated known-free cells."""
        is_op = (grid is not None and hasattr(grid, 'res') and getattr(grid, 'res', 0) > 0)
        # In operator mode, allow up to 0.20m start relaxation so vehicles parked close to walls/obstacles don't fail with START_BLOCKED
        try:
            path = (grid.path(pose[:2], goal, goal_tolerance=.20, start_tolerance=.20) if isinstance(grid, GridPlanner)
                    else None if grid is None else grid.path(pose[:2], goal))
        except TypeError:
            path = (grid.path(pose[:2], goal, goal_tolerance=.20) if isinstance(grid, GridPlanner)
                    else None if grid is None else grid.path(pose[:2], goal))
        if not path:
            return None
        wp = path[1] if len(path) > 1 else path[0]
        dx, dy = wp[0] - pose[0], wp[1] - pose[1]
        target_yaw = math.atan2(dy, dx)

        if len(path) < 3:
            return PathTarget(wp[0], wp[1], path_yaw=target_yaw, e_lat=0.0)

        to_cell = getattr(grid, 'world_to_cell', None)
        traversable = getattr(grid, 'traversable', None)
        sight = getattr(grid, 'segment_known_free', None)
        if not all(callable(f) for f in (to_cell, traversable, sight)):
            return PathTarget(wp[0], wp[1], path_yaw=target_yaw, e_lat=0.0)

        start = to_cell(pose[0], pose[1])
        if start is None:
            return None
        if not traversable(start):
            return PathTarget(wp[0], wp[1], path_yaw=target_yaw, e_lat=0.0)
        resolution = max(.01, float(getattr(grid, 'res', .05)))
        for candidate in path[2:]:
            distance = math.hypot(candidate[0] - pose[0], candidate[1] - pose[1])
            if distance > max_lookahead:
                break
            end = to_cell(*candidate)
            if end is None or not sight(start, end):
                break
            # segment_known_free checks raw cells; also require the robot's
            # inflated footprint to be traversable at every sampled step.
            samples = max(2, math.ceil(distance / (resolution * .5)))
            if not all(traversable(to_cell(pose[0] + (candidate[0] - pose[0]) * t / samples,
                                           pose[1] + (candidate[1] - pose[1]) * t / samples))
                       for t in range(samples + 1)):
                break
            wp = candidate

        p_start = path[0]
        dx_seg = wp[0] - p_start[0]
        dy_seg = wp[1] - p_start[1]
        seg_len = math.hypot(dx_seg, dy_seg)
        dx = wp[0] - pose[0]
        dy = wp[1] - pose[1]
        target_yaw = math.atan2(dy, dx)

        if seg_len > 0.04:
            seg_yaw = math.atan2(dy_seg, dx_seg)
            tx = dx_seg / seg_len
            ty = dy_seg / seg_len
            e_lat = -(pose[0] - p_start[0]) * ty + (pose[1] - p_start[1]) * tx
            return PathTarget(wp[0], wp[1], path_yaw=seg_yaw, e_lat=e_lat)

        return PathTarget(wp[0], wp[1], path_yaw=target_yaw, e_lat=0.0)

    def _follow(self, pose, goal, planned=None):
        self._last_arc_reason=None
        self._follow_transient=False
        self._follow_phase = 'TỰ HÀNH: bám đường A*'
        grid = self._grid()
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)

        wp = None
        if (is_op and getattr(self, '_is_pure_spinning', False) and
                getattr(self, '_locked_spin_wp', None) is not None and
                getattr(self, '_locked_spin_goal', None) == goal):
            locked_wp = self._locked_spin_wp
            dist_to_locked = math.hypot(locked_wp[0] - pose[0], locked_wp[1] - pose[1])
            locked_valid = dist_to_locked > 0.12
            if (locked_valid and grid is not None and
                    hasattr(grid, 'world_to_cell') and hasattr(grid, 'traversable')):
                cell = grid.world_to_cell(*locked_wp)
                if cell is None or not grid.traversable(cell):
                    locked_valid = False
            if locked_valid:
                wp = locked_wp
            else:
                self._locked_spin_wp = None
                self._locked_spin_goal = None

        if wp is None:
            grid_match = planned is not None and (planned[0] is None or planned[0] is grid or type(planned[0]) is type(grid))
            wp = (planned[1] if grid_match else self._local_path_target(grid, pose, goal))
        if wp is None:
            if is_op:
                self._is_pure_spinning = False
                self._spin_start_time = None
                self._locked_spin_wp = None
                self._locked_spin_goal = None
            if callable(getattr(getattr(self,'control',None),'_event',None)):
                self.control._event('navigation_blocked',reason='NO_SAFE_PATH',pose=pose,goal=goal)
            return False

        dx, dy = wp[0] - pose[0], wp[1] - pose[1]
        direct_error = (math.atan2(dy, dx) - pose[2] + math.pi) % (2 * math.pi) - math.pi
        path_yaw = getattr(wp, 'path_yaw', None)
        e_lat = getattr(wp, 'e_lat', 0.0)

        # Xoay tại chỗ ngắm THẲNG TẮP vào tâm đích khi nhắm Frontier (không cộng thêm góc lệch sườn theta_corr)
        if getattr(self, '_is_pure_spinning', False) and getattr(self, '_goal_type', None) == 'FRONTIER':
            error = direct_error
        elif path_yaw is not None:
            e_heading = (path_yaw - pose[2] + math.pi) % (2 * math.pi) - math.pi
            # Bounded approach angle proportional to signed cross-track error:
            lookahead_dist = max(0.20, min(0.30, math.hypot(dx, dy)))
            theta_corr = math.atan2(-e_lat, lookahead_dist)
            theta_corr = max(-0.35, min(0.35, theta_corr))
            error = (e_heading + theta_corr + math.pi) % (2 * math.pi) - math.pi
        else:
            error = direct_error
        w_max = max(0.40, min(1.80, getattr(state, 'turn_w_rads', 1.40)))

        cur_w = 0.0
        control = getattr(self, 'control', None)
        if control is not None and getattr(control, 'armed', False) is True:
            latest = getattr(control, 'latest', None)
            last_d0 = getattr(control, 'last_d0', None)
            clock_fn = getattr(control, 'clock', time.monotonic)
            if isinstance(latest, dict) and isinstance(last_d0, (int, float)):
                try:
                    now_clk = clock_fn()
                    if isinstance(now_clk, (int, float)):
                        d0_age = now_clk - last_d0
                        if 0.0 <= d0_age <= 0.25:
                            raw_w = latest.get('w', 0.0)
                            if isinstance(raw_w, (int, float)) and math.isfinite(raw_w):
                                cur_w = float(raw_w)
                except (TypeError, ValueError):
                    cur_w = 0.0

        if is_op:
            now_spin = time.monotonic()
            spinning = getattr(self, '_is_pure_spinning', False)
            is_home = getattr(self, '_goal_type', None) == 'HOME'
            spin_thresh = 1.45
            spin_sub_thresh = 0.80
            if (abs(error) > spin_thresh or (abs(error) > spin_sub_thresh and now_spin >= getattr(self, '_spin_timeout_until', 0.0))):
                spinning = True
            elif abs(error) <= 0.22:
                spinning = False

            if spinning:
                spin_start = getattr(self, '_spin_start_time', None)
                if spin_start is None:
                    self._spin_start_time = now_spin
                    spin_start = now_spin
                elif is_home:
                    # Xoay đủ hướng về Home (abs(error) <= 0.22 rad ~ 12 độ), không bị ngắt giữa chừng
                    if now_spin - spin_start > 6.0:
                        spinning = False
                        self._spin_start_time = None
                        self._locked_spin_wp = None
                        self._locked_spin_goal = None
                        self._spin_timeout_until = now_spin + 1.0
                elif (now_spin - spin_start > 1.8 and abs(error) <= 1.20) or now_spin - spin_start > 3.0:
                    spinning = False
                    self._spin_start_time = None
                    self._locked_spin_wp = None
                    self._locked_spin_goal = None
                    self._spin_timeout_until = now_spin + 1.5
            else:
                self._spin_start_time = None

            self._is_pure_spinning = spinning

            if spinning:
                if not self._spin_recovery_allows_turn(record=True):
                    self._is_pure_spinning = False
                    self._spin_start_time = None
                    self._locked_spin_wp = None
                    self._locked_spin_goal = None
                    self._spin_timeout_until = now_spin + 5.0
                    return False
                dist_to_wp = math.hypot(wp[0] - pose[0], wp[1] - pose[1])
                if dist_to_wp > 0.12:
                    self._locked_spin_wp = wp
                    self._locked_spin_goal = goal
                else:
                    self._locked_spin_wp = None
                    self._locked_spin_goal = None
                v = 0.000
                try:
                    turn_rpm_target = float(getattr(self.control, 'auto_turn_rpm', getattr(state, 'auto_target_turn_rpm', 35.0)))
                except (TypeError, ValueError):
                    turn_rpm_target = 35.0

                if turn_rpm_target < NORMAL_RPM:
                    # Chế độ quay êm có điều khiển (chống tụ lực xoắn sàn rích)
                    turn_rpm_base = min(28.0, max(15.0, turn_rpm_target))
                    spin_elapsed = max(0.0, now_spin - (spin_start if spin_start is not None else now_spin))
                    self._spin_ticks = getattr(self, '_spin_ticks', 0) + 1
                    progress = max(min(1.0, spin_elapsed / 0.25), min(1.0, self._spin_ticks / 3.0))
                    soft_start_factor = min(1.0, max(0.40, 0.40 + 0.60 * progress)) if is_op else 1.0

                    # Deceleration ramp: khi góc lệch còn dưới 25 độ (~0.45 rad), giảm tốc từ từ
                    if abs(error) < 0.45:
                        dec_factor = max(0.50, abs(error) / 0.45)
                    else:
                        dec_factor = 1.0

                    effective_turn_rpm = max(10.0, round(turn_rpm_base * soft_start_factor * dec_factor, 1))
                    if is_op and hasattr(self, 'control'):
                        self.control.auto_turn_rpm = effective_turn_rpm
                    w_turn_cal = effective_turn_rpm * (2 * math.pi * 0.0366 / 60) / 0.096
                    w = math.copysign(w_turn_cal, error)

                    # VỪA ĐI VỪA RẼ: nếu phía trước thoáng, cho xe bò nhẹ v = 0.050 m/s để cả 2 bánh cùng lăn tới
                    # Triệt tiêu hoàn toàn hiện tượng 1 bánh đứng yên làm điểm tựa gây tụ lực xoắn trên sàn rích!
                    with state.lock:
                        ranges = list(state.ranges) if state.ranges else []
                    if ranges:
                        f_cone = [ranges[d % 360] for d in range(-30, 31) if ranges[d % 360] > 0]
                        if f_cone and min(f_cone) > (state.body_radius_m or 0.20) + 0.12:
                            v = 0.050
                            w_bound_turn = (v / 0.096) * 0.60
                            w = math.copysign(min(abs(w), w_bound_turn), error)
                else:
                    w = math.copysign(w_max, error)
                setattr(self, '_last_smooth_w', 0.0)
                setattr(self, '_steer_trim', 0.0)
            else:
                self._spin_ticks = 0
                if is_op and hasattr(self, 'control'):
                    self.control.auto_speed_rpm = float(getattr(state, 'auto_target_speed_rpm', 40.0))
                    self.control.auto_turn_rpm = float(getattr(state, 'auto_target_turn_rpm', 35.0))
                self._locked_spin_wp = None
                self._locked_spin_goal = None
                dist_to_goal = math.hypot(goal[0] - pose[0], goal[1] - pose[1])
                if dist_to_goal < 0.35:
                    v = min(state.cruise_speed_mps, max(0.04, dist_to_goal * 0.5))
                elif abs(error) > 0.60:
                    # Góc lệch lớn: giảm tốc xuống ~0.09 m/s để lượn vòng cung bán kính hẹp mà không cần dừng đứng yên
                    v = min(0.09, state.cruise_speed_mps)
                elif abs(error) > 0.35:
                    v = min(rpm_to_speed(SLOW_RPM), state.cruise_speed_mps)
                else:
                    v = state.cruise_speed_mps
                if abs(error) <= STEER_DEADBAND_RAD:
                    w = 0.000
                else:
                    excess = math.copysign(max(0.0, abs(error) - STEER_DEADBAND_RAD), error)
                    w_prop = excess * 0.95
                    # Mở rộng trần lái w_bound lên tới 0.65 rad/s (~37°/s) để bám cua gắt mà không bị trôi dạt
                    # Hệ số 0.60 đảm bảo bánh trong luôn quay tới (v_inner >= 0.40 * v > 0), không hãm đứng bánh
                    w_bound = min(0.65, max(0.04, (v / 0.096) * 0.60))
                    w = max(-w_bound, min(w_bound, w_prop - 0.05 * cur_w))
                setattr(self, '_last_smooth_w', w)
        else:
            dx, dy = wp[0] - pose[0], wp[1] - pose[1]
            error = (math.atan2(dy, dx) - pose[2] + math.pi) % (2 * math.pi) - math.pi
            if abs(error) > 1.20:
                v = 0.
            elif abs(error) > .25:
                v_crawl = .03 if not getattr(self, '_cautious', False) else .02
                v = min(v_crawl, state.cruise_speed_mps,
                        math.hypot(dx, dy) / .5, math.hypot(goal[0] - pose[0], goal[1] - pose[1]) / .5)
            else:
                v = min(state.cruise_speed_mps,
                        math.hypot(dx, dy) / .5, math.hypot(goal[0] - pose[0], goal[1] - pose[1]) / .5)
            if getattr(self, '_cautious', False):
                v = min(v, .04)
            if v == 0 and abs(error) > .04:
                w_min = min(0.60, w_max)
                w = math.copysign(max(w_min, min(w_max, abs(error))), error)
            else:
                w = max(-w_max, min(w_max, error))
        if getattr(self, '_cautious', False):
            v = min(v, self._cautious_speed_limit())
        if v == 0 and abs(w) > 0:
            if is_op:
                ok, reason = self.send_cmd(f'V 0.000 {w:.3f}', autonomous=True, planned_turn=True)
                if ok:
                    with state.lock:
                        partial = (' | QUÉT MAP MỘT PHẦN' if
                                   getattr(self, '_goal_type', None) == 'HOME' and
                                   getattr(self, '_explore_partial', False) else '')
                        state.explore_phase = f'QUAY ĐẦU HƯỚNG MỤC TIÊU ({math.degrees(error):.0f}°){partial}'
                        self._follow_phase = state.explore_phase
                    return True
            elif not self._rotation_clear():
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
        if ok:
            self._front_blocked_count = 0
            if getattr(self, '_spin_recovery', None) is not None:
                anchor = self._spin_recovery.get('anchor')
                if anchor and math.dist(pose[:2], anchor) >= 0.12:
                    self._spin_recovery = None
            if is_op and getattr(self, '_is_pure_spinning', False):
                with state.lock:
                    partial = (' | QUÉT MAP MỘT PHẦN' if
                               getattr(self, '_goal_type', None) == 'HOME' and
                               getattr(self, '_explore_partial', False) else '')
                    state.explore_phase = f'QUAY ĐẦU HƯỚNG MỤC TIÊU ({math.degrees(error):.0f}°){partial}'
                    self._follow_phase = state.explore_phase
            return True
        if (getattr(self, '_last_arc_reason', None) in ('SCAN_BODY_CLEARANCE', 'OCCUPIED_SWEEP')
                and self._enter_cautious(pose)):
            self._follow_transient = True
            return False
        if reason in ('WRITER_BUSY','TRANSPORT_BUSY','SCAN_STALE','D0_STALE','CALLER_STALE') or \
           getattr(self,'_last_arc_reason',None) in ('INPUT_CHANGED_DURING_SWEEP','SWEEP_BUDGET','SCAN_STALE','MAP_OR_TF_UNAVAILABLE'):
            self._follow_transient=True
            return False
        # Align inside current cleared footprint ONLY if error is genuinely large (> 0.60 rad ~ 35 deg), never for minor deviations.
        spin_align_thresh = 0.60 if is_op else .04
        if v > 0 and abs(error) > spin_align_thresh and getattr(self, '_front_blocked_count', 0) <= 2:
            if self._rotation_clear():
                if not self._spin_recovery_allows_turn(record=True):
                    return False
                turn_rpm = min(28.0, float(getattr(state, 'auto_target_turn_rpm', 28.0)))
                w_turn_cal = turn_rpm * (2 * math.pi * 0.0366 / 60) / 0.096
                if abs(direct_error) < 0.60:
                    w_spin = max(0.40, min(w_turn_cal, abs(direct_error) * 1.50))
                else:
                    w_spin = w_turn_cal
                w_spin = min(w_spin, w_max) if is_op else w_max
                if is_op:
                    now_fallback = time.monotonic()
                    self._is_pure_spinning = True
                    self._spin_start_time = getattr(self, '_spin_start_time', None) or now_fallback
                    self._locked_spin_wp = wp
                    self._locked_spin_goal = goal
                    return self.send_cmd(f'V 0.000 {math.copysign(w_spin, direct_error):.3f}',
                                         autonomous=True, planned_turn=True)[0]
                return self.send_cmd(f'V 0.000 {math.copysign(w_spin, error):.3f}', autonomous=True)[0]
            elif is_op:
                # Mũi xe quá sát vật cản chưa đủ bán kính xoay: nếu sau lưng thông thoáng, lùi nhẹ để giải phóng góc quay
                if self._shared_checked_recovery(pose, reason='ROTATION_RETREAT'):
                    return True
        # Persistent actual front obstruction: invoke shared checked recovery to find open corridors
        front_blocked = getattr(self, '_last_arc_reason', None) in ('SCAN_BODY_CLEARANCE', 'OCCUPIED_SWEEP')
        if front_blocked:
            self._front_blocked_count = getattr(self, '_front_blocked_count', 0) + 1
            if is_op:
                if not getattr(self, '_cautious', False) and self._enter_cautious(pose):
                    self._follow_transient = True
                    return False
                if self._shared_checked_recovery(pose, reason='FRONT_BLOCKED'):
                    return True
                if getattr(self, '_front_blocked_count', 0) >= 3 and getattr(self, 'goal', None) is not None and getattr(self, '_goal_type', None) != 'HOME':
                    now_drop = time.monotonic()
                    self._exclude_goal(now_drop, failed=True, reason='FRONT_BLOCKED_PERSISTENT')
                    self._goal_blocked_count = 0
                    self._front_blocked_count = 0
                    self._last_frontier_search = now_drop - 1.5
                    self._hold('ĐỔI MỤC TIÊU: Lối đi bị chặn; quét LiDAR 360° tìm hướng khác')
                    return False
                self._hold('HOLD: phía trước có vật cản, đang chờ đường')
                return False
            if self._shared_checked_recovery(pose, reason='FRONT_BLOCKED'):
                return True
        return False

    def _rotation_clear(self):
        with state.lock:
            radius = state.body_radius_m
            bounds = state.body_bounds_m
            points = list(state.ranges)
            age = time.monotonic()-state.scan_mono
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        max_age = max(.65, getattr(self, 'scan_max_age_s', .25)) if is_op else getattr(self, 'scan_max_age_s', .25)
        returns=[p for p in points if finite(p) and 0<p<16.]
        if is_op:
            check_returns = [p for deg, p in enumerate(points)
                             if finite(p) and 0 < p < 16. and
                             not (100 <= deg <= 260 and p <= 0.25)]
        else:
            check_returns = returns
        if is_op and bounds is not None:
            max_corner = max(math.hypot(x, y) for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3]))
            min_clear = max_corner + 0.01
        elif is_op:
            min_clear = (radius or 0.20) + 0.02
        elif getattr(self, '_cautious', False):
            min_clear = radius or 0.20
        else:
            min_clear = (radius or 0.20) + state.wall_margin_m
        effective_returns = check_returns if is_op and check_returns else returns
        if not (radius is not None and 0<=age<=max_age and len(returns)>=30 and
                min(effective_returns)>min_clear):return False
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
                state.explore_phase = (getattr(self, '_home_completion_phase', 'HOME: đã về đích')
                                       if health['stop_confirmed'] else 'HOME: chờ MCU xác nhận dừng')
                if health['stop_confirmed']:
                    state.auto_mode = False
                    self.explore_state = 'COMPLETED'
                elif time.monotonic() - getattr(self, '_home_stop_started', time.monotonic()) > 1.0:
                    state.auto_mode = False
                    state.explore_phase = 'HOME_STOP_UNCONFIRMED: MCU chưa xác nhận dừng'
                    self.explore_state = 'HOME_FAILED'
            return
        with state.lock:
            auto = state.auto_mode
            scan_age = time.monotonic()-state.scan_mono
        self._ai1_active = False
        self._ai1_shadow_cmd = None
        self._ai1_v = None
        self._ai1_w = None
        if not auto:
            return
        is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
        pose = self._pose_map()
        if pose is None:
            self._hold(f'HOLD: chờ TF ({getattr(self, "_last_pose_error", "None")})')
            return
        self._coverage_tf_yaw = pose[2]
        grid = self._grid()
        if grid is None:
            self._hold(f'HOLD: chờ bản đồ (map_age={time.monotonic()-state.map_mono:.2f}s, recvd={state.map_received})')
            return
        max_scan_age = max(.65, getattr(self, 'scan_max_age_s', .25)) if is_op else getattr(self, 'scan_max_age_s', .25)
        if not -0.10 <= scan_age <= max_scan_age:
            self._hold(f'HOLD: chờ scan (scan_age={scan_age:.2f}s, max={max_scan_age:.2f}s)')
            return
        if self.home is None:
            self.home = pose
            self.explore_state = 'EXPLORING'
        with state.lock:
            last = state.last_path_pose
            if last is None:
                state.last_path_pose = (pose[0], pose[1])
                state.path_history.append([round(pose[0], 3), round(pose[1], 3)])
            else:
                d_step = math.hypot(pose[0] - last[0], pose[1] - last[1])
                if d_step >= 0.05:
                    state.last_path_pose = (pose[0], pose[1])
                    state.total_distance_m += d_step
                    state.path_history.append([round(pose[0], 3), round(pose[1], 3)])
            if state.map_resolution > 0:
                # The SLAM grid origin may be rotated. Use the same world->cell
                # transform as path planning, and never count cells off-map.
                origin_cell = grid.world_to_cell(pose[0], pose[1])
                r_c = int(math.ceil((state.body_radius_m or 0.20) / state.map_resolution))
                if origin_cell is not None:
                    gx, gy = origin_cell
                    for dx in range(-r_c, r_c + 1):
                        for dy in range(-r_c, r_c + 1):
                            cx, cy = gx + dx, gy + dy
                            if (dx * dx + dy * dy <= r_c * r_c and
                                    0 <= cx < state.map_width and 0 <= cy < state.map_height and
                                    state.map_data[cy * state.map_width + cx] == 0):
                                state.visited_cells.add((cx, cy))
            visited_count = len(state.visited_cells)
        previous_count = getattr(self, '_ai2_last_visited_count', None)
        self._ai2_no_progress_steps = (min(100, getattr(self, '_ai2_no_progress_steps', 0) + 1)
                                       if previous_count == visited_count else 0)
        self._ai2_last_visited_count = visited_count
        self._restore_normal_clearance(pose)
        grid=self._grid()
        if grid is None:
            self._hold('HOLD: chờ bản đồ mới')
            return
        now = time.monotonic()
        if is_op:
            # Retired reactive state has no command authority in operator AUTO.
            self._escape_latch_until = self._turn_latch_until = 0.
            self._last_escape_cmd = None
            if getattr(self, '_spin_recovery', None) is not None:
                anchor = self._spin_recovery.get('anchor')
                started = self._spin_recovery.get('started', now)
                angle = self._spin_recovery.get('angle', 0.0)
                if (anchor and math.dist(pose[:2], anchor) >= 0.12) or now - started >= 2.5 or angle >= math.pi:
                    self._spin_recovery = None
        if not is_op and getattr(self, '_escape_latch_until', 0) > now and getattr(self, '_last_escape_cmd', None):
            with state.lock:
                f_pts = [state.ranges[d % 360] for d in range(-25, 26) if 0 < state.ranges[d % 360] < 16.0] if state.ranges else []
                f_dist_check = min(f_pts) if f_pts else 9.99
            # Dừng xoay thoát hiểm ngay khi trước mũi xe đạt khoảng trống >= 50cm
            if f_dist_check >= 0.50:
                self._escape_latch_until = 0
            else:
                v, w = self._last_escape_cmd
                accepted, reason = self.control.drive(f'V {v:.3f} {w:.3f}', autonomous=True, escape=True)
                if not accepted:
                    # Changed geometry invalidates the latched escape. Do not
                    # replay it until the caller watchdog faults the mission.
                    self._escape_latch_until = 0.
                    self._last_escape_cmd = None
                    self._escape_index = (getattr(self, '_escape_index', 0) + 1) % 8
                    self._hold('TỰ THOÁT: hướng cũ đã bị chặn, tìm hướng khác')
                return
        if getattr(self, 'control', None) is not None and getattr(self.control, 'armed', False):
            if not is_op and self.control.clock() - (self.control.last_command or 0) > 0.15:
                self.send_cmd('V 0.000 0.000', autonomous=True)
        self.progress.append((now,pose))
        while self.progress and now-self.progress[0][0] > 2.:
            self.progress.popleft()

        target_rpm = getattr(state, 'auto_target_speed_rpm', 0)
        with state.lock:
            ranges = list(state.ranges)
            f_pts = [ranges[d % 360] for d in range(-25, 26) if ranges[d % 360] > 0]
            f_dist = min(f_pts) if f_pts else 9.99
            body_r = state.body_radius_m or 0.20
            min_ang = getattr(state, 'min_angle_deg', 0)
            ang_err = abs((min_ang + 180) % 360 - 180)
            if is_op:
                is_front_min = ang_err <= 30
                side_breach = state.min_dist_m is not None and state.min_dist_m <= 0.13
                body_breach = (state.min_dist_m is not None and state.min_dist_m <= body_r and is_front_min) or side_breach
                front_danger = (f_dist < 0.25)
            else:
                is_front_min = ang_err <= 90
                body_breach = (state.min_dist_m is not None and state.min_dist_m <= body_r + 0.02 and (is_front_min or not is_op))
                front_danger = (f_dist < 0.28)
            danger_close = body_breach or front_danger

        # Phát hiện kẹt bánh động cơ thực tế qua telemetry ESP32 (Chống kẹt ma sát trên sàn gạch)
        wheel_stalled = False
        control = getattr(self, 'control', None)
        latest_d0 = getattr(control, 'latest', None) if control is not None else None
        if latest_d0:
            l_rpm = abs(latest_d0.get('l_rpm', 0.0))
            r_rpm = abs(latest_d0.get('r_rpm', 0.0))
            l_tgt = abs(latest_d0.get('l_tgt', 0.0))
            r_tgt = abs(latest_d0.get('r_tgt', 0.0))
            is_stalling = (
                (l_tgt >= 10.0 and l_rpm < 2.0) or
                (r_tgt >= 10.0 and r_rpm < 2.0)
            )
            # A zero target intentionally holds the inner wheel during a
            # pivot. Its zero measured RPM must not restart escape every 1.4s.
            if is_stalling:
                if getattr(self, '_stall_start', None) is None:
                    self._stall_start = now
                elif now - self._stall_start > 1.4:
                    wheel_stalled = True
            else:
                self._stall_start = None
        else:
            self._stall_start = None

        self._motion_warning = 'WHEEL_RPM_BELOW_TARGET' if wheel_stalled else None

        if wheel_stalled:
            if is_op and not danger_close:
                # Operator mode: wheel slip on tile floor is common.
                # Only warn; keep following the A* path. Escape is reserved
                # for danger_close situations handled above.
                self._stall_start = None
            else:
                self._escape_index = (getattr(self, '_escape_index', 0) + 1) % 8
                self._stall_start = None
                if self.goal is not None and not is_op:
                    self._exclude_goal(now, reason='WHEEL_STALL')
                if not self._try_escape():
                    self._hold('Né kẹt: phát hiện kẹt bánh động cơ, chuyển hướng')
                return

        if danger_close:
            if not self._try_escape():
                self._escape_index = (getattr(self, '_escape_index', 0) + 1) % 8
                if self.goal is not None:
                    self._exclude_goal(now)
                self._hold('HOLD: vật cản quá gần, chưa có đường thoát an toàn')
            return

        if is_op:
            # Operator AUTO: mission selection followed by one A* path controller.
            # Recover from the actual starting pose before selecting frontiers.
            # Snapping a blocked start to a distant free cell cannot move the
            # physical robot and must not leave it holding without an escape.
            with state.lock:
                cruise_speed = state.cruise_speed_mps
                target_rpm = getattr(state, 'auto_target_speed_rpm', 0)
                remaining_frontiers = state.frontier_reachable

            # Quản lý mục tiêu tự hành (Frontier vs Coverage -> Return to Home)
            task_mode = getattr(self, '_auto_task_mode', 'EXPLORE')
            goal_type = getattr(self, '_goal_type', 'FRONTIER')
            if self.goal is not None:
                dist_to_goal = math.hypot(pose[0] - self.goal[0], pose[1] - self.goal[1])
                goal_age = now - getattr(self, '_goal_time', 0)
                progress = getattr(self, '_goal_progress', None)
                if (progress is None or progress[0] != self.goal or
                        math.dist(progress[1], pose[:2]) >= .05):
                    self._goal_progress = (self.goal, pose[:2], now)
                goal_idle_age = now - self._goal_progress[2]

                # Nếu đang trong chế độ chỉ định điểm đích (Point navigation)
                if goal_type == 'POINT':
                    if dist_to_goal <= 0.15:
                        with state.lock:
                            state.explore_phase = f'ĐÃ ĐẾN ĐÍCH: ({self.goal[0]:.2f}, {self.goal[1]:.2f}) & Dừng an toàn'
                            state.auto_mode = False
                            state.target_goal_x = state.target_goal_y = 0.0
                        self.goal = None
                        self.explore_state = 'COMPLETED'
                        self.control.request_stop('GOAL_REACHED', wait=False)
                        self.send_cmd('V 0.000 0.000', autonomous=True)
                        return
                    if goal_idle_age > 60.0:
                        with state.lock:
                            state.explore_phase = f'KHÔNG THỂ ĐẾN ĐÍCH: Kẹt mục tiêu ({self.goal[0]:.2f}, {self.goal[1]:.2f})'
                            state.auto_mode = False
                        self.goal = None
                        self.explore_state = 'GOAL_FAILED'
                        self.control.request_stop('GOAL_STALLED', wait=False)
                        return

                # Nếu đang trong chế độ Return to Home và đã về tới đích an toàn:
                elif goal_type == 'HOME':
                    dist_to_home = math.hypot(pose[0] - self.home[0], pose[1] - self.home[1]) if self.home else dist_to_goal
                    if dist_to_goal <= 0.12:
                        with state.lock:
                            free_cells_count = sum(1 for v in state.map_data if v == 0) if state.map_data else 1
                            cov_pct = round(len(state.visited_cells) / max(1, free_cells_count) * 100.0, 1)
                            if task_mode == 'COVERAGE':
                                completion = f'HOÀN THÀNH: Đã phủ kín sàn ({cov_pct}%) & MCU xác nhận dừng tại Home'
                            elif getattr(self, '_explore_partial', False):
                                completion = 'QUÉT MAP MỘT PHẦN: Hết frontier tiếp cận được; MCU xác nhận dừng tại Home'
                            else:
                                completion = 'HOÀN THÀNH: Đã quét xong bản đồ & MCU xác nhận dừng tại Home'
                        self._request_home_completion(completion)
                        return
                    if goal_idle_age > 35.0:
                        # Timeout is a navigation failure, never proof that
                        # the robot reached HOME. Latch STOP and report it.
                        with state.lock:
                            state.explore_phase = 'HOME_TIMEOUT: không xác nhận được vị trí Home'
                            state.auto_mode = False
                        self.explore_state = 'HOME_FAILED'
                        self.control.request_stop('HOME_TIMEOUT', wait=False)
                        return

                    # Never leave a HOME mission via generic goal completion,
                    # timeout blacklist, or reactive free-space cruising.
                    # Path existence and geometry are checked by _follow below.

                # Use the same arrival radius as the A* endpoint tolerance.
                # Proximity to an obstacle is not evidence of goal arrival.
                goal_satisfied = goal_type not in ('HOME', 'POINT') and dist_to_goal <= .12
                if goal_satisfied:
                    self._exclude_goal(now, failed=False, reason='ARRIVED_WITHIN_0.12M')
                    self.goal = None
                    self._goal_blocked_count = 0
                    self.send_cmd('V 0.000 0.000', autonomous=True)
                elif goal_type not in ('HOME', 'POINT') and goal_idle_age > 60.0:
                    self._exclude_goal(now, failed=True, reason='NO_TRANSLATION_FOR_60S')
                    self.goal = None
                    self._goal_blocked_count = 0

            # Giãn chu kỳ tìm kiếm mục tiêu ít nhất 1.5s để tránh nghẽn CPU Pi và UART STM32
            if self.goal is None:
                if task_mode in ('NAV_TO_GOAL', 'POINT'):
                    return
                if now - getattr(self, '_last_frontier_search', 0) >= 1.5:
                    self._last_frontier_search = now
                    # Kiểm tra xem bản đồ đã quét hết Unknown chưa
                    with state.lock:
                        u_cells = state.unknown_cells
                    is_map_complete = (remaining_frontiers == 0 and (u_cells == 0 or (u_cells is not None and u_cells < 20)))
                    auto_run_duration = now - getattr(self, '_auto_start_time', now)
                    can_finish = (remaining_frontiers == 0 and
                                  (is_map_complete or auto_run_duration > 15.0))

                    task_mode = getattr(self, '_auto_task_mode', None)

                    if task_mode == 'EXPLORE':
                        # CHẾ ĐỘ: QUÉT MỞ RỘNG BẢN ĐỒ (FRONTIER ONLY) -> VỀ HOME
                        new_goal = self.find_best_frontier(*pose[:2])
                        # A fresh frontier scan can invalidate cached counts.
                        # Timeout (None) must never be interpreted as completion.
                        with state.lock:
                            fresh_frontiers = state.frontier_reachable
                            fresh_unknown = state.unknown_cells
                        is_map_complete = (fresh_frontiers == 0 and fresh_unknown is not None
                                           and fresh_unknown < 20)
                        can_finish = (fresh_frontiers == 0 and
                                      (is_map_complete or auto_run_duration > 15.0))
                        with state.lock:
                            exhausted = (new_goal is None and fresh_frontiers is not None and
                                         state.frontier_count == 0 and
                                         bool(self.blocked_goals or self.blocked_regions))
                        can_finish = can_finish or exhausted
                        if new_goal is not None:
                            self.goal = new_goal
                            self._goal_type = 'FRONTIER'
                            self._goal_time = now
                            self._goal_retries = 0
                            self._goal_blocked_count = 0
                            self.explore_state = 'EXPLORING'
                        elif can_finish:
                            # No reachable frontier: return HOME, but never
                            # claim complete mapping with unknown cells left.
                            self._explore_partial = not is_map_complete
                            safe_home = self._get_safe_home_target(pose)
                            if safe_home is not None:
                                dist_to_home = math.hypot(pose[0] - safe_home[0], pose[1] - safe_home[1])
                                if dist_to_home > 0.12:
                                    self.goal = safe_home
                                    self._goal_type = 'HOME'
                                    self._goal_time = now
                                    self._goal_retries = 0
                                    self._goal_blocked_count = 0
                                    self.explore_state = 'RETURNING_HOME'
                                    with state.lock:
                                        phase = ('QUÉT MAP MỘT PHẦN: còn vùng Unknown, đang về Home'
                                                 if self._explore_partial else 'HOÀN THÀNH QUÉT MAP: Đang về Home')
                                        state.explore_phase = f'{phase} ({dist_to_home:.1f}m)...'
                                else:
                                    result = ('QUÉT MAP MỘT PHẦN: Hết frontier tiếp cận được; MCU xác nhận dừng tại Home'
                                              if self._explore_partial else
                                              'HOÀN THÀNH: Đã quét map & MCU xác nhận dừng tại Home')
                                    self._request_home_completion(result)
                                    return
                            else:
                                self._hold('HOLD: chưa tìm được đường an toàn về Home')
                                return
                        else:
                            self.explore_state = 'EXPLORING'

                    elif task_mode == 'COVERAGE':
                        # CHẾ ĐỘ: PHỦ KÍN MẶT SÀN (COVERAGE PATH)
                        cov_goal = self.find_best_coverage_goal(*pose[:2])
                        if cov_goal is not None:
                            self.goal = cov_goal
                            self._goal_type = 'COVERAGE'
                            self._goal_time = now
                            self._goal_retries = 0
                            self._goal_blocked_count = 0
                            self.explore_state = 'COVERAGE_PATROL'
                        else:
                            # Đã phủ kín xong mọi ngóc ngách an toàn -> Tự động về Home
                            safe_home = self._get_safe_home_target(pose)
                            if safe_home is not None:
                                dist_to_home = math.hypot(pose[0] - safe_home[0], pose[1] - safe_home[1])
                                if dist_to_home > 0.12:
                                    self.goal = safe_home
                                    self._goal_type = 'HOME'
                                    self._goal_time = now
                                    self._goal_retries = 0
                                    self._goal_blocked_count = 0
                                    self.explore_state = 'RETURNING_HOME'
                                    with state.lock:
                                        state.explore_phase = f'HOÀN THÀNH PHỦ KÍN: Đang quay về Home ({dist_to_home:.1f}m)...'
                                else:
                                    with state.lock:
                                        free_cells_count = sum(1 for v in state.map_data if v == 0) if state.map_data else 1
                                        cov_pct = round(len(state.visited_cells) / max(1, free_cells_count) * 100.0, 1)
                                    self._request_home_completion(f'HOÀN THÀNH: Phủ sàn {cov_pct}% & MCU xác nhận dừng tại Home')
                                    return
                            else:
                                self._hold('HOLD: chưa tìm được đường an toàn về Home')
                                return

                    else:
                        # Fallback cho unit tests cũ (khi chưa set _auto_task_mode):
                        new_goal = self.find_best_frontier(*pose[:2])
                        if new_goal is not None:
                            self.goal = new_goal
                            self._goal_type = 'FRONTIER'
                            self._goal_time = now
                            self._goal_retries = 0
                            self._goal_blocked_count = 0
                            self.explore_state = 'EXPLORING'
                        else:
                            cov_goal = None
                            if can_finish:
                                cov_goal = self.find_best_coverage_goal(*pose[:2])
                            if cov_goal is not None:
                                self.goal = cov_goal
                                self._goal_type = 'COVERAGE'
                                self._goal_time = now
                                self._goal_retries = 0
                                self._goal_blocked_count = 0
                                self.explore_state = 'COVERAGE_PATROL'
                            elif is_map_complete:
                                safe_home = self._get_safe_home_target(pose)
                                if safe_home is not None:
                                    dist_to_home = math.hypot(pose[0] - safe_home[0], pose[1] - safe_home[1])
                                    if dist_to_home > 0.12:
                                        self.goal = safe_home
                                        self._goal_type = 'HOME'
                                        self._goal_time = now
                                        self._goal_retries = 0
                                        self._goal_blocked_count = 0
                                        self.explore_state = 'RETURNING_HOME'
                                    else:
                                        with state.lock:
                                            free_cells_count = sum(1 for v in state.map_data if v == 0) if state.map_data else 1
                                            cov_pct = round(len(state.visited_cells) / max(1, free_cells_count) * 100.0, 1)
                                        self._request_home_completion(f'HOÀN THÀNH: Phủ sàn {cov_pct}% & MCU xác nhận dừng tại Home')
                                        return
                                else:
                                    self._hold('HOLD: chưa tìm được đường an toàn về Home')
                                    return
                            else:
                                self.explore_state = 'EXPLORING'

            if self.goal is not None:
                target_pt = self.goal
                if getattr(self, '_last_announced_goal', None) != self.goal:
                    self._last_announced_goal = self.goal
                    if callable(getattr(getattr(self, 'control', None), '_event', None)):
                        self.control._event('navigation_goal_selected', goal=list(self.goal),
                                            goal_type=getattr(self, '_goal_type', None), pose=pose)
                with state.lock:
                    state.target_goal_x, state.target_goal_y = self.goal
            else:
                target_pt = None
                with state.lock:
                    state.target_goal_x, state.target_goal_y = 0.0, 0.0

            if target_pt is None:
                if (not grid.traversable(grid.world_to_cell(*pose[:2])) or
                        not grid.swept_clear(pose, 0., 0.)):
                    if self._enter_cautious(pose):
                        self._hold('TỰ THOÁT: chọn hành lang hẹp đủ thân xe')
                        return
                    if not self._try_operator_clearance_recovery(pose):
                        self._hold('HOLD: thân xe chưa có lối tiến/lùi được map và scan xác nhận')
                    return
                self._hold('HOLD: chưa có mục tiêu A* an toàn')
                return

            if getattr(self, '_goal_type', None) == 'HOME' and target_pt is not None:
                # Operator profile also needs an A* route around known walls.
                # The reactive open-space controller must not aim through a wall.
                max_lh = 0.25 if (getattr(self, 'ai1_mode', 'shadow') == 'control' or not is_op) else 0.35
                home_target = self._local_path_target(grid, pose, target_pt, max_lookahead=max_lh)
                if home_target is None:
                    narrow = self._grid(margin=0.00 if is_op else .03)
                    if narrow is not None:
                        narrow_target = self._local_path_target(narrow, pose, target_pt, max_lookahead=max_lh)
                        if narrow_target is not None:
                            home_target = narrow_target
                            grid = narrow
                try:
                    follow_ok = self._follow(pose, target_pt, planned=(grid, home_target))
                except TypeError:
                    follow_ok = self._follow(pose, target_pt)
                if not follow_ok:
                    if not getattr(self, '_cautious', False):
                        narrow = self._grid(margin=0.00 if is_op else .03)
                        b = getattr(state, 'body_bounds_m', None)
                        narrow_ok = ((hasattr(narrow, 'box_swept_clear') and narrow.box_swept_clear(pose, 0., 0., b, allow_start_overlap=True)) if b else (narrow.swept_clear(pose, 0., 0.) if narrow is not None else False))
                        if (narrow is not None and narrow_ok and
                                self._enter_cautious(pose)):
                            return
                    if is_op and self._shared_checked_recovery(pose, reason='HOME_BLOCKED'):
                        return
                    self._hold('HOLD: không thể bám đường A* về Home')
                return

            # Operator AUTO and AI1 must both follow the same inflated A*
            # corridor. The waypoint is recomputed when SLAM updates the map.
            max_lh = 0.25 if (getattr(self, 'ai1_mode', 'shadow') == 'control' or not is_op) else 0.65
            local_target = self._local_path_target(grid, pose, target_pt, max_lookahead=max_lh)
            if local_target is None:
                path_reason = getattr(grid, 'last_path_status', 'PATH_UNAVAILABLE')
                if callable(getattr(getattr(self,'control',None),'_event',None)):
                    self.control._event('navigation_blocked', reason='NO_SAFE_PATH',
                                        path_reason=path_reason, pose=pose,
                                        goal=target_pt, goal_type=getattr(self,'_goal_type',None))
                # Normal margin can disconnect a corridor that still fits the
                # measured body. Only try the cautious grid when the entire
                # known-free A* route exists and the starting body is clear.
                if (path_reason in ('START_BLOCKED','GOAL_BLOCKED','NO_ROUTE') and
                        not getattr(self, '_cautious', False)):
                    narrow = self._grid(margin=0.00 if is_op else .03)
                    b = getattr(state, 'body_bounds_m', None)
                    narrow_ok = ((hasattr(narrow, 'box_swept_clear') and narrow.box_swept_clear(pose, 0., 0., b, allow_start_overlap=True)) if b else (narrow.swept_clear(pose, 0., 0.) if narrow is not None else False))
                    if (narrow is not None and narrow_ok and
                            narrow.path(pose[:2], target_pt) is not None and
                            self._enter_cautious(pose)):
                        self._hold('VÙNG VÀNG: đã tìm được đường vòng đủ thân xe, lập kế hoạch lại')
                        return
                # A definitive goal-side failure must release stale frontiers
                # immediately. Search timeouts and blocked robot starts are
                # transient and must never blacklist an otherwise valid goal.
                if ((path_reason in ('NO_ROUTE','GOAL_BLOCKED','GOAL_OUT_OF_MAP') or
                     (path_reason == 'START_BLOCKED' and getattr(self, '_goal_blocked_count', 0) >= 3)) and
                        getattr(self,'_goal_type',None) not in ('HOME', 'POINT') and
                        self.goal == target_pt):
                    self._exclude_goal(now, failed=True, reason='ASTAR_' + path_reason)
                    self._goal_blocked_count = 0
                    self._last_frontier_search = now - 1.5
                    self._hold(f'ĐỔI MỤC TIÊU: A* {path_reason}; tìm frontier khác')
                    return
                if getattr(self, '_goal_type', None) == 'POINT':
                    self._hold(f'HOLD: đường đến mục tiêu bị chặn ({path_reason})')
                    return
                if is_op and (not grid.traversable(grid.world_to_cell(*pose[:2])) or
                              not grid.swept_clear(pose, 0., 0.)):
                    if self._try_operator_clearance_recovery(pose):
                        return
                self._hold(f'HOLD: chưa có đường A* an toàn ({path_reason})')
                return

            # Tính góc lệch hướng mục tiêu (Heading Error)
            heading_err = None
            if local_target is not None:
                dx, dy = local_target[0] - pose[0], local_target[1] - pose[1]
                target_yaw = math.atan2(dy, dx)
                heading_err = (target_yaw - pose[2] + math.pi) % (2 * math.pi) - math.pi

            turn_w = max(0.40, min(1.80, getattr(state, 'turn_w_rads', 1.40)))

            ai1_active = False
            self._ai1_active = False
            ai1_available = (getattr(self, 'ai1_mode', 'shadow') != 'off' and
                             getattr(self, 'ai1_runtime', None) is not None and
                             self.goal is not None and len(ranges) == 360)
            if ai1_available:
                if heading_err is None or abs(heading_err) <= 0.80:
                    try:
                        cur_v, cur_w = measured_twist(getattr(self.control, 'latest', None))
                        model_scan = ai1_prepare_scan(ranges)
                        cmd_ai1 = self.ai1_runtime.predict_from_sensors(model_scan, pose, local_target, cur_v, cur_w)
                        v_ai1, w_ai1 = float(cmd_ai1[0]), float(cmd_ai1[1])
                        setattr(self, '_ai1_v', round(v_ai1, 3))
                        setattr(self, '_ai1_w', round(w_ai1, 3))
                        v_cmd, w_cmd = ai1_velocity(cmd_ai1, cruise_speed, turn_w)
                        self._ai1_shadow_cmd = (round(v_cmd, 3), round(w_cmd, 3))
                        self._ai1_error = None
                        if getattr(self, 'ai1_mode', 'shadow') == 'control':
                            # The ONNX runtime already applies acceleration and
                            # obstacle guards. Never restore a positive floor
                            # after the model/filter commanded a full stop.
                            self._last_smooth_v = v_cmd
                            ok, reason = self.send_cmd(f'V {v_cmd:.3f} {w_cmd:.3f}', autonomous=True)
                            if ok:
                                ai1_active = True
                                setattr(self, '_ai1_active', True)
                                with state.lock:
                                    goal_type = getattr(self, '_goal_type', 'FRONTIER')
                                    free_cells_count = sum(1 for v in state.map_data if v == 0) if state.map_data else 1
                                    cov_pct = round(len(state.visited_cells) / max(1, free_cells_count) * 100.0, 1)
                                    if goal_type == 'COVERAGE':
                                        state.explore_phase = f'AI 1 (NÉ CẢN): phủ kín sàn ({cov_pct:.0f}%) | V={v_cmd:.2f} W={w_cmd:.2f}'
                                    elif goal_type == 'HOME':
                                        state.explore_phase = f'AI 1 (NÉ CẢN): về Home | V={v_cmd:.2f} W={w_cmd:.2f}'
                                    else:
                                        state.explore_phase = f'AI 1 (NÉ CẢN): bám mục tiêu | V={v_cmd:.2f} W={w_cmd:.2f}'
                            else:
                                setattr(self, '_ai1_active', False)
                                self._hold('HOLD: AI1 command rejected (' + str(reason) + ')')
                                return
                    except Exception as exc:
                        ai1_active = False
                        setattr(self, '_ai1_active', False)
                        self._ai1_shadow_cmd = None
                        self._ai1_v = None
                        self._ai1_w = None
                        self._ai1_error = type(exc).__name__ + ': ' + str(exc)
                        # Missing LiDAR sectors are a recoverable sensor
                        # degradation: delegate this tick to the classical A*
                        # follower, whose writer still requires a fresh scan,
                        # sufficient forward observations and swept clearance.
                        # Runtime/inference errors remain fail-closed.
                        lidar_gap = (isinstance(exc, ValueError) and
                                     str(exc).startswith('AI1_LIDAR_'))
                        if getattr(self, 'ai1_mode', 'shadow') == 'control' and not lidar_gap:
                            self._hold('HOLD: AI1 inference failed')
                            return

            if ai1_active:
                return

            if not self._follow(pose, target_pt, planned=(grid, local_target)):
                reason = getattr(self, '_last_arc_reason', None) or 'PATH_OR_MOTION_NOT_VALIDATED'
                self._hold(f'HOLD: bám đường A* ({reason})')
            else:
                with state.lock:
                    state.explore_phase = getattr(self, '_follow_phase', 'TỰ HÀNH: bám đường A*')
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
        if getattr(self, '_goal_type', None) == 'POINT':
            if self.goal is not None:
                dist = math.hypot(pose[0]-self.goal[0], pose[1]-self.goal[1])
                if dist <= 0.15:
                    with state.lock:
                        state.explore_phase = f'ĐÃ ĐẾN ĐÍCH: ({self.goal[0]:.2f}, {self.goal[1]:.2f}) & Dừng an toàn'
                        state.auto_mode = False
                        state.target_goal_x = state.target_goal_y = 0.0
                    self.goal = None
                    self.explore_state = 'COMPLETED'
                    self.control.request_stop('GOAL_REACHED', wait=False)
                    return
                if not self._follow(pose, self.goal[:2]):
                    self._enter_cautious(pose)
                    self._hold('HOLD: chưa có đường an toàn đến điểm đã chọn')
            return
        if self.goal is None or math.hypot(pose[0]-self.goal[0],pose[1]-self.goal[1]) < .06:
            if self.goal is not None:
                self._exclude_goal(now,failed=False)
                self.goal = self.find_best_frontier(*pose[:2])
                self.progress.clear()
            elif getattr(self, '_goal_just_excluded', False) or now - getattr(self, '_last_frontier_search', 0) >= 1.5:
                self._goal_just_excluded = False
                self._last_frontier_search = now
                self.goal = self.find_best_frontier(*pose[:2])
                self.progress.clear()
        if self.goal is None:
            if not is_op:
                if self._enter_cautious(pose):
                    self._hold('VÙNG VÀNG: tìm frontier qua hành lang hẹp')
                    return
                with state.lock:
                    remaining = state.frontier_reachable
                    selectable = getattr(state, 'frontier_selectable', remaining or 0)
                    blocked_count = len(self.blocked_regions)
                if selectable == 0 and blocked_count == 0:
                    self.explore_state = 'RETURNING_HOME'
                    self._hold('Hết frontier reachable; nghiệm thu toàn phòng và về Home')
                elif selectable == 0 and blocked_count > 0:
                    self._active_spin_start = getattr(self, '_active_spin_start', None)
                    if self._active_spin_start is None:
                        self._active_spin_start = now
                        self._spin_fail_count = 0
                    if now - self._active_spin_start < 3.0:
                        turn_w = getattr(state, 'turn_w_rads', 1.60)
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

        else:
            self._active_spin_start = None
        if self.goal is not None:
            with state.lock:
                state.target_goal_x, state.target_goal_y = self.goal
                state.explore_phase = 'EXPLORING: bám đường A* known-free'
        else:
            with state.lock:
                state.target_goal_x, state.target_goal_y = 0.0, 0.0
        if not self._follow(pose,self.goal):
            if getattr(self,'_follow_transient',False):
                self._hold('CHỜ MẪU MỚI: '+str(getattr(self,'_last_arc_reason','BUSY_OR_STALE')))
                return
            if self._enter_cautious(pose):
                self._hold('VÙNG VÀNG: giữ mục tiêu, tính lại đường chậm')
                return
            self._goal_retries = getattr(self, '_goal_retries', 0) + 1
            if self._goal_retries < 5:
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
            if path in ('/api/cmd','/api/pid','/api/auto','/api/set_goal') and not stop:
                self._command_reply(423,{'status':'FAILED','reason':'OBSERVE_ONLY'},path,params)
                return

        if path == '/api/diagnostics':
            report=ros_node.control.diagnostics() if ros_node else {'status':'NO_TRANSPORT'}
            report['command_journal']=self.server.command_journal.snapshot()
            if ros_node:
                with state.lock:
                    report['navigation'] = dict(
                        home=getattr(ros_node, 'home', None),
                        goal=getattr(ros_node, 'goal', None),
                        goal_type=getattr(ros_node, '_goal_type', None),
                        cautious=bool(getattr(ros_node, '_cautious', False)),
                        controller='ASTAR_PATH_FOLLOWER',
                        motion_warning=getattr(ros_node, '_motion_warning', None),
                        last_arc_reason=getattr(ros_node, '_last_arc_reason', None),
                        blocked_goals=list(getattr(ros_node, 'blocked_goals', [])),
                        blocked_regions=list(getattr(ros_node, 'blocked_regions', [])),
                        last_goal_change=getattr(ros_node, '_last_goal_change', None),
                        reachable_frontiers=state.frontier_reachable,
                        selectable_frontiers=state.frontier_count)
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
                    "speed_config": {
                        "speed_rpm": state.auto_target_speed_rpm,
                        "turn_rpm": state.auto_target_turn_rpm,
                        "slow_rpm": SLOW_RPM,
                        "cruise_mps": state.cruise_speed_mps,
                        "turn_w": state.turn_w_rads,
                    },
                    "status": 'OBSERVE_ONLY' if observe_only else state.safety_status,
                    "hz": state.hz,
                    "lidar": {
                        "connected": bool(state.scan_mono and -0.1 <= time.monotonic() - state.scan_mono <= 1.0 and state.valid_points > 0),
                        "age_s": round(time.monotonic() - state.scan_mono, 3) if state.scan_mono else None,
                        "points": state.valid_points,
                    },
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
                    "trajectory": {
                        "path": list(state.path_history),
                        "distance_m": round(state.total_distance_m, 2),
                        "points_count": len(state.path_history),
                        "visited_count": len(state.visited_cells),
                        "coverage_pct": round(len(state.visited_cells) / max(1, sum(1 for v in state.map_data if v == 0)) * 100.0, 1) if (state.map_data and any(v == 0 for v in state.map_data)) else 0.0
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
                        "tf_error": getattr(ros_node, '_last_pose_error', None) if ros_node else None,
                        "goal_x": state.target_goal_x, "goal_y": state.target_goal_y,
                        "home": getattr(ros_node, 'home', None),
                        "goal_type": getattr(ros_node, '_goal_type', None),
                        "task_mode": getattr(ros_node, '_auto_task_mode', 'EXPLORE') if ros_node else 'EXPLORE',
                        "phase": state.explore_phase
                    },
                    "ai": {
                        "ai1_loaded": getattr(ros_node, 'ai1_runtime', None) is not None,
                        "ai1_mode": getattr(ros_node, 'ai1_mode', 'off'),
                        "ai1_active": bool(getattr(ros_node, '_ai1_active', False)),
                        "ai1_v": getattr(ros_node, '_ai1_v', None),
                        "ai1_w": getattr(ros_node, '_ai1_w', None),
                        "ai1_shadow_cmd": getattr(ros_node, '_ai1_shadow_cmd', None),
                        "ai1_error": getattr(ros_node, '_ai1_error', None),
                        "ai1_scan_ready": False,
                        "ai1_scan_blocker": None,
                        "ai1_scan_valid_bins": 0,
                        "ai2_loaded": getattr(ros_node, 'ai2_session', None) is not None,
                        "ai2_mode": getattr(ros_node, 'ai2_mode', 'off'),
                        "ai2_action": getattr(ros_node, '_ai2_best_action', None),
                        "ai2_q": getattr(ros_node, '_ai2_q_vals', None),
                        "ai2_shadow_goal": getattr(ros_node, '_ai2_shadow_goal', None),
                        "ai2_error": getattr(ros_node, '_ai2_error', None)
                    }
                }
            # Goals and breadcrumbs are in map, not in the MCU's odom frame.
            # Publish the same fresh TF pose used by the navigator for drawing.
            lookup_pose = getattr(ros_node, '_pose_map', None)
            map_pose = lookup_pose() if callable(lookup_pose) else None
            d['map_info']['robot_pose'] = (list(map_pose) if isinstance(map_pose, (tuple, list))
                                           and len(map_pose) == 3 and all(finite(v) for v in map_pose)
                                           else None)
            # The AI model may be loaded while the real C1 scan still has a
            # persistent blind sector. Publish the inference gate separately
            # from inference errors, even when AUTO is idle / AI is in shadow.
            # Compute after releasing the shared ROS state lock.
            d['ai']['ai1_scan_valid_bins'] = sum(
                math.isfinite(x) and .05 <= x < 16.0
                for x in d['ranges'] if isinstance(x, (int, float)))
            try:
                is_op = getattr(self, 'control', None) is not None and not getattr(self.control, 'strict_preflight', True)
                max_lidar_age = .75 if is_op else .50
                if not d['lidar']['connected'] or d['lidar']['age_s'] is None or d['lidar']['age_s'] > max_lidar_age:
                    raise ValueError('AI1_LIDAR_STALE')
                ai1_prepare_scan(d['ranges'])
                d['ai']['ai1_scan_ready'] = True
            except ValueError as exc:
                d['ai']['ai1_scan_blocker'] = str(exc)[:100]
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

        elif path == '/api/reset_map':
            if ros_node:
                ok, reason = ros_node.reset_slam_map()
            else:
                ok, reason = False, 'NO_TRANSPORT'
            self._command_reply(200 if ok else 500, {'status': 'OK' if ok else 'FAILED', 'reason': reason}, 'RESET_MAP', {})
            return

        elif path == '/api/cmd':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            val = params.get('val',[''])[0]
            if ros_node:
                ok,reason = ros_node.send_cmd(val)
                if val.startswith(('M ', 'V ', 'S ')) and ros_node.control.autonomy_allowed is False:
                    with state.lock: state.auto_mode = False
                if val == 'STOP' and reason == 'STOP_SUPERSEDED':
                    ok = True
                    reason = 'STOPPED'
            else:
                ok,reason = False,'NO_TRANSPORT'
            response={'status':'SENT' if ok else 'FAILED','reason':reason}
            if ros_node and not ok and reason == 'SESSION_OR_SENSOR_NOT_READY':
                # Surface the MCU session failure instead of blaming LiDAR
                # proximity when a MANUAL command reached a DISARMED MCU.
                health=ros_node.control.health()
                d0=health.get('latest_d0') or {}
                blocked=[]
                if health.get('latched'): blocked.append('LATCHED')
                if not health.get('armed'): blocked.append('NOT_ARMED')
                if health.get('fault') or d0.get('safety')=='FAULT': blocked.append('FAULT')
                age=health.get('d0_age_s')
                if age is None or not 0<=age<=.25: blocked.append('D0_STALE')
                if d0.get('safety')!='ARMED': blocked.append('MCU_NOT_ARMED')
                response['blockers']=blocked
            self._command_reply(200 if ok else (409 if reason == 'AUTO_OWNS_CONTROL' else 422),response,'COMMAND',{'val':val})
            return

        elif path == '/api/auto_config':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                spd_rpm = float(params.get('speed', [state.auto_target_speed_rpm])[0])
                trn_rpm = float(params.get('turn', [state.auto_target_turn_rpm])[0])
                if spd_rpm not in (SLOW_RPM, NORMAL_RPM) or trn_rpm not in (SLOW_RPM, NORMAL_RPM):
                    raise ValueError('Chọn tốc độ 40 hoặc 65 RPM')
                with state.lock:
                    state.auto_target_speed_rpm = spd_rpm
                    state.auto_target_turn_rpm = trn_rpm
                    state.cruise_speed_mps = rpm_to_speed(spd_rpm)
                    state.turn_w_rads = rpm_to_turn(trn_rpm)
                if ros_node:
                    with ros_node.control.lock:
                        ros_node.control.auto_speed_rpm = spd_rpm
                        ros_node.control.auto_turn_rpm = trn_rpm
                result = {
                    'status': 'OK',
                    'speed_rpm': spd_rpm,
                    'turn_rpm': trn_rpm,
                    'slow_rpm': SLOW_RPM,
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
            params = urllib.parse.parse_qs(q)
            act = params.get('act',[''])[0].upper()
            mode = params.get('mode', ['EXPLORE'])[0].upper()
            ok,reason = False,'NO_TRANSPORT'
            blockers,snapshot=[],{}
            if ros_node and act == 'START':
                if mode in ('NAV_TO_GOAL', 'POINT') and 'x' in params and 'y' in params:
                    try:
                        gx = float(params.get('x', [0])[0])
                        gy = float(params.get('y', [0])[0])
                        ok, reason, blockers, snapshot = ros_node.navigate_to_point(gx, gy)
                    except (ValueError, IndexError):
                        ok, reason = False, 'INVALID_COORDINATES'
                else:
                    ok,reason,blockers,snapshot=ros_node.start_auto(mode=mode)
            elif ros_node and act == 'STOP':
                ok,reason = ros_node.send_cmd('STOP')
                if reason == 'STOP_SUPERSEDED' or not state.auto_mode:
                    ok = True
                    reason = 'STOPPED'
            self._command_reply(200 if ok else 422,{'status':'ok' if ok else 'FAILED',
                'auto':state.auto_mode,'reason':reason,'blockers':blockers,'gate':snapshot,'mode':mode},'AUTO_'+act,{'act':act,'mode':mode})
            return

        elif path == '/api/set_goal':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                gx = float(params.get('x', [''])[0])
                gy = float(params.get('y', [''])[0])
            except (ValueError, IndexError):
                self._command_reply(400, {'status': 'FAILED', 'reason': 'INVALID_COORDINATES'}, 'SET_GOAL', params)
                return
            ok, reason, blockers, snapshot = False, 'NO_TRANSPORT', [], {}
            if ros_node:
                ok, reason, blockers, snapshot = ros_node.navigate_to_point(gx, gy)
            self._command_reply(200 if ok else 422, {
                'status': 'ok' if ok else 'FAILED',
                'auto': state.auto_mode,
                'reason': reason,
                'target_x': gx,
                'target_y': gy,
                'blockers': blockers,
                'gate': snapshot
            }, 'SET_GOAL', {'x': gx, 'y': gy})
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
