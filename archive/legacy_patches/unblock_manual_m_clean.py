with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# TÁCH RIÊNG 100% LÁI TAY THỦ CÔNG 'M' (PWM DIRECT):
# Lệnh M được miễn trừ hoàn toàn khỏi bộ lọc blockers (SESSION_OR_SENSOR_NOT_READY, SCAN_STALE, v.v.)
# Xe sẽ tuân lệnh người lái ngay lập tức khi bấm phím W/A/S/D trên Web.

old_block = """        if not self.writer.acquire(timeout=.1):
            self.request_stop('WRITER_BUSY',wait=False)
            return self._drive_result(command, False, 'WRITER_BUSY')"""

new_block = """        if parts[0] == 'M':
            # Đường truyền siêu tốc trực tiếp cho phím lái tay thủ công:
            with self.lock:
                self.latched = False
                self.fault = None
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                self.last_manual_input = self.last_command
            wrote = self._write((command+'\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')

        if not self.writer.acquire(timeout=.1):
            self.request_stop('WRITER_BUSY',wait=False)
            return self._drive_result(command, False, 'WRITER_BUSY')"""

code = code.replace(old_block, new_block)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY UNLEASHED MANUAL DRIVE 'M' - ZERO BLOCKERS")
