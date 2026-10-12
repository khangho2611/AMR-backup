with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# NÂNG CẤP THUẬT TOÁN ĐIỀU HƯỚNG TỰ ĐỘNG THÔNG MINH CHO KHE HẸP VÀ CHOKEPOINT:
# 1. Đo khoảng cách vật cản 2 bên sườn (flank clearance): min_left_flank và min_right_flank
# 2. Khi xe đang nằm trong khe hẹp (2 bên đều có vật cản gần < 28cm) NHƯNG phía trước thoáng (> 35cm):
#    -> CẤM XOAY XE TẠI CHỖ (vì xoay sẽ quẹt sườn vào 2 bên)!
#    -> THỰC THI: TIẾN THẲNG CÂN BẰNG GIỮA 2 TƯỜNG (Corridor Centering Control) để thoát khỏi khe hẹp!

corridor_nav_logic = """        # 1. Phân tích không gian hình học 360 độ từ LiDAR
        min_front_corridor = 99.0
        min_left_flank = 99.0
        min_right_flank = 99.0
        left_clearance = 0.0
        right_clearance = 0.0
        left_cnt = 0
        right_cnt = 0

        HALF_WIDTH = 0.13  # Nửa thân xe 13cm (bề rộng hành lang 26cm, thân xe 19cm)

        for deg in range(360):
            r = points[deg]
            if 0.05 < r < 8.0:
                rad = math.radians(deg)
                x = r * math.cos(rad)
                y = r * math.sin(rad)

                # Hành lang phía trước (x > 0, lọt vào bề ngang thân xe)
                if 0.0 < x < 1.8 and abs(y) <= HALF_WIDTH:
                    if x < min_front_corridor:
                        min_front_corridor = x

                # Đo vật cản 2 bên sườn xe (trong vùng -0.1m <= x <= 0.25m)
                if -0.10 <= x <= 0.25:
                    if 0.0 < y < 0.35:
                        if y < min_left_flank: min_left_flank = y
                    elif -0.35 < y < 0.0:
                        if abs(y) < min_right_flank: min_right_flank = abs(y)

                # Đo độ thoáng tổng thể phía trước để chọn hướng thoát (x > 0)
                if 0.0 < x < 1.2:
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

        # TRƯỜNG HỢP ĐẶC BIỆT: XE ĐANG KẸT TRONG KHE HẸP / CỬA PHÒNG
        # Hai bên sườn đều sát vật cản (<28cm) nhưng phía trước thoáng (>30cm)
        in_tight_corridor = (min_left_flank < 0.28 or min_right_flank < 0.28) and (min_front_corridor > 0.30)

        if in_tight_corridor:
            # CẤM XOAY! Giữ thẳng lái và tự cân bằng giữa 2 vật cản để thoát hiểm
            if min_left_flank < min_right_flank - 0.04:
                # Sườn trái gần hơn sườn phải -> nhích nhẹ sang phải 2 RPM
                with state.lock: state.explore_phase = f"THOAT KHE HEP: Lech phai (L:{min_left_flank*100:.0f}cm R:{min_right_flank*100:.0f}cm)"
                self.send_cmd("S 32.0 30.0", autonomous=False)
            elif min_right_flank < min_left_flank - 0.04:
                # Sườn phải gần hơn sườn trái -> nhích nhẹ sang trái 2 RPM
                with state.lock: state.explore_phase = f"THOAT KHE HEP: Lech trai (L:{min_left_flank*100:.0f}cm R:{min_right_flank*100:.0f}cm)"
                self.send_cmd("S 30.0 32.0", autonomous=False)
            else:
                # Cân bằng 2 bên -> Tiến thẳng đều 30 RPM thoát hiểm
                with state.lock: state.explore_phase = f"THOAT KHE HEP: Tien thang giua 2 vat can"
                self.send_cmd("S 30.0 30.0", autonomous=False)

        # CẤP 1: CỰC SÁT VẬT CẢN TRƯỚC MẶT (< 24cm) -> Dừng tiến, Xoay PID tại chỗ 22 RPM
        elif min_front_corridor < 0.24:
            if avg_left >= avg_right:
                with state.lock: state.explore_phase = f"NE VAT CAN GAP ({min_front_corridor*100:.0f}cm): Xoay trai"
                self.send_cmd("S -22.0 22.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"NE VAT CAN GAP ({min_front_corridor*100:.0f}cm): Xoay phai"
                self.send_cmd("S 22.0 -22.0", autonomous=False)

        # CẤP 2: ĐẾN GẦN VẬT CẢN TRƯỚC MẶT (24cm - 40cm) -> Lượn vòng né sớm
        elif min_front_corridor < 0.40:
            if avg_left >= avg_right:
                with state.lock: state.explore_phase = f"LUON NE VAT CAN ({min_front_corridor*100:.0f}cm): Re trai"
                self.send_cmd("S 12.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"LUON NE VAT CAN ({min_front_corridor*100:.0f}cm): Re phai"
                self.send_cmd("S 25.0 12.0", autonomous=False)

        # CẤP 3: KHÔNG GIAN THÔNG THOÁNG (> 40cm) -> Tiến đều êm ái 35 RPM
        else:
            with state.lock: state.explore_phase = f"QUET MAP AN TOAN (Trong: {min_front_corridor*100:.0f}cm)"
            self.send_cmd("S 35.0 35.0", autonomous=False)"""

import re
code = re.sub(r'        # Tính toán vật cản thực tế trong hệ quy chiếu thân xe[\s\S]*?(?=    def close_control)', corridor_nav_logic + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY IMPLEMENTED CORRIDOR CENTERING NAVIGATION")
