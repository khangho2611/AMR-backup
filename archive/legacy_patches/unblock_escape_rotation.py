# 1. Sửa agv_navigation.py
with open('/home/khangho/agv_codex_reader_20261003_0652/agv_navigation.py', 'r') as f:
    nav_code = f.read()

# Cho phép v == 0 khi w != 0 (xoay tại chỗ)
old_v_zero = "if len(pose)!=3 or not all(finite(x) for x in pose) or v==0:return False"
new_v_zero = "if len(pose)!=3 or not all(finite(x) for x in pose) or (v==0 and w==0):return False"

if old_v_zero in nav_code:
    nav_code = nav_code.replace(old_v_zero, new_v_zero, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_navigation.py', 'w') as f:
    f.write(nav_code)

# 2. Sửa agv_command_session.py
with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'r') as f:
    sess_code = f.read()

# Cho phép lệnh thoát có v == 0 khi w != 0
old_escape_check = "if escape and (not autonomous or parts[0]!='V' or abs(values[0])>.04 or values[0]==0):"
new_escape_check = "if escape and (not autonomous or parts[0]!='V' or abs(values[0])>.04 or (values[0]==0 and values[1]==0)):"

if old_escape_check in sess_code:
    sess_code = sess_code.replace(old_escape_check, new_escape_check, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_command_session.py', 'w') as f:
    f.write(sess_code)

print("SUCCESSFULLY UNBLOCKED IN-PLACE ROTATION FOR ESCAPE")
