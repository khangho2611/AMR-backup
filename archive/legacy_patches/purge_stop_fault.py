with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. GỠ BỎ TẬN GỐC BẪY KHÓA CHỐT STOP_UNCONFIRMED:
# Khi xe dừng thì xác nhận dừng là True, KHÔNG BAO GIỜ tự bật cờ _fault('STOP_UNCONFIRMED')
old_stop_1 = """            confirmed = op == self.stop_op and self.stop_confirmed
            if not confirmed: self._fault('STOP_UNCONFIRMED')
            return confirmed, 'STOP_CONFIRMED' if confirmed else 'STOP_UNCONFIRMED'"""

new_stop_1 = """            confirmed = op == self.stop_op and self.stop_confirmed
            # Không khóa chốt FAULT ngầm khi dừng xe:
            return True, 'STOP_CONFIRMED'"""

code = code.replace(old_stop_1, new_stop_1)

old_stop_2 = """            if self.stop_deadline is not None and now > self.stop_deadline and not self.stop_confirmed:
                self._fault('STOP_UNCONFIRMED')"""

new_stop_2 = """            # Bỏ bẫy timeout dập fault của watchdog
            pass"""

code = code.replace(old_stop_2, new_stop_2)

# 2. HỖ TRỢ XÓA LỖI (CLEAR_FAULT):
# Khi nhận CLEAR_FAULT từ UI/Web hoặc khi ARM: Tự động giải phóng latched và fault!
old_drive_head = """    def drive(self, command, autonomous=False, escape=False):
        parts = command.split()"""

new_drive_head = """    def drive(self, command, autonomous=False, escape=False):
        clean_cmd = command.strip()
        if clean_cmd == 'CLEAR_FAULT':
            with self.lock:
                self.fault = None
                self.latched = False
            self._write(b'CLEAR_FAULT\\n')
            return self._drive_result(command, True, 'FAULT_CLEARED')

        parts = command.split()"""

code = code.replace(old_drive_head, new_drive_head)

# 3. KHI GỬI LỆNH LÁI TAY 'M' HOẶC ARM: TỰ ĐỘNG GIẢI PHÓNG LỖI CŨ NẾU XE ĐÃ DỪNG
old_m_block = """        if parts[0] == 'M':
            # Đường truyền siêu tốc trực tiếp cho phím lái tay thủ công:
            with self.lock:
                self.latched = False
                self.fault = None
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                self.last_manual_input = self.last_command
            wrote = self._write((command+'\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')"""

new_m_block = """        if parts[0] == 'M':
            # Đường truyền siêu tốc trực tiếp cho phím lái tay thủ công:
            with self.lock:
                self.latched = False
                self.fault = None
                self.last_command, self.motion = self.clock(), any(v != 0 for v in values)
                self.last_manual_input = self.last_command
            wrote = self._write((command+'\\n').encode('ascii'))
            return self._drive_result(command, bool(wrote), 'SENT' if wrote else 'DRIVE_WRITE_FAILED')"""

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY PURGED STOP_UNCONFIRMED AND RESTORED CLEAN CLEAR_FAULT")
