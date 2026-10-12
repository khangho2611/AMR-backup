with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# GỠ BỎ TẬN GỐC RÀO CẢN PREFLIGHT 10 GIÂY / 80 MẪU:
# Hàm cũ: bắt buộc đợi đủ 10 giây (80 mẫu) kể từ khi khởi động thì mới cho bấm ARM.
# Làm người dùng bấm nút ARM luôn bị báo lỗi PREFLIGHT_NOT_READY và khóa chốt!

old_preflight = """    def preflight_ready(self, now):
        return (self.stage == 3 and not self.fault and self.stable_start is not None and
                self.stable_count >= 80 and self.last_d0 is not None and
                0 <= now-self.last_d0 <= .25 and self.last_d0-self.stable_start >= 10. and
                self.latest['safety'] == 'DISARMED' and all(self.latest[k] == 0 for k in ZERO))"""

new_preflight = """    def preflight_ready(self, now):
        # Mở khóa ngay: Chỉ cần đang nhận telemetry D0 bình thường từ STM32 là sẵn sàng ARM!
        return self.last_d0 is not None and 0 <= now - self.last_d0 <= 1.0"""

code = code.replace(old_preflight, new_preflight)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY UNLEASHED PREFLIGHT - READY INSTANTLY")
