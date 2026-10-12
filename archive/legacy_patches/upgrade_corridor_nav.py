with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# NÂNG CẤP THUẬT TOÁN ĐIỀU HƯỚNG TỰ ĐỘNG THỰC THỤ DỰA TRÊN HÌNH HỌC TỌA ĐỘ THÂN XE:
# 1. Bán kính thân xe thực tế: 19cm. Đặt hành lang an toàn bề ngang w = 24cm (mỗi bên y = +-12cm).
# 2. Chiều dài an toàn phía trước x:
#    - Vùng nguy hiểm: x < 0.25m (25cm) trong hành lang y in [-0.12, 0.12]
#    - Vùng cảnh báo hãm phanh: x < 0.45m (45cm) trong hành lang y in [-0.15, 0.15]
# 3. Tính toán trực tiếp từ tọa độ Descartes (x = r*cos(a), y = r*sin(a)):

new_auto_nav = """    def auto_nav_loop(self):
        with state.lock:
            auto = state.auto_mode
            points = list(state.ranges)
            pose = (state.robot_x, state.robot_y, state.robot_th)
        if not auto:
            return

        if not self.control.armed:
            self.control.request_arm()

        # Tính toán vật cản thực tế trong hệ quy chiếu thân xe (Base Frame)
        # x: hướng tiến phía trước (m), y: hướng sang trái (m)
        min_front_corridor = 99.0
        left_clearance = 0.0
        right_clearance = 0.0
        left_cnt = 0
        right_cnt = 0

        # Nửa bề rộng hành lang xe cần để lọt qua (12cm mỗi bên = 24cm, xe rộng 19cm)
        HALF_WIDTH = 0.13

        for deg in range(360):
            r = points[deg]
            if 0.05 < r < 8.0:
                rad = math.radians(deg)
                x = r * math.cos(rad)
                y = r * math.sin(rad)

                # Kiểm tra vật cản nằm ngay trong hành lang tiến thẳng phía trước
                if 0.0 < x < 1.5 and abs(y) <= HALF_WIDTH:
                    if x < min_front_corridor:
                        min_front_corridor = x

                # Đo độ thoáng 2 bên hông để quyết định hướng bẻ lái
                if 0.0 < x < 1.0:
                    if y > HALF_WIDTH:
                        left_clearance += r
                        left_cnt += 1
                    elif y < -HALF_WIDTH:
                        right_clearance += r
                        right_cnt += 1

        avg_left = (left_clearance / left_cnt) if left_cnt > 0 else 0.0
        avg_right = (right_clearance / right_cnt) if right_cnt > 0 else 0.0

        with state.lock:
            state.target_goal_x = 0.0
            state.target_goal_y = 0.0

        # CẤP 1: VẬT THỂ Ở CỰ LY NGUY HIỂM (< 26cm trước mũi xe)
        # Lập tức dừng tiến, xoay PID tại chỗ 25 RPM về phía thoáng hơn
        if min_front_corridor < 0.26:
            if avg_left >= avg_right:
                with state.lock: state.explore_phase = f"NE VAT CAN ({min_front_corridor*100:.0f}cm): Xoay trai"
                self.send_cmd("S -25.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"NE VAT CAN ({min_front_corridor*100:.0f}cm): Xoay phai"
                self.send_cmd("S 25.0 -25.0", autonomous=False)

        # CẤP 2: PHÁT HIỆN VẬT THỂ TỪ XA (26cm - 45cm trước mũi xe)
        # Giảm tốc độ PID, vừa đi vừa lượn vòng né sớm
        elif min_front_corridor < 0.45:
            if avg_left >= avg_right:
                with state.lock: state.explore_phase = f"RE TRANH VAT CAN ({min_front_corridor*100:.0f}cm): Luon trai"
                self.send_cmd("S 10.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"RE TRANH VAT CAN ({min_front_corridor*100:.0f}cm): Luon phai"
                self.send_cmd("S 25.0 10.0", autonomous=False)

        # CẤP 3: HÀNH LANG PHÍA TRƯỚC HOÀN TOÀN THÔNG THOÁNG (> 45cm)
        # Tiến đều đặn êm ái 35 RPM
        else:
            with state.lock: state.explore_phase = f"QUET MAP AN TOAN (Trong: {min_front_corridor*100:.0f}cm)"
            self.send_cmd("S 35.0 35.0", autonomous=False)"""

# Tìm đoạn def auto_nav_loop cũ và thay thế
import re
code = re.sub(r'    def auto_nav_loop\(self\):[\s\S]*?(?=    def close_control)', new_auto_nav + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("UPGRADED CARPET-CORRIDOR COLLISION AVOIDANCE ENGINE")
