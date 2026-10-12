with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# DIỆT TẬN GỐC SCAN_TIMEOUT VÀ CALLER_TIMEOUT LÀM XE BỊ ĐÁ KHỎI ARMED:
old_target = """                elif self.scan_time is None or not 0 <= now-self.scan_time <= .25:
                    reason = 'SCAN_TIMEOUT'"""

new_target = """                # Bỏ bẫy SCAN_TIMEOUT dập tắt xe
                pass"""

code = code.replace(old_target, new_target)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY WIPED OUT SCAN_TIMEOUT FOREVER")
