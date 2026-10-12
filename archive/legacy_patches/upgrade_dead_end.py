with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# NÂNG CẤP THUẬT TOÁN: TỰ ĐỘNG THOÁT NGÕ CỤT & QUAY ĐẦU TÌM ĐƯỜNG MỚI (DEAD-END ESCAPE & 180 REVERSE)
# 1. Nhận diện "Ngõ cụt" (Dead-End):
#    - Phía trước bị chặn (< 25cm)
#    - VÀ cả 2 bên sườn trái/phải cũng hẹp (avg_left < 30cm và avg_right < 30cm) hoặc xoay qua lại mà không thoát
# 2. Xử lý thông minh:
#    - Bước 1: Lùi thẳng an toàn ra khỏi ngõ cụt 25 RPM (nếu phía sau thoáng)
#    - Bước 2: Xoay đầu 180 độ quay về hướng cũ để tìm các vùng không gian mở khác trong phòng chưa quét!

dead_end_logic = """        # 2. Đo khoảng cách phía sau lưng (rear clearance) để dự phòng lùi xe
        rear_ranges = [points[d % 360] for d in range(155, 206) if points[d % 360] > 0.05]
        min_rear = min(rear_ranges) if rear_ranges else 1.0

        with state.lock:
            state.target_goal_x = 0.0
            state.target_goal_y = 0.0

        # PHÁT HIỆN NGÕ CỤT (DEAD-END): Phía trước bị bít (< 24cm) và cả 2 bên sườn đều chật hẹp (< 32cm)
        is_dead_end = (min_front_corridor < 0.24) and (avg_left < 0.32 and avg_right < 0.32)

        # TRƯỜNG HỢP 1: NGÕ CỤT HOÀN TOÀN -> LÙI RA VÀ QUAY ĐẦU TÌM HƯỚNG MỚI
        if is_dead_end:
            if min_rear > 0.25:
                # Phía sau còn đường lùi -> Lùi thẳng thoát ngõ cụt 25 RPM
                with state.lock: state.explore_phase = f"NGO CUT: Lui thang thoat hiem ({min_front_corridor*100:.0f}cm)"
                self.send_cmd("S -25.0 -25.0", autonomous=False)
            else:
                # Phía sau cũng gần tường -> Xoay ngược đầu 180 độ sang bên có khoảng trống lớn hơn
                if avg_left >= avg_right:
                    with state.lock: state.explore_phase = "NGO CUT: Quay dau 180 do sang trai"
                    self.send_cmd("S -28.0 28.0", autonomous=False)
                else:
                    with state.lock: state.explore_phase = "NGO CUT: Quay dau 180 do sang phai"
                    self.send_cmd("S 28.0 -28.0", autonomous=False)

        # TRƯỜNG HỢP 2: KHE HẸP / CỬA PHÒNG (2 bên có vật cản nhưng phía trước trống)
        elif (min_left_flank < 0.28 or min_right_flank < 0.28) and (min_front_corridor > 0.30):
            if min_left_flank < min_right_flank - 0.04:
                with state.lock: state.explore_phase = f"THOAT KHE: Lech phai (L:{min_left_flank*100:.0f}cm R:{min_right_flank*100:.0f}cm)"
                self.send_cmd("S 32.0 30.0", autonomous=False)
            elif min_right_flank < min_left_flank - 0.04:
                with state.lock: state.explore_phase = f"THOAT KHE: Lech trai (L:{min_left_flank*100:.0f}cm R:{min_right_flank*100:.0f}cm)"
                self.send_cmd("S 30.0 32.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = "THOAT KHE: Tien thang giua 2 vat can"
                self.send_cmd("S 30.0 30.0", autonomous=False)

        # TRƯỜNG HỢP 3: CỰC SÁT VẬT CẢN TRƯỚC MẶT (< 24cm) nhưng 1 bên hông thoáng -> Bẻ góc sang bên thoáng
        elif min_front_corridor < 0.24:
            if avg_left >= avg_right:
                with state.lock: state.explore_phase = f"RE TRANH ({min_front_corridor*100:.0f}cm): Sang trai ({avg_left*100:.0f}cm)"
                self.send_cmd("S -25.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"RE TRANH ({min_front_corridor*100:.0f}cm): Sang phai ({avg_right*100:.0f}cm)"
                self.send_cmd("S 25.0 -25.0", autonomous=False)

        # TRƯỜNG HỢP 4: GẦN VẬT CẢN (24cm - 40cm) -> Lượn vòng né sớm
        elif min_front_corridor < 0.40:
            if avg_left >= avg_right:
                with state.lock: state.explore_phase = f"LUON NE ({min_front_corridor*100:.0f}cm): Vong trai"
                self.send_cmd("S 12.0 25.0", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"LUON NE ({min_front_corridor*100:.0f}cm): Vong phai"
                self.send_cmd("S 25.0 12.0", autonomous=False)

        # TRƯỜNG HỢP 5: THÔNG THOÁNG (> 40cm) -> Tiến đều êm ái 35 RPM
        else:
            with state.lock: state.explore_phase = f"QUET MAP AN TOAN (Trong: {min_front_corridor*100:.0f}cm)"
            self.send_cmd("S 35.0 35.0", autonomous=False)"""

import re
code = re.sub(r'        with state\.lock:\n            state\.target_goal_x = 0\.0[\s\S]*?(?=    def close_control)', dead_end_logic + "\n\n", code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY IMPLEMENTED DEAD-END ESCAPE & 180-DEGREE RETURN")
