import subprocess

script = r'''
with open('/home/khangho/rplidar_c1_test/bridge/lidar_bridge_server.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Thêm hàm điều khiển serial
serial_def = """import serial

s_esp32_lock = threading.Lock()
s_esp32_serial = None

def get_esp32_serial():
    global s_esp32_serial
    with s_esp32_lock:
        if s_esp32_serial is None:
            try:
                s_esp32_serial = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.1)
                print('[BRIDGE] Đã mở cổng /dev/ttyUSB0 điều khiển xe AGV!')
            except Exception as e:
                print('[BRIDGE] Lỗi mở cổng /dev/ttyUSB0:', e)
                s_esp32_serial = None
        return s_esp32_serial

def send_robot_cmd(cmd_str):
    ser = get_esp32_serial()
    if ser:
        try:
            with s_esp32_lock:
                ser.write((cmd_str.strip() + '\r\n').encode('utf-8'))
                return True
        except Exception as e:
            print('[BRIDGE] Lỗi gửi lệnh xuống robot:', e)
    return False

class BridgeHttpHandler(BaseHTTPRequestHandler):"""

if 'def get_esp32_serial' not in code:
    code = code.replace('class BridgeHttpHandler(BaseHTTPRequestHandler):', serial_def)

# 2. Thêm routing /api/cmd
route_def = """    def do_GET(self):
        parsed = self.path.split('?')
        path = parsed[0]
        query = parsed[1] if len(parsed) > 1 else ''

        if path == '/api/cmd':
            import urllib.parse
            params = urllib.parse.parse_qs(query)
            val = params.get('val', [''])[0]
            ok = send_robot_cmd(val)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok' if ok else 'error', 'cmd': val}).encode('utf-8'))
            return"""

old_do_get = """    def do_GET(self):
        path = self.path.split("?")[0]"""

if 'if path == \'/api/cmd\':' not in code:
    code = code.replace(old_do_get, route_def)

with open('/home/khangho/rplidar_c1_test/bridge/lidar_bridge_server.py', 'w', encoding='utf-8') as f:
    f.write(code)

print('SUCCESSFULLY PATCHED LIDAR_BRIDGE_SERVER.PY WITH /api/cmd!')
'''

with open(r'D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH\patch_server_py.py', 'w', encoding='utf-8') as f:
    f.write(script)
