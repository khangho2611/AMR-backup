with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. Bỏ blockers cho cả lệnh 'S' (Closed-loop RPM):
old_b = """                blockers = [name for name,blocked in checks if blocked]
                if blockers and parts[0] != 'M':
                    return self._drive_result(command,False,'SESSION_OR_SENSOR_NOT_READY',blockers)"""

new_b = """                blockers = [name for name,blocked in checks if blocked]
                if blockers and parts[0] not in ('M', 'S'):
                    return self._drive_result(command,False,'SESSION_OR_SENSOR_NOT_READY',blockers)"""

code = code.replace(old_b, new_b)

# 2. Xóa chốt latched và tự động ARM cho lệnh S:
old_s_unlatch = """            if parts[0] == 'M':
                with self.lock:
                    self.latched = False
                    self.fault = None
                if not self.armed:
                    self._write(b'ARM\\n')
                    time.sleep(0.02)"""

new_s_unlatch = """            if parts[0] in ('M', 'S'):
                with self.lock:
                    self.latched = False
                    self.fault = None
                if not self.armed:
                    self._write(b'ARM\\n')
                    time.sleep(0.04)"""

code = code.replace(old_s_unlatch, new_s_unlatch)

old_s_cancel = """                    if parts[0] == 'M':
                        self.latched = False
                    if (generation != self.generation or self.latched) and parts[0] != 'M':
                        return self._drive_result(command, False, 'CANCELLED_BY_STOP')"""

new_s_cancel = """                    if parts[0] in ('M', 'S'):
                        self.latched = False
                    if (generation != self.generation or self.latched) and parts[0] not in ('M', 'S'):
                        return self._drive_result(command, False, 'CANCELLED_BY_STOP')"""

code = code.replace(old_s_cancel, new_s_cancel)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("UNLATCHED S PID COMMAND COMPLETELY")
