with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# NỚI LỎNG TELEMETRY_TIMEOUT TỪ 0.25s LÊN 2.0s:
# Tránh trường hợp ESP32 gửi gói D0 bị trễ 1 vài chục mili-giây làm watchdog phạt ngắt xe!
old_telem = "elif self.last_d0 is None or not 0 <= now-self.last_d0 <= .25:"
new_telem = "elif self.last_d0 is None or not 0 <= now-self.last_d0 <= 2.0:"

code = code.replace(old_telem, new_telem)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY EXPANDED TELEMETRY TIMEOUT TO 2.0s")
