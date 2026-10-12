target = '/home/khangho/rplidar_c1_test/bridge/agv_unified_brain.py'
with open(target, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Thêm biến trạng thái continuous_slam_nav
old_init = """        self.auto_mode = False
        self.auto_slam_scan = False
        self.slam_scan_step = 0
        self.slam_scan_timer = 0"""

new_init = """        self.auto_mode = False
        self.auto_slam_scan = False
        self.slam_scan_step = 0
        self.slam_scan_timer = 0
        self.continuous_slam_nav = False
        self.target_heading = 0.0
        self.kp_heading = 1.2
        self.target_speed = 0.22"""

if 'self.continuous_slam_nav = False' not in code:
    code = code.replace(old_init, new_init)

# 2. Cập nhật thuật toán auto_nav_loop: Chạy bình thường (0.22 m/s), bù góc Odometry liên tục, quét map SLAM
old_auto_loop = """        if not auto:
            return

        # VẬT CẢN QUÁ GẦN (< 35cm): DỪNG & LÙI CHẬM
        if f_cm < 35 or fr_cm < 30 or fl_cm < 30:
            self.send_cmd("V -0.06 0.0") # Lùi nhẹ 6cm/s
            time.sleep(0.2)
            if l_cm > r_cm:
                self.send_cmd("V 0.0 0.50") # Xoay trái né
            else:
                self.send_cmd("V 0.0 -0.50") # Xoay phải né
        # VÙNG GIẢM TỐC NÉ THÔNG MINH (35cm - 70cm)
        elif f_cm < 70 or fr_cm < 60 or fl_cm < 60:
            ratio = (f_cm - 35) / 35.0
            v = 0.05 + ratio * 0.05 # Tốc độ bò êm 5 - 10 cm/s
            if l_cm > r_cm:
                w = 0.50 * (1.0 - ratio) # Bẻ lái sang trái
            else:
                w = -0.50 * (1.0 - ratio) # Bẻ lái sang phải
            self.send_cmd(f"V {v:.2f} {w:.2f}")
        # ĐƯỜNG TRỐNG (> 70cm): TIẾN THẲNG CHẬM AN TOÀN
        else:
            w = 0.0
            if l_cm < 35: w = -0.2
            elif r_cm < 35: w = 0.2
            self.send_cmd(f"V 0.10 {w:.2f}")"""

new_auto_loop = """        # CHẾ ĐỘ CHẠY BÌNH THƯỜNG & QUÉT MAP LIÊN TỤC (TỐC ĐỘ 0.22 m/s, BÙ SAI SỐ GÓC THỜI GIAN THỰC)
        with state.lock:
            cont_slam = state.continuous_slam_nav
            cur_th = state.robot_th
            tgt_th = state.target_heading
            kp = state.kp_heading
            base_v = state.target_speed

        if cont_slam or auto:
            # 1. TÌNH HUỐNG NGUY HIỂM: VẬT CẢN TRƯỚC MẶT < 40cm
            if f_cm < 40 or fr_cm < 35 or fl_cm < 35:
                # Phanh và đổi hướng mượt mà
                self.send_cmd("V -0.10 0.0")
                time.sleep(0.15)
                # Chọn bên thoáng hơn và cộng dồn góc mục tiêu
                turn_dir = 1.0 if l_cm > r_cm else -1.0
                with state.lock:
                    state.target_heading = cur_th + turn_dir * 0.785 # Bẻ góc 45 độ
                self.send_cmd(f"V 0.0 {turn_dir * 0.80:.2f}")
                time.sleep(0.2)
            
            # 2. VÙNG ĐIỀU CHỈNH HƯỚNG BÁM ĐƯỜNG (40cm - 80cm)
            elif f_cm < 80 or fr_cm < 65 or fl_cm < 65:
                v = max(0.14, base_v * 0.70) # Chạy đều 15 cm/s
                turn_dir = 1.0 if l_cm > r_cm else -1.0
                ratio = (80 - f_cm) / 40.0
                w = turn_dir * 0.60 * ratio
                with state.lock:
                    state.target_heading = cur_th # Cập nhật mốc góc
                self.send_cmd(f"V {v:.2f} {w:.2f}")

            # 3. ĐƯỜNG THOÁNG (> 80cm): CHẠY TỐC ĐỘ CHUẨN (0.22 m/s) VÀ DÙNG PID BÙ LỆCH GÓC TỰ ĐỘNG
            else:
                # Tính sai lệch góc: error = target - current
                err_th = tgt_th - cur_th
                # Chuẩn hóa góc về [-pi, pi]
                err_th = (err_th + math.pi) % (2 * math.pi) - math.pi
                
                # Bù góc Closed-loop chống lệch Caster: w = Kp * err_th
                w_correction = max(-0.45, min(0.45, kp * err_th))
                
                # Bù lệch vách 2 bên
                if l_cm < 45: w_correction -= 0.15
                elif r_cm < 45: w_correction += 0.15
                
                self.send_cmd(f"V {base_v:.2f} {w_correction:.2f}")
            return"""

if 'cont_slam = state.continuous_slam_nav' not in code:
    code = code.replace(old_auto_loop, new_auto_loop)

# 3. Thêm route /api/continuous_slam
route_cont = """        elif path == '/api/continuous_slam':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            act = params.get('act', [''])[0].upper()
            spd = float(params.get('speed', [0.22])[0])
            with state.lock:
                if act == 'START':
                    state.continuous_slam_nav = True
                    state.auto_mode = True
                    state.target_speed = spd
                    state.target_heading = state.robot_th # Khóa góc hiện tại làm mốc
                else:
                    state.continuous_slam_nav = False
                    state.auto_mode = False
                    if ros_node: ros_node.send_cmd('STOP')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"status":"ok", "continuous_slam": state.continuous_slam_nav}).encode('utf-8'))
            return

        elif path == '/api/slam_auto':"""

if 'elif path == \'/api/continuous_slam\':' not in code:
    code = code.replace("        elif path == '/api/slam_auto':", route_cont)

with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

import py_compile
py_compile.compile(target, doraise=True)
print("SUCCESSFULLY INJECTED CONTINUOUS SLAM & REAL-TIME HEADING CORRECTION!")
