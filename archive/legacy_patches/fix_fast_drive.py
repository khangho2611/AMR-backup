with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Khi nhận lệnh M lái tay, KHÔNG CẦN CHỜ KHÓA WRITER .1s VÀ KHÔNG GỌI SLEEP LÃNG PHÍ THỜI GIAN
old_manual_section = """            if parts[0] in ('M', 'S'):
                with self.lock:
                    self.latched = False
                    if self.fault == 'FAULT_ACTIVE_CANNOT_ARM':
                        self.fault = None
                if not self.armed:
                    self._write(b'CLEAR_FAULT\\n')
                    time.sleep(0.02)
                    self._write(b'ARM\\n')
                    time.sleep(0.04)
            wrote = self._write((command+'\\n').encode('ascii'))"""

new_manual_section = """            if parts[0] in ('M', 'S'):
                with self.lock:
                    self.latched = False
                    self.armed = True
                    self.fault = None
            wrote = self._write((command+'\\n').encode('ascii'))"""

code = code.replace(old_manual_section, new_manual_section)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("PURGED BLOCKING SLEEP DELAYS IN DRIVE")
