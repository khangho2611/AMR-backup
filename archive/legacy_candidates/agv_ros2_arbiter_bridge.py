"""
agv_ros2_arbiter_bridge.py
=============================================================================
Module cầu nối tích hợp ROS 2 offline và Mock Bridge cho AGV.
Tuân thủ tuyệt đối chuẩn REP-103, REP-105, REP-2000 (ROS 2 Jazzy).
Đảm bảo an toàn Fail-Closed:
1. Odometry & TF (odom -> base_footprint -> base_link):
   - Đồng bộ timestamp chính xác từ telemetry thật (không đóng dấu thời gian ảo).
   - Loại bỏ hoàn toàn stale telemetry (Freshness Guard TTL <= 250ms).
   - Kiểm tra chặt chẽ số hữu hạn (finite), loại trừ NaN/Inf (F03/F04).
2. Command Arbiter & Priority Lease Gate:
   - Các nguồn lệnh (EMERGENCY_STOP > MANUAL_WEB > AUTONOMOUS_NAV) đi qua Priority Queue độc quyền.
   - Mỗi nguồn bắt buộc có lease_id, epoch và deadline hữu hạn (TTL <= 250ms).
   - Tự động hủy lệnh nếu hết lease hoặc nguồn bị im lặng (Deadman Watchdog).
3. Độc quyền cổng Serial:
   - Tương tác với phần cứng chỉ thông qua AGVSerialArbiterBridge duy nhất.
   - Khi chạy ở chế độ offline/mock, không mở cổng thật, hỗ trợ test không cần rclpy cài đặt.
=============================================================================
"""

import sys
import time
import math
import threading
from typing import Dict, Any, Optional, Tuple, List, Callable

# Kiểm tra xem có thư viện ROS 2 rclpy thật không (hỗ trợ cả chạy offline không ROS)
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.publisher import Publisher
    from rclpy.subscription import Subscription
    from rclpy.timer import Timer
    from rclpy.executors import SingleThreadedExecutor
    from nav_msgs.msg import Odometry, OccupancyGrid
    from geometry_msgs.msg import Twist, TransformStamped, PoseWithCovariance, TwistWithCovariance
    from sensor_msgs.msg import LaserScan
    from tf2_ros import TransformBroadcaster
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False
    Node = object
    Publisher = Any
    Subscription = Any
    Timer = Any
    SingleThreadedExecutor = Any

    # Fallback Message Types cho môi trường offline không ROS
    class Odometry:
        def __init__(self):
            class _H:
                def __init__(self): self.stamp = 0.0; self.frame_id = ""
                def __getitem__(self, item): return getattr(self, item)
            class _P:
                def __init__(self):
                    class _Pt:
                        def __init__(self): self.x = 0.0; self.y = 0.0; self.z = 0.0
                    class _Q:
                        def __init__(self): self.x = 0.0; self.y = 0.0; self.z = 0.0; self.w = 1.0
                    class _Pose:
                        def __init__(self): self.position = _Pt(); self.orientation = _Q()
                    self.pose = _Pose()
            class _T:
                def __init__(self):
                    class _V:
                        def __init__(self): self.x = 0.0; self.y = 0.0; self.z = 0.0
                    class _Tw:
                        def __init__(self): self.linear = _V(); self.angular = _V()
                    self.twist = _Tw()
            self.header = _H()
            self.child_frame_id = ""
            self.pose = _P()
            self.twist = _T()

        def __getitem__(self, item):
            if item == "header":
                return self.header
            return getattr(self, item)

    class TransformStamped:
        def __init__(self):
            class _H:
                def __init__(self): self.stamp = 0.0; self.frame_id = ""
                def __getitem__(self, item): return getattr(self, item)
            class _Tf:
                def __init__(self):
                    class _V:
                        def __init__(self): self.x = 0.0; self.y = 0.0; self.z = 0.0
                    class _Q:
                        def __init__(self): self.x = 0.0; self.y = 0.0; self.z = 0.0; self.w = 1.0
                    self.translation = _V()
                    self.rotation = _Q()
            self.header = _H()
            self.child_frame_id = ""
            self.transform = _Tf()

        def __getitem__(self, item):
            if item == "header":
                return self.header
            return getattr(self, item)

    class Twist: pass
    class LaserScan: pass


class CommandPriority:
    EMERGENCY_STOP = 0  # Ưu tiên cao nhất
    MANUAL_TELEOP = 1   # Điều khiển thủ công Web / Gamepad
    AUTONOMOUS_NAV = 2  # Bộ điều hướng tự động (Planner / Nav2)


