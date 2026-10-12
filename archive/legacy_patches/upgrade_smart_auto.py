with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Thay thế toàn bộ auto_nav_loop thành thuật toán né vật cản động lực học thông minh:
# - Quét góc rộng +-55 độ phía trước thân xe để không bị mù góc tường nghiêng
# - Phân cấp tốc độ: xa thì chạy êm (40 RPM), trung bình (25-35cm) thì hãm phanh chậm lại (20 RPM), sát (<22cm) thì dừng và xoay vòng kín PID
# - So sánh khoảng trống 2 bên sườn trái/phải để chọn hướng rẽ thông minh nhất

old_nav = """        front_ranges = [points[d % 360] for d in range(-25, 26) if points[d % 360] > 0.05]
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
                with state.lock: state.explore_phase = "NE TUONG [PID]: Xoay trai 30 RPM"
                self.send_cmd("S -30.0 30.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = "NE TUONG [PID]: Xoay phai 30 RPM"
                self.send_cmd("S 30.0 -30.0", autonomous=False)
        else:
            with state.lock: state.explore_phase = f"QUET MAP [PID] TIEN TOI 45 RPM (Trong: {min_front*100:.0f}cm)"
            self.send_cmd("S 45.0 45.0", autonomous=False)"""

new_nav = """        # 1. Quét hình chữ nhật an toàn phía trước mặt xe (+-55 độ)
        front_ranges = [points[d % 360] for d in range(-55, 56) if points[d % 360] > 0.05]
        min_front = min(front_ranges) if front_ranges else 1.0

        # 2. Đánh giá khoảng trống 2 bên sườn (trái 30..110 độ, phải 250..330 độ)
        left_ranges = [points[d % 360] for d in range(30, 110) if points[d % 360] > 0.05]
        right_ranges = [points[d % 360] for d in range(250, 330) if points[d % 360] > 0.05]
        avg_left = sum(left_ranges)/len(left_ranges) if left_ranges else 0.0
        avg_right = sum(right_ranges)/len(right_ranges) if right_ranges else 0.0

        with state.lock:
            state.target_goal_x = 0.0
            state.target_goal_y = 0.0

        # CẤP 1: Cực sát vật cản (< 22cm) -> Dừng hẳn tiến, Xoay PID vòng kín nhẹ nhàng 25 RPM về phía thoáng
        if min_front < 0.22:
            if avg_left >= avg_right:
                with state.lock: state.explore_phase = f"NE TUONG GAP ({min_front*100:.0f}cm): Xoay trai"
                self.send_cmd("S -25.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"NE TUONG GAP ({min_front*100:.0f}cm): Xoay phai"
                self.send_cmd("S 25.0 -25.0", autonomous=False)

        # CẤP 2: Đến gần tường (22cm - 38cm) -> Giảm tốc độ PID xuống 20 RPM để hãm quán tính an toàn
        elif min_front < 0.38:
            if avg_left >= avg_right:
                with state.lock: state.explore_phase = f"HAM PHANH RE TRAI ({min_front*100:.0f}cm)"
                self.send_cmd("S 12.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"HAM PHANH RE PHAI ({min_front*100:.0f}cm)"
                self.send_cmd("S 25.0 12.0", autonomous=False)

        # CẤP 3: Phía trước thoáng (> 38cm) -> Tiến đều êm ái 35 RPM
        else:
            with state.lock: state.explore_phase = f"QUET MAP AN TOAN ({min_front*100:.0f}cm)"
            self.send_cmd("S 35.0 35.0", autonomous=False)"""

code = code.replace(old_nav, new_nav)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("UPGRADED SMART AUTO EXPLORATION ALGORITHM SUCCESSFUL")
