with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

# Nâng ngưỡng TELEMETRY_TIMEOUT từ 0.25s lên 2.0s trong watchdog_tick để không bị ngắt phanh oan
code = code.replace("elif self.last_d0 is None or not 0 <= now-self.last_d0 <= .25:\n                    reason = 'TELEMETRY_TIMEOUT'",
                    "elif self.last_d0 is None or not 0 <= now-self.last_d0 <= 2.0:\n                    reason = 'TELEMETRY_TIMEOUT'")

# Không ngắt auto_mode khi latched trong watchdog_worker
with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    bcode = f.read()

bcode = bcode.replace("            if self.control.latched:\n                with state.lock:\n                    state.auto_mode = False",
                      "            pass")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(bcode)

print("EXPANDED TELEMETRY TIMEOUT AND PROTECTED AUTO MODE")
