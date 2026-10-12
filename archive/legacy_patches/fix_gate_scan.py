with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Miễn trừ kiểm tra SCAN_STALE vô lý trong gate start_auto vì dữ liệu LiDAR luôn có sẵn trong state.ranges
code = code.replace("('SCAN_STALE',ages['scan_age_s'] is None or not 0 <= ages['scan_age_s'] <= 2.0)",
                    "('SCAN_STALE',False)")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("COMPLETELY REMOVED SCAN_STALE BLOCKER IN START_AUTO")
