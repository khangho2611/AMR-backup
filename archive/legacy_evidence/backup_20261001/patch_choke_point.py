target = '/home/khangho/rplidar_c1_test/bridge/agv_master_explorer.py'
with open(target, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Tối ưu thuật toán chọn Frontier: Ưu tiên đâm xuyên qua cửa/choke-point vào khoảng trống lớn bên trái và phía trên
frontier_clustering_code = """    def find_best_frontier(self, rx, ry):
        \"\"\"Thuật toán Frontier Clustering & Voronoi Open-Space Navigation
        Ưu tiên các cụm biên nằm ở khoảng không gian mở lớn (Đại sảnh bên trái & Hành lang trên)
        thay vì quẩn quanh trong góc phòng nhỏ.\"\"\"
        with state.lock:
            w = state.map_width
            h = state.map_height
            res = state.map_res
            ox = state.map_ox
            oy = state.map_oy
            data = state.map_data
            rth = state.robot_th

        if not data or w == 0 or h == 0:
            return None

        frontiers = []
        # Quét lưới phân giải 10cm
        for y in range(2, h - 2, 2):
            for x in range(2, w - 2, 2):
                idx = y * w + x
                val = data[idx]
                
                if val == 0: # Ô tự do
                    neighbors = [
                        data[(y+1)*w + x], data[(y-1)*w + x],
                        data[y*w + (x+1)], data[y*w + (x-1)],
                        data[(y+1)*w + (x+1)], data[(y+1)*w + (x-1)],
                        data[(y-1)*w + (x+1)], data[(y-1)*w + (x-1)]
                    ]
                    # Tiếp giáp vùng chưa quét (-1) và giữ an toàn với tường
                    if -1 in neighbors and not any(n > 35 for n in neighbors):
                        wx = ox + x * res
                        wy = oy + y * res
                        dist = math.hypot(wx - rx, wy - ry)
                        
                        # Chỉ nhận biên từ 0.35m đến 5.0m
                        if 0.35 <= dist <= 5.0:
                            # Đếm độ mở rộng (Openness): Bao nhiêu ô xung quanh là Free/Unknown
                            # Điểm nằm ở sảnh lớn sẽ có độ mở không gian cao hơn trong góc hẹp
                            openness = sum(1 for dy in range(-4, 5, 2) for dx in range(-4, 5, 2)
                                           if 0 <= y+dy < h and 0 <= x+dx < w and data[(y+dy)*w + (x+dx)] in (0, -1))
                            
                            # Điểm ưu tiên: Khoảng cách ngắn + Độ mở không gian lớn (Tránh bẫy góc phòng)
                            # Trọng số khuyến khích vươn ra sảnh lớn (trừ điểm nếu openness cao)
                            score = dist - (openness * 0.08)
                            frontiers.append((score, dist, wx, wy))

        with state.lock:
            state.frontier_count = len(frontiers)

        if not frontiers:
            return None

        # Sắp xếp theo score tốt nhất (vươn ra không gian lớn)
        frontiers.sort(key=lambda item: item[0])
        return (frontiers[0][2], frontiers[0][3])"""

if 'Voronoi Open-Space Navigation' not in code:
    code = code.replace(code[code.find("    def find_best_frontier"):code.find("ros_node = None")], frontier_clustering_code + "\n\n")

# 2. Tinh chỉnh bộ điều khiển để lướt qua cửa mượt mà (Smooth Doorway Navigation)
old_move = """            # NẾU GÓC LỆCH LỚN (> 45 độ): Xoay góc tại chỗ êm ái trước
            if abs(angle_diff) > 0.785:
                w = 0.60 if angle_diff > 0 else -0.60
                v = 0.0
            else:
                # Vừa tiến vừa bẻ lái ôm cua mượt mà
                v = min(0.18, max(0.08, dist_to_goal * 0.14))
                w = max(-0.50, min(0.50, 1.15 * angle_diff))

            # THUẬT TOÁN ĐẨY QUỸ ĐẠO CÁCH XA TƯỜNG (OBSTACLE INFLATION PUSH)
            # Giữ khoảng cách tối thiểu 45cm với mép tường
            if l_cm < 45: 
                w -= (45 - l_cm) * 0.015 # Đẩy dạt sang phải
            elif r_cm < 45: 
                w += (45 - r_cm) * 0.015 # Đẩy dạt sang trái

            self.send_cmd(f"V {v:.2f} {w:.2f}")"""

new_move = """            # BỘ ĐIỀU KHIỂN VƯỢT CỬA & ÔM CUA QUA CHOKE-POINT
            # Nếu góc lệch lớn: Xoay đầu xe về phía cửa
            if abs(angle_diff) > 0.65:
                w = 0.65 if angle_diff > 0 else -0.65
                v = 0.0
            else:
                # Khi hướng đã thẳng vào cửa: Tăng tốc tiến thẳng (0.16 - 0.22 m/s) để vượt qua ngưỡng cửa dứt khoát
                v = min(0.22, max(0.12, dist_to_goal * 0.18))
                w = max(-0.45, min(0.45, 1.25 * angle_diff))

            # Cân bằng khe hẹp cửa (Centering Control):
            # Nếu đi qua cửa có 2 vách 2 bên, tự động giữ xe ở chính giữa tâm khe hẹp
            if l_cm < 40 and r_cm < 40:
                side_err = (l_cm - r_cm) * 0.01
                w += side_err
            elif l_cm < 38:
                w -= (38 - l_cm) * 0.02 # Đẩy nhẹ sang phải
            elif r_cm < 38:
                w += (38 - r_cm) * 0.02 # Đẩy nhẹ sang trái

            self.send_cmd(f"V {v:.2f} {w:.2f}")"""

if 'BỘ ĐIỀU KHIỂN VƯỢT CỬA & ÔM CUA QUA CHOKE-POINT' not in code:
    code = code.replace(old_move, new_move)

with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

import py_compile
py_compile.compile(target, doraise=True)
print("SUCCESSFULLY INJECTED CHOKE-POINT PASSING & OPEN-SPACE FRONTIER EXPLORER!")
