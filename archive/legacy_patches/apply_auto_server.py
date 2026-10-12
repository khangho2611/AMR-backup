target = '/home/khangho/rplidar_c1_test/bridge/lidar_bridge_server.py'
with open(target, 'r', encoding='utf-8') as f:
    code = f.read()

# Chèn s_avoidance_process
if 's_auto_mode' not in code:
    code = code.replace(
        "s_esp32_serial = None",
        "s_esp32_serial = None\ns_avoidance_process = None\ns_auto_mode = False"
    )

route_auto = """        # 0.1 API: Kích hoạt / Tắt chế độ Tự Hành Né Vật Cản
        if path == '/api/auto':
            global s_auto_mode, s_avoidance_process
            import urllib.parse
            import subprocess
            params = urllib.parse.parse_qs(query)
            act = params.get('act', [''])[0].upper()
            
            if act == 'START':
                s_auto_mode = True
                if s_avoidance_process is None or s_avoidance_process.poll() is not None:
                    cmd = ['bash', '-c', 'source /opt/ros/jazzy/setup.bash && python3 /home/khangho/rplidar_c1_test/app/run_avoidance.py']
                    s_avoidance_process = subprocess.Popen(cmd)
                    print('[AUTO] Đã bật chế độ Tự Né Vật Cản Thông Minh!')
            else:
                s_auto_mode = False
                if s_avoidance_process and s_avoidance_process.poll() is None:
                    s_avoidance_process.terminate()
                    s_avoidance_process = None
                send_robot_cmd('STOP')
                print('[AUTO] ĐÃ DỪNG KHẨN CẤP / TẮT TỰ HÀNH!')

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'auto_mode': s_auto_mode}).encode('utf-8'))
            return

        if path == '/api/cmd':"""

if 'if path == \'/api/auto\':' not in code:
    code = code.replace("if path == '/api/cmd':", route_auto)

with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

import py_compile
py_compile.compile(target, doraise=True)
print("SUCCESSFULLY APPLIED /api/auto IN LIDAR_BRIDGE_SERVER.PY!")
