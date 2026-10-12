with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

bad = """                        if parts[0] == 'S':
                # Đảm bảo STM32 luôn ở trạng thái ARMED để chấp nhận lệnh S vòng kín
                self._write(b'ARM\\n')
            wrote = self._write((command+'\\n').encode('ascii'))"""

good = """            if parts[0] == 'S':
                self._write(b'ARM\\n')
            wrote = self._write((command+'\\n').encode('ascii'))"""

code = code.replace(bad, good)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("FIXED INDENTATION IN agv_command_session.py")
