import sys
import json

from agv_motor_bench_supervisor_strict_v3 import run_bench_test

class VirtualClock:
    def __init__(self):
        self.cur_time = 1000.0

    def time(self):
        return self.cur_time

    def sleep(self, seconds):
        self.cur_time += seconds

class MockSerial:
    def __init__(self, timed_lines, vclock):
        self.timed_lines = timed_lines # List of (timestamp, line_str)
        self.idx = 0
        self.written = []
        self.is_open = True
        self.vclock = vclock
        self.fileno = lambda: 1

    def readline(self):
        now = self.vclock.time()
        while self.idx < len(self.timed_lines):
            item_t, line_str = self.timed_lines[self.idx]
            if now >= item_t:
                self.idx += 1
                return line_str.encode('utf-8')
            else:
                return b""
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

print("=== BẮT ĐẦU KIỂM THỬ RIGOROUS SUPERVISOR V3 THEO ĐỐI SOÁT MSG 732 ===")

# TEST 1: Boot chỉ có 3 mẫu ở 0.1s, 0.2s, 0.3s rồi im lặng đến 5.0s -> PHẢI TỪ CHỐI BOOT (KHÔNG ARM, RETURN FALSE)
vclock1 = VirtualClock()
t0 = vclock1.time()
timed_lines_test1 = [
    (t0 + 0.1, make_telem("DISARMED")),
    (t0 + 0.2, make_telem("DISARMED")),
    (t0 + 0.3, make_telem("DISARMED")),
] # Sau 0.3s im lặng hoàn toàn, không có mẫu nào sau 3.0s!
mock_ser1 = MockSerial(timed_lines_test1, vclock1)
res1 = run_bench_test(ser_instance=mock_ser1, clock_fn=vclock1.time, sleep_fn=vclock1.sleep)
assert res1 == False, "Test 1 Thất bại: Boot chỉ 3 mẫu sớm rồi im lặng mà vẫn pass boot!"
assert not any(b"ARM\n" in w for w in mock_ser1.written), "Test 1 Thất bại: Đã phát lệnh ARM dù boot chưa hợp lệ!"
print("[PASS 1/5] Boot chỉ 3 mẫu sớm (0.1, 0.2, 0.3s) rồi im lặng bị từ chối tuyệt đối (KHÔNG ARM, Return False)")

# TEST 2: Boot có gap > 250ms giữa các mẫu sau 3s làm reset bộ đếm -> PHẢI TỪ CHỐI BOOT
vclock2 = VirtualClock()
t0 = vclock2.time()
timed_lines_test2 = [
    (t0 + 3.1, make_telem("DISARMED")),
    (t0 + 3.2, make_telem("DISARMED")),
    (t0 + 3.6, make_telem("DISARMED")), # Gap 400ms > 250ms -> Bị reset bộ đếm!
    (t0 + 3.7, make_telem("DISARMED")), # Mới được 2 mẫu liên tiếp
]
mock_ser2 = MockSerial(timed_lines_test2, vclock2)
res2 = run_bench_test(ser_instance=mock_ser2, clock_fn=vclock2.time, sleep_fn=vclock2.sleep)
assert res2 == False, "Test 2 Thất bại: Gap > 250ms mà không reset bộ đếm!"
print("[PASS 2/5] Gap > 250ms giữa các mẫu sau 3s được phát hiện và reset bộ đếm chính xác")

# TEST 3: Vượt quá 10cm -> PHẢI KÍCH HOẠT DỪNG KHẨN CẤP VÀ TRẢ VỀ FAIL (Return False)
vclock3 = VirtualClock()
t0 = vclock3.time()
timed_lines_test3 = [
    (t0 + 3.1, make_telem("DISARMED")),
    (t0 + 3.2, make_telem("DISARMED")),
    (t0 + 3.3, make_telem("DISARMED")), # Đủ 3 mẫu tươi sau 3s -> Boot PASS
    (t0 + 3.35, '{"ack":"ARM","state":"ARMED"}'),
    (t0 + 3.36, make_telem("ARMED", l_tgt=10.0, r_tgt=10.0)),
    (t0 + 3.40, make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=0.03, y=0.0)),
    (t0 + 3.48, make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=0.11, y=0.0)), # Vượt quá 10cm!
    (t0 + 3.52, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, x=0.11, y=0.0)),
    (t0 + 3.60, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, x=0.11, y=0.0)),
    (t0 + 3.70, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, x=0.11, y=0.0)),
]
mock_ser3 = MockSerial(timed_lines_test3, vclock3)
res3 = run_bench_test(ser_instance=mock_ser3, clock_fn=vclock3.time, sleep_fn=vclock3.sleep)
assert res3 == False, "Test 3 Thất bại: Vượt quá 10cm mà vẫn cho PASS!"
print("[PASS 3/5] Vượt quá 10cm kích hoạt ngắt khẩn cấp và trả về FAIL (Return False)")

