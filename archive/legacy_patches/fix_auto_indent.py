with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r', encoding='utf-8') as f:
    code = f.read()

bad_block = """                elif path == '/api/auto_config':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                if 'speed' in params:
                    with state.lock: state.auto_fwd_rpm = float(params['speed'][0])
                if 'turn' in params:
                    with state.lock: state.auto_turn_rpm = float(params['turn'][0])
                self._json(200, {'status': 'OK', 'speed': state.auto_fwd_rpm, 'turn': state.auto_turn_rpm})
            except Exception as e:
                self._json(400, {'status': 'ERROR', 'msg': str(e)})
            return"""

clean_block = """        elif path == '/api/auto_config':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                if 'speed' in params:
                    with state.lock: state.auto_fwd_rpm = float(params['speed'][0])
                if 'turn' in params:
                    with state.lock: state.auto_turn_rpm = float(params['turn'][0])
                self._json(200, {'status': 'OK', 'speed': state.auto_fwd_rpm, 'turn': state.auto_turn_rpm})
            except Exception as e:
                self._json(400, {'status': 'ERROR', 'msg': str(e)})
            return"""

code = code.replace(bad_block, clean_block)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("FIXED INDENTATION SUCCESSFULLY")
