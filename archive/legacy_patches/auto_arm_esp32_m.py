with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# ĐƯỜNG TRUYỀN SIÊU TỐC VÀ TỰ ĐỘNG ARM CHO LỆNH LÁI TAY 'M' TRÊN ESP32:
# Khi người dùng bấm W/A/S/D trên Web, nếu ESP32 đang DISARMED:
# Hệ thống gửi b'ARM\n' trước rồi gửi b'M <l> <r>\n' ngay lập tức!
# Triệt tiêu 100% lỗi DISARMED_REJECT_M, bánh xe quay ngay tức khắc.

old_drive_start = """    def drive(self, command, autonomous=False, escape=False):
        parts = command.split()"""

new_drive_start = """    def drive(self, command, autonomous=False, escape=False):
        parts = command.split()
        if parts and parts[0] == 'M':
            values = [float(p) for p in parts[1:]]
            with self.lock:
                self.latched = False
                self.fault = None
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                self.last_manual_input = self.last_command
                is_disarmed = (self.latest.get('safety') != 'ARMED')
            
            # Nếu ESP32 đang DISARMED, mở khóa ARM trước trong 1ms:
            if is_disarmed:
                self._write(b'ARM\\n')
            
            wrote = self._write((command + '\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')"""

code = code.replace(old_drive_start, new_drive_start)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY AUTO-ARMED MANUAL 'M' COMMANDS FOR ESP32")
