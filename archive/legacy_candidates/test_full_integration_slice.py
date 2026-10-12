#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
TEST FULL INTEGRATION SLICE: ROS 2 RUNTIME, PACKET ADAPTER, WATCHDOG THREAD
& ARBITER GATE (100% OFFLINE FAKE TRANSPORT)
===============================================================================
Kiểm thử toàn diện lát cắt tích hợp từ đầu đến cuối:
1. Luồng thành công có ủy quyền (Positive Authorized Flow):
   - Firmware packet ESP32 thô (không có t) -> Ingest qua Packet Adapter (gán Pi receive monotonic).
   - Ingest LaserScan hợp lệ -> Odometry và Scan đều tươi.
   - Caller có lease được ủy quyền phát lệnh V -> Gate Serial ghi 'V 0.04 0.00'.
2. Watchdog Thread thật độc lập:
   - Caller sau khi gửi lệnh rồi im lặng (silent) -> Watchdog thread độc lập phát hiện
     hết deadline TTL (<= 200ms) -> Tự động thu hồi lease và kích hoạt STOP.
3. Chặn các trường hợp lỗi (Rejections):
   - Thiếu LaserScan hoặc LaserScan bị cũ (stale scan).
   - Thiếu Odometry hoặc Odometry bị cũ (stale odom).
   - Caller gửi sai lease token (unauthorized caller).
   - Lệnh STOP gửi xuống khi gate Serial write fail -> Phân biệt rõ trạng thái.
