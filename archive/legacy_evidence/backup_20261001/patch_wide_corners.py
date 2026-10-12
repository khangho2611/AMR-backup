target = '/home/khangho/rplidar_c1_test/bridge/agv_master_explorer.py'
with open(target, 'r', encoding='utf-8') as f:
    code = f.read()

# Nâng cấp hàm find_best_frontier và cơ chế luồn lách men tường (Wall-following & Corner-rounding)
old_frontier_func = """    def find_best_frontier(self, rx, ry):
        \"\"\"Quét mảng OccupancyGrid tìm điểm biên giữa ô tự do (0) và ô chưa biết (-1)\"\"\"
        with state.lock:
            w = state.map_width
            h = state.map_height
            res = state.map_res
            ox = state.map_ox
            oy = state.map_oy
            data = state.map_data

        if not data or w == 0 or h == 0:
            return None

        frontiers = []
        # Quét lưới theo bước nhảy 4 ô để tối ưu tốc độ tính toán
        for y in range(2, h - 2, 4):
            for x in range(2, w - 2, 4):
                idx = y * w + x
                val = data[idx]
                
                # Điểm biên là ô trống (0) có ít nhất 1 ô lân cận là chưa biết (-1)
                if val == 0:
                    neighbors = [data[(y+1)*w + x], data[(y-1)*w + x], data[y*w + (x+1)], data[y*w + (x-1)]]
                    if -1 in neighbors and not any(n > 50 for n in neighbors):
                        # Tọa độ thực mét
                        wx = ox + x * res
                        wy = oy + y * res
                        dist = math.hypot(wx - rx, wy - ry)
                        # Chỉ chọn điểm cách xe ít nhất 0.5m để tránh rung lắc
                        if 0.5 <= dist <= 3.5:
                            frontiers.append((dist, wx, wy))

        with state.lock:
            state.frontier_count = len(frontiers)

        if not frontiers:
            return None

        # Sắp xếp chọn Frontier gần nhất
        frontiers.sort(key=lambda x: x[0])
        return (frontiers[0][1], frontiers[0][2])"""

new_frontier_func = """    def find_best_frontier(self, rx, ry):
        \"\"\"Quét toàn bộ ma trận OccupancyGrid /map tìm tất cả các góc chết và biên chưa quét\"\"\"
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
        # Bước nhảy 2 ô (độ phân giải 10cm) để không bỏ sót bất kỳ ngách hẹp hay góc chết nào
        for y in range(2, h - 2, 2):
            for x in range(2, w - 2, 2):
                idx = y * w + x
                val = data[idx]
                
                if val == 0: # Ô tự do đã xác nhận an toàn
                    # Kiểm tra 8 ô xung quanh để tìm ranh giới vùng mù (-1)
                    neighbors = [
                        data[(y+1)*w + x], data[(y-1)*w + x],
                        data[y*w + (x+1)], data[y*w + (x-1)],
                        data[(y+1)*w + (x+1)], data[(y+1)*w + (x-1)],
                        data[(y-1)*w + (x+1)], data[(y-1)*w + (x-1)]
                    ]
                    # Phải tiếp giáp với vùng chưa quét (-1) và giữ khoảng cách an toàn với tường (> 50)
                    if -1 in neighbors and not any(n > 40 for n in neighbors):
                        wx = ox + x * res
                        wy = oy + y * res
                        dist = math.hypot(wx - rx, wy - ry)
                        
                        # Chỉ chọn điểm từ 0.35m đến 4.5m
                        if 0.35 <= dist <= 4.5:
                            # Tính góc lệch hướng để ưu tiên điểm tiện đường đi nhất
                            ang_to_goal = math.atan2(wy - ry, wx - rx)
                            ang_diff = abs((ang_to_goal - rth + math.pi) % (2 * math.pi) - math.pi)
                            
                            # Điểm số Cost: Khoảng cách + Trọng số quay đầu
                            cost = dist + 0.8 * ang_diff
                            frontiers.append((cost, dist, wx, wy))

        with state.lock:
            state.frontier_count = len(frontiers)

        if not frontiers:
            return None

        # Sắp xếp chọn điểm Frontier có chi phí tối ưu nhất
        frontiers.sort(key=lambda item: item[0])
        return (frontiers[0][2], frontiers[0][3])"""

if 'Quét toàn bộ ma trận OccupancyGrid /map tìm tất cả các góc chết' not in code:
    code = code.replace(old_frontier_func, new_frontier_func)

# Nâng cấp logic di chuyển: Lượn bo góc quanh vách tường (Wide turn around convex corners)
old_drive_logic = """            # 3. Lái xe mượt mà hướng tới Frontier Goal
            gx, gy = goal
            with state.lock:
                state.target_goal_x = round(gx, 2)
                state.target_goal_y = round(gy, 2)

            dx = gx - rx
            dy = gy - ry
            dist_to_goal = math.hypot(dx, dy)
            target_angle = math.atan2(dy, dx)
            angle_diff = (target_angle - rth + math.pi) % (2 * math.pi) - math.pi

            # PID điều hướng tới mục tiêu
            if abs(angle_diff) > 0.60: # Góc lệch lớn: Quay đầu trước
                w = 0.65 if angle_diff > 0 else -0.65
                v = 0.05
            else:
                v = min(0.20, 0.08 + dist_to_goal * 0.15)
                w = max(-0.45, min(0.45, 1.2 * angle_diff))

            # Bù vật cản sườn 2 bên
            if l_cm < 40: w -= 0.20
            elif r_cm < 40: w += 0.20

            self.send_cmd(f\"V {v:.2f} {w:.2f}\")"""

new_drive_logic = """            # 3. Lái xe mượt mà hướng tới Frontier Goal (Có bộ uốn lượn né tường)
            gx, gy = goal
            with state.lock:
                state.target_goal_x = round(gx, 2)
                state.target_goal_y = round(gy, 2)

            dx = gx - rx
            dy = gy - ry
            dist_to_goal = math.hypot(dx, dy)
            target_angle = math.atan2(dy, dx)
            angle_diff = (target_angle - rth + math.pi) % (2 * math.pi) - math.pi

            # NẾU GÓC LỆCH LỚN (> 45 độ): Xoay góc tại chỗ êm ái trước
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

            self.send_cmd(f\"V {v:.2f} {w:.2f}\")"""

if 'THUẬT TOÁN ĐẨY QUỸ ĐẠO CÁCH XA TƯỜNG' not in code:
    code = code.replace(old_drive_logic, new_drive_logic)

with open(target, 'w', encoding='utf-8') as f:
    f.write(code)

import py_compile
py_compile.compile(target, doraise=True)
print("SUCCESSFULLY INJECTED WIDE-CORNER NAVIGATION & HIGH-RES FRONTIER EXPLORER!")