# TEST 4: Sau khi dừng nếu target != 0 (chưa reset sạch) -> PHẢI BỊ TỪ CHỐI PASS
vclock4 = VirtualClock()
t0 = vclock4.time()
timed_lines_test4 = [
    (t0 + 3.1, make_telem("DISARMED")),
    (t0 + 3.2, make_telem("DISARMED")),
    (t0 + 3.3, make_telem("DISARMED")),
    (t0 + 3.35, '{"ack":"ARM","state":"ARMED"}'),
    (t0 + 3.36, make_telem("ARMED", l_tgt=10.0, r_tgt=10.0)),
    (t0 + 3.40, make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=0.03, y=0.0)),
    (t0 + 3.48, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, l_tgt=5.0, r_tgt=5.0)), # Target != 0!
    (t0 + 3.52, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, l_tgt=5.0, r_tgt=5.0)),
    (t0 + 3.60, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, l_tgt=5.0, r_tgt=5.0)),
]
mock_ser4 = MockSerial(timed_lines_test4, vclock4)
res4 = run_bench_test(ser_instance=mock_ser4, clock_fn=vclock4.time, sleep_fn=vclock4.sleep)
assert res4 == False, "Test 4 Thất bại: Target != 0 sau dừng mà vẫn cho PASS!"
print("[PASS 4/5] Target != 0.0 sau khi dừng bị từ chối xác minh dừng an toàn")

# TEST 5: VALID RUN CHUẨN MỰC TRONG GIỚI HẠN (Di chuyển 4cm < 10cm, dừng sạch sẽ RPM=0, Target=0) -> RETURN TRUE
vclock5 = VirtualClock()
t0 = vclock5.time()
timed_lines_test5 = [
    (t0 + 3.1, make_telem("DISARMED")),
    (t0 + 3.2, make_telem("DISARMED")),
    (t0 + 3.3, make_telem("DISARMED")), # Boot verified
    (t0 + 3.35, '{"ack":"ARM","state":"ARMED"}'),
    (t0 + 3.36, make_telem("ARMED", l_tgt=10.0, r_tgt=10.0)), # ARM verified
]
# Phát telemetry liên tục mỗi 100ms (10Hz) trong suốt 2s
for step in range(20):
    t_step = t0 + 3.40 + step * 0.10
    dist = min(0.04, step * 0.003)
    timed_lines_test5.append((t_step, make_telem("ARMED", l_rpm=8.0, r_rpm=8.0, x=dist, y=0.0)))

t_stop = t0 + 5.42
timed_lines_test5.extend([
    (t_stop + 0.05, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, l_tgt=0.0, r_tgt=0.0, x=0.04, y=0.0)),
    (t_stop + 0.15, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, l_tgt=0.0, r_tgt=0.0, x=0.04, y=0.0)),
    (t_stop + 0.25, make_telem("DISARMED", l_rpm=0.0, r_rpm=0.0, l_pwm=0, r_pwm=0, l_tgt=0.0, r_tgt=0.0, x=0.04, y=0.0)),
])
mock_ser5 = MockSerial(timed_lines_test5, vclock5)
res5 = run_bench_test(ser_instance=mock_ser5, clock_fn=vclock5.time, sleep_fn=vclock5.sleep)
assert res5 == True, "Test 5 Thất bại: Luồng hợp lệ chuẩn mực không PASS!"
print("[PASS 5/5] Luồng hợp lệ chuẩn mực trong giới hạn (<10cm, deadline 2s -> Dừng an toàn RPM 0, Target 0) PASS 100%")

print("\n=== TOÀN BỘ 5/5 CA KIỂM THỬ RIGOROUS VỚI VIRTUAL CLOCK ĐỀU PASS ĐẠT CHUẨN CODEX ===")