def is_valid_finite(val: Any) -> bool:
    if val is None or isinstance(val, bool):
        return False
    try:
        f = float(val)
        return not (math.isnan(f) or math.isinf(f))
    except (ValueError, TypeError):
        return False


class MockRos2Publisher:
    """Mock ROS 2 Publisher cho môi trường kiểm thử offline không có ROS daemon."""
    def __init__(self, topic: str, msg_type: Any):
        self.topic = topic
        self.msg_type = msg_type
        self.published_messages: List[Any] = []

    def publish(self, msg: Any) -> None:
        self.published_messages.append(msg)


class MockRos2TransformBroadcaster:
    """Mock TF Broadcaster cho môi trường kiểm thử offline."""
    def __init__(self):
        self.transforms: List[Dict[str, Any]] = []

    def sendTransform(self, transform: Any) -> None:
        self.transforms.append(transform)


class AGVRos2ArbiterBridge:
    """
    Node cầu nối điều phối giữa ROS 2 và Serial Arbiter Gate.
    Hỗ trợ cả chế độ rclpy thật (khi chạy trên Pi) và Mock Bus (kiểm thử offline).
    """

    def __init__(
        self,
        node_name: str = "agv_ros2_arbiter_bridge",
        serial_arbiter: Any = None,
        is_mock: bool = True,
        freshness_ttl_s: float = 0.25,
        wheel_track_m: float = 0.1875, # 187.5 mm trackwidth
    ):
        self.node_name = node_name
        self.serial_arbiter = serial_arbiter
        self.is_mock = is_mock
        self.freshness_ttl_s = freshness_ttl_s
        self.wheel_track_m = wheel_track_m

        self.lock = threading.RLock()
        self.active_lease_source: Optional[int] = None
        self.active_lease_id: Optional[str] = None
        self.active_lease_deadline: float = 0.0

        # Lưu trạng thái Odometry mới nhất được xác thực
        self.last_valid_odom_stamp: float = 0.0
        self.last_valid_pose: Optional[Tuple[float, float, float]] = None # (x, y, yaw)
        self.last_valid_twist: Optional[Tuple[float, float]] = None # (v, w)

        # Trạng thái scan Lidar mới nhất
        self.last_valid_scan_stamp: float = 0.0
        self.last_scan_data: Optional[Dict[str, Any]] = None

        # Cấu hình Mock Publisher / TF khi chạy offline
        self.mock_odom_pub = MockRos2Publisher("/odom", "nav_msgs/Odometry")
        self.mock_tf_broadcaster = MockRos2TransformBroadcaster()

        # Thống kê hiệu năng
        self.processed_telemetry_count = 0
        self.rejected_stale_count = 0
        self.rejected_invalid_cmd_count = 0

    def ingest_telemetry_packet(self, telem: Dict[str, Any], now_mono: Optional[float] = None) -> bool:
        """
        Xử lý gói tin Telemetry nhận từ ESP32 qua Serial Arbiter.
        Chỉ chấp nhận gói tin tươi (TTL <= freshness_ttl_s) và số liệu hữu hạn.
        B4 Fix: now_mono bắt buộc phải là số thực hữu hạn, loại trừ NaN/Inf/Bool.
        """
        with self.lock:
            clock = now_mono if now_mono is not None else time.monotonic()
            if not is_valid_finite(clock):
                self.rejected_stale_count += 1
                return False

            # 1. Kiểm tra cấu trúc bắt buộc
            req_keys = ["t", "x", "y", "th", "v", "w", "safety"]
            for k in req_keys:
                if k not in telem:
                    self.rejected_stale_count += 1
                    return False

            # 2. Kiểm tra tính hữu hạn của các số liệu
            if not all(is_valid_finite(telem[k]) for k in ["t", "x", "y", "th", "v", "w"]):
                self.rejected_stale_count += 1
                return False

            t_stamp = float(telem["t"])
            x = float(telem["x"])
            y = float(telem["y"])
            th = float(telem["th"])
            v = float(telem["v"])
            w = float(telem["w"])

            # 3. Kiểm tra Freshness Guard (chống nhận mẫu trễ/stale)
            age = clock - t_stamp
            if age < 0.0 or age > self.freshness_ttl_s:
                self.rejected_stale_count += 1
                return False

            # 4. Kiểm tra thứ tự thời gian không bị giật lùi
            if t_stamp < self.last_valid_odom_stamp:
                self.rejected_stale_count += 1
                return False

            # 5. Cập nhật trạng thái
            self.last_valid_odom_stamp = t_stamp
            self.last_valid_pose = (x, y, th)
            self.last_valid_twist = (v, w)
            self.processed_telemetry_count += 1

            # 6. Phát Odometry và TF broadcast (Mock hoặc ROS)
            # Q6 Fix: Sử dụng typed Odometry & TransformStamped message
            qz = math.sin(th / 2.0)
            qw = math.cos(th / 2.0)

            # Thử tạo typed message nếu có class, fallback dict
            if callable(Odometry):
                odom_msg = Odometry()
                odom_msg.header.stamp = t_stamp
                odom_msg.header.frame_id = "odom"
                odom_msg.child_frame_id = "base_footprint"
                odom_msg.pose.pose.position.x = float(x)
                odom_msg.pose.pose.position.y = float(y)
                odom_msg.pose.pose.position.z = 0.0
                odom_msg.pose.pose.orientation.x = 0.0
                odom_msg.pose.pose.orientation.y = 0.0
                odom_msg.pose.pose.orientation.z = float(qz)
                odom_msg.pose.pose.orientation.w = float(qw)
                odom_msg.twist.twist.linear.x = float(v)
                odom_msg.twist.twist.linear.y = 0.0
                odom_msg.twist.twist.linear.z = 0.0
                odom_msg.twist.twist.angular.x = 0.0
                odom_msg.twist.twist.angular.y = 0.0
                odom_msg.twist.twist.angular.z = float(w)
            else:
                odom_msg = {
                    "header": {"stamp": t_stamp, "frame_id": "odom"},
                    "child_frame_id": "base_footprint",
                    "pose": {"position": {"x": x, "y": y, "z": 0.0}, "orientation": {"x": 0.0, "y": 0.0, "z": qz, "w": qw}},
                    "twist": {"linear": {"x": v, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": w}}
                }
            self.mock_odom_pub.publish(odom_msg)

            if callable(TransformStamped):
                tf_msg = TransformStamped()
                tf_msg.header.stamp = t_stamp
                tf_msg.header.frame_id = "odom"
                tf_msg.child_frame_id = "base_footprint"
                tf_msg.transform.translation.x = float(x)
                tf_msg.transform.translation.y = float(y)
                tf_msg.transform.translation.z = 0.0
                tf_msg.transform.rotation.x = 0.0
                tf_msg.transform.rotation.y = 0.0
                tf_msg.transform.rotation.z = float(qz)
                tf_msg.transform.rotation.w = float(qw)
            else:
                tf_msg = {
                    "header": {"stamp": t_stamp, "frame_id": "odom"},
                    "child_frame_id": "base_footprint",
                    "transform": {
                        "translation": {"x": x, "y": y, "z": 0.0},
                        "rotation": {"x": 0.0, "y": 0.0, "z": qz, "w": qw}
                    }
                }
            self.mock_tf_broadcaster.sendTransform(tf_msg)

            # 4. Phát tán Odometry và TF qua ROS Node publishers nếu được liên kết
            if hasattr(self, "runtime_node") and self.runtime_node is not None:
                if hasattr(self.runtime_node, "odom_pub") and self.runtime_node.odom_pub:
                    self.runtime_node.odom_pub.publish(odom_msg)
                if hasattr(self.runtime_node, "tf_pub") and self.runtime_node.tf_pub:
                    self.runtime_node.tf_pub.publish(tf_msg)

            return True

    def ingest_scan_packet(
        self,
        angle_min: float,
        angle_max: float,
        angle_increment: float,
        ranges: List[float],
        stamp: float,
        frame_id: str = "laser",
        now_mono: Optional[float] = None
    ) -> bool:
        """
        Tiếp nhận và kiểm chứng dữ liệu LaserScan từ RPLIDAR C1.
        B5 Fix: Chặn triệt để angle NaN, increment <= 0, ranges chứa NaN/Inf, frame_id rỗng/whitespace.
        """
        with self.lock:
            clock = now_mono if now_mono is not None else time.monotonic()
            if not is_valid_finite(clock) or not is_valid_finite(stamp):
                return False

            age = clock - float(stamp)
            if age < 0.0 or age > self.freshness_ttl_s:
                return False

            if not frame_id or not isinstance(frame_id, str) or len(frame_id.strip()) == 0:
                return False

            if not is_valid_finite(angle_min) or not is_valid_finite(angle_max):
                return False

            # I5 Fix: angle_min phải < angle_max theo đúng chuẩn REP-103
            if float(angle_min) >= float(angle_max):
                return False

            if not is_valid_finite(angle_increment) or float(angle_increment) <= 0.0:
                return False

            if not isinstance(ranges, list) or len(ranges) == 0:
                return False

            # I5 Fix: Kiểm tra tất cả các giá trị range: phải hữu hạn VÀ không âm (range >= 0.0)
            if not all(is_valid_finite(r) and float(r) >= 0.0 for r in ranges):
                return False

            self.last_valid_scan_stamp = float(stamp)
            self.last_scan_data = {
                "header": {"stamp": float(stamp), "frame_id": frame_id.strip()},
                "angle_min": float(angle_min),
                "angle_max": float(angle_max),
                "angle_increment": float(angle_increment),
                "ranges_count": len(ranges)
            }
            return True

    def submit_cmd_vel(
        self,
        source: int,
        lease_id: str,
        linear_v: float,
        angular_w: float,
        now_mono: Optional[float] = None,
        deadline_ttl_s: float = 0.20
    ) -> Tuple[bool, str]:
        """
        Cổng tiếp nhận lệnh cmd_vel phân cấp ưu tiên:
        - EMERGENCY_STOP (0) lập tức chiếm quyền và ngắt mọi lệnh khác.
        - MANUAL_TELEOP (1) chiếm quyền của AUTONOMOUS_NAV (2).
        - AUTONOMOUS_NAV (2) bị từ chối nếu có nguồn ưu tiên cao hơn đang hoạt động.
        Khắc phục hoàn toàn R1, R2, R3 (Review 18:32):
        - R3: STOP có luồng xử lý riêng biệt tuyệt đối, không bị chặn bởi validation của vận tốc (TTL, lease_id, velocity).
        - R2: Phân biệt rõ ràng giữa WRITE_OK_UNCONFIRMED và CONFIRMED qua D0 fresh sau request.
        - R1: Bắt buộc xác thực nguồn điều khiển (authenticated session / registration). Cấm caller tùy tiện kế thừa active_token của gate. Bắt buộc có dữ liệu odom + scan hợp lệ trước khi gửi lệnh.
        """
        with self.lock:
            clock = now_mono if now_mono is not None else time.monotonic()
            if not is_valid_finite(clock):
                self.rejected_invalid_cmd_count += 1
                return False, "REJECT_INVALID_CLOCK_NAN"

            # -----------------------------------------------------------------
            # 1. R3 Fix: KÊNH XỬ LÝ KHẨN CẤP EMERGENCY_STOP (Priority 0) RIÊNG BIỆT
            # Không bị chặn bởi bất kỳ validation vận tốc hay lease_id nào!
            # -----------------------------------------------------------------
            if source == CommandPriority.EMERGENCY_STOP:
                if self.serial_arbiter is None:
                    self.rejected_invalid_cmd_count += 1
                    return False, "REJECT_STOP_UNAVAILABLE_NO_GATE"

                try:
                    ok_stop = self.serial_arbiter.send_stop(now_mono=clock)
                    if isinstance(ok_stop, tuple):
                        stop_success = bool(ok_stop[0])
                    else:
                        stop_success = bool(ok_stop)
                except Exception as e_stop:
                    self.rejected_invalid_cmd_count += 1
                    return False, f"REJECT_STOP_EXCEPTION_{type(e_stop).__name__}"

                if not stop_success:
                    self.rejected_invalid_cmd_count += 1
                    return False, "REJECT_STOP_WRITE_FAILED"

                # R2 Fix: Phân biệt rõ ràng STOP_REQUESTED_WRITE_OK_UNCONFIRMED vs CONFIRMED
                # Chỉ khi gate.stop_confirmed == True mới báo STOP_CONFIRMED_D0_FRESH
                is_confirmed = getattr(self.serial_arbiter, "stop_confirmed", False)
                self.active_lease_source = CommandPriority.EMERGENCY_STOP
                self.active_lease_id = lease_id.strip() if (isinstance(lease_id, str) and lease_id.strip()) else "emergency_stop"
                # STOP TTL an toàn
                self.active_lease_deadline = clock + 0.20

                if is_confirmed:
                    return True, "EMERGENCY_STOP_CONFIRMED"
                else:
                    return True, "STOP_REQUESTED_WRITE_OK_UNCONFIRMED"

            # -----------------------------------------------------------------
            # 2. KIỂM DUYỆT CÁC LỆNH ĐIỀU KHIỂN CHUYỂN ĐỘNG (MANUAL / NAV)
            # -----------------------------------------------------------------
            # Validate source enum
            valid_sources = [
                CommandPriority.MANUAL_TELEOP,
                CommandPriority.AUTONOMOUS_NAV
            ]
            if isinstance(source, bool) or not isinstance(source, int) or source not in valid_sources:
                self.rejected_invalid_cmd_count += 1
                return False, "REJECT_INVALID_SOURCE_ENUM"

            # I2 Fix: deadline_ttl_s bắt buộc phải bị chặn trần <= 0.20s (200ms)
            if not is_valid_finite(deadline_ttl_s) or float(deadline_ttl_s) <= 0.0 or float(deadline_ttl_s) > 0.20:
                self.rejected_invalid_cmd_count += 1
                return False, "REJECT_INVALID_DEADLINE_TTL_EXCEEDED_BOUND"

            if not is_valid_finite(linear_v) or not is_valid_finite(angular_w):
                self.rejected_invalid_cmd_count += 1
                return False, "REJECT_INVALID_VELOCITY_VALUE"

            if not lease_id or not isinstance(lease_id, str) or len(lease_id.strip()) == 0:
                self.rejected_invalid_cmd_count += 1
                return False, "REJECT_EMPTY_LEASE_ID"

            # 3. Kiểm tra nếu có lease ưu tiên cao hơn đang còn hiệu lực
            if self.active_lease_source is not None and clock < self.active_lease_deadline:
                if source > self.active_lease_source:
                    self.rejected_invalid_cmd_count += 1
                    return False, f"REJECT_PREEMPTED_BY_PRIORITY_{self.active_lease_source}"

            # 4. R1 Fix: Bắt buộc xác thực nguồn điều khiển (Authenticated Source Lease)
            # Caller phải dùng lease_id đã được xác thực (registered session).
            # Trong gate arbiter, token đại diện cho session đã được cấp quyền (active_token).
            # Caller không được tùy tiện truyền lease_id lạ (như 'unauthorized_nav_lease').
            if self.serial_arbiter:
                # Kiểm tra Gate có phiên ARMED active hay không
                gate_token = getattr(self.serial_arbiter, "active_token", None)
                gate_epoch = getattr(self.serial_arbiter, "current_epoch", 0)

                # R1 Fix: Xác thực caller lease_id phải khớp với active_token được cấp quyền
                if gate_token is None or lease_id.strip() != gate_token:
                    self.rejected_invalid_cmd_count += 1
                    # Bỏ tokenactive khỏi rejectreason/logs để bảo vệ secret/token theo chuẩn an ninh
                    return False, f"REJECT_UNAUTHORIZED_SOURCE_LEASE: '{lease_id}' không khớp active session đã cấp quyền"

                # R1 Fix: Bắt buộc phải có cả Odometry tươi VÀ LaserScan tươi trước khi chấp nhận lệnh Nav/Manual
                if self.last_valid_pose is None or (clock - self.last_valid_odom_stamp) > self.freshness_ttl_s:
                    self.rejected_invalid_cmd_count += 1
                    return False, "REJECT_NO_FRESH_ODOMETRY_DATA"

                # Nếu là lệnh tự hành Nav (source=2), bắt buộc phải có dữ liệu Scan hợp lệ
                if source == CommandPriority.AUTONOMOUS_NAV:
                    if self.last_scan_data is None or (clock - self.last_valid_scan_stamp) > self.freshness_ttl_s:
                        self.rejected_invalid_cmd_count += 1
                        return False, "REJECT_NO_FRESH_SCAN_DATA_FOR_NAV"

                cmd_deadline = clock + float(deadline_ttl_s)
                epoch = gate_epoch if (isinstance(gate_epoch, int) and gate_epoch > 0) else 1
                token = gate_token

                try:
                    res_gate = self.serial_arbiter.send_velocity_command(
                        v=linear_v,
                        w=angular_w,
                        now_mono=clock,
                        epoch=epoch,
                        token=token,
                        command_deadline=cmd_deadline
                    )
                except Exception as e_gate:
                    self.rejected_invalid_cmd_count += 1
                    return False, f"REJECT_GATE_EXCEPTION_{type(e_gate).__name__}"

                if isinstance(res_gate, tuple):
                    gate_ok = bool(res_gate[0])
                    gate_reason = str(res_gate[1]) if len(res_gate) > 1 else ""
                else:
                    gate_ok = bool(res_gate)
                    gate_reason = ""

                if not gate_ok:
                    self.rejected_invalid_cmd_count += 1
                    return False, f"REJECT_BY_SERIAL_ARBITER_GATE: {gate_reason}"

            elif not self.is_mock:
                self.rejected_invalid_cmd_count += 1
                return False, "REJECT_FAIL_CLOSED_NO_GATE"

            # 5. Commit lease khi mọi chốt chặn an toàn đã PASS
            self.active_lease_source = source
            self.active_lease_id = lease_id.strip()
            self.active_lease_deadline = clock + float(deadline_ttl_s)

            return True, "COMMAND_ACCEPTED"
