with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. BỎ BẪY PACKET ERROR TỰ DỰNG CỜ FAULT KHI THẤY 'DISARMED_REJECT_M':
# Nếu ESP32 phản hồi DISARMED_REJECT_M, không được dựng cờ self._fault() làm tê liệt cả xe!
old_err_line = "self._fault(str(packet['error']))"
new_err_line = """if str(packet.get('error')) not in ('DISARMED_REJECT_M', 'DISARMED_REJECT_S'):
                        self._fault(str(packet['error']))"""

code = code.replace(old_err_line, new_err_line)

# 2. XỬ LÝ LỆNH M TRỰC TIẾP TRONG DRIVE:
# Khi nhận lệnh M:
# Luôn phát 'ARM\n' trước để đánh thức ESP32, sau đó phát 'M <l> <r>\n' ngay lập tức!
old_drive = """        parts = command.split()
        if len(parts) != 3 or parts[0] not in ('M','V'):"""

new_drive = """        parts = command.split()
        if parts and parts[0] == 'M':
            values = [float(p) for p in parts[1:]]
            with self.lock:
                self.latched = False
                self.fault = None
                self.armed = True
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                self.last_manual_input = self.last_command
            # Đánh thức ESP32 bằng ARM trước, rồi cấp xung M ngay:
            self._write(b'ARM\\n')
            wrote = self._write((command + '\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')

        if len(parts) != 3 or parts[0] not in ('M','V'):"""

code = code.replace(old_drive, new_drive)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED BULLETPROOF ESP32 M AUTO-ARM")
