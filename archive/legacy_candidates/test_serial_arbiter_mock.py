import sys
import time
import json
import math

from agv_serial_arbiter_bridge import SerialArbiterGate

class MockSerial:
    def __init__(self):
        self.written_bytes = []
        self.is_open = True

    def write(self, data: bytes):
        self.written_bytes.append(data)

    def flush(self):
        pass

    def close(self):
        self.is_open = False

def run_arbiter_mock_tests():
    print("=== BẮT ĐẦU KIỂM THỬ TRỌNG TÀI SERIAL ARBITER & SAFETY GATE (MOCK) ===")
    mock_s = MockSerial()
    arbiter = SerialArbiterGate(mock_serial=mock_s)
    arbiter.connect()

    t_now = 100.0

    # Test 1: Khi khởi tạo, trạng thái là DISARMED -> lệnh V phải bị từ chối
    ok, msg = arbiter.send_velocity_command(0.04, 0.0, t_now)
    assert not ok and "REJECTED" in msg, f"Test 1 Thất bại: {msg}"
    print("[PASS 1/5] Lệnh V khi DISARMED bị chặn tuyệt đối")

    # Test 2: Nạp telemetry DISARMED tươi -> cập nhật Odometry
    line_disarmed = '{"safety":"DISARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,"x":0.05,"y":0.0,"th":0.0,"v":0.0,"w":0.0}'
    res = arbiter.process_incoming_line(line_disarmed, t_now)
    assert res is not None, "Test 2 Thất bại: Không parse được telemetry"
    assert arbiter.latest_odom["x"] == 0.05
    print("[PASS 2/5] Telemetry hợp lệ cập nhật Pose thành công")

    # Test 3: Chuyển trạng thái sang ARMED -> Lệnh V được chấp thuận và kẹp giới hạn
    line_armed = '{"safety":"ARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,"x":0.05,"y":0.0,"th":0.0,"v":0.0,"w":0.0}'
    arbiter.process_incoming_line(line_armed, t_now)
    ok, msg = arbiter.send_velocity_command(0.08, 0.50, t_now + 0.05) # Vượt trần 0.05m/s và 0.35rad/s
    assert ok and "0.050 0.350" in msg, f"Test 3 Thất bại: {msg}"
    assert mock_s.written_bytes[-1] == b"V 0.050 0.350\n"
    print("[PASS 3/5] Lệnh V khi ARMED được duyệt và kẹp cứng trong giới hạn an toàn")

    # Test 4: Mất telemetry quá 250ms (TTL Stale) -> Lệnh V bị từ chối và tự động phát STOP
    mock_s.written_bytes.clear()
    ok, msg = arbiter.send_velocity_command(0.03, 0.0, t_now + 0.35) # Cách 350ms > 250ms
    assert not ok and "REJECTED_STALE_TELEMETRY" in msg, f"Test 4 Thất bại: {msg}"
    assert b"STOP\n" in mock_s.written_bytes, "Test 4 Thất bại: Không phát lệnh STOP khi telemetry cũ"
    print("[PASS 4/5] Mất telemetry > 250ms tự động chặn lệnh và phát STOP khẩn cấp")

    # Test 5: Shutdown an toàn -> phát STOP và DISARM
    mock_s.written_bytes.clear()
    arbiter.close()
    assert b"STOP\nDISARM\n" in mock_s.written_bytes
    assert arbiter.safety_state == "DISARMED"
    print("[PASS 5/5] Shutdown giải phóng cổng và đảm bảo gửi STOP + DISARM an toàn")

    print("\n=== TOÀN BỘ 5/5 BÀI TEST SERIAL ARBITER ĐỀU PASS ĐẠT CHUẨN ===")
    return True

if __name__ == "__main__":
    if not run_arbiter_mock_tests():
        sys.exit(1)
