with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    bcode = f.read()

# Khi tìm thấy frontier mà self.goal is None, nếu có frontier thô thì lấy ngay mục tiêu thoáng nhất!
old_logic = """        if self.goal is None:
            with state.lock:
                remaining = state.frontier_reachable
            if remaining == 0:
                self.explore_state = 'RETURNING_HOME'
                self._hold('Hết frontier reachable; về home, unknown khác còn chưa nghiệm thu')
            else:
                self._hold('HOLD: frontier còn nhưng chưa có mục tiêu an toàn mới')
            return"""

new_logic = """        if self.goal is None:
            # Fallback thong minh: Tim o trong known-free cach xa nhat ve phia truoc de di tiep
            grid = self._grid()
            if grid is not None:
                # Quet cac o reachable cach tu 0.3m den 1.0m
                best_pt = None
                max_d = 0.0
                cx, cy = grid.world_to_cell(*pose[:2])
                for dx in range(-15, 16):
                    for dy in range(-15, 16):
                        cell = (cx + dx, cy + dy)
                        if grid.traversable(cell):
                            wx, wy = grid.cell_to_world(*cell)
                            d = math.hypot(wx - pose[0], wy - pose[1])
                            if 0.25 <= d <= 1.0 and d > max_d:
                                max_d = d
                                best_pt = (wx, wy)
                if best_pt is not None:
                    self.goal = best_pt
            if self.goal is None:
                self._hold('Dang quet tim huong thoang...')
                return"""

bcode = bcode.replace(old_logic, new_logic)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(bcode)

print("INTEGRATED CONTINUOUS FRONTIER FALLBACK")
