import heapq
import math

def plan_astar_path(data, w, h, res, ox, oy, rx, ry, gx, gy):
    """
    Thuật toán A* Pathfinding kết hợp Costmap Inflation (tránh ôm tường):
    - data: mảng occupancy grid 1D (w x h)
    - inflation_cells: 3 ô (~15cm) đệm an toàn thân xe
    """
    if not data or w <= 0 or h <= 0:
        return None

    def w2m(wx, wy):
        mx = int((wx - ox) / res)
        my = int((wy - oy) / res)
        if 0 <= mx < w and 0 <= my < h:
            return (mx, my)
        return None

    def m2w(mx, my):
        return (ox + (mx + 0.5) * res, oy + (my + 0.5) * res)

    start_cell = w2m(rx, ry)
    goal_cell = w2m(gx, gy)
    if not start_cell or not goal_cell:
        return None

    # Tạo costmap / kiểm tra ô vật cản và vùng đệm lân cận
    def is_blocked(cx, cy):
        # Kiểm tra bán kính thân xe (3 ô ~ 15cm)
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    v = data[ny * w + nx]
                    if v > 40: # Vật cản hoặc tường
                        return True
                else:
                    return True
        return False

    # Nếu goal bị vướng tường, tìm ô free gần nhất
    if is_blocked(goal_cell[0], goal_cell[1]):
        found_alt = False
        for r in range(1, 6):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    cand = (goal_cell[0] + dx, goal_cell[1] + dy)
                    if 0 <= cand[0] < w and 0 <= cand[1] < h and not is_blocked(cand[0], cand[1]):
                        goal_cell = cand
                        found_alt = True
                        break
                if found_alt:
                    break
            if found_alt:
                break
        if not found_alt:
            return None

    # Thuật toán A* chuẩn
    pq = []
    start_h = math.hypot(goal_cell[0] - start_cell[0], goal_cell[1] - start_cell[1])
    heapq.heappush(pq, (start_h, 0, start_cell))
    came_from = {}
    cost_so_far = {start_cell: 0}
    dirs = [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]

    expanded = 0
    max_expand = 2500 # Ngăn nghẽn CPU

    while pq and expanded < max_expand:
        _, current_cost, current = heapq.heappop(pq)
        expanded += 1

        if current == goal_cell or math.hypot(current[0] - goal_cell[0], current[1] - goal_cell[1]) <= 1.5:
            # Reconstruct path
            path = []
            curr = current
            while curr in came_from:
                path.append(m2w(curr[0], curr[1]))
                curr = came_from[curr]
            path.reverse()
            return path

        for dx, dy in dirs:
            nx, ny = current[0] + dx, current[1] + dy
            if 0 <= nx < w and 0 <= ny < h:
                # Kiểm tra lọt khe/vật cản
                if is_blocked(nx, ny):
                    continue
                step_cost = 1.414 if (dx != 0 and dy != 0) else 1.0
                new_cost = current_cost + step_cost
                nxt = (nx, ny)
                if nxt not in cost_so_far or new_cost < cost_so_far[nxt]:
                    cost_so_far[nxt] = new_cost
                    h_val = math.hypot(goal_cell[0] - nx, goal_cell[1] - ny)
                    priority = new_cost + h_val
                    heapq.heappush(pq, (priority, new_cost, nxt))
                    came_from[nxt] = current

    return None
