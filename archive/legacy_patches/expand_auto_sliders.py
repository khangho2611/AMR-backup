# SCRIPT MỞ RỘNG DẢI THANH TRƯỢT AUTO LÊN TỐI ĐA 140 RPM:
# 1. Slider Tốc độ tiến AUTO: từ 15 RPM lên tối đa 140 RPM
# 2. Slider Tốc độ quay AUTO: từ 10 RPM lên tối đa 90 RPM

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Thay thế max="60" thành max="140" cho sliderAutoSpeed
html = html.replace('id="sliderAutoSpeed" min="15" max="60"', 'id="sliderAutoSpeed" min="15" max="140"')

# Thay thế max="45" thành max="90" cho sliderAutoTurn
html = html.replace('id="sliderAutoTurn" min="10" max="45"', 'id="sliderAutoTurn" min="10" max="90"')

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("SUCCESSFULLY EXPANDED AUTO SLIDERS: Speed up to 140 RPM, Turn up to 90 RPM")

# Cập nhật backend agv_unified_brain.py để không kẹp giới hạn 35 RPM
with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r', encoding='utf-8') as f:
    py = f.read()

# Nâng trần bão hòa trong A* Pure Pursuit từ 35.0 lên state.auto_fwd_rpm
py = py.replace('rpm_l = max(10.0, min(35.0, (vl * 60.0) / (2.0 * math.pi * R)))', 'rpm_l = max(10.0, min(state.auto_fwd_rpm, (vl * 60.0) / (2.0 * math.pi * R)))')
py = py.replace('rpm_r = max(10.0, min(35.0, (vr * 60.0) / (2.0 * math.pi * R)))', 'rpm_r = max(10.0, min(state.auto_fwd_rpm, (vr * 60.0) / (2.0 * math.pi * R)))')

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w', encoding='utf-8') as f:
    f.write(py)

print("SUCCESSFULLY UNLEASHED BACKEND AUTO RPM CAP UP TO 140 RPM")
