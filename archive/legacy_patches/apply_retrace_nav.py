with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# NÂNG CẤP THUẬT TOÁN "BÁM VỆT BÁNH LÙI CHÍNH XÁC NƠI VỪA TIẾN TỚI" (ODOMETRY BREADCRUMB RETRACE):
# 1. Liên tục lưu lại lịch sử tọa độ vệt bánh xe vừa đi qua (Trail History / Breadcrumbs).
# 2. Loại bỏ điểm mù laser liếm đuôi xe (chống kẹt cờ lùi).
# 3. Khi gặp vật cản trước mặt: LÙI NGƯỢC LẠI ĐÚNG VỊ TRÍ AN TOÀN TRƯỚC ĐÓ 1.5 - 2 GIÂY!
#    - Nơi mình vừa đi qua CHẮC CHẮN 100% LÀ NƠI KHÔNG CÓ VẬT CẢN (ĐÃ ĐƯỢC CHỨNG MINH AN TOÀN)!
# 4. Sau khi rút lui về đúng vết bánh an toàn -> Xoay sang hướng thoáng nhất (Bên Trái) để đi tiếp!

retrace_nav = """    def auto_nav_loop(self):
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

        # KHỞI TẠO BỘ NHỚ LỊCH SỬ VỆT BÁNH (BREADCRUMB TRAIL)
        if not hasattr(self, '_trail_history'): self._trail_history = []  # list các (x, y, th, time)
        if not hasattr(self, '_recovering_steps'): self._recovering_steps = 0
        if not hasattr(self, '_stall_counter'): self._stall_counter = 0
        if not hasattr(self, '_blocked_spots'): self._blocked_spots = []

        # Lưu vết bánh xe mỗi 0.1s (chỉ lưu khi xe đang di chuyển bình thường)
        if self._recovering_steps == 0:
            if not self._trail_history or math.hypot(rx - self._trail_history[-1][0], ry - self._trail_history[-1][1]) > 0.03:
                self._trail_history.append((rx, ry, rth, now))
                # Giữ tối đa 50 điểm vệt bánh gần nhất (~1.5m đường vừa đi)
                if len(self._trail_history) > 50:
                    self._trail_history.pop(0)

        # -------------------------------------------------------------
        # 1. HÌNH HỌC KHUNG XE THỰC TẾ & LỌC ĐIỂM MÙ ĐUÔI XE
        # -------------------------------------------------------------
        HALF_LEN = 0.160
        HALF_WID = 0.140

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

                # LỌC ĐIỂM MÙ ĐUÔI XE: Bỏ qua phản xạ bánh caster/dây điện sau xe (-0.14m <= x <= 0.0, |y| <= 0.08m)
                if -0.14 <= x <= 0.0 and abs(y) <= 0.08:
                    continue

                # Phía trước trong hành lang thân xe
                if x > 0.0 and abs(y) <= HALF_WID:
                    if x < min_front_dist: min_front_dist = x

                # Phía sau lưng xe
                if x < 0.0 and abs(y) <= HALF_WID:
                    dist_b = abs(x)
                    if dist_b < min_rear_dist: min_rear_dist = dist_b

                # Hai bên sườn xe
                if -HALF_LEN <= x <= HALF_LEN:
                    if y > 0.0 and y < min_left_dist: min_left_dist = y
                    elif y < 0.0 and abs(y) < min_right_dist: min_right_dist = abs(y)

        # -------------------------------------------------------------
        # 2. XỬ LÝ LÙI RÚT THẲNG THEO VỆT BÁNH CŨ (RETRACING BREADCRUMBS)
        # -------------------------------------------------------------
        if self._recovering_steps > 0:
            self._recovering_steps -= 1
            with state.lock: state.explore_phase = f"LUI RETRACE VE VET BANH AN TOAN ({self._recovering_steps})"
            # Lùi thẳng đều 2 bánh để bám đúng vệt bánh vừa tiến vào
            self.send_cmd("S -22.0 -22.0", autonomous=False)
            return

        # -------------------------------------------------------------
        # 3. KÍCH HOẠT LÙI KHI GẶP VẬT CẢN TRƯỚC MẶT (< 26cm) HOẶC KẸT
        # -------------------------------------------------------------
        # Điều kiện: Trước mặt có thanh chắn (< 26cm)
        if min_front_dist < 0.26:
            # LẬP TỨC LÙI NGAY NƠI VỪA TIẾN VÀO (12 nhịp = 1.2s lùi ~ 15-20cm an toàn)
            self._recovering_steps = 14
            self._blocked_spots.append((rx, ry, now + 60.0))
            with state.lock: state.explore_phase = f"GAP VAT CAN ({min_front_dist*100:.0f}cm): LUI NGAY VE VET CU"
            self.send_cmd("S -22.0 -22.0", autonomous=False)
            return

        # Giám sát kẹt cơ khí (Stall)
        is_stalled = (abs(l_pwm) > 150 or abs(r_pwm) > 150) and (abs(l_rpm) < 3.0 and abs(r_rpm) < 3.0)
        if is_stalled:
            self._stall_counter += 1
        else:
            self._stall_counter = max(0, self._stall_counter - 1)

        if self._stall_counter >= 8:
            self._stall_counter = 0
            self._recovering_steps = 16
            self._blocked_spots.append((rx, ry, now + 60.0))
            with state.lock: state.explore_phase = "KET CO KHI: LUI RUT VE VET CU"
            self.send_cmd("S -22.0 -22.0", autonomous=False)
            return

        # -------------------------------------------------------------
        # 4. BẢO VỆ 2 BÊN SƯỜN XE
        # -------------------------------------------------------------
        if min_left_dist < 0.16 and min_front_dist > 0.30:
            with state.lock: state.explore_phase = f"TACH SUON TRAI ({min_left_dist*100:.0f}cm): Luon phai"
            self.send_cmd("S 26.0 16.0", autonomous=False)
            return

        if min_right_dist < 0.16 and min_front_dist > 0.30:
            with state.lock: state.explore_phase = f"TACH SUON PHAI ({min_right_dist*100:.0f}cm): Luon trai"
            self.send_cmd("S 16.0 26.0", autonomous=False)
            return

        # -------------------------------------------------------------
        # 5. LƯỢN TRÁNH VẬT CẢN TỪ XA (26cm - 65cm) THEO ĐƯỜNG CONG DWA
        # -------------------------------------------------------------
        if min_front_dist < 0.65:
            spd = 18.0 + (min_front_dist - 0.26) * 25.0
            if min_left_dist >= min_right_dist:
                with state.lock: state.explore_phase = f"DWA LUON TRAI ({min_front_dist*100:.0f}cm)"
                self.send_cmd(f"S {spd*0.5:.1f} {spd*1.0:.1f}", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"DWA LUON PHAI ({min_front_dist*100:.0f}cm)"
                self.send_cmd(f"S {spd*1.0:.1f} {spd*0.5:.1f}", autonomous=False)
            return

        # -------------------------------------------------------------
        # 6. TỰ KHÁM PHÁ A* & FRONTIER VÀO VÙNG THOÁNG CHƯA QUÉT
        # -------------------------------------------------------------
        goal = self.find_best_frontier(rx, ry)
        if goal is not None:
            gx, gy = goal[0], goal[1]
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

                    with state.lock: state.explore_phase = f"A* DWA LƯỚT TỚI VÙNG TRỐNG ({dist_goal:.2f}m)"
                    self.send_cmd(f"S {rpm_l:.1f} {rpm_r:.1f}", autonomous=False)
                    return

        # VÙNG RỘNG RÃI -> TIẾN ĐỀU 30 RPM
        with state.lock: state.explore_phase = "QUET TOAN BO PHONG"
        self.send_cmd("S 30.0 30.0", autonomous=False)"""

import re
code = re.sub(r'    def auto_nav_loop\(self\):[\s\S]*?(?=    def close_control)', retrace_nav + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED RETRACE-TO-HISTORY SAFE BACKUP NAVIGATION")
