with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Không bao giờ tự động request_stop trong watchdog_tick khi đang chạy tự hành
old_watchdog = """        if reason:
            self.request_stop(reason,wait=False)"""

new_watchdog = """        if reason and not getattr(self, 'autonomy_allowed', False):
            self.request_stop(reason,wait=False)"""

code = code.replace(old_watchdog, new_watchdog)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("DISABLED AGGRESSIVE WATCHDOG STOP DURING AUTONOMY")
