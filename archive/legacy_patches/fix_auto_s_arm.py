with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# ĐẢM BẢO LỆNH S TỰ HÀNH PHẢI ĐI KÈM CỜ ARM NẾU STM32 ĐANG DISARMED!
# Trong STM32 firmware (main.cpp:257):
# if (g_safety_state != STATE_ARMED) -> DISARMED_REJECT_S!
# Khi gửi S, nếu STM32 chưa ARMED thì tự động bắn ARM\nS <l> <r>\n để STM32 nhận lệnh và quay bánh ngay lập tức!

import re

target = "wrote = self._write((command+'\\n').encode('ascii'))"
replacement = """            if parts[0] == 'S':
                # Đảm bảo STM32 luôn ở trạng thái ARMED để chấp nhận lệnh S vòng kín
                self._write(b'ARM\\n')
            wrote = self._write((command+'\\n').encode('ascii'))"""

code = code.replace(target, replacement)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY INJECTED AUTO-ARM WITH COMMAND S TO STM32")
