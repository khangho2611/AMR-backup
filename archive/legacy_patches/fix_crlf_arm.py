with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# ĐỒNG BỘ CHUẨN XUỐNG STM32:
# Khi gửi S: Gửi '\r\nARM\r\n' trước để STM32 nhận đủ ký tự xuống dòng và chuyển STATE_ARMED!
# Sau đó gửi 'S <l> <r>\r\n'

old_s = """            if parts[0] == 'S':
                self._write(b'ARM\\n')
            wrote = self._write((command+'\\n').encode('ascii'))"""

new_s = """            if parts[0] in ('S', 'M'):
                self._write(b'\\r\\nARM\\r\\n')
            wrote = self._write((command+'\\r\\n').encode('ascii'))"""

code = code.replace(old_s, new_s)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY SYNCED CRLF ARM PROTOCOL TO STM32")
