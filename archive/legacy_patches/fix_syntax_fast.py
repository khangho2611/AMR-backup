with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Sửa lại dòng indent bị lệch trong khối M
bad_m = """                self._write(b'ARM\\n')
                self._write(b'ARM\\n')
            wrote = self._write((command + '\\n').encode('ascii'))"""

clean_m = """                self._write(b'ARM\\n')
                wrote = self._write((command + '\\n').encode('ascii'))"""

if bad_m in code:
    code = code.replace(bad_m, clean_m, 1)

# Đảm bảo lệnh V ở phía dưới cũng tự động kẹp ARM\n trước khi ghi
old_v_write = """            wrote = self._write(payload)"""
new_v_write = """            self._write(b'ARM\\n')
            wrote = self._write(payload)"""

if old_v_write in code:
    code = code.replace(old_v_write, new_v_write, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY FIXED INDENT AND V_WRITE")
