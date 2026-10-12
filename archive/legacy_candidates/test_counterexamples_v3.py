import sys
import math
import time
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3

class MockSerialDevice:
    def __init__(self, fail_writes=False):
        self.fail_writes = fail_writes
        self.written_bytes = []
        self.is_open = True

    def write(self, data: bytes):
        if self.fail_writes:
            raise OSError("Hardware Bus Error")
        self.written_bytes.append(data)
        return len(data)

    def flush(self):
        pass

    def close(self):
        self.is_open = False

def run_counterexample_v3_tests():
    print("=== BẮT ĐẦU KIỂM THỬ KHẮC PHỤC TRIỆT ĐỂ 9 COUNTEREXAMPLES REVIEW 15:06 & PREFLIGHT/STOP ===")

    mock_s = MockSerialDevice()
    arb = SerialArbiterGateV3(mock_serial=mock_s)
    arb.connect()

    t0 = 1000.0

    # -------------------------------------------------------------
    # CASE 1: Telemetry có ARMED tươi nhưng CHƯA arm_control_session -> Lệnh V BẮT BUỘC BỊ TỪ CHỐI
    # -------------------------------------------------------------
    line_armed_t0 = '{"safety":"ARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}'
    arb.process_incoming_line(line_armed_t0, t0)
    
    # Gửi lệnh V khi chưa hề khởi tạo session
    ok_c1, msg_c1 = arb.send_velocity_command(0.04, 0.0, t0 + 0.05, epoch=1, token="fake_token", command_deadline=t0 + 0.2)
    assert not ok_c1 and "REJECT_NO_ACTIVE_SESSION" in msg_c1, f"Case 1 Thất bại: {msg_c1}"
    print("[PASS 1/9] Case 1: Telemetry ARMED nhưng chưa có phiên active -> Lệnh V bị từ chối tuyệt đối")

    # -------------------------------------------------------------
    # CASE 2: now_mono hoặc deadline là NaN/Inf/Bool -> BẮT BUỘC TỪ CHỐI
    # -------------------------------------------------------------
    ok_c2_nan, msg_c2_nan = arb.send_velocity_command(0.04, 0.0, float('nan'), epoch=1, token="token_1", command_deadline=t0 + 0.2)
    assert not ok_c2_nan and "REJECT_INVALID_CLOCK" in msg_c2_nan, f"Case 2-1 Thất bại: {msg_c2_nan}"

    ok_c2_bool, msg_c2_bool = arb.send_velocity_command(True, 0.0, t0 + 0.05, epoch=1, token="token_1", command_deadline=t0 + 0.2)
    assert not ok_c2_bool and "REJECT_NON_FINITE_VELOCITY" in msg_c2_bool, f"Case 2-2 Thất bại: {msg_c2_bool}"
    print("[PASS 2/9] Case 2: Validate chặt chẽ clock/deadline/velocity: loại trừ tuyệt đối NaN/Inf/Bool")

    # -------------------------------------------------------------
    # CASE 3: arm_control_session khi chưa có boot D0 tươi bị từ chối; không mở gate bằng old ARMED
    # -------------------------------------------------------------
    # Hiện tại arbiter chưa nhận mẫu DISARMED nào (mới chỉ nhận mẫu ARMED ở Case 1) -> ARM phải bị từ chối
    ok_c3_no_d0, msg_c3_no_d0 = arb.arm_control_session(token="token_c3", now_mono=t0 + 0.1)
    assert not ok_c3_no_d0 and "REJECT_PREFLIGHT_NOT_DISARMED" in msg_c3_no_d0, f"Case 3-1 Thất bại: {msg_c3_no_d0}"

    # Cung cấp telemetry DISARMED tươi
    line_disarmed = '{"safety":"DISARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}'
    arb.process_incoming_line(line_disarmed, t0 + 0.2)

    # Gửi yêu cầu ARM hợp lệ
    ok_c3_arm, msg_c3_arm = arb.arm_control_session(token="token_c3", now_mono=t0 + 0.25)
    assert ok_c3_arm, f"Case 3-2 Thất bại: {msg_c3_arm}"
    assert arb.stop_latched == True, "Gate không được phép mở ngay khi vừa gửi write(ARM)"

    # Thử nạp lại mẫu ARMED cũ trước thời điểm ARM (t=1000.0 <= 1000.25)
    arb.process_incoming_line(line_armed_t0, t0 + 0.24)
    assert arb.stop_latched == True, "Old ARMED telemetry không được phép mở gate"

    # Nạp ARM_ACK và Telemetry ARMED mới tươi sau thời điểm gửi ARM (t=1000.30 > 1000.25)
    arb.process_incoming_line('{"ack":"ARM","state":"ARMED"}', t0 + 0.28)
    arb.process_incoming_line(line_armed_t0, t0 + 0.30)
    assert arb.stop_latched == False, "Sau khi có ACK + Telemetry ARMED mới, gate phải được mở"
    print("[PASS 3/9] Case 3: Quy trình ARM bắt buộc DISARMED preflight, không mở gate bằng old ARMED")

    # -------------------------------------------------------------
    # CASE 4: STOP hủy epoch/token; tái sử dụng token cũ bị từ chối
    # -------------------------------------------------------------
    # Gửi lệnh V hợp lệ trong phiên token_c3 (epoch 1)
    ok_v_c4, msg_v_c4 = arb.send_velocity_command(0.04, 0.0, t0 + 0.32, epoch=1, token="token_c3", command_deadline=t0 + 0.5)
    assert ok_v_c4, f"Lệnh V hợp lệ bị từ chối: {msg_v_c4}"

    # Phát STOP
    arb.send_stop()
    assert arb.stop_latched == True
    assert arb.active_token is None

    # Lệnh V với token cũ và epoch cũ bị từ chối
    ok_v_old, msg_v_old = arb.send_velocity_command(0.04, 0.0, t0 + 0.35, epoch=1, token="token_c3", command_deadline=t0 + 0.5)
    assert not ok_v_old, "Lệnh V sau STOP phải bị từ chối"

    # Thử ARM lại nhưng dùng lại token cũ "token_c3"
    arb.process_incoming_line(line_disarmed, t0 + 0.40)
    ok_rearm_reused, msg_rearm_reused = arb.arm_control_session(token="token_c3", now_mono=t0 + 0.45)
    assert not ok_rearm_reused and "REJECT_REUSED_TOKEN" in msg_rearm_reused, f"Case 4-2 Thất bại: {msg_rearm_reused}"
    print("[PASS 4/9] Case 4: STOP hủy token/epoch; cấm tái sử dụng token cũ; epoch/token bắt buộc unique")

    # -------------------------------------------------------------
    # CASE 5: Autonomous Watchdog thread tự động phát STOP khi caller im lặng hoặc mất telemetry
    # -------------------------------------------------------------
    # Khởi tạo phiên mới với token_c5
    ok_arm_c5, msg_arm_c5 = arb.arm_control_session(token="token_c5", now_mono=t0 + 0.50)
    assert ok_arm_c5, f"ARM c5 thất bại: {msg_arm_c5}"
    arb.process_incoming_line('{"ack":"ARM","state":"ARMED"}', t0 + 0.52)
    arb.process_incoming_line(line_armed_t0, t0 + 0.55)
    assert arb.stop_latched == False

    # Giả lập caller gửi 1 lệnh V
    ok_v_c5, _ = arb.send_velocity_command(0.04, 0.0, t0 + 0.56, epoch=2, token="token_c5", command_deadline=t0 + 0.8)
    assert ok_v_c5

    # Chờ watchdog thread tự động phát hiện timeout khi caller im lặng
    # Ta gọi trực tiếp hàm kiểm tra của watchdog với thời gian t0 + 0.80 (> 200ms)
    arb._autonomous_watchdog_tick(t0 + 0.80)
    assert arb.stop_latched == True, "Watchdog không tự động ngắt gate khi caller im lặng"
    assert b"STOP\n" in mock_s.written_bytes
    print("[PASS 5/9] Case 5: Watchdog tự động phát hiện mất heartbeat/telemetry và phát STOP khẩn cấp")
    arb.close()

    # -------------------------------------------------------------
    # CASE 6 (evidence/v3_review_preflight_stop.json): nonzero_D0 bị từ chối
    # -------------------------------------------------------------
    mock_s6 = MockSerialDevice()
    arb6 = SerialArbiterGateV3(mock_serial=mock_s6)
    arb6.connect()
    line_nonzero = '{"safety":"DISARMED","mode":"PID","l_tgt":1.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,"l_pwm":50,"r_pwm":0,"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}'
    arb6.process_incoming_line(line_nonzero, 100.0)
    ok_c6, msg_c6 = arb6.arm_control_session("new_c6", 100.1)
    assert not ok_c6 and "REJECT_PREFLIGHT_NONZERO_D0" in msg_c6, f"Case 6 Thất bại: {msg_c6}"
    assert len(mock_s6.written_bytes) == 0, f"Case 6 Thất bại: Vẫn ghi Serial {mock_s6.written_bytes}"
    arb6.close()
    print("[PASS 6/9] Case 6: Preflight DISARMED phi zero (nonzero_D0) bị từ chối tuyệt đối, không ghi Serial")

    # -------------------------------------------------------------
    # CASE 7 (evidence/v3_review_preflight_stop.json): future_D0 bị từ chối
    # -------------------------------------------------------------
    mock_s7 = MockSerialDevice()
    arb7 = SerialArbiterGateV3(mock_serial=mock_s7)
    arb7.connect()
    line_d_clean = '{"safety":"DISARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}'
    arb7.process_incoming_line(line_d_clean, 200.0) # Timestamp tương lai
    ok_c7, msg_c7 = arb7.arm_control_session("new_c7", 100.0) # now_mono < timestamp telemetry
    assert not ok_c7 and "REJECT_PREFLIGHT_FUTURE_TIME_SKEW" in msg_c7, f"Case 7 Thất bại: {msg_c7}"
    assert len(mock_s7.written_bytes) == 0, f"Case 7 Thất bại: Vẫn ghi Serial {mock_s7.written_bytes}"
    arb7.close()
    print("[PASS 7/9] Case 7: Preflight DISARMED tương lai (future_D0) bị từ chối triệt để, không ghi Serial")

    # -------------------------------------------------------------
    # CASE 8 (evidence/v3_review_preflight_stop.json): invalid_telem_clock bị từ chối
    # -------------------------------------------------------------
    mock_s8 = MockSerialDevice()
    arb8 = SerialArbiterGateV3(mock_serial=mock_s8)
    arb8.connect()
    arb8.process_incoming_line(line_d_clean, float('nan'))
    ok_c8, msg_c8 = arb8.arm_control_session("new_c8", 100.0)
    assert not ok_c8 and "REJECT_NO_FRESH_BOOT_TELEMETRY" in msg_c8, f"Case 8 Thất bại: {msg_c8}"
    assert len(mock_s8.written_bytes) == 0, f"Case 8 Thất bại: Vẫn ghi Serial {mock_s8.written_bytes}"
    arb8.close()
    print("[PASS 8/9] Case 8: Clock telemetry NaN/Inf (invalid_telem_clock) bị lọc sạch, chặn hoàn toàn ARM")

    # -------------------------------------------------------------
    # CASE 9 (evidence/v3_review_preflight_stop.json): STOP_confirmed_with_older_sample
    # -------------------------------------------------------------
    mock_s9 = MockSerialDevice()
    arb9 = SerialArbiterGateV3(mock_serial=mock_s9)
    arb9.connect()
    # Nhận telemetry DISARMED ban đầu
    arb9.process_incoming_line(line_d_clean, 100.0)
    assert arb9.stop_confirmed == True
    # Gửi lệnh STOP tại t=100.5
    arb9.send_stop(now_mono=100.5)
    assert arb9.stop_confirmed == False, "Sau send_stop, stop_confirmed phải là False"
    # Mẫu cũ (t=100.2 <= 100.5) tuyệt đối KHÔNG được phép xác nhận STOP
    arb9.process_incoming_line(line_d_clean, 100.2)
    assert arb9.stop_confirmed == False, "Case 9 Thất bại: Mẫu cũ (t <= t_stop) đã xác nhận STOP sai trái!"
    # Mẫu mới tươi (t=100.6 > 100.5) xác nhận STOP thành công
    arb9.process_incoming_line(line_d_clean, 100.6)
    assert arb9.stop_confirmed == True, "Mẫu tươi sau STOP phải xác nhận stop_confirmed thành công"
    arb9.close()
    print("[PASS 9/9] Case 9: STOP chỉ được xác nhận bằng telemetry tươi sau thời điểm phát lệnh (chống older sample)")

    print("\n=== TOÀN BỘ 9/9 BÀI TEST CHỐNG COUNTEREXAMPLES ĐỀU PASS 100% ===")
    return True

if __name__ == "__main__":
    if not run_counterexample_v3_tests():
        sys.exit(1)
