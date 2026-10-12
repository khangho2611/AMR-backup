with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# 1. Hạ margin an toàn tường (wall_margin_m) từ 15cm xuống 5cm để xe đi lọt hành lang
old_margin = "        self.wall_margin_m = .15"
new_margin = "        self.wall_margin_m = .05"

if old_margin in code:
    code = code.replace(old_margin, new_margin, 1)

# 2. Sửa điều kiện gắt gao làm xe đứng HOLD vùng đỏ
# Khi xe ở mép tường, không bắt đứng im HOLD mà tự động lùi hoặc quay thoát ngay
old_red_check = """        if not grid.traversable(grid.world_to_cell(*pose[:2])) or not grid.swept_clear(pose,0.,0.):
            if self._enter_cautious(pose):
                self._hold('VÙNG VÀNG: chọn đường chậm đủ thân xe')
            elif not self._try_escape():
                self._hold('HOLD: chưa có đường thoát vùng đỏ đủ thân xe')
            return"""

new_red_check = """        if not grid.traversable(grid.world_to_cell(*pose[:2])) or not grid.swept_clear(pose,0.,0.):
            if self._enter_cautious(pose):
                pass # Đã vào vùng vàng, tiếp tục chạy dò đường
            elif self._try_escape():
                return
            else:
                # Nếu chưa tìm được đường thoát lý tưởng, nhích lùi nhẹ để tạo khoảng cách với vật cản
                self.send_cmd('V -0.030 0.000', autonomous=True)
                with state.lock: state.explore_phase = 'TỰ HÀNH: nhích lùi tạo khoảng trống'
                return"""

if old_red_check in code:
    code = code.replace(old_red_check, new_red_check, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED UNBLOCK HOLD LOGIC")
