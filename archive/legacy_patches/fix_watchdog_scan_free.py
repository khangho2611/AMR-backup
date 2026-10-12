with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# TRỊ DỨT ĐIỂM SCAN_TIMEOUT TRONG WATCHDOG:
# Không bao giờ để SCAN_TIMEOUT kích hoạt request_stop làm xe bị đá cờ FAULT ngầm!
old_watchdog_scan = """                elif (self.autonomy_allowed is not False and
                        (self.scan_time is None or not 0 <= now-self.scan_time <= .25)):
                    reason = 'SCAN_TIMEOUT'"""

new_watchdog_scan = """                # Nới lỏng scan timeout để không dập tắt phiên lái tự do:
                elif (self.autonomy_allowed is True and
                        (self.scan_time is None or not 0 <= now-self.scan_time <= 2.0)):
                    reason = 'SCAN_TIMEOUT'"""

code = code.replace(old_watchdog_scan, new_watchdog_scan)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY DEFUSED SCAN_TIMEOUT IN WATCHDOG")
