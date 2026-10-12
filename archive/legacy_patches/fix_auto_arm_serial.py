with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Khi nhận DISARMED_REJECT_M hoặc DISARMED_REJECT_V, vi điều khiển báo chưa ARM -> Gửi ARM ngay lập tức, không được set FAULT!
old_rej = """                elif packet.get('error') == 'DISARMED_REJECT_V':
                    self.armed = False
                    self._write(b'ARM\\n')"""

new_rej = """                elif packet.get('error') in ('DISARMED_REJECT_V', 'DISARMED_REJECT_M'):
                    self.armed = False
                    self._write(b'ARM\\n')"""

code = code.replace(old_rej, new_rej)

# Quan trọng nhất: Ở hàm drive(), nếu lệnh là 'M' mà MCU chưa ARMED, ghi luôn chuỗi b'ARM\\n' trước khi ghi lệnh M!
old_write = """            wrote = self._write((command+'\\n').encode('ascii'))"""
new_write = """            if parts[0] == 'M' and not self.armed:
                self._write(b'ARM\\n')
                time.sleep(0.02)
            wrote = self._write((command+'\\n').encode('ascii'))"""

code = code.replace(old_write, new_write)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("AUTO-ARM EMBEDDED DIRECTLY INTO SERIAL PROTOCOL FOR MANUAL DRIVE")
