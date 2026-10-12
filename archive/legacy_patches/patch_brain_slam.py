target = '/home/khangho/rplidar_c1_test/bridge/agv_unified_brain.py'
with open(target, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Thêm trạng thái auto_slam_scan
if 'self.auto_slam_scan = False' not in code:
    code = code.replace(
        "self.auto_mode = False",
        "self.auto_mode = False\n        self.auto_slam_scan = False\n        self.slam_scan_step = 0\n        self.slam_scan_timer = 0"
    )

# 2. Xử lý logic Auto SLAM 360 Spin trong auto_nav_loop
slam_logic = """    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            auto_slam = state.auto_slam_scan
            f_cm = state.zones["front"]
            fr_cm = state.zones["front_right"]
            fl_cm = state.zones["front_left"]
            l_cm = state.zones["left"]
            r_cm = state.zones["right"]

        # CHẾ ĐỘ QUÉT MAP SLAM 360 TỰ ĐỘNG
        if auto_slam:
            with state.lock:
                state.slam_scan_timer += 0.10
                t = state.slam_scan_timer
            
            # Xoay tại chỗ 360 độ cực chậm (0.35 rad/s) trong 18 giây để Ceres Solver tối ưu bản đồ hoàn hảo
            if t <= 18.0:
                self.send_cmd("V 0.0 0.35")
            else:
                # Sau khi quay xong 360 độ: Tự động phanh dừng và hoàn tất
                with state.lock:
                    state.auto_slam_scan = False
                    state.slam_scan_timer = 0
                self.send_cmd("STOP")
            return

        if not auto:
            return"""

if 'if auto_slam:' not in code:
    code = code.replace("    def auto_nav_loop(self):\n        with state.lock:\n            auto = state.auto_mode\n            f_cm = state.zones[\"front\"]", slam_logic)

# 3. Thêm API /api/slam_auto
api_slam = """        elif path == '/api/slam_auto':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            act = params.get('act', [''])[0].upper()
            with state.lock:
                if act == 'START':
                    state.auto_slam_scan = True
                    state.slam_scan_timer = 0
                    state.auto_mode = False
                else:
                    state.auto_slam_scan = False
                    state.slam_scan_timer = 0
                    if ros_node: ros_node.send_cmd('STOP')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"status":"ok", "auto_slam": state.auto_slam_scan}).encode('utf-8'))
            return

        elif path == '/api/cmd':"""

if 'elif path == \'/api/slam_auto\':' not in code:
    code = code.replace("        elif path == '/api/cmd':", api_slam)

with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

import py_compile
py_compile.compile(target, doraise=True)
print("SUCCESSFULLY INJECTED AUTO SLAM 360 SPIN LOGIC!")
