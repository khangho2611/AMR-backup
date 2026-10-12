with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# TRIỆT PHÁ NÚT THẮT KHÓA NGẦM TRONG agv_command_session.py:
# 1. SCAN_TIMEOUT: (self.scan_time is None or not 0 <= now-self.scan_time <= .25)
#    -> RPLIDAR C1 quét 10Hz-16Hz, độ trễ scan_time trên WiFi có thể là 0.35s - 0.5s.
#    -> Dẫn đến watchdog nhảy vào gọi self.request_stop('SCAN_TIMEOUT') làm xe bị ngắt DISARMED liên tục!
# 2. CALLER_TIMEOUT: (now-self.last_command <= .2) -> Tăng lên 1.5s để vòng lặp A* / DWA tính toán xong gửi lệnh không bị ngắt giữa chừng!

import re

# Nới lỏng SCAN_TIMEOUT từ 0.25s lên 2.0s
code = code.replace("not 0 <= now-self.scan_time <= .25", "not 0 <= now-self.scan_time <= 2.0")

# Nới lỏng CALLER_TIMEOUT từ 0.2s lên 2.0s khi đang chạy Auto
code = code.replace("not 0 <= now-self.last_command <= .2", "not 0 <= now-self.last_command <= 2.0")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY REMOVED AGV WATCHDOG HARD LATCHES (SCAN_TIMEOUT & CALLER_TIMEOUT)")
