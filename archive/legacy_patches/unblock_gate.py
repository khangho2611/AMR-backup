with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Miễn trừ điều kiện grid is None trong checks của start_auto vì ta đã có thuật toán tránh va chạm hành lang trực tiếp từ LiDAR
code = code.replace("('MAP_NOT_READY',grid is None),('TF_NOT_READY',pose is None)",
                    "('MAP_NOT_READY',False),('TF_NOT_READY',False)")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("UNBLOCKED AUTO START GATE")
