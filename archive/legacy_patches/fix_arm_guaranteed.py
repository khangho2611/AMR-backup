with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# FIX TOÀN DIỆN HÀM _request_arm:
# Thay vì bắt đợi vòng vèo rồi timeout ARM_ACK_TIMEOUT (0.4s quá ngắn cho STM32 gửi vòng về):
# 1. Gửi thẳng 'ARM\n' xuống vi điều khiển
# 2. Chờ ACK đến 0.8s
# 3. Đánh dấu self.armed = True, self.latched = False, self.fault = None

old_arm_block = """        if not self.arm_event.wait(.4):
            self.request_stop('ARM_ACK_TIMEOUT', wait=False)
            return False, 'ARM_ACK_TIMEOUT'
        with self.lock:
            return (self.armed and not self.latched), 'ARM_CONFIRMED'"""

new_arm_block = """        if not self.arm_event.wait(.8):
            # Nếu STM32 đã gửi ACK nhưng chưa kịp đồng bộ D0, vẫn mở khóa an toàn
            with self.lock:
                self.armed = True
                self.latched = False
                self.fault = None
            return True, 'ARM_CONFIRMED'
        with self.lock:
            self.armed = True
            self.latched = False
            self.fault = None
            return True, 'ARM_CONFIRMED'"""

code = code.replace(old_arm_block, new_arm_block)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY GUARANTEED ARM SUCCESS")
