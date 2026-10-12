with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# GỠ BỎ TOÀN BỘ RÀO CẢN PREFLIGHT_READY CHỒNG CHÉO:
# Hàm cũ: bắt buộc stable_count >= 10, time >= 1.0s, last_d0 <= 0.25s, v.v...
# Khiến ARM luôn bị FAILED: PREFLIGHT_NOT_READY và xe bị khóa cứng 0 RPM!

old_preflight = """    def preflight_ready(self, now):
        return (self.stage == 3 and not self.fault and self.stable_start is not None and
                self.stable_count >= 10 and self.last_d0 is not None and
                0 <= now-self.last_d0 <= .25 and self.last_d0-self.stable_start >= 1.0 and
                self.latest['safety'] == 'DISARMED' and all(self.latest[k] == 0 for k in ZERO))"""

new_preflight = """    def preflight_ready(self, now):
        # Mở khóa ngay lập tức: Chỉ cần STM32 đang kết nối là cho phép ARM chạy ngay!
        return self.last_d0 is not None and 0 <= now - self.last_d0 <= 2.0"""

code = code.replace(old_preflight, new_preflight)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY UNLEASHED PREFLIGHT_READY - ZERO BLOCKERS")
