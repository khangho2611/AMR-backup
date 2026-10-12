with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# CẬP NHẬT CHÍNH XÁC KÍCH THƯỚC KHUNG XE THỰC TẾ:
# Chiều dài: 260 mm (0.260 m) -> Nửa chiều dài x = +-0.130 m (đệm 3cm = +-0.160 m)
# Chiều rộng: 207 mm (0.207 m) -> Nửa chiều rộng y = +-0.1035 m (đệm 3cm = +-0.1335 m)
# Bán kính bao góc thực tế: sqrt(0.13^2 + 0.1035^2) + 0.03m đệm = 0.196 m (~0.20 m)

real_chassis_nav = """    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            points = list(state.ranges)
            pose = (state.robot_x, state.robot_y, state.robot_th)
            l_rpm = state.left_rpm
            r_rpm = state.right_rpm
            l_pwm = state.left_pwm
            r_pwm = state.right_pwm
        if not auto:
            return

        if not self.control.armed:
            self.control.request_arm()

        now = time.monotonic()
        rx, ry, rth = pose

        # KHỞI TẠO BIẾN GIÁM SÁT MẮC KẸT NẾU CHƯA CÓ
        if not hasattr(self, '_stall_counter'): self._stall_counter = 0
        if not hasattr(self, '_recovering'): self._recovering = 0  # 0: bình thường, >0: đang lùi thoát
        if not hasattr(self, '_blocked_spots'): self._blocked_spots = []  # danh sách điểm chết (x, y, expire_time)

        # -------------------------------------------------------------
        # HẠNG MỤC 1: HÌNH HỌC KHUNG XE THẬT 260 x 207 mm
        # -------------------------------------------------------------
        # Nửa chiều dài và nửa chiều rộng kèm đệm an toàn 3cm
        HALF_LEN = 0.160   # 130mm + 30mm buffer
        HALF_WID = 0.135   # 103.5mm + 30mm buffer

        min_front_dist = 99.0
        min_rear_dist = 99.0
        min_left_dist = 99.0
        min_right_dist = 99.0

        for deg in range(360):
            r = points[deg]
            if 0.05 < r < 8.0:
                rad = math.radians(deg)
                x = r * math.cos(rad)
                y = r * math.sin(rad)

                # Phía trước trong hành lang thân xe
                if x > 0.0 and abs(y) <= HALF_WID:
                    if x < min_front_dist: min_front_dist = x

                # Phía sau trong hành lang thân xe
                if x < 0.0 and abs(y) <= HALF_WID:
                    dist_b = abs(x)
                    if dist_b < min_rear_dist: min_rear_dist = dist_b

                # Hai cạnh hông xe (-HALF_LEN <= x <= HALF_LEN)
                if -HALF_LEN <= x <= HALF_LEN:
                    if y > 0.0 and y < min_left_dist: min_left_dist = y
                    elif y < 0.0 and abs(y) < min_right_dist: min_right_dist = abs(y)

        # -------------------------------------------------------------
        # HẠNG MỤC 2 & 3: NHẬN DIỆN MẮC KẸT THỰC TẾ & THOÁT KẸT CÓ TRÌNH TỰ
        # -------------------------------------------------------------
        # Điều kiện kẹt: PWM tăng cao (>150) nhưng bánh không lăn được (<3 RPM)
        is_stalled = (abs(l_pwm) > 150 or abs(r_pwm) > 150) and (abs(l_rpm) < 3.0 and abs(r_rpm) < 3.0)
        
        if is_stalled:
            self._stall_counter += 1
        else:
            self._stall_counter = max(0, self._stall_counter - 1)

        # Đang trong chu kỳ lùi thoát hiểm (Back-up Maneuver)
        if self._recovering > 0:
            self._recovering -= 1
            if min_rear_dist > 0.20:
                with state.lock: state.explore_phase = f"DANG LUI THOAT KET KHUNG ({self._recovering})"
                self.send_cmd("S -22.0 -22.0", autonomous=False)
            else:
                # Phía sau chạm tường -> Dừng lùi và xoay sang bên thoáng
                self._recovering = 0
                turn_dir = 25.0 if min_left_dist >= min_right_dist else -25.0
                with state.lock: state.explore_phase = "LUI GAP TUONG: Xoay dau doi huong"
                self.send_cmd(f"S {-turn_dir:.1f} {turn_dir:.1f}", autonomous=False)
            return

        # Xác nhận kẹt liên tục 8 nhịp (~0.8s) -> KÍCH HOẠT QUY TRÌNH THOÁT KẸT
        if self._stall_counter >= 8:
            self._stall_counter = 0
            # Ghi nhớ tọa độ kẹt vào danh sách điểm chết trong 60 giây (Chống lặp vòng)
            self._blocked_spots.append((rx, ry, now + 60.0))
            self._blocked_spots = [b for b in self._blocked_spots if b[2] > now]

            # BƯỚC THOÁT HIỂM 1: Lập tức bỏ động tác đang thất bại, LÙI THẲNG 15-20cm nếu sau thoáng
            if min_rear_dist > 0.20:
                self._recovering = 15  # Lùi liên tục trong 1.5 giây
                with state.lock: state.explore_phase = "PHAT HIEN KET KHUNG: Bat dau lui rut khoi vat can"
                self.send_cmd("S -22.0 -22.0", autonomous=False)
                return
            else:
                # Không lùi được -> Xoay dứt khoát sang bên thoáng nhất
                turn_dir = 25.0 if min_left_dist >= min_right_dist else -25.0
                with state.lock: state.explore_phase = "KET KHUNG & BICH SAU: Xoay doi huong"
                self.send_cmd(f"S {-turn_dir:.1f} {turn_dir:.1f}", autonomous=False)
                return

        # -------------------------------------------------------------
        # HẠNG MỤC 4: NÉ VA CHẠM TOÀN BỘ 4 GÓC VÀ 2 CẠNH KHUNG XE
        # -------------------------------------------------------------
        # CẠNH TRÁI ÁP SÁT (< HALF_WID = 13.5cm) -> Lượn sang phải tách xa tường
        if min_left_dist < HALF_WID and min_front_dist > 0.25:
            with state.lock: state.explore_phase = f"CANH TRAI SAT ({min_left_dist*100:.0f}cm): Tach phai"
            self.send_cmd("S 28.0 16.0", autonomous=False)
            return

        # CẠNH PHẢI ÁP SÁT (< HALF_WID = 13.5cm) -> Lượn sang trái tách xa tường
        if min_right_dist < HALF_WID and min_front_dist > 0.25:
            with state.lock: state.explore_phase = f"CANH PHAI SAT ({min_right_dist*100:.0f}cm): Tach trai"
            self.send_cmd("S 16.0 28.0", autonomous=False)
            return

        # MŨI TRƯỚC GẦN VẬT CẢN (< 25cm) -> Dừng tiến, Xoay dứt khoát sang bên thoáng
        if min_front_dist < 0.25:
            turn_dir = 22.0 if min_left_dist >= min_right_dist else -22.0
            side_name = "trai" if turn_dir > 0 else "phai"
            with state.lock: state.explore_phase = f"NE TRUOC MAT ({min_front_dist*100:.0f}cm): Xoay {side_name}"
            self.send_cmd(f"S {-turn_dir:.1f} {turn_dir:.1f}", autonomous=False)
            return

        # GẦN VẬT CẢN TỪ XA (25cm - 55cm) -> LƯỢN VÒNG CUNG DWA MƯỢT
        if min_front_dist < 0.55:
            spd = 18.0 + (min_front_dist - 0.25) * 25.0
            if min_left_dist >= min_right_dist:
                with state.lock: state.explore_phase = f"DWA LUON TRAI ({min_front_dist*100:.0f}cm)"
                self.send_cmd(f"S {spd*0.5:.1f} {spd*1.0:.1f}", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"DWA LUON PHAI ({min_front_dist*100:.0f}cm)"
                self.send_cmd(f"S {spd*1.0:.1f} {spd*0.5:.1f}", autonomous=False)
            return

        # -------------------------------------------------------------
        # HẠNG MỤC 5: TỰ KHÁM PHÁ A* & FRONTIER (TRÁNH CÁC ĐIỂM CHẾT ĐÃ GHI NHỚ)
        # -------------------------------------------------------------
        goal = self.find_best_frontier(rx, ry)
        if goal is not None:
            gx, gy = goal[0], goal[1]
            # Kiểm tra xem goal có nằm gần điểm chết vừa bị kẹt không
            is_near_dead_spot = any(math.hypot(gx - bx, gy - by) < 0.40 for bx, by, exp in self._blocked_spots if exp > now)
            if not is_near_dead_spot:
                path = self.plan_astar_path(rx, ry, gx, gy)
                if path and len(path) > 1:
                    wp = path[1] if len(path) > 1 else path[0]
                    dx, dy = wp[0] - rx, wp[1] - ry
                    err_ang = (math.atan2(dy, dx) - rth + math.pi) % (2 * math.pi) - math.pi
                    dist_goal = math.hypot(gx - rx, gy - ry)

                    L, R = 0.1875, 0.0366
                    v = 0.12
                    w = max(-0.4, min(0.4, 0.8 * err_ang))

                    vl = v - w * (L / 2.0)
                    vr = v + w * (L / 2.0)
                    rpm_l = max(10.0, min(35.0, (vl * 60.0) / (2.0 * math.pi * R)))
                    rpm_r = max(10.0, min(35.0, (vr * 60.0) / (2.0 * math.pi * R)))

                    with state.lock: state.explore_phase = f"A* DWA LƯỚT TỚI ĐIỂM CHƯA QUÉT ({dist_goal:.2f}m)"
                    self.send_cmd(f"S {rpm_l:.1f} {rpm_r:.1f}", autonomous=False)
                    return

        # VÙNG TRỐNG THÔNG THOÁNG -> TIẾN ĐỀU 30 RPM
        with state.lock: state.explore_phase = "QUET MO RONG TOAN PHONG"
        self.send_cmd("S 30.0 30.0", autonomous=False)"""

import re
code = re.sub(r'    def auto_nav_loop\(self\):[\s\S]*?(?=    def close_control)', real_chassis_nav + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED 260x207mm CHASSIS BOUNDS & SEQUENTIAL STALL RECOVERY")
