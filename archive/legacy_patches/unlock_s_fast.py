with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Khi nhận lệnh S tự hành, ghi thẳng xuống Serial tương tự như lệnh M, không để qua writer lock hay blockers checks cũ
old_s_handling = """        if parts[0] == 'M':
            # Đường truyền siêu tốc dành riêng cho lái tay thủ công: Ghi thẳng xuống Serial, độ trễ <1ms
            with self.lock:
                self.latched = False
                self.armed = True
                self.fault = None
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
            wrote = self._write((command+'\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')"""

new_s_handling = """        if parts[0] in ('M', 'S'):
            # Đường truyền siêu tốc dành riêng cho cả M (lái tay) và S (tự hành PID):
            # Không qua hàng đợi writer lock, không bị dính blockers ảo, độ trễ <1ms
            with self.lock:
                self.latched = False
                self.armed = True
                self.fault = None
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
            wrote = self._write((command+'\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')"""

code = code.replace(old_s_handling, new_s_handling)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("UNLOCKED REAL-TIME CLOSED-LOOP PID S COMMAND")
