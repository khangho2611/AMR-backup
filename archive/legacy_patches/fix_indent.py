with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_auto = False
for line in lines:
    if line.startswith('def auto_nav_loop(self):') or line.startswith('    def auto_nav_loop(self):'):
        in_auto = True
        auto_block = """    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            points = list(state.ranges)
            pose = (state.robot_x, state.robot_y, state.robot_th)
        if not auto:
            return

        if not self.control.armed:
            self.control.request_arm()

        front_ranges = [points[d % 360] for d in range(-25, 26) if points[d % 360] > 0.05]
        min_front = min(front_ranges) if front_ranges else 1.0

        with state.lock:
            state.target_goal_x = 0.0
            state.target_goal_y = 0.0

        if min_front < 0.15:
            left_ranges = [points[d % 360] for d in range(30, 90) if points[d % 360] > 0.05]
            right_ranges = [points[d % 360] for d in range(270, 330) if points[d % 360] > 0.05]
            avg_left = sum(left_ranges)/len(left_ranges) if left_ranges else 0.0
            avg_right = sum(right_ranges)/len(right_ranges) if right_ranges else 0.0

            if avg_left >= avg_right:
                with state.lock: state.explore_phase = "NE TUONG (<15cm): Xoay trai sang vung thoang"
                self.send_cmd("M -110 110", autonomous=False)
            else:
                with state.lock: state.explore_phase = "NE TUONG (<15cm): Xoay phai sang vung thoang"
                self.send_cmd("M 110 -110", autonomous=False)
        else:
            with state.lock: state.explore_phase = f"QUET MAP TIEN TOI (Trong: {min_front*100:.0f}cm)"
            self.send_cmd("M 120 120", autonomous=False)

"""
        new_lines.append(auto_block)
        continue
    if in_auto:
        if line.strip().startswith('def close_control(self):'):
            in_auto = False
            new_lines.append(line)
        continue
    new_lines.append(line)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.writelines(new_lines)

print("FIXED INDENTATION AND SYNTAX")
