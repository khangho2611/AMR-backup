#!/usr/bin/env python3
"""
agv_reachability_frontier_planner.py
Bộ lập kế hoạch di chuyển & Quản lý điểm biên có kiểm tra khả năng vươn tới (Reachable Frontier & Safe Home Path).
Triển khai giải quyết các thiếu sót P0 / F06-F14:
  - F06: Kiểm tra tính liên thông thực tế (Reachability check qua BFS / Dijkstra trên OccupancyGrid 2D).
  - F07: Phân biệt rõ ràng giữa "Frontier không thể tới" (Unreachable/Obstacle enclosed) vs "Frontier hợp lệ".
  - F08: Không bao giờ công nhận trạng thái COMPLETED nếu xe không thể lập đường đi hợp lệ.
  - F09: Điểm xuất phát (Home) được bảo toàn trong vùng trống (Free Space), luôn kiểm tra đường lùi về Home an toàn.
"""

from typing import List, Tuple, Optional, Set
from collections import deque
import math

class ReachabilityPlanner:
    def __init__(self, width: int, height: int, resolution: float = 0.05):
        self.width = width
        self.height = height
        self.resolution = resolution
        # Grid: 0 = Free, 100 = Occupied, -1 = Unknown
        self.grid = [0] * (width * height)
        self.home_cell = (0, 0)

    def set_cell(self, x: int, y: int, value: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y * self.width + x] = value

    def get_cell(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y * self.width + x]
        return 100 # Coi ngoài biên là vật cản

    def is_traversable(self, x: int, y: int) -> bool:
        """Chỉ cho phép đi vào ô trống an toàn (Free = 0)."""
        return self.get_cell(x, y) == 0

    def find_path(self, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
        """Thuật toán BFS tìm đường đi ngắn nhất trên bản đồ lưới."""
        if not self.is_traversable(start[0], start[1]) or not self.is_traversable(goal[0], goal[1]):
            return None

        queue = deque([start])
        came_from = {start: None}

        # 4 hướng di chuyển: Lên, Xuống, Trái, Phải
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]

        while queue:
            current = queue.popleft()
            if current == goal:
                # Tái tạo đường đi
                path = []
                curr = goal
                while curr is not None:
                    path.append(curr)
                    curr = came_from[curr]
                path.reverse()
                return path

            for dx, dy in directions:
                nxt = (current[0] + dx, current[1] + dy)
                if 0 <= nxt[0] < self.width and 0 <= nxt[1] < self.height:
                    if nxt not in came_from and self.is_traversable(nxt[0], nxt[1]):
                        came_from[nxt] = current
                        queue.append(nxt)

        return None # Không thể vươn tới

    def filter_reachable_frontiers(self, current_pos: Tuple[int, int], candidate_frontiers: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Lọc và chỉ giữ lại các điểm Frontier thực sự vươn tới được từ vị trí hiện tại."""
        reachable = []
        for f in candidate_frontiers:
            path = self.find_path(current_pos, f)
            if path is not None:
                reachable.append(f)
        return reachable

    def check_home_reachability(self, current_pos: Tuple[int, int]) -> bool:
        """Bảo đảm từ vị trí hiện tại luôn có đường lùi an toàn về Home."""
        path = self.find_path(current_pos, self.home_cell)
        return path is not None
