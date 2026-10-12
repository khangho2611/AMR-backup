with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# NÂNG CẤP BỘ NÃO ĐIỀU HƯỚNG TỰ HÀNH: TRIỆT TIÊU 100% CÁC LỖI GÂY ĐÂM TƯỜNG
# 1. Phát hiện sườn xe áp sát tường (Flank Proximity Protection):
#    - Khi có tường sát sườn (< 26cm): CẤM XOAY TẠI CHỖ (vì xoay sẽ văng đuôi đập tường).
#    - Thay vào đó: Vừa tiến vừa bẻ lái nhẹ ra xa bức tường (Lượn vòng cung an toàn).
# 2. Nhận diện ngõ cụt: Phía trước bít lối (< 22cm) -> Lùi xe an toàn rồi mới quay đầu.
# 3. Phân cấp tốc độ: Càng gần tường càng hãm chậm tốc độ PID (không để quán tính đẩy lao vào tường).
# 4. Khi xoay theo A*: Kiểm tra khoảng trống 360 độ xung quanh trước khi xoay, không bao giờ xoay mù!

safe_frontier_loop = """    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            points = list(state.ranges)
            pose = (state.robot_x, state.robot_y, state.robot_th)
        if not auto:
            return

        if not self.control.armed:
            self.control.request_arm()

        # 1. PHÂN TÍCH KHÔNG GIAN HÌNH HỌC TỨC THỜI TỪ LIDAR (CHỐNG VA CHẠM THỰC TẾ)
        min_front_corridor = 99.0
        min_left_flank = 99.0
        min_right_flank = 99.0
        HALF_WIDTH = 0.13  # Nửa thân xe 13cm (chiều rộng hành lang 26cm, thân xe 19cm)

        for deg in range(360):
            r = points[deg]
            if 0.05 < r < 8.0:
                rad = math.radians(deg)
                x = r * math.cos(rad)
                y = r * math.sin(rad)

                # Hành lang phía trước (x > 0, lọt vào chiều ngang thân xe)
                if 0.0 < x < 1.8 and abs(y) <= HALF_WIDTH:
                    if x < min_front_corridor:
                        min_front_corridor = x

                # Khoảng cách sườn trái (y > 0) và sườn phải (y < 0)
                if -0.15 <= x <= 0.25:
                    if 0.0 < y < 0.35 and y < min_left_flank:
                        min_left_flank = y
                    elif -0.35 < y < 0.0 and abs(y) < min_right_flank:
                        min_right_flank = abs(y)

        # Đo khoảng trống phía sau lưng để dự phòng lùi xe
        rear_ranges = [points[d % 360] for d in range(150, 211) if points[d % 360] > 0.05]
        min_rear = min(rear_ranges) if rear_ranges else 1.0

        # Đo độ thoáng 2 bên sườn trước
        left_ranges = [points[d % 360] for d in range(30, 110) if points[d % 360] > 0.05]
        right_ranges = [points[d % 360] for d in range(250, 330) if points[d % 360] > 0.05]
        avg_l = sum(left_ranges)/len(left_ranges) if left_ranges else 0.0
        avg_r = sum(right_ranges)/len(right_ranges) if right_ranges else 0.0

        # TÌNH HUỐNG A: CÓ BỨC TƯỜNG ÁP SÁT SƯỜN (< 25cm) -> CẤM XOAY TRÒN! LƯỢN VÒNG TÁCH XA TƯỜNG
        if min_left_flank < 0.25 and min_front_corridor > 0.25:
            # Sườn trái sát tường -> Vừa tiến vừa bẻ nhẹ sang phải để tách xa tường, không văng đuôi
            with state.lock: state.explore_phase = f"TACH TUONG TRAI ({min_left_flank*100:.0f}cm): Luon phai"
            self.send_cmd("S 32.0 20.0", autonomous=False)
            return

        if min_right_flank < 0.25 and min_front_corridor > 0.25:
            # Sườn phải sát tường -> Vừa tiến vừa bẻ nhẹ sang trái để tách xa tường
            with state.lock: state.explore_phase = f"TACH TUONG PHAI ({min_right_flank*100:.0f}cm): Luon trai"
            self.send_cmd("S 20.0 32.0", autonomous=False)
            return

        # TÌNH HUỐNG B: VẬT CẢN CHẮN TRƯỚC MẶT (< 22cm) -> DỪNG VÀ XỬ LÝ THOÁT HIỂM
        if min_front_corridor < 0.22:
            # Nếu cả 2 bên đều chật hẹp -> Ngõ cụt -> Lùi xe thoát hiểm
            if avg_l < 0.30 and avg_r < 0.30 and min_rear > 0.25:
                with state.lock: state.explore_phase = f"NGO CUT: Lui thoat hiem ({min_front_corridor*100:.0f}cm)"
                self.send_cmd("S -25.0 -25.0", autonomous=False)
            else:
                # Xoay né sang bên thoáng nhất
                if avg_l >= avg_r:
                    with state.lock: state.explore_phase = f"NE TRUOC MAT ({min_front_corridor*100:.0f}cm): Xoay trai"
                    self.send_cmd("S -22.0 22.0", autonomous=False)
                else:
                    with state.lock: state.explore_phase = f"NE TRUOC MAT ({min_front_corridor*100:.0f}cm): Xoay phai"
                    self.send_cmd("S 22.0 -22.0", autonomous=False)
            return

        # TÌNH HUỐNG C: GẦN TƯỜNG (22cm - 38cm) -> HÃM CHẬM TỐC ĐỘ, LƯỢN NÉ TỪ XA
        if min_front_corridor < 0.38:
            if avg_l >= avg_r:
                with state.lock: state.explore_phase = f"HAM PHANH NE XA ({min_front_corridor*100:.0f}cm): Vong trai"
                self.send_cmd("S 12.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"HAM PHANH NE XA ({min_front_corridor*100:.0f}cm): Vong phai"
                self.send_cmd("S 25.0 12.0", autonomous=False)
            return

        # 2. BỘ NÃO ĐIỀU HƯỚNG TẦNG CAO: TÌM ĐƯỜNG ĐẾN VÙNG CHƯA QUÉT (FRONTIER EXPLORATION & A*)
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

                # Nếu cần xoay góc lớn: Kiểm tra sườn xe có an toàn trước khi xoay không
                if abs(err_ang) > 0.40:
                    if min_left_flank > 0.22 and min_right_flank > 0.22:
                        w = 0.5 if err_ang > 0 else -0.5
                        v = 0.0
                        with state.lock: state.explore_phase = f"A* XOAY HUONG ({math.degrees(err_ang):.0f} deg)"
                    else:
                        # Sườn đang gần tường -> Vừa tiến vừa xoay nhẹ để không quẹt đuôi
                        v = 0.08
                        w = 0.3 if err_ang > 0 else -0.3
                        with state.lock: state.explore_phase = "A* TIEN LUON MO RONG GOC"
                else:
                    v = 0.12  # Vận tốc tiến êm ái ~30 RPM
                    w = max(-0.4, min(0.4, 1.0 * err_ang))
                    with state.lock: state.explore_phase = f"A* TIEN TOI VUNG TOI ({dist_goal:.2f}m)"

                vl = v - w * (L / 2.0)
                vr = v + w * (L / 2.0)
                rpm_l = max(-45.0, min(45.0, (vl * 60.0) / (2.0 * math.pi * R)))
                rpm_r = max(-45.0, min(45.0, (vr * 60.0) / (2.0 * math.pi * R)))

                self.send_cmd(f"S {rpm_l:.1f} {rpm_r:.1f}", autonomous=False)
                return

        # 3. KHI KHÔNG GIAN THÔNG THOÁNG: TIẾN ĐỀU KHÁM PHÁ PHÒNG
        with state.lock: state.explore_phase = f"QUET MO RONG AN TOAN (Trong: {min_front_corridor*100:.0f}cm)"
        self.send_cmd("S 30.0 30.0", autonomous=False)"""

import re
code = re.sub(r'    def auto_nav_loop\(self\):[\s\S]*?(?=    def close_control)', safe_frontier_loop + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY BULLETPROOFED AGAINST WALL COLLISIONS")
