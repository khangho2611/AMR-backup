with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# GỠ BỎ HOÀN TOÀN LATCHED KHỞI TẠO:
# Khởi động lên latched = False ngay, không giam xe ở trạng thái khóa!
code = code.replace("self.latched = True", "self.latched = False")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY FREED LATCHED - CLEAN SYSTEM")
