with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# ĐẤU NỐI THUẬT TOÁN TỰ ĐỘNG KHÁM PHÁ BẢN ĐỒ SLAM (AUTONOMOUS FRONTIER EXPLORATION & A* PATHFINDING):
# - Robot nhớ toàn bộ các ô đã quét (Free cells) và các ô chưa quét (Unknown cells).
# - Liên tục tìm các điểm Frontier (biên giới vùng chưa quét) an toàn gần xe nhất.
# - Dùng A* vạch lộ trình đi qua vùng đã biết để tiến tới khai phá vùng tối!
# - Chuyển đổi vận tốc dài v (m/s) và vận tốc góc w (rad/s) của A* thành lệnh RPM chuẩn cho bộ điều khiển PID của STM32!

frontier_brain_loop = """    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            points = list(state.ranges)
            pose = (state.robot_x, state.robot_y, state.robot_th)
        if not auto:
            return

        if not self.control.armed:
            self.control.request_arm()

        # 1. KIỂM TRA PHẢN XẠ AN TOÀN TỨC THỜI TỪ LIDAR (CHỐNG VA CHẠM KHẨN CẤP)
        min_front_corridor = 99.0
        HALF_WIDTH = 0.13
        for deg in range(360):
            r = points[deg]
            if 0.05 < r < 8.0:
                rad = math.radians(deg)
                x = r * math.cos(rad)
                y = r * math.sin(rad)
                if 0.0 < x < 1.5 and abs(y) <= HALF_WIDTH:
                    if x < min_front_corridor:
                        min_front_corridor = x

        # CẤP KHẨN CẤP: Nếu có vật cản đột ngột chắn đường (< 22cm) -> Phanh và xoay né tức thì
        if min_front_corridor < 0.22:
            left_ranges = [points[d % 360] for d in range(30, 110) if points[d % 360] > 0.05]
            right_ranges = [points[d % 360] for d in range(250, 330) if points[d % 360] > 0.05]
            avg_l = sum(left_ranges)/len(left_ranges) if left_ranges else 0.0
            avg_r = sum(right_ranges)/len(right_ranges) if right_ranges else 0.0
            if avg_l >= avg_r:
                with state.lock: state.explore_phase = f"NE KHAN CAP ({min_front_corridor*100:.0f}cm): Xoay trai"
                self.send_cmd("S -25.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"NE KHAN CAP ({min_front_corridor*100:.0f}cm): Xoay phai"
                self.send_cmd("S 25.0 -25.0", autonomous=False)
            return

        # 2. BỘ NÃO ĐIỀU HƯỚNG TẦNG CAO: TÌM ĐƯỜNG ĐẾN VÙNG CHƯA QUÉT (FRONTIER EXPLORATION)
        rx, ry, rth = pose
        goal = self.find_best_frontier(rx, ry)

        if goal is not None:
            gx, gy = goal[0], goal[1]
            with state.lock:
                state.target_goal_x = float(gx)
                state.target_goal_y = float(gy)

            # Tìm đường A* từ vị trí hiện tại đến mục tiêu vùng chưa quét
            path = self.plan_astar_path(rx, ry, gx, gy)
            if path and len(path) > 1:
                # Điểm dẫn đường gần nhất trên quỹ đạo A*
                wp = path[1] if len(path) > 1 else path[0]
                dx, dy = wp[0] - rx, wp[1] - ry
                target_ang = math.atan2(dy, dx)
                err_ang = (target_ang - rth + math.pi) % (2 * math.pi) - math.pi
                dist_goal = math.hypot(gx - rx, gy - ry)

                # Bộ điều khiển động học vi sai (Kinematic Controller)
                # Động học xe: L = 0.1875m, R = 0.0366m
                L = 0.1875
                R = 0.0366

                if abs(err_ang) > 0.40:
                    # Lệch góc lớn -> Xoay hướng về phía điểm chưa quét
                    w = 0.6 if err_ang > 0 else -0.6
                    v = 0.0
                    with state.lock: state.explore_phase = f"XOAY HUONG VUNG TOI ({math.degrees(err_ang):.0f} deg)"
                else:
                    # Góc chuẩn -> Tiến theo quỹ đạo A* khai phá vùng tối
                    v = 0.14  # 0.14 m/s (chạy êm ái khoảng 36 RPM)
                    w = max(-0.5, min(0.5, 1.2 * err_ang))
                    with state.lock: state.explore_phase = f"A* DANG TIEN TOI VUNG TOI ({dist_goal:.2f}m)"

                # Chuyển đổi v, w sang RPM bánh trái, bánh phải
                vl = v - w * (L / 2.0)
                vr = v + w * (L / 2.0)
                rpm_l = (vl * 60.0) / (2.0 * math.pi * R)
                rpm_r = (vr * 60.0) / (2.0 * math.pi * R)

                # Giới hạn RPM an toàn
                rpm_l = max(-50.0, min(50.0, rpm_l))
                rpm_r = max(-50.0, min(50.0, rpm_r))

                self.send_cmd(f"S {rpm_l:.1f} {rpm_r:.1f}", autonomous=False)
                return

        # 3. NẾU BẢN ĐỒ SLAM CHƯA KỊP DỰNG HOẶC ĐÃ QUÉT HẾT: LĂN BÁNH QUÉT THĂM DÒ AN TOÀN
        with state.lock: state.explore_phase = "QUET MO RONG BAN DO (Tham do tu do)"
        self.send_cmd("S 32.0 32.0", autonomous=False)"""

import re
code = re.sub(r'    def auto_nav_loop\(self\):[\s\S]*?(?=    def close_control)', frontier_brain_loop + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY INTEGRATED AUTONOMOUS FRONTIER EXPLORATION & A* PATHFINDING")
