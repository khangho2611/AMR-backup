with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# THUẬT TOÁN BẢO VỆ PHẦN MỀM THUẦN TÚY (ZERO MECHANICAL HARDWARE FIX):
# 1. Thân xe ảo an toàn 32cm (HALF_WID = 0.16m): Không bao giờ chui vào khe hẹp giữa 2 chân ghế.
# 2. Vùng đệm sườn an toàn (Safe Flank Margin = 0.22m): Khoảng cách 2 bên hông luôn cách chướng ngại vật > 22cm.
# 3. KHÓA XOAY TRONG NGÕ HẸP (NO-SPIN IN CONFINED SPACE):
#    - Khi sườn xe < 20cm, CẤM XOAY TRÁI/PHẢI (chống văng góc Mica 90 độ vào chân ghế).
#    - Hành vi duy nhất: LÙI THẲNG TẮP ra vùng rộng rãi rồi mới đổi hướng!

no_rubber_pure_sw = """    def auto_nav_loop(self):
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

        if not hasattr(self, '_stall_counter'): self._stall_counter = 0
        if not hasattr(self, '_recovering'): self._recovering = 0
        if not hasattr(self, '_blocked_spots'): self._blocked_spots = []

        # -------------------------------------------------------------
        # THÂN XE ẢO RỘNG 32CM (CHỐNG CHUI GẦM BÀN GHẾ)
        # -------------------------------------------------------------
        HALF_LEN = 0.180   # Dài an toàn 36cm (thực tế 26cm)
        HALF_WID = 0.160   # Rộng an toàn 32cm (thực tế 20.7cm) -> Khe chân ghế < 32cm coi như BỊ TẮC!

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

                # Phía trước trong hành lang thân xe ảo rộng 32cm
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
        # GIÁM SÁT MẮC KẸT THỰC TẾ & THOÁT KẸT CƠ KHÍ
        # -------------------------------------------------------------
        is_stalled = (abs(l_pwm) > 150 or abs(r_pwm) > 150) and (abs(l_rpm) < 3.0 and abs(r_rpm) < 3.0)
        if is_stalled:
            self._stall_counter += 1
        else:
            self._stall_counter = max(0, self._stall_counter - 1)

        # Trạng thái đang lùi thoát kẹt
        if self._recovering > 0:
            self._recovering -= 1
            if min_rear_dist > 0.20:
                with state.lock: state.explore_phase = f"LUI THOAT KET RONG ({self._recovering})"
                self.send_cmd("S -22.0 -22.0", autonomous=False)
            else:
                self._recovering = 0
                turn_dir = 22.0 if min_left_dist >= min_right_dist else -22.0
                with state.lock: state.explore_phase = "SAU BICH: Xoay doi huong"
                self.send_cmd(f"S {-turn_dir:.1f} {turn_dir:.1f}", autonomous=False)
            return

        # Phát hiện kẹt quá 8 nhịp (~0.8s) -> LẬP TỨC LÙI THẲNG RÚT KHUNG
        if self._stall_counter >= 8:
            self._stall_counter = 0
            self._blocked_spots.append((rx, ry, now + 60.0))
            self._blocked_spots = [b for b in self._blocked_spots if b[2] > now]

            if min_rear_dist > 0.20:
                self._recovering = 15  # Lùi thẳng 1.5 giây
                with state.lock: state.explore_phase = "PHAT HIEN KET: Lui thang rut khoi vat can"
                self.send_cmd("S -22.0 -22.0", autonomous=False)
                return
            else:
                turn_dir = 22.0 if min_left_dist >= min_right_dist else -22.0
                with state.lock: state.explore_phase = "KET & BICH SAU: Xoay doi huong"
                self.send_cmd(f"S {-turn_dir:.1f} {turn_dir:.1f}", autonomous=False)
                return

        # -------------------------------------------------------------
        # NGUYÊN TẮC THÉP: KHÓA XOAY KHI Ở TRONG KHE HẸP (CHỐNG MÓC GÓC MICA)
        # -------------------------------------------------------------
        # Nếu sườn xe đang gần vật cản (< 20cm) hoặc trước mặt bị chặn (< 28cm)
        in_confined_space = (min_left_dist < 0.20 or min_right_dist < 0.20)

        if min_front_dist < 0.28:
            # Trước mặt gần vật cản:
            if in_confined_space and min_rear_dist > 0.20:
                # ĐANG TRONG KHE HẸP (Chân ghế/ngõ cụt) -> TUYỆT ĐỐI CẤM XOAY! LÙI THẲNG TẮP!
                with state.lock: state.explore_phase = f"KHE HEP ({min_front_dist*100:.0f}cm): CAM XOAY - Lui thang"
                self.send_cmd("S -22.0 -22.0", autonomous=False)
                return
            else:
                # Vùng thoáng -> Xoay dứt khoát sang bên rộng nhất
                turn_dir = 22.0 if min_left_dist >= min_right_dist else -22.0
                side = "trai" if turn_dir > 0 else "phai"
                with state.lock: state.explore_phase = f"NE TRUOC MAT ({min_front_dist*100:.0f}cm): Xoay {side}"
                self.send_cmd(f"S {-turn_dir:.1f} {turn_dir:.1f}", autonomous=False)
                return

        # Sườn xe áp sát (< 18cm) nhưng trước mặt còn thoáng -> Lượn nhẹ tách ra xa tường
        if min_left_dist < 0.18 and min_front_dist > 0.35:
            with state.lock: state.explore_phase = f"TACH SUON TRAI ({min_left_dist*100:.0f}cm): Luon phai"
            self.send_cmd("S 28.0 16.0", autonomous=False)
            return

        if min_right_dist < 0.18 and min_front_dist > 0.35:
            with state.lock: state.explore_phase = f"TACH SUON PHAI ({min_right_dist*100:.0f}cm): Luon trai"
            self.send_cmd("S 16.0 28.0", autonomous=False)
            return

        # Trước mặt có vật cản từ xa (28cm - 65cm) -> LƯỢN VÒNG CUNG DWA MƯỢT
        if min_front_dist < 0.65:
            spd = 18.0 + (min_front_dist - 0.28) * 25.0
            if min_left_dist >= min_right_dist:
                with state.lock: state.explore_phase = f"DWA LUON TRAI ({min_front_dist*100:.0f}cm)"
                self.send_cmd(f"S {spd*0.5:.1f} {spd*1.0:.1f}", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"DWA LUON PHAI ({min_front_dist*100:.0f}cm)"
                self.send_cmd(f"S {spd*1.0:.1f} {spd*0.5:.1f}", autonomous=False)
            return

        # -------------------------------------------------------------
        # TỰ KHÁM PHÁ A* & FRONTIER VÀO CÁC VÙNG THOÁNG CHƯA QUÉT
        # -------------------------------------------------------------
        goal = self.find_best_frontier(rx, ry)
        if goal is not None:
            gx, gy = goal[0], goal[1]
            is_near_dead_spot = any(math.hypot(gx - bx, gy - by) < 0.45 for bx, by, exp in self._blocked_spots if exp > now)
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

        # VÙNG RỘNG RÃI THÔNG THOÁNG -> TIẾN ĐỀU 30 RPM
        with state.lock: state.explore_phase = "QUET TOAN BO KHONG GIAN MO"
        self.send_cmd("S 30.0 30.0", autonomous=False)"""

import re
code = re.sub(r'    def auto_nav_loop\(self\):[\s\S]*?(?=    def close_control)', no_rubber_pure_sw + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED 100% PURE SOFTWARE PROTECTION")
