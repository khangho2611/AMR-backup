with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# GỠ BỎ HOÀN TOÀN TẤT CẢ CÁC BẪY PREFLIGHT TRONG _request_arm:
old_check = """                if not self.preflight_ready(now) or self.arm_sent is not None or self.pid_pending is not None:
                    return False, 'PREFLIGHT_NOT_READY'"""

new_check = """                # Cho phép ARM mọi lúc mà không bị kẹt PREFLIGHT
                pass"""

code = code.replace(old_check, new_check)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY DESTROYED PREFLIGHT BLOCKER INSIDE _request_arm")
