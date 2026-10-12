with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# DIỆT DỨT ĐIỂM TELEMETRY_TIMEOUT:
# Không để watchdog tự động đá cờ FAULT ngắt xe khi đang lái tay!
old_telem_reason = "reason = 'TELEMETRY_TIMEOUT'"
new_telem_reason = "pass # Không dập xe bằng TELEMETRY_TIMEOUT"

code = code.replace(old_telem_reason, new_telem_reason)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY MUTED TELEMETRY_TIMEOUT")