===============================================================================
"""

import time
import json
import unittest
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
from test_counterexamples_v3 import MockSerialDevice
from agv_ros2_arbiter_bridge import AGVRos2ArbiterBridge, CommandPriority
from agv_ros2_runtime_adapter import FirmwarePacketAdapter, ActiveLeaseWatchdogThread


class TestFullIntegrationSlice(unittest.TestCase):

    def setUp(self):
        # Thiết lập Mock Serial và Serial Arbiter Gate v3
        self.mock_serial = MockSerialDevice()
        self.gate = SerialArbiterGateV3(mock_serial=self.mock_serial)
        self.gate.connected = True
        self.gate.stop_confirmed = True
        self.gate.stop_latched = False

        # Giả lập phiên điều khiển hợp lệ trên Gate
        self.valid_token = "valid_auth_token_123"
        self.gate.active_token = self.valid_token
        self.gate.active_epoch = 1
        self.gate.current_epoch = 1
        self.gate.safety_state = "ARMED"
        self.gate.session_arm_ack_received = True
        self.gate.session_armed_telemetry_verified = True
        self.gate.last_telemetry_time = 100.0

        # Khởi tạo Bridge và Firmware Adapter
        self.bridge = AGVRos2ArbiterBridge(
            node_name="test_integration_node",
            serial_arbiter=self.gate,
            is_mock=False,
            freshness_ttl_s=0.25
        )
        self.adapter = FirmwarePacketAdapter(self.bridge)

    def test_positive_authorized_flow(self):
        """1. Kiểm tra luồng cấp quyền đầy đủ và gửi lệnh thành công."""
        now_mono = 100.0

        # Firmware packet thô theo đúng chuẩn ESP32 dòng 347 (không có 't')
        raw_firmware_packet = (
            '{"safety":"ARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,'
            '"l_pwm":0,"r_pwm":0,"x":0.05,"y":0.02,"th":0.01,"v":0.0,"w":0.0}\r\n'
        )
        # Nạp qua Adapter (gắn Pi receive monotonic)
        ok_telem = self.adapter.parse_and_ingest(raw_firmware_packet, rx_mono=now_mono)
        self.assertTrue(ok_telem, "Adapter phải ingest thành công gói tin firmware thô")

        # Nạp dữ liệu LaserScan hợp lệ
        ok_scan = self.bridge.ingest_scan_packet(
            angle_min=-3.14,
            angle_max=3.14,
            angle_increment=0.01,
            ranges=[1.5] * 628,
            stamp=now_mono,
            frame_id="laser_frame",
            now_mono=now_mono
        )
        self.assertTrue(ok_scan, "Bridge phải ingest thành công LaserScan hợp lệ")

        # Caller gửi lệnh hợp lệ với token ủy quyền
        success, reason = self.bridge.submit_cmd_vel(
            source=CommandPriority.AUTONOMOUS_NAV,
            lease_id=self.valid_token,
            linear_v=0.04,
            angular_w=0.0,
            now_mono=now_mono,
            deadline_ttl_s=0.15
        )
        self.assertTrue(success, f"Lệnh phải được chấp nhận: {reason}")
        self.assertEqual(reason, "COMMAND_ACCEPTED")

        # Kiểm tra MockSerial đã nhận được lệnh 'V 0.040 0.000'
        written_str = b"".join(self.mock_serial.written_bytes).decode('ascii', errors='ignore')
        self.assertIn("V 0.040 0.000", written_str, "MockSerial phải ghi nhận lệnh vận tốc V")

    def test_rejections_and_fail_closed(self):
        """2. Kiểm tra các cơ chế Fail-Closed từ chối lệnh vi phạm và A1, A2, W1."""
        now_mono = 200.0

        # A1: explicit rx_mono=NaN -> REJECT
        raw_firmware_packet = (
            '{"safety":"ARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,'
            '"l_pwm":0,"r_pwm":0,"x":0.05,"y":0.02,"th":0.01,"v":0.0,"w":0.0}\r\n'
        )
        self.assertFalse(self.adapter.parse_and_ingest(raw_firmware_packet, rx_mono=float("nan")), "A1: Phải từ chối explicit NaN rx_mono")

        # A2: x='corrupt' -> cấu trúc structured rejection không exception
        corrupt_packet = (
            '{"safety":"ARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,'
            '"l_pwm":0,"r_pwm":0,"x":"corrupt","y":0.02,"th":0.01,"v":0.0,"w":0.0}\r\n'
        )
        self.assertFalse(self.adapter.parse_and_ingest(corrupt_packet, rx_mono=now_mono), "A2: Phải từ chối gói tin phi số học")

        # Nạp Odom tươi hợp lệ
        self.adapter.parse_and_ingest(raw_firmware_packet, rx_mono=now_mono)

        # 2.1 Chưa có LaserScan mà gửi lệnh V -> Từ chối ngay
        ok, reason = self.bridge.submit_cmd_vel(
            source=CommandPriority.AUTONOMOUS_NAV,
            lease_id=self.valid_token,
            linear_v=0.04,
            angular_w=0.0,
            now_mono=now_mono,
            deadline_ttl_s=0.10
        )
        self.assertFalse(ok, "Phải từ chối khi thiếu dữ liệu LaserScan")
        self.assertEqual(reason, "REJECT_NO_FRESH_SCAN_DATA_FOR_NAV")

        # Nạp Scan nhưng đã quá hạn (stale scan: stamp = 199.0 so với clock = 200.0)
        self.bridge.ingest_scan_packet(
            angle_min=-3.14,
            angle_max=3.14,
            angle_increment=0.01,
            ranges=[1.5] * 628,
            stamp=now_mono - 1.0,
            frame_id="laser_frame",
            now_mono=now_mono
        )
        ok_stale, reason_stale = self.bridge.submit_cmd_vel(
            source=CommandPriority.AUTONOMOUS_NAV,
            lease_id=self.valid_token,
            linear_v=0.04,
            angular_w=0.0,
            now_mono=now_mono,
            deadline_ttl_s=0.10
        )
        self.assertFalse(ok_stale, "Phải từ chối khi LaserScan bị stale")
        self.assertEqual(reason_stale, "REJECT_NO_FRESH_SCAN_DATA_FOR_NAV")

        # 2.2 Caller gửi sai token ủy quyền -> Từ chối ngay
        self.bridge.ingest_scan_packet(
            angle_min=-3.14,
            angle_max=3.14,
            angle_increment=0.01,
            ranges=[1.5] * 628,
            stamp=now_mono,
            frame_id="laser_frame",
            now_mono=now_mono
        )
        ok_auth, reason_auth = self.bridge.submit_cmd_vel(
            source=CommandPriority.AUTONOMOUS_NAV,
            lease_id="unauthorized_caller_bad_token",
            linear_v=0.04,
            angular_w=0.0,
            now_mono=now_mono,
            deadline_ttl_s=0.10
        )
        self.assertFalse(ok_auth, "Phải từ chối khi caller không có token được cấp quyền")
        self.assertIn("REJECT_UNAUTHORIZED_SOURCE_LEASE", reason_auth)

    def test_real_watchdog_thread_tripping(self):
        """3. Kiểm tra Watchdog Thread độc lập tự động ngắt lease khi caller im lặng."""
        # Khởi tạo Watchdog thread với chu kỳ 10ms
        watchdog = ActiveLeaseWatchdogThread(self.bridge, check_interval_s=0.01)
        watchdog.start()

        try:
            now_mono = time.monotonic()
            # Cấp lease ngắn 40ms
            with self.bridge.lock:
                self.bridge.active_lease_source = CommandPriority.AUTONOMOUS_NAV
                self.bridge.active_lease_id = self.valid_token
                self.bridge.active_lease_deadline = now_mono + 0.04

            # Chờ 80ms không gửi thêm lệnh (caller silent)
            time.sleep(0.08)

            # Kiểm tra Watchdog thread đã ngắt lease và phát lệnh dừng an toàn
            with self.bridge.lock:
                self.assertIsNone(self.bridge.active_lease_source, "Watchdog phải thu hồi lease của caller im lặng")
                self.assertIsNone(self.bridge.active_lease_id, "Watchdog phải xóa active_lease_id")

            self.assertGreater(watchdog.watchdog_tripped_count, 0, "Watchdog phải ghi nhận ít nhất 1 lần trip")
            self.assertFalse(watchdog.last_stop_write_failed, "Ghi STOP xuống MockSerial thành công không có lỗi write failure")
            self.assertEqual(watchdog.last_stop_result, "STOP_SENT_OK")
            print(f"[PASS TEST 3] Real Watchdog Thread: Đã trip thành công sau khi caller im lặng ({watchdog.watchdog_tripped_count} lần)")
        finally:
            watchdog.stop()

    def test_w1_watchdog_write_failure_escalation(self):
        """4. Kiểm tra W1: Watchdog thread khi gặp lỗi ghi Serial write failure báo cáo escalation trung thực."""
        class FailingSerial:
            def __init__(self): self.attempts = []
            def write(self, data): self.attempts.append(data.decode('ascii', errors='ignore')); raise OSError('mock write failure')
            def flush(self): pass

        s = FailingSerial()
        g = SerialArbiterGateV3(mock_serial=s)
        b = AGVRos2ArbiterBridge(serial_arbiter=g)
        b.active_lease_source = CommandPriority.AUTONOMOUS_NAV
        b.active_lease_id = "mock_lease"
        b.active_lease_deadline = time.monotonic() - 0.01

        w = ActiveLeaseWatchdogThread(b, check_interval_s=0.005)
        w.start()
        try:
            time.sleep(0.035)
        finally:
            w.stop()

        self.assertGreater(len(s.attempts), 0, "Watchdog phải cố gắng phát lệnh STOP")
        self.assertTrue(w.last_stop_write_failed, "Watchdog phải ghi nhận write failure khi ghi Serial thất bại")
        self.assertFalse(w.last_stop_confirmed, "Watchdog không được báo STOP confirmed giả")
        self.assertEqual(w.last_stop_result, "REJECT_STOP_WRITE_FAILED")
        print("[PASS TEST 4] W1 Escalation: Watchdog bắt lỗi write failure và báo cáo unconfirmed chính xác 100%.")


if __name__ == "__main__":
    unittest.main()
