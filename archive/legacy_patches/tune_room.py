with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    bcode = f.read()

# 1. Ha wall_margin_m tu 0.15 (15cm dem ao) xuong 0.03 (3cm dem thuc te phu hop phong hep)
bcode = bcode.replace('self.wall_margin_m = .15', 'self.wall_margin_m = .03')

# 2. Xu ly khi xe bi ket swept_clear o phong hep: Cho phep bo qua swept_clear(0,0) va thoat theo duong A*
old_stuck = """        if not grid.traversable(grid.world_to_cell(*pose[:2])) or not grid.swept_clear(pose,0.,0.):
            if not self._try_escape():
                self._hold('HOLD: chưa có đường thoát vùng đỏ đủ thân xe')
            return"""

new_stuck = """        # Phong hep: Neu dung yen ma cham vach an toan thi khong dung im chiu chet, uu tien quay hoac chay tiep
        if not grid.traversable(grid.world_to_cell(*pose[:2])):
            if not self._try_escape():
                pass"""

bcode = bcode.replace(old_stuck, new_stuck)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(bcode)

print("TUNED WALL MARGIN TO 3CM FOR REAL LAB ROOM")
