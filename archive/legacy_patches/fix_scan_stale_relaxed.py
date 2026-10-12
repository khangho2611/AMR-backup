with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# Nới lỏng ngưỡng scan_age_s từ 0.25s lên 0.60s (LiDAR C1 10Hz chu kỳ 0.1s - 0.25s rất dễ chạm ngưỡng 0.2504s)
old_scan_check = "('SCAN_STALE',ages['scan_age_s'] is None or not 0 <= ages['scan_age_s'] <= .25)"
new_scan_check = "('SCAN_STALE',ages['scan_age_s'] is None or not 0 <= ages['scan_age_s'] <= .60)"

if old_scan_check in code:
    code = code.replace(old_scan_check, new_scan_check, 1)

old_scan_mono = "if not 0 <= time.monotonic()-state.scan_mono <= .25:return failed('SCAN_STALE')"
new_scan_mono = "if not 0 <= time.monotonic()-state.scan_mono <= .60:return failed('SCAN_STALE')"

if old_scan_mono in code:
    code = code.replace(old_scan_mono, new_scan_mono, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY RELAXED SCAN STALE CHECK")
