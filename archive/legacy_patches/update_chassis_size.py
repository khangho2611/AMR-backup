with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# ĐIỀU CHỈNH KÍCH THƯỚC BỘ KHUNG THEO YÊU CẦU CỦA KHANG:
# Chiều rộng: 22 cm (0.22 m) -> Nửa chiều rộng HALF_WID = 0.110 m (11.0 cm)
# Chiều dài:  28 cm (0.28 m) -> Nửa chiều dài HALF_LEN = 0.140 m (14.0 cm)

import re

# Thay thế HALF_LEN và HALF_WID trong code
code = re.sub(r'HALF_LEN\s*=\s*0\.\d+', 'HALF_LEN = 0.140', code)
code = re.sub(r'HALF_WID\s*=\s*0\.\d+', 'HALF_WID = 0.110', code)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY UPDATED CHASSIS BOUNDS: Width = 22cm (HALF_WID = 0.110m), Length = 28cm (HALF_LEN = 0.140m)")
