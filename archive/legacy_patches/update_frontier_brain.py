import os

path = r'D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH\agv_unified_brain.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target_find = '    def auto_nav_loop(self):\n        with state.lock:\n            auto = state.auto_mode\n            f_cm = state.zones["front"]'
pos = text.find(target_find)
if pos == -1:
    print("CANNOT FIND auto_nav_loop")
    exit(1)

end_marker = 'ros_node = None'
end_pos = text.find(end_marker, pos)
if end_pos == -1:
    print("CANNOT FIND end_marker")
    exit(1)

new_code = '''    def find_best_frontier(self, rx, ry):
        """Thuật toán Frontier Exploration: Quét bản đồ tìm vùng chưa biết (-1) tiếp giáp ô thoáng (0)"""
        with state.lock:
            w = state.map_width
            h = state.map_height
            res = state.map_resolution
            ox = state.map_origin_x
            oy = state.map_origin_y
            data = state.map_data

        if not data or w == 0 or h == 0:
            return None

        frontiers = []
        step = 3
        for y in range(2, h - 2, step):
            for x in range(2, w - 2, step):
                idx = y * w + x
                val = data[idx]
                if val == 0:
                    neighbors = [data[(y+1)*w + x], data[(y-1)*w + x], data[y*w + (x+1)], data[y*w + (x-1)]]
                    if -1 in neighbors and not any(n > 50 for n in neighbors):
                        wx = ox + x * res
                        wy = oy + y * res
                        dist = math.hypot(wx - rx, wy - ry)
                        if 0.4 <= dist <= 3.5:
                            frontiers.append((dist, wx, wy))

        with state.lock:
            state.frontier_count = len(frontiers)

        if not frontiers:
            return None
        frontiers.sort(key=lambda x: x[0])
        return (frontiers[0][1], frontiers[0][2])

    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            f_cm = state.zones["front"]
            fr_cm = state.zones["front_right"]
            fl_cm = state.zones["front_left"]
            l_cm = state.zones["left"]
            r_cm = state.zones["right"]
            rx = state.robot_x
            ry = state.robot_y
            rth = state.robot_th

        if not auto:
            self.explore_state = "INITIAL_SPIN"
            self.spin_timer = 0.0
            self.stuck_counter = 0
            with state.lock:
                state.explore_phase = "CHỜ LỆNH"
            return

        # 1. AN TOÀN PHẢN XẠ TUYỆT ĐỐI (Theo file Word: Hãm dừng 40cm)
        if f_cm < 40 or fr_cm < 32 or fl_cm < 32:
            self.send_cmd("M -115 -115")
            time.sleep(0.25)
            if l_cm > r_cm:
                self.send_cmd("M -125 125")
            else:
                self.send_cmd("M 125 -125")
            time.sleep(0.35)
            return

        # 2. KHỞI TẠO BẢN ĐỒ: QUAY 360 ĐỘ
        if self.explore_state == "INITIAL_SPIN":
            with state.lock:
                state.explore_phase = "QUAY QUÉT KHUNG 360°"
            self.spin_timer += 0.10
            if self.spin_timer <= 6.0:
                self.send_cmd("M -120 120")
            else:
                self.send_cmd("STOP")
                time.sleep(0.5)
                self.home_x = rx
                self.home_y = ry
                self.home_th = rth
                self.explore_state = "EXPLORING"
                self.last_pos = (rx, ry)
            return

        # 3. FRONTIER EXPLORATION: TỰ ĐẾN VÙNG CHƯA BIẾT (-1)
        if self.explore_state == "EXPLORING":
            dist_moved = math.hypot(rx - self.last_pos[0], ry - self.last_pos[1])
            if dist_moved < 0.03:
                self.stuck_counter += 1
            else:
                self.stuck_counter = 0
            self.last_pos = (rx, ry)

            if self.stuck_counter >= 12:
                self.send_cmd("M -120 -120")
                time.sleep(0.4)
                self.send_cmd("M 125 -125")
                time.sleep(0.5)
                self.stuck_counter = 0
                return

            goal = self.find_best_frontier(rx, ry)
            if goal is None:
                self.explore_state = "RETURNING_HOME"
                return

            gx, gy = goal
            with state.lock:
                state.target_goal_x = gx
                state.target_goal_y = gy
                state.explore_phase = f"KHÁM PHÁ ({gx:.1f}m, {gy:.1f}m)"

            dx = gx - rx
            dy = gy - ry
            dist_to_goal = math.hypot(dx, dy)
            target_angle = math.atan2(dy, dx)
            angle_diff = (target_angle - rth + math.pi) % (2 * math.pi) - math.pi

            if abs(angle_diff) > 0.6:
                if angle_diff > 0:
                    self.send_cmd("M -120 120")
                else:
                    self.send_cmd("M 120 -120")
            else:
                base_pwm = 125
                steer = int(angle_diff * 25.0)
                pwm_l = max(110, min(135, base_pwm - steer))
                pwm_r = max(110, min(135, base_pwm + steer))
                self.send_cmd(f"M {pwm_l} {pwm_r}")
            return

        # 4. TỰ ĐỘNG VỀ LẠI VỊ TRÍ XUẤT PHÁT
        if self.explore_state == "RETURNING_HOME":
            dx = self.home_x - rx
            dy = self.home_y - ry
            dist_home = math.hypot(dx, dy)

            if dist_home < 0.20:
                self.send_cmd("STOP")
                with state.lock:
                    state.explore_phase = "🏆 ĐÃ VỀ HOME THÀNH CÔNG!"
                    state.auto_mode = False
                return

            with state.lock:
                state.explore_phase = f"QUÉT XONG! VỀ HOME ({dist_home:.2f}m)"

            target_angle = math.atan2(dy, dx)
            angle_diff = (target_angle - rth + math.pi) % (2 * math.pi) - math.pi
            if abs(angle_diff) > 0.5:
                if angle_diff > 0:
                    self.send_cmd("M -120 120")
                else:
                    self.send_cmd("M 120 -120")
            else:
                self.send_cmd("M 120 120")
\n'''

text = text[:pos] + new_code + text[end_pos:]
with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print("SUCCESSFULLY_UPDATED_UNIFIED_BRAIN")
