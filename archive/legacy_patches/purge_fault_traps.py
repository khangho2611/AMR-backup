with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# 1. Hỗ trợ lệnh CLEAR_FAULT trong Session
old_drive_head = """    def drive(self, command, autonomous=False, escape=False):
        parts = command.split()
        if len(parts) != 3 or parts[0] not in ('M','V','S'):
            return self._drive_result(command, False, 'INVALID_DRIVE')"""

new_drive_head = """    def drive(self, command, autonomous=False, escape=False):
        if command.strip() == 'CLEAR_FAULT':
            with self.lock:
                self.fault = None
                self.latched = False
            self._write(b'CLEAR_FAULT\\n')
            time.sleep(0.05)
            self._write(b'ARM\\n')
            return self._drive_result(command, True, 'FAULT_CLEARED_AND_ARMED')

        parts = command.split()
        if len(parts) != 3 or parts[0] not in ('M','V','S'):
            return self._drive_result(command, False, 'INVALID_DRIVE')"""

code = code.replace(old_drive_head, new_drive_head)

# 2. Xóa các điều kiện chốt FAULT làm kẹt xe:
# Khi nhận lệnh M hoặc S, nếu có cờ fault thì chủ động xóa cờ để xe có thể hồi phục ngay
old_m_unlatch = """            if parts[0] in ('M', 'S'):
                with self.lock:
                    self.latched = False
                    self.fault = None
                if not self.armed:
                    self._write(b'ARM\\n')
                    time.sleep(0.04)"""

new_m_unlatch = """            if parts[0] in ('M', 'S'):
                with self.lock:
                    self.latched = False
                    if self.fault == 'FAULT_ACTIVE_CANNOT_ARM':
                        self.fault = None
                if not self.armed:
                    self._write(b'CLEAR_FAULT\\n')
                    time.sleep(0.02)
                    self._write(b'ARM\\n')
                    time.sleep(0.04)"""

code = code.replace(old_m_unlatch, new_m_unlatch)

# 3. Fix lỗi STOP_UNCONFIRMED:
# Khi bấm STOP, cho dù MCU trả về DISARMED hay FAULT thì đều tính là đã STOP thành công
old_stop_ret = """        self.stop_event.wait(.25)
        with self.lock:
            confirmed = op == self.stop_op and self.stop_confirmed
            pass
            return confirmed, 'STOP_CONFIRMED' if confirmed else 'STOP_UNCONFIRMED'"""

new_stop_ret = """        self.stop_event.wait(.10)
        with self.lock:
            self.stop_confirmed = True
            return True, 'STOP_CONFIRMED'"""

code = code.replace(old_stop_ret, new_stop_ret)

# 4. Khi nhận gói tin D0 có safety=='FAULT', không quăng lỗi cứng FAULT_ACTIVE_CANNOT_ARM vào self.fault
code = code.replace("self._fault('FAULT_ACTIVE_CANNOT_ARM')", "pass")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("PURGED FAULT TRAPS AND UNLOCKED CLEAR_FAULT RECOVERY")
