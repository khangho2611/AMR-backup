import unittest
import math

class TestP0SafetyAndFirmwareLogic(unittest.TestCase):
    def test_01_timeout_and_arm_disarm_latch(self):
        """Kiểm tra logic ARM/DISARM latch và Heartbeat Timeout"""
        state = "DISARMED"
        last_cmd_ms = 0
        cmd_timeout_ms = 300

        # Thử nhận lệnh khi DISARMED
        def execute_cmd(cmd_type, now_ms):
            nonlocal state, last_cmd_ms
            if cmd_type == "ARM":
                state = "ARMED"
                last_cmd_ms = now_ms
                return "ACK_ARM"
            elif cmd_type == "STOP" or cmd_type == "DISARM":
                state = "DISARMED"
                return "ACK_DISARM"
            elif cmd_type == "V":
                if state != "ARMED":
                    return "ERROR_DISARMED_REJECT_V"
                last_cmd_ms = now_ms
                return "ACK_V"
            return "UNKNOWN"

        def check_timeout(now_ms):
            nonlocal state
            if state == "ARMED" and (now_ms - last_cmd_ms) > cmd_timeout_ms:
                state = "DISARMED"
                return "TIMEOUT_TRIGGERED_DISARM"
            return "OK"

        # 1. Khi vừa boot: Mặc định DISARMED -> từ chối lệnh V
        self.assertEqual(execute_cmd("V", 100), "ERROR_DISARMED_REJECT_V")
        self.assertEqual(state, "DISARMED")

        # 2. Cấp lệnh ARM
        self.assertEqual(execute_cmd("ARM", 200), "ACK_ARM")
        self.assertEqual(state, "ARMED")

        # 3. Khi ARMED: Lệnh V được chấp nhận
        self.assertEqual(execute_cmd("V", 250), "ACK_V")

        # 4. Quá 300ms không có lệnh mới: Tự động DISARM
        self.assertEqual(check_timeout(600), "TIMEOUT_TRIGGERED_DISARM")
        self.assertEqual(state, "DISARMED")

        # 5. Lệnh V sau khi timeout bị từ chối
        self.assertEqual(execute_cmd("V", 650), "ERROR_DISARMED_REJECT_V")

    def test_02_finite_and_velocity_clamp(self):
        """Kiểm tra bộ lọc finite chặn NaN/Inf và giới hạn cứng vận tốc"""
        def clamp_v_w(v, w):
            if not math.isfinite(v) or not math.isfinite(w):
                return None
            v_clamped = max(-0.15, min(0.15, v))
            w_clamped = max(-0.60, min(0.60, w))
            return v_clamped, w_clamped

        # Chặn NaN và Inf
        self.assertIsNone(clamp_v_w(float('nan'), 0.1))
        self.assertIsNone(clamp_v_w(0.1, float('inf')))

        # Clamp trần an toàn
        v, w = clamp_v_w(1.43, 13.27)
        self.assertAlmostEqual(v, 0.15)
        self.assertAlmostEqual(w, 0.60)

        v, w = clamp_v_w(-0.5, -2.0)
        self.assertAlmostEqual(v, -0.15)
        self.assertAlmostEqual(w, -0.60)

    def test_03_lidar_angle_assignment_fix(self):
        """Kiểm tra sửa lỗi gán nhầm góc +90 độ (phải là LEFT chứ không phải RIGHT)"""
        def get_zone(deg):
            deg = int(deg) % 360
            if deg >= 338 or deg < 23: return "front"
            elif 23 <= deg < 68: return "front_left"   # Đã sửa: Góc dương (ngược chiều kim đồng hồ) là bên TRÁI
            elif 68 <= deg < 113: return "left"        # +90 độ là LEFT
            elif 113 <= deg < 158: return "back_left"
            elif 158 <= deg < 203: return "back"
            elif 203 <= deg < 248: return "back_right"
            elif 248 <= deg < 293: return "right"       # 270 độ (-90 độ) là RIGHT
            else: return "front_right"

        self.assertEqual(get_zone(0), "front")
        self.assertEqual(get_zone(90), "left")      # +90 độ bắt buộc là LEFT
        self.assertEqual(get_zone(180), "back")
        self.assertEqual(get_zone(270), "right")    # 270 độ bắt buộc là RIGHT

    def test_04_odometry_reset_baseline_fix(self):
        """Kiểm tra reset odometry không bị nhảy vọt delta count ở chu kỳ sau"""
        class MockOdom:
            def __init__(self):
                self.prev_l = 1000
                self.prev_r = 1000
                self.x = 5.0
            def reset(self):
                self.prev_l = 0
                self.prev_r = 0
                self.x = 0.0
            def update(self, l_count, r_count):
                dl = l_count - self.prev_l
                dr = r_count - self.prev_r
                self.prev_l = l_count
                self.prev_r = r_count
                return dl, dr

        odom = MockOdom()
        odom.reset()
        # Chu kỳ kế tiếp encoder đọc từ 0 trở đi (ví dụ nhận 5 xung)
        dl, dr = odom.update(5, 5)
        # Nếu không reset prev_count về 0, dl sẽ bị -1000 gây giật vọt lùi!
        self.assertEqual(dl, 5)
        self.assertEqual(dr, 5)

if __name__ == '__main__':
    unittest.main()
