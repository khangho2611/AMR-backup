with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# 1. Thêm thuộc tính vào AGVSharedState
old_init = "        self.cruise_speed_mps = .20"
new_init = """        self.cruise_speed_mps = .20
        self.auto_target_speed_rpm = 30.0
        self.auto_target_turn_rpm = 22.0"""

if old_init in code and "self.auto_target_speed_rpm" not in code:
    code = code.replace(old_init, new_init, 1)

# 2. Thêm endpoint /api/auto_config vào WebHandler
old_handler = "        elif path == '/api/pid':"
new_handler = """        elif path == '/api/auto_config':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                spd = float(params.get('speed', [30.0])[0])
                trn = float(params.get('turn', [22.0])[0])
                with state.lock:
                    state.auto_target_speed_rpm = spd
                    state.auto_target_turn_rpm = trn
                    # Chu vi bánh xe ~0.23m => v (m/s) = (rpm / 60) * 0.23
                    state.cruise_speed_mps = max(0.04, min(0.35, (spd / 60.0) * 0.23))
                result = {'status': 'OK', 'speed_rpm': spd, 'turn_rpm': trn, 'cruise_mps': state.cruise_speed_mps}
            except Exception as e:
                result = {'status': 'ERROR', 'reason': str(e)}
            self._command_reply(200, result, 'AUTO_CONFIG', params)
            return

        elif path == '/api/pid':"""

if old_handler in code and "'/api/auto_config'" not in code:
    code = code.replace(old_handler, new_handler, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED AUTO_CONFIG ROUTE")
