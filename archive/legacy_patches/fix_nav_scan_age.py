with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Sửa scan_age <= .25 thành scan_age <= .60 trong auto_nav_loop
old_check = "if pose is None or grid is None or not 0 <= scan_age <= .25:"
new_check = "if pose is None or grid is None or not 0 <= scan_age <= .60:"

if old_check in code:
    code = code.replace(old_check, new_check, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY RELAXED NAV LOOP SCAN AGE")
