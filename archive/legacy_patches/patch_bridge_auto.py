target = '/home/khangho/rplidar_c1_test/bridge/lidar_bridge_server.py'
with open(target, 'r', encoding='utf-8') as f:
    code = f.read()

# Bổ sung import và biến quản lý avoidance
avoidance_init = """import serial
import subprocess

s_esp32_lock = threading.Lock()
s_esp32_serial = None
s_avoidance_process = None
s_auto_mode = False

def get_esp32_serial():"""

if 's_auto_mode = False' not in code:
    code = code.replace('import serial\n\ns_esp32_lock = threading.Lock()\ns_esp32_serial = None\n\ndef get_esp32_serial():', avoidance_init)

# Thêm route xử lý /api/auto (START / STOP)
route_auto = """        # 0.1 API: Kích hoạt / Tắt chế độ Tự Hành Né Vật Cản
        if path == '/api/auto':
            global s_auto_mode, s_avoidance_process
            import urllib.parse
            params = urllib.parse.parse_qs(query)
            act = params.get('act', [''])[0].upper()
            
            if act == 'START':
                s_auto_mode = True
                if s_avoidance_process is None or s_avoidance_process.poll() is not None:
                    # Chạy script tự hành nền
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

        # 0. API: Điều khiển Robot AGV (Tiến / Lùi / Trái / Phải / Dừng)"""

if 'if path == \'/api/auto\':' not in code:
    code = code.replace("# 0. API: Điều khiển Robot AGV (Tiến / Lùi / Trái / Phải / Dừng)", route_auto)

with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

print("SUCCESSFULLY INTEGRATED /api/auto ROUTE!")
