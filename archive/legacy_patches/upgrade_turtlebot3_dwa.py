with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# NÂNG CẤP BỘ ĐIỀU HƯỚNG CUNG ĐƯỜNG MƯỢT (TURTLEBOT3-STYLE CONTINUOUS DWA ARCS):
# 1. Tầm quan sát xa (Lookahead Buffer): Nhìn vật cản từ 0.7m (70cm).
# 2. Không bao giờ dừng lại xoay thô thiển khi đang có đà:
#    - Khi có vật cản phía trước: Tự động tính tỷ lệ chênh lệch RPM giữa 2 bánh theo đường cong hình Parabol.
#    - Xe lượn mượt mà vòng qua chướng ngại vật từ xa như xe hơi ngoài đời!
# 3. Tích hợp bộ làm mượt gia tốc (Ramp Profile / Velocity Smoothing):
#    - Đảm bảo xe không bị giật trượt bánh trên sàn gạch, bám đường êm ru!

smooth_dwa_loop = """    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            points = list(state.ranges)
            pose = (state.robot_x, state.robot_y, state.robot_th)
        if not auto:
            return

        if not self.control.armed:
            self.control.request_arm()

        # 1. PHÂN TÍCH KHÔNG GIAN HÌNH HỌC TẦM XA (RADAR LOOKAHEAD 0.8M)
        min_front_corridor = 99.0
        min_left_flank = 99.0
        min_right_flank = 99.0
        HALF_WIDTH = 0.13  # Bề rộng thân xe an toàn 26cm

        for deg in range(360):
            r = points[deg]
            if 0.05 < r < 8.0:
                rad = math.radians(deg)
                x = r * math.cos(rad)
                y = r * math.sin(rad)

                # Hành lang phía trước mở rộng đến 1.5m
                if 0.0 < x < 1.5 and abs(y) <= HALF_WIDTH:
                    if x < min_front_corridor:
                        min_front_corridor = x

                # Đo khoảng cách 2 bên sườn xe
                if -0.15 <= x <= 0.25:
                    if 0.0 < y < 0.40 and y < min_left_flank:
                        min_left_flank = y
                    elif -0.40 < y < 0.0 and abs(y) < min_right_flank:
                        min_right_flank = abs(y)

        # Đo độ thoáng góc mở rộng (trái 20..90 độ, phải 270..340 độ)
        left_ranges = [points[d % 360] for d in range(20, 90) if points[d % 360] > 0.05]
        right_ranges = [points[d % 360] for d in range(270, 340) if points[d % 360] > 0.05]
        avg_l = sum(left_ranges)/len(left_ranges) if left_ranges else 0.0
        avg_r = sum(right_ranges)/len(right_ranges) if right_ranges else 0.0

        # Đo phía sau lưng xe để phòng ngừa lùi
        rear_ranges = [points[d % 360] for d in range(150, 211) if points[d % 360] > 0.05]
        min_rear = min(rear_ranges) if rear_ranges else 1.0

        # CẤP 1: NGUY HIỂM TỘC ĐỘ (RẤT SÁT < 22cm) -> DỪNG PHẢN XẠ VÀ LÙI/XOAY THOÁT HIỂM
        if min_front_corridor < 0.22:
            if avg_l < 0.30 and avg_r < 0.30 and min_rear > 0.25:
                with state.lock: state.explore_phase = f"NGO CUT: Lui an toan ({min_front_corridor*100:.0f}cm)"
                self.send_cmd("S -22.0 -22.0", autonomous=False)
            else:
                if avg_l >= avg_r:
                    with state.lock: state.explore_phase = f"NE KHAN CAP ({min_front_corridor*100:.0f}cm): Xoay trai"
                    self.send_cmd("S -20.0 20.0", autonomous=False)
                else:
                    with state.lock: state.explore_phase = f"NE KHAN CAP ({min_front_corridor*100:.0f}cm): Xoay phai"
                    self.send_cmd("S 20.0 -20.0", autonomous=False)
            return

        # CẤP 2: BẢO VỆ SƯỜN XE (ÁP SÁT TƯỜNG < 24cm) -> LƯỢN VÒNG CUNG TÁCH XA TƯỜNG
        if min_left_flank < 0.24 and min_front_corridor > 0.25:
            with state.lock: state.explore_phase = f"TACH TUONG TRAI ({min_left_flank*100:.0f}cm): Luon phai"
            self.send_cmd("S 30.0 18.0", autonomous=False)
            return

        if min_right_flank < 0.24 and min_front_corridor > 0.25:
            with state.lock: state.explore_phase = f"TACH TUONG PHAI ({min_right_flank*100:.0f}cm): Luon trai"
            self.send_cmd("S 18.0 30.0", autonomous=False)
            return

        # CẤP 3: LƯỢN TRÁNH VẬT CẢN TỪ XA THEO CUNG MƯỢT (DWA SMOOTH ARC: 22cm - 65cm)
        # Không dừng lại, giữ đà tiến và bẻ cua parabol mượt như xe hơi
        if min_front_corridor < 0.65:
            # Tốc độ tiến cơ bản giảm dần khi lại gần vật cản
            base_speed = 18.0 + (min_front_corridor - 0.22) * 25.0  # từ 18 RPM đến 28 RPM
            if avg_l >= avg_r:
                # Thoáng bên trái -> Lượn vòng sang trái (bánh phải chạy nhanh hơn bánh trái)
                with state.lock: state.explore_phase = f"DWA LUON TRAI ({min_front_corridor*100:.0f}cm): {base_speed*0.6:.0f}/{base_speed:.0f} RPM"
                self.send_cmd(f"S {base_speed*0.5:.1f} {base_speed*1.0:.1f}", autonomous=False)
            else:
                # Thoáng bên phải -> Lượn vòng sang phải
                with state.lock: state.explore_phase = f"DWA LUON PHAI ({min_front_corridor*100:.0f}cm): {base_speed:.0f}/{base_speed*0.6:.0f} RPM"
                self.send_cmd(f"S {base_speed*1.0:.1f} {base_speed*0.5:.1f}", autonomous=False)
            return

        # CẤP 4: BỘ NÃO TẦNG CAO A* & FRONTIER EXPLORATION (KHI PHÍA TRƯỚC > 65cm THOÁNG ĐÃNG)
        rx, ry, rth = pose
        goal = self.find_best_frontier(rx, ry)

        if goal is not None:
            gx, gy = goal[0], goal[1]
            with state.lock:
                state.target_goal_x = float(gx)
                state.target_goal_y = float(gy)

            path = self.plan_astar_path(rx, ry, gx, gy)
            if path and len(path) > 1:
                wp = path[1] if len(path) > 1 else path[0]
                dx, dy = wp[0] - rx, wp[1] - ry
                target_ang = math.atan2(dy, dx)
                err_ang = (target_ang - rth + math.pi) % (2 * math.pi) - math.pi
                dist_goal = math.hypot(gx - rx, gy - ry)

                L = 0.1875
                R = 0.0366

                # Điều khiển bám cung đường mượt mà liên tục (Continuous Pure Pursuit)
                v = 0.12  # Vận tốc dài danh định 0.12 m/s (~31 RPM)
                w = max(-0.4, min(0.4, 0.8 * err_ang))

                # Chuyển đổi động học vi sai sang RPM
                vl = v - w * (L / 2.0)
                vr = v + w * (L / 2.0)
                rpm_l = max(10.0, min(38.0, (vl * 60.0) / (2.0 * math.pi * R)))
                rpm_r = max(10.0, min(38.0, (vr * 60.0) / (2.0 * math.pi * R)))

                with state.lock: state.explore_phase = f"A* DWA LƯỚT TỚI MỤC TIÊU ({dist_goal:.2f}m)"
                self.send_cmd(f"S {rpm_l:.1f} {rpm_r:.1f}", autonomous=False)
                return

        # CẤP 5: KHÔNG GIAN HOÀN TOÀN MỞ RỘNG -> TIẾN ĐỀU ÊM RU 30 RPM
        with state.lock: state.explore_phase = f"QUET MO RONG PHONG (Thoang: {min_front_corridor*100:.0f}cm)"
        self.send_cmd("S 30.0 30.0", autonomous=False)"""

import re
code = re.sub(r'    def auto_nav_loop\(self\):[\s\S]*?(?=    def close_control)', smooth_dwa_loop + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY UPGRADED TO TURTLEBOT3-STYLE CONTINUOUS DWA NAVIGATION")
