with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Soi rõ nguyên nhân vì sao HOLD trong auto_nav_loop:
# In ra log chính xác biến nào bị None (pose, grid hay scan_age)
old_hold_check = """        pose,grid = self._pose_map(),self._grid()
        if pose is None or grid is None or not 0 <= scan_age <= .60:
            self._hold('HOLD: chờ map, TF, scan hoặc kích thước thân xe')
            return"""

new_hold_check = """        pose,grid = self._pose_map(),self._grid()
        if pose is None or grid is None or not 0 <= scan_age <= .60:
            sub_reason = []
            if pose is None: sub_reason.append('TF_NONE')
            if grid is None: sub_reason.append('GRID_NONE')
            if not 0 <= scan_age <= .60: sub_reason.append(f'SCAN_AGE_{scan_age:.2f}')
            self._hold('HOLD: ' + '+'.join(sub_reason))
            return"""

if old_hold_check in code:
    code = code.replace(old_hold_check, new_hold_check, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED DIAGNOSTIC SUB_REASON")
