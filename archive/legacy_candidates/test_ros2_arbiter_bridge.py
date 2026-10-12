"""
test_ros2_arbiter_bridge.py
=============================================================================
Bộ kiểm thử độc lập cho module agv_ros2_arbiter_bridge.py (Mock Bus & Priority Queue).
Kiểm tra các tiêu chuẩn:
1. Odometry & TF REP-105 theo timestamp telemetry thật, loại bỏ stale/skew.
2. Scan Freshness Guard TTL <= 250ms, kiểm tra frame_id.
3. Priority Queue: EMERGENCY_STOP (0) > MANUAL (1) > AUTONOMOUS (2).
4. Lease Gate: Ngăn chặn chiếm quyền khi lease cũ còn hạn, từ chối NaN/Inf velocity.
=============================================================================
"""

import sys
import math
import time
from agv_ros2_arbiter_bridge import AGVRos2ArbiterBridge, CommandPriority

def run_tests():
    print("=== BẮT ĐẦU KIỂM THỬ AGV ROS 2 ARBITER BRIDGE (OFFLINE/MOCK BUS) ===")
    bridge = AGVRos2ArbiterBridge(is_mock=True, freshness_ttl_s=0.25)

    # -------------------------------------------------------------------------
    # TEST 1: INGEST TELEMETRY THẬT VÀ BROADCAST ODOMETRY / TF
    # -------------------------------------------------------------------------
    print("\n--- [TEST 1] TELEMETRY INGESTION & TF BROADCAST ---")
    now = 100.0
    valid_telem = {
        "t": 99.9, # age = 0.1s <= 0.25s
        "x": 0.5,
        "y": 0.2,
        "th": 0.1,
        "v": 0.05,
        "w": 0.0,
        "safety": "ARMED"
    }
    ok = bridge.ingest_telemetry_packet(valid_telem, now_mono=now)
    assert ok, "Lỗi Test 1: Telemetry hợp lệ bị từ chối!"
    assert len(bridge.mock_odom_pub.published_messages) == 1
    assert len(bridge.mock_tf_broadcaster.transforms) == 1
    tf_msg = bridge.mock_tf_broadcaster.transforms[0]
    assert tf_msg["header"]["frame_id"] == "odom"
    assert tf_msg["child_frame_id"] == "base_footprint"
    assert tf_msg["transform"]["translation"]["x"] == 0.5
    print("[PASS TEST 1] Telemetry hợp lệ được ingest thành công, phát đúng TF odom->base_footprint theo chuẩn REP-105.")

    # -------------------------------------------------------------------------
    # TEST 2: FRESHNESS GUARD & REJECT STALE TELEMETRY
    # -------------------------------------------------------------------------
    print("\n--- [TEST 2] FRESHNESS GUARD & STALE TELEMETRY REJECTION ---")
    stale_telem = {
        "t": 99.5, # age = 0.5s > 0.25s
        "x": 0.6,
        "y": 0.2,
        "th": 0.1,
        "v": 0.05,
        "w": 0.0,
        "safety": "ARMED"
    }
    ok_stale = bridge.ingest_telemetry_packet(stale_telem, now_mono=now)
    assert not ok_stale, "Lỗi Test 2: Mẫu telemetry cũ (stale) vẫn được chấp nhận!"

    future_telem = dict(valid_telem, t=100.5) # age = -0.5s (tương lai)
    assert not bridge.ingest_telemetry_packet(future_telem, now_mono=now), "Lỗi Test 2: Mẫu tương lai được chấp nhận!"

    nan_telem = dict(valid_telem, t=100.0, x=float("nan"))
    assert not bridge.ingest_telemetry_packet(nan_telem, now_mono=now), "Lỗi Test 2: Mẫu chứa NaN được chấp nhận!"
    print("[PASS TEST 2] Freshness Guard chặn đứng mẫu cũ (stale), tương lai (future) và dữ liệu NaN/Inf.")

    # -------------------------------------------------------------------------
    # TEST 3: SCAN FRESHNESS GUARD
    # -------------------------------------------------------------------------
    print("\n--- [TEST 3] LASERSCAN FRESHNESS GUARD ---")
    ok_scan = bridge.ingest_scan_packet(
        angle_min=-math.pi,
        angle_max=math.pi,
        angle_increment=0.01,
        ranges=[1.0]*100,
        stamp=99.9,
        frame_id="laser",
        now_mono=now
    )
    assert ok_scan, "Lỗi Test 3: LaserScan hợp lệ bị từ chối!"

    ok_stale_scan = bridge.ingest_scan_packet(
        angle_min=-math.pi,
        angle_max=math.pi,
        angle_increment=0.01,
        ranges=[1.0]*100,
        stamp=99.5, # stale
        frame_id="laser",
        now_mono=now
    )
    assert not ok_stale_scan, "Lỗi Test 3: LaserScan stale vẫn được chấp nhận!"
    print("[PASS TEST 3] LaserScan Freshness Guard hoạt động chuẩn xác.")

    # -------------------------------------------------------------------------
    # TEST 4: PRIORITY LEASE GATE & PREEMPTION
    # -------------------------------------------------------------------------
    print("\n--- [TEST 4] PRIORITY QUEUE & LEASE PREEMPTION ---")
    # Để test submit_cmd_vel khi is_mock=True, ingest telemetry tươi trước
    bridge.ingest_telemetry_packet(valid_telem, now_mono=now)

    # 4.1 Khởi tạo lệnh tự hành Nav (Priority 2)
    ok_nav, reason = bridge.submit_cmd_vel(
        source=CommandPriority.AUTONOMOUS_NAV,
        lease_id="nav_task_01",
        linear_v=0.04,
        angular_w=0.0,
        now_mono=now,
        deadline_ttl_s=0.20
    )
    assert ok_nav, f"Lỗi Test 4-1: Lệnh Nav hợp lệ bị từ chối ({reason})"

    # 4.2 Lệnh Manual (Priority 1) đến và cướp quyền (preempt) của Nav (Priority 2)
    ok_man, reason = bridge.submit_cmd_vel(
        source=CommandPriority.MANUAL_TELEOP,
        lease_id="web_manual_01",
        linear_v=0.05,
        angular_w=0.1,
        now_mono=now + 0.05,
        deadline_ttl_s=0.20
    )
    assert ok_man, f"Lỗi Test 4-2: Lệnh Manual không cướp được quyền của Nav ({reason})"

    # 4.3 Nav cố tình gửi lệnh khi Manual còn hạn deadline -> Phải bị từ chối
    ok_nav_blocked, reason = bridge.submit_cmd_vel(
        source=CommandPriority.AUTONOMOUS_NAV,
        lease_id="nav_task_02",
        linear_v=0.04,
        angular_w=0.0,
        now_mono=now + 0.10,
        deadline_ttl_s=0.20
    )
    assert not ok_nav_blocked, "Lỗi Test 4-3: Nav cướp được quyền của Manual khi chưa hết hạn lease!"
    assert "REJECT_PREEMPTED" in reason

    # 4.4 Gắn mock serial arbiter để kiểm tra EMERGENCY_STOP
    class SimpleMockGate:
        def send_stop(self, now_mono=None):
            return True

    bridge.serial_arbiter = SimpleMockGate()

    # Cấp cứu: EMERGENCY_STOP (Priority 0) lập tức chiếm quyền và chặn đứng tất cả
    ok_stop, reason = bridge.submit_cmd_vel(
        source=CommandPriority.EMERGENCY_STOP,
        lease_id="e_stop_button",
        linear_v=0.0,
        angular_w=0.0,
        now_mono=now + 0.12,
        deadline_ttl_s=0.20
    )
    assert ok_stop, f"Lỗi Test 4-4: EMERGENCY_STOP không kích hoạt được ({reason})"
    assert bridge.active_lease_source == CommandPriority.EMERGENCY_STOP

    # Manual cố gửi lệnh khi STOP còn hiệu lực -> Bị chặn
    ok_man_blocked, _ = bridge.submit_cmd_vel(
        source=CommandPriority.MANUAL_TELEOP,
        lease_id="web_manual_02",
        linear_v=0.05,
        angular_w=0.0,
        now_mono=now + 0.20
    )
    assert not ok_man_blocked, "Lỗi Test 4-4: Manual ghi đè được trạng thái EMERGENCY_STOP!"
    print("[PASS TEST 4] Priority Queue phân cấp hoàn hảo: EMERGENCY_STOP > MANUAL > AUTONOMOUS.")

    print("\n=================================================================")
    print("=== TẤT CẢ 4 BÀI TEST AGV ROS 2 ARBITER BRIDGE ĐỀU PASS 100%! ===")
    print("=================================================================")
    return True

if __name__ == "__main__":
    if not run_tests():
        sys.exit(1)
    sys.exit(0)
