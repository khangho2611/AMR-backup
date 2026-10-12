import sys
import json
import io

from agv_motor_bench_supervisor_strict import run_bench_test, parse_valid_telemetry

class MockSerial:
    def __init__(self, incoming_lines):
        self.incoming_lines = [l.encode('utf-8') if isinstance(l, str) else l for l in incoming_lines]
        self.idx = 0
        self.written = []
        self.is_open = True
        self.fileno = lambda: 1

    def readline(self):
        if self.idx < len(self.incoming_lines):
            line = self.incoming_lines[self.idx]
            self.idx += 1
            return line
        return b""

    def write(self, data):
        self.written.append(data)

    def flush(self):
        pass

    def close(self):
        self.is_open = False

def make_telem(safety="DISARMED", l_tgt=0.0, r_tgt=0.0, l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, x=0.0, y=0.0, th=0.0):
    return json.dumps({
        "mode": "PID",
        "safety": safety,
        "l_tgt": l_tgt, "r_tgt": r_tgt,
        "l_rpm": l_rpm, "r_rpm": r_rpm,
        "l_pwm": l_pwm, "r_pwm": r_pwm,
        "v": 0.0, "w": 0.0,
        "x": x, "y": y, "th": th
    })

print("=== BẮT ĐẦU KIỂM THỬ TRỰC TIẾP HÀM run_bench_test() QUA CÁC CA BIÊN AN TOÀN ===")

# TEST 1: Boot thiếu safety / Chỉ có ACK -> PHẢI TỪ CHỐI BOOT (Return False)
mock_boot_fail = MockSerial([
    '{"mode":"PID"}',
    '{"ack":"V"}',
    '{"info":"hello"}'
])
res1 = run_bench_test(ser_instance=mock_boot_fail)
assert res1 == False, "Test 1 Thất bại: Supervisor chấp nhận boot thiếu safety!"
print("[PASS 1/6] Boot thiếu trường safety hoặc chỉ có ACK bị từ chối tuyệt đối (Return False)")

# TEST 2: Boot có NaN hoặc Infinity trong Telemetry -> PHẢI TỪ CHỐI BOOT (Return False)
mock_nan = MockSerial([
    '{"safety":"DISARMED","l_tgt":"NaN","r_tgt":0.0,"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}'
])
res2 = run_bench_test(ser_instance=mock_nan)
assert res2 == False, "Test 2 Thất bại: Chấp nhận số thực NaN!"
print("[PASS 2/6] Telemetry chứa NaN / Inf bị loại bỏ, không chấp nhận boot")

# TEST 3: Boot DISARMED hợp lệ, nhưng ARM bị từ chối (Chỉ có ACK ARM, không có Telemetry ARMED) -> PHẢI DỪNG & FAIL
valid_boot_lines = [make_telem("DISARMED")] * 4
mock_arm_fail = MockSerial(valid_boot_lines + [
    '{"ack":"ARM","state":"ARMED"}',
    make_telem("DISARMED") # Vẫn DISARMED, không chuyển ARMED
])
res3 = run_bench_test(ser_instance=mock_arm_fail)
assert res3 == False, "Test 3 Thất bại: ARM thiếu Telemetry ARMED mà vẫn cho chạy!"
print("[PASS 3/6] ARM thiếu Telemetry xác nhận ARMED bị từ chối phát lệnh V")

# TEST 4: Đang chạy mà mất Telemetry (>250ms timeout) -> PHẢI KÍCH HOẠT DỪNG KHẨN CẤP & FAIL
mock_lost_telem = MockSerial(valid_boot_lines + [
    '{"ack":"ARM","state":"ARMED"}',
    make_telem("ARMED")
] + ['{"ack":"V"}'] * 10) # Chỉ gửi ACK, không gửi Telemetry -> Freshness timeout
res4 = run_bench_test(ser_instance=mock_lost_telem)
assert res4 == False, "Test 4 Thất bại: Mất telemetry không kích hoạt ngắt an toàn!"
assert any(b"STOP\n" in w for w in mock_lost_telem.written), "Chưa phát lệnh STOP khi timeout!"
print("[PASS 4/6] Mất Telemetry (>250ms) kích hoạt ngay lệnh STOP và trả về False")

# TEST 5: Sau khi STOP chỉ nhận ACK STOP mà RPM chưa về 0 hoặc thiếu Telemetry -> KHÔNG CHO PASS
mock_stop_ack_only = MockSerial(valid_boot_lines + [
    '{"ack":"ARM","state":"ARMED"}',
    make_telem("ARMED")
] + [make_telem("ARMED", l_rpm=5.0, r_rpm=5.0)] * 5 + [
    '{"ack":"STOP"}',
    '{"ack":"DISARM"}'
])
res5 = run_bench_test(ser_instance=mock_stop_ack_only)
assert res5 == False, "Test 5 Thất bại: Chỉ có ACK STOP thiếu RPM=0 mà vẫn cho PASS!"
print("[PASS 5/6] Sau khi dừng nếu chỉ có ACK STOP mà thiếu Telemetry RPM=0 thì không công nhận PASS")

# TEST 6: CASE HỢP LỆ HOÀN HẢO (Valid Run) -> Đạt max displacement an toàn rồi dừng sạch sẽ -> RETURN TRUE
mock_valid_run = MockSerial(
    valid_boot_lines + 
    ['{"ack":"ARM","state":"ARMED"}', make_telem("ARMED", l_tgt=10.0, r_tgt=10.0)] +
    [make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=0.02, y=0.0)] * 5 +
    [make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=0.11, y=0.0)] + # Kích hoạt dừng an toàn EXCEEDED_MAX_DISPLACEMENT
    [make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, x=0.11, y=0.0)] * 5
)
res6 = run_bench_test(ser_instance=mock_valid_run)
assert res6 == True, "Test 6 Thất bại: Luồng hợp lệ chuẩn mực không PASS!"
print("[PASS 6/6] Luồng hợp lệ chuẩn mực (Boot DISARMED -> ARM xác nhận -> Chạy kiểm soát -> Dừng an toàn khi đủ quãng đường -> RPM về 0) PASS 100%")

print("\n=== TOÀN BỘ 6/6 CA KIỂM THỬ TRỰC TIẾP HÀM SUPERVISOR ĐỀU PASS ĐẠT CHUẨN AN TOÀN ===")
