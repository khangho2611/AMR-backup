with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r', encoding='utf-8') as f:
    code = f.read()

# BIẾN XE THÀNH HỆ THỐNG BIẾN THIÊN TỐC ĐỘ ĐỘNG (DYNAMIC SPEED GEARING: CHẬM - BÌNH THƯỜNG - NHANH)
# Không bao giờ chạy đúng 1 tốc độ chết cứng!
# 1. MỨC NHANH (FAST): Khi phía trước thoáng đãng (> 1.2m) hoặc đang trên đường A* dài -> Phóng kịch tốc độ max_rpm (60 - 90 RPM)!
# 2. MỨC BÌNH THƯỜNG (NORMAL): Khi đang đi trong hành lang, có vật cản vừa phải (0.6m - 1.2m) -> Đi 40 - 50 RPM mượt mà.
# 3. MỨC CHẬM (SLOW/CREEP): Khi áp sát vật cản (0.26m - 0.6m) hoặc lách khe hẹp -> Tự động hãm phanh bò chậm 18 - 25 RPM để luồn lách an toàn!

dynamic_speed_logic = """        # -------------------------------------------------------------
        # TỰ ĐỘNG BIẾN THIÊN 3 CẤP TỐC ĐỘ: CHẬM - BÌNH THƯỜNG - NHANH
        # -------------------------------------------------------------
        max_rpm = getattr(state, 'auto_fwd_rpm', 60.0)
        turn_rpm = getattr(state, 'auto_turn_rpm', 25.0)

        # Tính toán mức tốc độ thích ứng dựa trên cự ly vật cản phía trước
        if min_front_dist > 1.20:
            # 🚀 CẤP NHANH (FAST): Phía trước trống trải > 1.2m -> Phóng tối đa!
            target_fwd_rpm = max_rpm
            speed_mode = "NHANH"
        elif min_front_dist > 0.60:
            # ⚡ CẤP BÌNH THƯỜNG (NORMAL): Cự ly trung bình 0.6m - 1.2m -> Chạy 60% công suất
            target_fwd_rpm = max(25.0, max_rpm * 0.60)
            speed_mode = "BINH THUONG"
        else:
            # 🐢 CẤP CHẬM (SLOW): Áp sát vật cản 0.26m - 0.6m -> Bò chậm 35% công suất để né mượt
            target_fwd_rpm = max(18.0, max_rpm * 0.35)
            speed_mode = "CHAM"

        # -------------------------------------------------------------
        # 5. LƯỢN TRÁNH VẬT CẢN TỪ XA (26cm - 65cm) THEO ĐƯỜNG CONG DWA
        # -------------------------------------------------------------
        if min_front_dist < 0.65:
            # Tốc độ giảm dần tỷ lệ thuận theo cự ly
            spd = 16.0 + (min_front_dist - 0.26) * 20.0
            if min_left_dist >= min_right_dist:
                with state.lock: state.explore_phase = f"DWA [{speed_mode}]: Luon trai ({min_front_dist*100:.0f}cm)"
                self.send_cmd(f"S {spd*0.4:.1f} {spd*1.0:.1f}", autonomous=False)
            else:
                with state.lock: state.explore_phase = f"DWA [{speed_mode}]: Luon phai ({min_front_dist*100:.0f}cm)"
                self.send_cmd(f"S {spd*1.0:.1f} {spd*0.4:.1f}", autonomous=False)
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
                    # Đổi target_fwd_rpm sang vận tốc dài m/s tương ứng
                    v = (target_fwd_rpm * 2.0 * math.pi * R) / 60.0
                    w = max(-0.4, min(0.4, 0.8 * err_ang))

                    vl = v - w * (L / 2.0)
                    vr = v + w * (L / 2.0)
                    rpm_l = max(10.0, min(target_fwd_rpm, (vl * 60.0) / (2.0 * math.pi * R)))
                    rpm_r = max(10.0, min(target_fwd_rpm, (vr * 60.0) / (2.0 * math.pi * R)))

                    with state.lock: state.explore_phase = f"A* [{speed_mode} {target_fwd_rpm:.0f}RPM] -> {dist_goal:.2f}m"
                    self.send_cmd(f"S {rpm_l:.1f} {rpm_r:.1f}", autonomous=False)
                    return

        # VÙNG RỘNG RÃI HOÀN TOÀN -> CHẠY THEO MỨC TỐC ĐỘ THÍCH ỨNG
        with state.lock: state.explore_phase = f"QUET MO RONG [{speed_mode}: {target_fwd_rpm:.0f} RPM]"
        self.send_cmd(f"S {target_fwd_rpm:.1f} {target_fwd_rpm:.1f}", autonomous=False)"""

import re
pattern = r'# -------------------------------------------------------------\s*# 5\. LƯỢN TRÁNH VẬT CẢN TỪ XA[\s\S]*?self\.send_cmd\(f"S {state\.auto_fwd_rpm:\.1f} {state\.auto_fwd_rpm:\.1f}", autonomous=False\)'

code = re.sub(pattern, dynamic_speed_logic, code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED DYNAMIC 3-GEAR SPEED LOGIC (SLOW - NORMAL - FAST)")
