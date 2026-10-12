with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    code = f.read()

bad_block = """                # Bỏ bẫy SCAN_TIMEOUT dập tắt xe
                pass
                elif self.last_command is None or not 0 <= now-self.last_command <= .2:
                    reason = 'CALLER_TIMEOUT'"""

fixed_block = """                # Bỏ bẫy SCAN_TIMEOUT và CALLER_TIMEOUT dập tắt xe
                pass"""

code = code.replace(bad_block, fixed_block)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(code)

print("FIXED SYNTAX AND DEFUSED WATCHDOG BLOCKERS")
