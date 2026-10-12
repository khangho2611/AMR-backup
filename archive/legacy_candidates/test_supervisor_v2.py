import sys
import json
import time

from agv_motor_bench_supervisor_strict_v2 import run_bench_test

class MockSerial:
    def __init__(self, incoming_lines, delay_per_line=0.0):
        self.incoming_lines = [l.encode('utf-8') if isinstance(l, str) else l for l in incoming_lines]
        self.idx = 0
        self.written = []
        self.is_open = True
        self.delay_per_line = delay_per_line
        self.fileno = lambda: 1

    def readline(self):
        if self.delay_per_line > 0:
            time.sleep(self.delay_per_line)
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

print("=== KIỂM THỬ RIGOROUS CHO SUPERVISOR V2 THEO REVIEW STRICT 13:42 ===")

# TEST 1: Vượt quá 10cm -> PHẢI BỊ ĐÁNH DẤU FAIL (Return False)
# Dùng delay_per_line=0.1s cho 32 dòng boot để vượt qua mốc 3.0s boot check
valid_boot_lines = [make_telem("DISARMED")] * 32 
mock_exceed_10cm = MockSerial(
    valid_boot_lines + 
    ['{"ack":"ARM","state":"ARMED"}', make_telem("ARMED", l_tgt=10.0, r_tgt=10.0)] +
    [make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=0.02, y=0.0)] * 5 +
    [make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=0.11, y=0.0)] + # Vượt quá 10cm
    [make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, x=0.11, y=0.0)] * 5,
    delay_per_line=0.1
)
res1 = run_bench_test(ser_instance=mock_exceed_10cm)
assert res1 == False, "Test 1 Thất bại: Vượt 10cm mà vẫn cho PASS!"
print("[PASS 1/4] Vượt quá 10cm kích hoạt ngắt khẩn cấp và trả về FAIL (Return False)")

# TEST 2: Đang RUN mà safety != ARMED (bị rớt DISARMED giữa chừng) -> PHẢI DỪNG & FAIL
mock_safety_drop = MockSerial(
    valid_boot_lines + 
    ['{"ack":"ARM","state":"ARMED"}', make_telem("ARMED")] +
    [make_telem("ARMED", l_rpm=5.0, r_rpm=5.0, x=0.01, y=0.0)] * 3 +
    [make_telem("DISARMED", l_rpm=5.0, r_rpm=5.0, x=0.01, y=0.0)] + # Rớt an toàn
    [make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, x=0.01, y=0.0)] * 5,
    delay_per_line=0.1
)
res2 = run_bench_test(ser_instance=mock_safety_drop)
assert res2 == False, "Test 2 Thất bại: Safety != ARMED trong lúc run mà vẫn PASS!"
print("[PASS 2/4] Safety state bị vi phạm trong lúc run kích hoạt ngắt khẩn cấp và trả về FAIL")

# TEST 3: Sau khi dừng nếu target != 0 (chưa reset) -> PHẢI BỊ TỪ CHỐI PASS
mock_nonzero_target_stop = MockSerial(
    valid_boot_lines + 
    ['{"ack":"ARM","state":"ARMED"}', make_telem("ARMED")] +
    [make_telem("ARMED", l_rpm=5.0, r_rpm=5.0, x=0.02, y=0.0)] * 5 +
    [make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, l_tgt=5.0, r_tgt=5.0)] * 5,
    delay_per_line=0.1
)
res3 = run_bench_test(ser_instance=mock_nonzero_target_stop)
assert res3 == False, "Test 3 Thất bại: Sau khi dừng target != 0 mà vẫn cho PASS!"
print("[PASS 3/4] Sau khi dừng nếu target != 0.0 bị từ chối xác minh dừng an toàn")

# TEST 4: VALID RUN TRONG GIỚI HẠN (Di chuyển hợp lệ < 10cm, hết thời gian 2.0s -> Dừng an toàn) -> RETURN TRUE
mock_valid_run = MockSerial(
    valid_boot_lines + 
    ['{"ack":"ARM","state":"ARMED"}', make_telem("ARMED", l_tgt=10.0, r_tgt=10.0)] +
    [make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=0.03, y=0.0)] * 20 + # Di chuyển 3cm, trong ngưỡng < 10cm
    [make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, l_tgt=0.0, r_tgt=0.0, x=0.03, y=0.0)] * 5,
    delay_per_line=0.1
)
res4 = run_bench_test(ser_instance=mock_valid_run)
assert res4 == True, "Test 4 Thất bại: Luồng hợp lệ chuẩn mực trong giới hạn không PASS!"
print("[PASS 4/4] Luồng hợp lệ chuẩn mực trong giới hạn (<10cm, hết deadline 2s -> Dừng an toàn) PASS 100%")

print("\n=== TOÀN BỘ 4/4 CA KIỂM THỬ STRICT ĐỀU PASS ĐẠT YÊU CẦU CODEX 13:42 ===")
