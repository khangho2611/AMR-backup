with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Khi nhận lệnh M lái tay, giải phóng ngay chốt latched để không bị CANCELLED_BY_STOP
old_chk = """                    if generation != self.generation or self.latched:
                        return self._drive_result(command, False, 'CANCELLED_BY_STOP')"""

new_chk = """                    if parts[0] == 'M':
                        self.latched = False
                    if (generation != self.generation or self.latched) and parts[0] != 'M':
                        return self._drive_result(command, False, 'CANCELLED_BY_STOP')"""

code = code.replace(old_chk, new_chk)

# Cho phép lệnh M tự mở chốt latched ngay từ đầu
old_m_arm = """            if parts[0] == 'M' and not self.armed:
                self._write(b'ARM\\n')
                time.sleep(0.02)"""

new_m_arm = """            if parts[0] == 'M':
                with self.lock:
                    self.latched = False
                    self.fault = None
                if not self.armed:
                    self._write(b'ARM\\n')
                    time.sleep(0.02)"""

code = code.replace(old_m_arm, new_m_arm)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("UNLATCHED MANUAL M DRIVE")
