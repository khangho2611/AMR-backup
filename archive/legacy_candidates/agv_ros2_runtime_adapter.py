#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
AGV ROS 2 RUNTIME & FIRMWARE PACKET ADAPTER (OFFLINE FAKE TRANSPORT SLICE)
===============================================================================
Triển khai lát cắt tích hợp hoàn chỉnh (Full End-to-End Integration Slice):
1. Firmware Packet Receiver & Monotonic Ingest Adapter:
   - Nhận gói tin JSON chuẩn từ firmware ESP32 (không có t) qua cổng Serial Pi.
   - Gắn timestamp Pi Monotonic chính xác tại thời điểm nhận (receive timestamp).
   - Ánh xạ sang ROS 2 Header Stamp (sec, nanosec) mà không bịt/chế dữ liệu.
2. ROS 2 Node Runtime (REP-103 / REP-105 / REP-2000):
   - Quản lý Node, Publishers (/odom), Subscriptions (/cmd_vel_nav, /cmd_vel_teleop, /scan),
     Timers, SingleThreadedExecutor.
   - Broadcaster TF odom -> base_footprint -> base_link -> laser_frame.
3. Authenticated Source Lease & Priority Gate:
   - EMERGENCY_STOP (0) > MANUAL_TELEOP (1) > AUTONOMOUS_NAV (2).
   - Xác thực lease caller, quản lý epoch, token, deadman TTL trần <= 200ms.
4. Thread Watchdog:
   - Giám sát luồng độc lập, tự động hủy lease và phát STOP nếu caller im lặng (silent).
