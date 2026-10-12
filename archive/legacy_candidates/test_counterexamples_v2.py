import sys
import math
from agv_serial_arbiter_bridge_v2 import SerialArbiterGateV2

class MockFaultySerial:
    def __init__(self, raise_write_error=False):
        self.raise_write_error = raise_write_error
        self.written_bytes = []
        self.is_open = True

    def write(self, data: bytes):
        if self.raise_write_error:
            raise OSError("I/O Hardware Bus Failure on /dev/ttyUSB0")
        self.written_bytes.append(data)

    def flush(self):
        if self.raise_write_error:
            raise OSError("I/O Flush Failure")

    def close(self):
        self.is_open = False

def run_counterexample_verification():
    print("=== BẮT ĐẦU KIỂM THỬ KHẮC PHỤC TRIỆT ĐỂ COUNTEREXAMPLES A, B, C, D ===")

    mock_s = MockFaultySerial(raise_write_error=False)
    arb = SerialArbiterGateV2(mock_serial=mock_s)
    arb.connect()

    t0 = 100.0
    line_armed = '{"safety":"ARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}'

    # Nạp telemetry ARMED tươi tại t0
    arb.process_incoming_line(line_armed, t0)
    arb.arm_control_session(token="session_1", now_mono=t0)

    # -------------------------------------------------------------
    # COUNTEREXAMPLE A: NaN và Inf phải bị TỪ CHỐI trước clamp
    # -------------------------------------------------------------
    ok_nan, msg_nan = arb.send_velocity_command(float('nan'), 0.0, t0 + 0.01, token="session_1")
    assert not ok_nan and "REJECT_NON_FINITE" in msg_nan, f"Lỗi A-1: Không từ chối NaN! Msg: {msg_nan}"

    ok_inf, msg_inf = arb.send_velocity_command(float('inf'), 0.0, t0 + 0.01, token="session_1")
    assert not ok_inf and "REJECT_NON_FINITE" in msg_inf, f"Lỗi A-2: Không từ chối Inf! Msg: {msg_inf}"
    print("[PASS A] Counterexample A: NaN và Infinity bị từ chối tuyệt đối (REJECT_NON_FINITE)")

    # -------------------------------------------------------------
    # COUNTEREXAMPLE B: Chống nguồn timestamp âm / tương lai
    # -------------------------------------------------------------
    # Telemetry tại t=100.0, command gửi t=90.0 (age = -10.0s)
    ok_skew, msg_skew = arb.send_velocity_command(0.04, 0.0, t0 - 10.0, token="session_1")
    assert not ok_skew and "REJECT_FUTURE_TIME_SKEW" in msg_skew, f"Lỗi B: Không bắt được timestamp âm! Msg: {msg_skew}"
    print("[PASS B] Counterexample B: Timestamp âm (future time skew) bị từ chối tuyệt đối")

    # -------------------------------------------------------------
    # COUNTEREXAMPLE C: STOP Latch & Token Epoch khóa cứng lệnh tiếp theo
    # -------------------------------------------------------------
    # Gửi lệnh V hợp lệ
    ok_v, msg_v = arb.send_velocity_command(0.04, 0.0, t0 + 0.05, token="session_1")
    assert ok_v, "Lệnh V hợp lệ phải được chấp thuận"

    # Gọi STOP
    arb.send_stop()

    # Thử gửi tiếp lệnh V ngay sau đó khi chưa có phiên ARM mới
    ok_after_stop, msg_after_stop = arb.send_velocity_command(0.04, 0.0, t0 + 0.06, token="session_1")
    assert not ok_after_stop and "REJECT_STOP_LATCHED" in msg_after_stop, f"Lỗi C: Sau STOP vẫn chấp thuận lệnh V! Msg: {msg_after_stop}"
    print("[PASS C] Counterexample C: STOP Latch khóa cứng hoàn toàn gate cho tới khi cấp phiên mới")

    # -------------------------------------------------------------
    # COUNTEREXAMPLE D: Serial.write raise OSError phải chốt FAULT
    # -------------------------------------------------------------
    mock_faulty = MockFaultySerial(raise_write_error=True)
    arb_fault = SerialArbiterGateV2(mock_serial=mock_faulty)
    arb_fault.connect()
    arb_fault.process_incoming_line(line_armed, t0)
    
    # Lúc gửi lệnh ARM, việc write lỗi sẽ lập tức chốt FAULT
    ok_arm, msg_arm = arb_fault.arm_control_session(token="session_fault", now_mono=t0)
    assert not ok_arm and "HARDWARE_WRITE_ERROR" in msg_arm, f"Lỗi D-1: Không báo lỗi write khi ARM! Msg: {msg_arm}"
    assert arb_fault.safety_state == "FAULT", "Lỗi D-2: Không chốt trạng thái sang FAULT sau khi ARM lỗi"

    # Gửi lệnh V sau đó phải bị từ chối vì đang ở trạng thái FAULT
    ok_write_err, msg_write_err = arb_fault.send_velocity_command(0.04, 0.0, t0 + 0.05, token="session_fault")
    assert not ok_write_err and "REJECT_NOT_ARMED" in msg_write_err and "FAULT" in msg_write_err
    print("[PASS D] Counterexample D: Lỗi I/O Serial lập tức chốt FAULT và từ chối xác nhận ảo")

    # -------------------------------------------------------------
    # TỰ ĐỘNG WATCHDOG: Caller im lặng quá 200ms tự phát STOP
    # -------------------------------------------------------------
    mock_s2 = MockFaultySerial(raise_write_error=False)
    arb2 = SerialArbiterGateV2(mock_serial=mock_s2)
    arb2.connect()
    arb2.process_incoming_line(line_armed, t0)
    arb2.arm_control_session(token="session_wd", now_mono=t0)
    arb2.send_velocity_command(0.04, 0.0, t0 + 0.05, token="session_wd")

    # Caller im lặng suốt 300ms (> 200ms)
    stopped = arb2.autonomous_watchdog_tick(t0 + 0.35)
    assert stopped and arb2.stop_latched, "Watchdog không kích hoạt STOP khi caller im lặng"
    assert b"STOP\n" in mock_s2.written_bytes, "Watchdog không gửi b'STOP\\n' xuống Serial"
    print("[PASS E] Autonomous Watchdog: Tự động phát STOP và chốt Stop-Latch khi caller im lặng")

    print("\n=== TOÀN BỘ 5/5 CA KIỂM THỬ KHẮC PHỤC COUNTEREXAMPLES ĐỀU PASS ĐẠT CHUẨN ===")
    return True

if __name__ == "__main__":
    if not run_counterexample_verification():
        sys.exit(1)