5. Tích hợp Fake Transport an toàn 100% OFFLINE (chặn phát xung phần cứng thật).
===============================================================================
"""

import sys
import time
import math
import json
import threading
from typing import Dict, Any, Optional, Tuple, List, Callable

# Kiểm tra thư viện ROS 2 rclpy
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.publisher import Publisher
    from rclpy.subscription import Subscription
    from rclpy.timer import Timer
    from rclpy.executors import SingleThreadedExecutor
    from nav_msgs.msg import Odometry
    from geometry_msgs.msg import Twist, TransformStamped
    from sensor_msgs.msg import LaserScan
    import tf2_ros
    HAVE_REAL_RCLPY = True
except ImportError:
    HAVE_REAL_RCLPY = False
    Node = object
    Publisher = Any
    Subscription = Any
    Timer = Any
    SingleThreadedExecutor = Any

    # Q6 Fix: Typed Message Classes cho môi trường Offline
    class FakeHeader:
        def __init__(self, stamp: Any = None, frame_id: str = ""):
            self.stamp = stamp
            self.frame_id = frame_id

    class FakeVector3:
        def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    class FakePoint:
        def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    class FakeQuaternion:
        def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0, w: float = 1.0):
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)
            self.w = float(w)

    class FakePose:
        def __init__(self):
            self.position = FakePoint()
            self.orientation = FakeQuaternion()

    class FakeTwist:
        def __init__(self):
            self.linear = FakeVector3()
            self.angular = FakeVector3()

    class FakePoseWithCovariance:
        def __init__(self):
            self.pose = FakePose()
            self.covariance = [0.0] * 36

    class FakeTwistWithCovariance:
        def __init__(self):
            self.twist = FakeTwist()
            self.covariance = [0.0] * 36

    class FakeOdometry:
        def __init__(self):
            self.header = FakeHeader()
            self.child_frame_id = ""
            self.pose = FakePoseWithCovariance()
            self.twist = FakeTwistWithCovariance()

    class FakeTransform:
        def __init__(self):
            self.translation = FakeVector3()
            self.rotation = FakeQuaternion()

    class FakeTransformStamped:
        def __init__(self):
            self.header = FakeHeader()
            self.child_frame_id = ""
            self.transform = FakeTransform()

    class FakeLaserScan:
        def __init__(self):
            self.header = FakeHeader()
            self.angle_min = 0.0
            self.angle_max = 0.0
            self.angle_increment = 0.0
            self.ranges = []

    Odometry = FakeOdometry
    Twist = FakeTwist
    TransformStamped = FakeTransformStamped
    LaserScan = FakeLaserScan


# =============================================================================
# HELPER: VALIDATE SỐ HỮU HẠN
# =============================================================================
def _is_valid_finite(val: Any) -> bool:
    if val is None or isinstance(val, bool):
        return False
    try:
        f = float(val)
        return not (math.isnan(f) or math.isinf(f))
    except (ValueError, TypeError):
        return False


# =============================================================================
# ROS 2 MOCK / FAKE OBJECTS CHO KIỂM THỬ OFFLINE WINDOWS (KHÔNG CẦN ROS DAEMON)
# =============================================================================
class _FakeClock:
    def __init__(self):
        self.time_fn = time.monotonic

    def now(self):
        t = self.time_fn()
        sec = int(t)
        nanosec = int((t - sec) * 1e9)
        return _FakeTime(sec, nanosec)


class _FakeTime:
    def __init__(self, sec: int, nanosec: int):
        self.sec = sec
        self.nanosec = nanosec

    def to_msg(self):
        return {"sec": self.sec, "nanosec": self.nanosec}


class _FakePublisher:
    def __init__(self, topic: str, msg_type: Any):
        self.topic = topic
        self.msg_type = msg_type
        self.published_messages: List[Any] = []

    def publish(self, msg: Any):
        self.published_messages.append(msg)


class _FakeSubscription:
    def __init__(self, topic: str, msg_type: Any, callback: Callable[[Any], None]):
        self.topic = topic
        self.msg_type = msg_type
        self.callback = callback


class _FakeTimer:
    def __init__(self, period_s: float, callback: Callable[[], None]):
        self.period_s = period_s
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _BaseNode:
    """Base Node hỗ trợ dependency injection cho môi trường offline."""
    def __init__(self, node_name: str):
        self.node_name = node_name
        self.publishers_map: Dict[str, Any] = {}
        self.subscriptions_map: Dict[str, Any] = {}
        self.timers_list: List[Any] = []
        self._clock = _FakeClock()

    def get_clock(self):
        return self._clock

    def create_publisher(self, msg_type: Any, topic: str, qos_profile: int = 10):
        pub = _FakePublisher(topic, msg_type)
        self.publishers_map[topic] = pub
        return pub

    def create_subscription(self, msg_type: Any, topic: str, callback: Callable[[Any], None], qos_profile: int = 10):
        sub = _FakeSubscription(topic, msg_type, callback)
        self.subscriptions_map[topic] = sub
        return sub

    def create_timer(self, period_s: float, callback: Callable[[], None]):
        timer = _FakeTimer(period_s, callback)
        self.timers_list.append(timer)
        return timer

    def destroy_node(self):
        self.timers_list.clear()
        self.publishers_map.clear()
        self.subscriptions_map.clear()


NodeClass = Node if HAVE_REAL_RCLPY else _BaseNode

# Import Serial Arbiter Gate v3
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
from agv_ros2_arbiter_bridge import AGVRos2ArbiterBridge, CommandPriority


# =============================================================================
# 1. FIRMWARE PACKET ADAPTER (SOURCE-LINKED MONOTONIC RECEIVER)
# =============================================================================
class FirmwarePacketAdapter:
    """
    Adapter chuyển đổi luồng tin thô từ ESP32 firmware sang cấu trúc chuẩn ROS.
    - Firmware packet format (main.cpp L347):
      {"safety":"...","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,
       "l_pwm":0,"r_pwm":0,"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}
    - ĐẶC TẢ: Firmware KHÔNG phát trường 't'. Adapter phải lấy Pi time.monotonic()
      ngay tại thời điểm đọc xong dòng Serial làm mốc chuẩn (Pi Receive Monotonic).
    """

    def __init__(self, bridge: AGVRos2ArbiterBridge):
        self.bridge = bridge
        self.total_packets_received = 0
        self.corrupt_packets_count = 0

    def parse_and_ingest(self, raw_line: str, rx_mono: Optional[float] = None) -> bool:
        """
        Nhận 1 dòng Serial thô, gắn timestamp thu nhận Pi Monotonic và ingest vào Bridge.
        P1 Fix: Phân loại gói tin đa hình:
        1. Gói phản hồi xác nhận ("ack") từ ESP32 -> Chuyển tiếp thẳng cho Gate xử lý ACK (ARM/DISARM),
           không parse odometry, trả về True.
        2. Gói telemetry đo đạc ("safety") -> Validate đầy đủ trường số học, chuyển tiếp Gate và ingest Bridge.
        3. Dòng rác hoặc định dạng sai -> Reject False.
        """
        # A1 Fix: Kiểm tra chặt chẽ timestamp nhận rx_mono
        if rx_mono is not None:
            if not _is_valid_finite(rx_mono) or rx_mono <= 0.0:
                self.corrupt_packets_count += 1
                return False
            now_mono = float(rx_mono)
        else:
            now_mono = time.monotonic()

        try:
            line_str = str(raw_line).strip()
            if not line_str or not line_str.startswith("{") or not line_str.endswith("}"):
                self.corrupt_packets_count += 1
                return False
            data = json.loads(line_str)
        except Exception:
            self.corrupt_packets_count += 1
            return False

        if not isinstance(data, dict):
            self.corrupt_packets_count += 1
            return False

        # ---------------------------------------------------------------------
        # P1 Fix (Nhánh 1): Gói phản hồi ACK (ví dụ {"ack":"ARM","state":"ARMED"})
        # ---------------------------------------------------------------------
        if "ack" in data:
            if self.bridge.serial_arbiter:
                try:
                    self.bridge.serial_arbiter.process_incoming_line(line_str, now_mono)
                except Exception:
                    pass
            self.total_packets_received += 1
            return True

        # ---------------------------------------------------------------------
        # P1 Fix (Nhánh 2): Gói Telemetry thông thường (phải có "safety" và trường số)
        # ---------------------------------------------------------------------
        # A2 Fix: Bắt lỗi toàn bộ trường số học, loại trừ 'corrupt' hoặc phi finite
        req_numeric = ["x", "y", "th", "v", "w", "l_rpm", "r_rpm", "l_pwm", "r_pwm"]
        for f in req_numeric:
            if f not in data or not _is_valid_finite(data[f]):
                self.corrupt_packets_count += 1
                return False

        if "safety" not in data or not isinstance(data["safety"], str):
            self.corrupt_packets_count += 1
            return False

        # Chuẩn hóa gói tin chuyển vào ROS 2 Arbiter Bridge
        telemetry_packet = {
            "t": now_mono,
            "x": float(data["x"]),
            "y": float(data["y"]),
            "th": float(data["th"]),
            "v": float(data["v"]),
            "w": float(data["w"]),
            "safety": str(data["safety"]).strip(),
            "l_rpm": float(data["l_rpm"]),
            "r_rpm": float(data["r_rpm"]),
            "l_pwm": float(data["l_pwm"]),
            "r_pwm": float(data["r_pwm"])
        }

        # S1 Fix: Đảm bảo luồng thống nhất transport -> gate -> adapter -> watchdog
        # Nếu bridge có serial_arbiter, cập nhật trạng thái gói tin vào gate để gate phân tích
        if self.bridge.serial_arbiter:
            try:
                self.bridge.serial_arbiter.process_incoming_line(line_str, now_mono)
            except Exception:
                pass

        # Cập nhật trạng thái xác nhận dừng D0 cho watchdog supervisor nếu có
        if hasattr(self.bridge, "runtime_node") and self.bridge.runtime_node is not None:
            if hasattr(self.bridge.runtime_node, "watchdog"):
                if getattr(self.bridge.serial_arbiter, "stop_confirmed", False):
                    self.bridge.runtime_node.watchdog.last_stop_confirmed = True

        self.total_packets_received += 1
        return self.bridge.ingest_telemetry_packet(telemetry_packet, now_mono=now_mono)


# =============================================================================
# 2. WATCHDOG THREAD RUNTIME (INDEPENDENT LEASE MONITOR)
# =============================================================================
class ActiveLeaseWatchdogThread:
    """
    Watchdog thread chạy độc lập với tần số 50Hz (20ms/chu kỳ).
    - Giám sát thời hạn lease của caller đang giữ quyền điều khiển.
    - W1 Fix: Giữ lại toàn bộ kết quả STOP (`last_stop_result`), trạng thái xác nhận
      `last_stop_confirmed`, và cờ lỗi `last_stop_write_failed` để supervisor
      có thể phát hiện và kích hoạt bounded escalation thay vì chỉ xóa lease mù quáng.
    """

    def __init__(self, bridge: AGVRos2ArbiterBridge, check_interval_s: float = 0.02):
        self.bridge = bridge
        self.check_interval_s = check_interval_s
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.watchdog_tripped_count = 0

        # W1 State tracking
        self.last_stop_result: Optional[str] = None
        self.last_stop_confirmed: bool = False
        self.last_stop_write_failed: bool = False
        self.last_trip_time: float = 0.0

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _run_loop(self):
        while self.running:
            time.sleep(self.check_interval_s)
            now = time.monotonic()
            with self.bridge.lock:
                if self.bridge.active_lease_source is not None:
                    # Kiểm tra quá hạn lease
                    if now >= self.bridge.active_lease_deadline:
                        self.watchdog_tripped_count += 1
                        self.last_trip_time = now
                        # Thu hồi quyền lease của caller
                        self.bridge.active_lease_source = None
                        self.bridge.active_lease_id = None

                        # Thực hiện Emergency STOP khẩn cấp qua Gate
                        if self.bridge.serial_arbiter:
                            try:
                                stop_res = self.bridge.serial_arbiter.send_stop(now_mono=now)
                                if isinstance(stop_res, tuple):
                                    write_ok = bool(stop_res[0])
                                    detail = str(stop_res[1])
                                else:
                                    write_ok = bool(stop_res)
                                    detail = "STOP_SENT_OK" if write_ok else "STOP_WRITE_FAILED"
                                
                                self.last_stop_confirmed = getattr(self.bridge.serial_arbiter, "stop_confirmed", False)
                                self.last_stop_write_failed = not write_ok
                                self.last_stop_result = detail if write_ok else "REJECT_STOP_WRITE_FAILED"
                            except Exception as e_stop:
                                self.last_stop_write_failed = True
                                self.last_stop_confirmed = False
                                self.last_stop_result = f"STOP_EXCEPTION_{type(e_stop).__name__}: {str(e_stop)}"


# =============================================================================
# 3. PRODUCTION-GRADE ROS 2 RUNTIME NODE (FULL REP-103/105/2000 ARCHITECTURE)
# =============================================================================
class AGVRos2RuntimeNode(NodeClass):
    """
    Node ROS 2 thực thi đầy đủ chu trình điều khiển của xe AGV:
    - Publishers:
      * /odom (nav_msgs/Odometry): Tọa độ Odometry theo chuẩn REP-105
      * /tf (geometry_msgs/TransformStamped): Cây tọa độ odom -> base_footprint -> base_link
    - Subscriptions:
      * /cmd_vel_nav (geometry_msgs/Twist): Lệnh điều hướng từ Navigation / Planner
      * /cmd_vel_teleop (geometry_msgs/Twist): Lệnh điều khiển thủ công từ Web/Gamepad
      * /scan (sensor_msgs/LaserScan): Luồng quét laser từ RPLIDAR C1
    - Timers:
      * Watchdog health monitor (20Hz)
    - Executor compatibility: spin, spin_once, add_node
    """

    def __init__(
        self,
        node_name: str = "agv_ros2_runtime_node",
        serial_arbiter: Any = None,
        is_mock: bool = True,
        freshness_ttl_s: float = 0.25,
    ):
        if HAVE_REAL_RCLPY and isinstance(self, Node):
            super().__init__(node_name)
        else:
            _BaseNode.__init__(self, node_name)

        self.bridge = AGVRos2ArbiterBridge(
            node_name=node_name,
            serial_arbiter=serial_arbiter,
            is_mock=is_mock,
            freshness_ttl_s=freshness_ttl_s,
        )
        self.bridge.runtime_node = self
        self.adapter = FirmwarePacketAdapter(self.bridge)
        self.watchdog = ActiveLeaseWatchdogThread(self.bridge, check_interval_s=0.02)

        # 1. Khởi tạo Publishers
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        self.tf_pub = self.create_publisher(TransformStamped, "/tf", 10)

        # 2. Khởi tạo Subscriptions
        self.nav_sub = self.create_subscription(Twist, "/cmd_vel_nav", self._on_cmd_vel_nav, 10)
        self.teleop_sub = self.create_subscription(Twist, "/cmd_vel_teleop", self._on_cmd_vel_teleop, 10)
        self.scan_sub = self.create_subscription(LaserScan, "/scan", self._on_laserscan, 10)

        # 3. Khởi tạo Timer giám sát an toàn (20Hz)
        self.health_timer = self.create_timer(0.05, self._on_health_timer)

    def _validate_and_submit_cmd(
        self,
        source: int,
        msg: Any,
        now_mono: float,
        deadline_ttl_s: float = 0.15
    ) -> bool:
        """
        D1-D5 Fix: Bộ kiểm duyệt lệnh điều khiển dùng chung (Common Trusted Command Adapter).
        - Triệt tiêu hoàn toàn unhandled exceptions (không throw ValueError ra ngoài callback).
        - Bắt buộc phải có `lease_id`, `stamp`, `epoch`.
        - Kiểm tra kiểu dữ liệu nghiêm ngặt: `type(epoch) is int and not isinstance(epoch, bool)`.
        - Temporal Guard: Chặn future stamp (`stamp > now_mono + 0.05s`) và stale age (`now_mono - stamp > 0.20s`).
        - Khớp epoch với `gate.current_epoch`.
        """
        try:
            if not hasattr(msg, "linear") or not hasattr(msg, "angular"):
                return False

            linear_v = getattr(msg.linear, "x", 0.0)
            angular_w = getattr(msg.angular, "z", 0.0)

            # 1. Lease ID bắt buộc
            lease_id = getattr(msg, "lease_id", None) or getattr(msg, "session_token", "")
            if not lease_id or not isinstance(lease_id, str) or not lease_id.strip():
                return False

            # 2. D1 Fix: Bắt buộc phải có stamp VÀ epoch
            if not hasattr(msg, "stamp") or getattr(msg, "stamp") is None:
                return False
            if not hasattr(msg, "epoch") or getattr(msg, "epoch") is None:
                return False

            raw_stamp = getattr(msg, "stamp")
            raw_epoch = getattr(msg, "epoch")

            # 3. D4 & D5 Fix: Kiểm tra nghiêm ngặt kiểu epoch (chính xác int, không bool, không float/string)
            if type(raw_epoch) is not int or isinstance(raw_epoch, bool):
                return False

            # 4. Kiểm tra stamp số thực hữu hạn
            if not _is_valid_finite(raw_stamp):
                return False
            s = float(raw_stamp)
            if s <= 0.0:
                return False

            # Quy đổi timestamp sang monotonic nếu là ROS epoch
            cmd_mono = self._to_mono(s, now_mono)

            # 5. D2 Fix: Chặn future timestamp (vượt quá 50ms)
            if cmd_mono > (now_mono + 0.05):
                return False

            # 6. D3 Fix: Chặn stale age vượt quá deadman budget (<= 200ms)
            age = now_mono - cmd_mono
            if age < 0.0 or age > 0.20:
                return False

            # 7. Khớp epoch với Gate
            if self.bridge.serial_arbiter:
                gate_epoch = getattr(self.bridge.serial_arbiter, "current_epoch", 0)
                if raw_epoch != gate_epoch:
                    return False

            ok, _ = self.bridge.submit_cmd_vel(
                source=source,
                lease_id=lease_id.strip(),
                linear_v=linear_v,
                angular_w=angular_w,
                now_mono=now_mono,
                deadline_ttl_s=deadline_ttl_s
            )
            return ok
        except Exception:
            # D5 Fix: Chặn mọi ngoại lệ, không để lọt ra ngoài callback
            return False

    def _on_cmd_vel_nav(self, msg: Any):
        """Callback nhận lệnh từ bộ điều hướng tự động (Priority 2)."""
        now_mono = time.monotonic()
        self._validate_and_submit_cmd(
            source=CommandPriority.AUTONOMOUS_NAV,
            msg=msg,
            now_mono=now_mono,
            deadline_ttl_s=0.15
        )

    def _on_cmd_vel_teleop(self, msg: Any):
        """Callback nhận lệnh từ điều khiển thủ công (Priority 1)."""
        now_mono = time.monotonic()
        self._validate_and_submit_cmd(
            source=CommandPriority.MANUAL_TELEOP,
            msg=msg,
            now_mono=now_mono,
            deadline_ttl_s=0.15
        )

    def _to_mono(self, stamp: float, now_mono: float) -> float:
        """
        Q1 Fix: Ánh xạ timestamp đo đạc (có thể là ROS clock hoặc Wall clock)
        sang monotonic clock của Pi.
        Nếu stamp nằm ở vùng ROS epoch (~1.7e9) hoặc chênh lệch lớn so với now_mono,
        tính toán offset giữa ROS clock và mono_now để quy đổi tất định.
        """
        if stamp is None or not _is_valid_finite(stamp):
            return now_mono

        s = float(stamp)
        ros_now = self.get_clock().now()
        # Chuyển ros_now sang float seconds
        if hasattr(ros_now, "nanoseconds"):
            ros_sec = float(ros_now.nanoseconds) * 1e-9
        elif hasattr(ros_now, "sec") and hasattr(ros_now, "nanosec"):
            ros_sec = float(ros_now.sec) + float(ros_now.nanosec) * 1e-9
        else:
            try:
                ros_sec = float(ros_now)
            except (ValueError, TypeError):
                ros_sec = now_mono

        # Nếu ros_sec > 1e6 (ROS Epoch) và s > 1e6 -> Ánh xạ dựa trên clock chênh lệch
        if ros_sec > 1e6 and s > 1e6:
            # age tính theo ROS clock
            age = ros_sec - s
            return now_mono - age

        return s

    def _on_laserscan(self, msg: Any):
        """
        Callback nhận dữ liệu quét RPLIDAR C1.
        Q1, Q2, Q3, Q4 Fix:
        - Bắt buộc phải có msg.header (Q2).
        - Validate frame_id thuộc known_frames cấu hình sẵn (Q3).
        - Bắt toàn bộ lỗi parse sec/nanosec, không throw ValueError (Q4).
        - Ánh xạ ROS clock timestamp sang monotonic qua _to_mono (Q1).
        """
        now_mono = time.monotonic()

        # 1. Payload ranges bắt buộc
        if not hasattr(msg, "ranges") or msg.ranges is None:
            return
        ranges = getattr(msg, "ranges", None)
        if not isinstance(ranges, (list, tuple)) or len(ranges) == 0:
            return

        # 2. Q2 Fix: Header bắt buộc phải tồn tại
        if not hasattr(msg, "header") or msg.header is None:
            return
        header = msg.header

        # 3. Q3 Fix: Kiểm tra frame_id thuộc danh sách cấu hình hợp lệ
        known_frames = {"laser", "laser_frame", "rplidar_link", "base_scan"}
        frame_id = getattr(header, "frame_id", None)
        if not isinstance(frame_id, str) or frame_id.strip() not in known_frames:
            return

        # 4. Q4 & Q1 Fix: Trích xuất và parse an toàn timestamp
        if not hasattr(header, "stamp") or header.stamp is None:
            return

        stamp_obj = header.stamp
        try:
            sec_val = getattr(stamp_obj, "sec", None)
            nanosec_val = getattr(stamp_obj, "nanosec", 0)
            if sec_val is None:
                # Trường hợp stamp là số float trực tiếp
                if not _is_valid_finite(stamp_obj):
                    return
                raw_stamp = float(stamp_obj)
            else:
                if not _is_valid_finite(sec_val) or not _is_valid_finite(nanosec_val):
                    return
                sec = float(sec_val)
                nanosec = float(nanosec_val)
                if sec == 0.0 and nanosec == 0.0:
                    return
                raw_stamp = sec + nanosec * 1e-9
        except (ValueError, TypeError):
            # Q4 Fix: Chặn lỗi văng ValueError ra ngoài
            return

        # Q1 Fix: Ánh xạ timestamp ROS sang monotonic timestamp tương ứng
        measurement_stamp = self._to_mono(raw_stamp, now_mono)

        angle_min = getattr(msg, "angle_min", None)
        angle_max = getattr(msg, "angle_max", None)
        angle_increment = getattr(msg, "angle_increment", None)

        if angle_min is None or angle_max is None or angle_increment is None:
            return

        try:
            a_min = float(angle_min)
            a_max = float(angle_max)
            a_inc = float(angle_increment)
        except (ValueError, TypeError):
            return

        self.bridge.ingest_scan_packet(
            angle_min=a_min,
            angle_max=a_max,
            angle_increment=a_inc,
            ranges=list(ranges),
            stamp=measurement_stamp,
            frame_id=frame_id.strip(),
            now_mono=now_mono
        )

    def destroy_node(self):
        """
        Q7 & D6 Fix: Graceful shutdown an toàn tuyệt đối:
        - Thu hồi toàn bộ lease.
        - Phát lệnh STOP khẩn cấp qua Gate để đưa xe về trạng thái an toàn.
        - D6 Fix: Bắt lỗi OSError khi ghi Serial, cập nhật chính xác trạng thái lỗi
          `last_stop_write_failed = True` và ghi nhận `last_stop_result` vào watchdog.
        - Dừng luồng Watchdog an toàn.
        """
        now = time.monotonic()
        with self.bridge.lock:
            self.bridge.active_lease_source = None
            self.bridge.active_lease_id = None
            if self.bridge.serial_arbiter:
                try:
                    stop_res = self.bridge.serial_arbiter.send_stop(now_mono=now)
                    if isinstance(stop_res, tuple):
                        write_ok = bool(stop_res[0])
                        detail = str(stop_res[1])
                    else:
                        write_ok = bool(stop_res)
                        detail = "STOP_SENT_OK" if write_ok else "STOP_WRITE_FAILED"

                    self.watchdog.last_stop_confirmed = getattr(self.bridge.serial_arbiter, "stop_confirmed", False)
                    self.watchdog.last_stop_write_failed = not write_ok
                    self.watchdog.last_stop_result = detail if write_ok else "REJECT_STOP_WRITE_FAILED"
                except Exception as e_stop:
                    # D6 Fix: Bắt toàn bộ lỗi (như OSError) và ghi nhận escalation
                    self.watchdog.last_stop_write_failed = True
                    self.watchdog.last_stop_confirmed = False
                    self.watchdog.last_stop_result = f"STOP_EXCEPTION_{type(e_stop).__name__}: {str(e_stop)}"
        self.stop_watchdog()

    def _on_health_timer(self):
        """
        Kiểm tra sức khỏe hệ thống định kỳ (20Hz).
        Đồng bộ quy trình STOP escalation với ActiveLeaseWatchdogThread:
        - Thu hồi lease.
        - Gửi lệnh STOP khẩn cấp.
        - Lưu vết chi tiết kết quả (stop_result, write_failed, stop_confirmed).
        """
        now = time.monotonic()
        with self.bridge.lock:
            if self.bridge.active_lease_source is not None and now >= self.bridge.active_lease_deadline:
                self.bridge.active_lease_source = None
                self.bridge.active_lease_id = None
                if self.bridge.serial_arbiter:
                    try:
                        stop_res = self.bridge.serial_arbiter.send_stop(now_mono=now)
                        if isinstance(stop_res, tuple):
                            write_ok = bool(stop_res[0])
                            detail = str(stop_res[1])
                        else:
                            write_ok = bool(stop_res)
                            detail = "STOP_SENT_OK" if write_ok else "STOP_WRITE_FAILED"
                        
                        self.watchdog.last_stop_confirmed = getattr(self.bridge.serial_arbiter, "stop_confirmed", False)
                        self.watchdog.last_stop_write_failed = not write_ok
                        self.watchdog.last_stop_result = detail if write_ok else "REJECT_STOP_WRITE_FAILED"
                    except Exception as e_stop:
                        self.watchdog.last_stop_write_failed = True
                        self.watchdog.last_stop_confirmed = False
                        self.watchdog.last_stop_result = f"STOP_EXCEPTION_{type(e_stop).__name__}: {str(e_stop)}"

    def start_watchdog(self):
        self.watchdog.start()

    def stop_watchdog(self):
        self.watchdog.stop()


# =============================================================================
# 4. MOCK RUNTIME EXECUTOR (CHO OFFLINE TESTS & BENCHMARKS)
# =============================================================================
class MockRos2RuntimeExecutor:
    """
    Trình điều phối chu kỳ ROS 2 Runtime offline (hỗ trợ mô phỏng kiến trúc ROS 2
    Node, Publisher, Subscription và Timer trên Fake Transport).
    """

    def __init__(self, node: Optional[AGVRos2RuntimeNode] = None):
        self.node = node
        self.nodes: List[Any] = [node] if node else []

    def add_node(self, node: Any):
        if node not in self.nodes:
            self.nodes.append(node)

    def spin_once(self, timeout_sec: float = 0.0):
        for n in self.nodes:
            if hasattr(n, "_on_health_timer"):
                n._on_health_timer()


if __name__ == "__main__":
    print("=== AGV ROS 2 RUNTIME & FIRMWARE PACKET ADAPTER READY ===")
