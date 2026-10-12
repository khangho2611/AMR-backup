# SCRIPT THÊM 2 SLIDER ĐIỀU CHỈNH TỐC ĐỘ VÀ TỐC ĐỘ QUAY CHO CHẾ ĐỘ AUTO:
# 1. Slider Auto RPM Tiến: 15 RPM đến 60 RPM (Mặc định 30 RPM)
# 2. Slider Auto RPM Quay: 10 RPM đến 45 RPM (Mặc định 22 RPM)
# 3. Tự động gửi API /api/auto_config?speed=...&turn=... xuống con Pi và cập nhật ngay lập tức!

# Đọc file HTML
with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'r', encoding='utf-8') as f:
    html = f.read()

auto_sliders_html = """
          <!-- SLIDER ĐIỀU CHỈNH CHẾ ĐỘ AUTO (RPM PID) -->
          <div style="background: rgba(0, 240, 255, 0.05); border: 1px solid rgba(0, 240, 255, 0.3); border-radius: 6px; padding: 10px; margin-bottom: 12px;">
            <div style="font-size: 10px; font-weight: bold; color: var(--cyan); margin-bottom: 6px; text-transform: uppercase;">⚡ CẤU HÌNH TỰ ĐỘNG QUÉT MAP (AUTO PID)</div>
            <div style="margin-bottom: 8px;">
              <div style="display: flex; justify-content: space-between; font-size: 9px; color: var(--text-muted); margin-bottom: 2px;">
                <span>Tốc độ tiến AUTO (Target RPM)</span>
                <span id="valAutoSpeedLbl" style="color: var(--cyan); font-weight:bold;">30 RPM</span>
              </div>
              <input type="range" id="sliderAutoSpeed" min="15" max="60" value="30" step="1" style="width: 100%; cursor: pointer;" oninput="updateAutoParams()">
            </div>
            <div>
              <div style="display: flex; justify-content: space-between; font-size: 9px; color: var(--text-muted); margin-bottom: 2px;">
                <span>Tốc độ quay AUTO (Target RPM)</span>
                <span id="valAutoTurnLbl" style="color: var(--cyan); font-weight:bold;">22 RPM</span>
              </div>
              <input type="range" id="sliderAutoTurn" min="10" max="45" value="22" step="1" style="width: 100%; cursor: pointer;" oninput="updateAutoParams()">
            </div>
          </div>
"""

# Chèn vào trước cụm điều khiển lái tay
target_pos = html.find('<!-- THANH TRƯỢT PWM TỐC ĐỘ VÀ QUAY -->')
if target_pos != -1:
    html = html[:target_pos] + auto_sliders_html + html[target_pos:]
else:
    # Nếu không tìm thấy comment thì chèn trước <div class="dpad-grid">
    target_pos = html.find('<div class="dpad-grid">')
    html = html[:target_pos] + auto_sliders_html + html[target_pos:]

# Thêm hàm JavaScript updateAutoParams()
js_func = """
    function updateAutoParams() {
      const spd = parseInt(document.getElementById('sliderAutoSpeed').value);
      const turn = parseInt(document.getElementById('sliderAutoTurn').value);
      document.getElementById('valAutoSpeedLbl').innerText = spd + " RPM";
      document.getElementById('valAutoTurnLbl').innerText = turn + " RPM";
      fetch(`/api/auto_config?speed=${spd}&turn=${turn}`).catch(e => console.error(e));
    }
"""

html = html.replace('function updateDriveParams() {', js_func + '\n    function updateDriveParams() {')

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("SUCCESSFULLY INJECTED AUTO SLIDERS INTO HTML")

# 2. CẬP NHẬT BACKEND PYTHON ĐỂ NHẬN API /api/auto_config VÀ ĂN VÀO VÒNG LẶP AUTO
with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r', encoding='utf-8') as f:
    py = f.read()

# Thêm biến auto_fwd_rpm và auto_turn_rpm vào GlobalState
if 'self.auto_fwd_rpm = 30.0' not in py:
    py = py.replace('class GlobalState:', 'class GlobalState:\n    auto_fwd_rpm = 30.0\n    auto_turn_rpm = 22.0')

# Xử lý API endpoint /api/auto_config
api_code = """        elif path == '/api/auto_config':
            import urllib.parse
            params = urllib.parse.parse_qs(q)
            try:
                if 'speed' in params:
                    with state.lock: state.auto_fwd_rpm = float(params['speed'][0])
                if 'turn' in params:
                    with state.lock: state.auto_turn_rpm = float(params['turn'][0])
                self._json(200, {'status': 'OK', 'speed': state.auto_fwd_rpm, 'turn': state.auto_turn_rpm})
            except Exception as e:
                self._json(400, {'status': 'ERROR', 'msg': str(e)})
            return
"""

py = py.replace("elif path == '/api/pid':", api_code + "\n        elif path == '/api/pid':")

# Cập nhật vòng lặp auto_nav_loop để ăn trực tiếp theo state.auto_fwd_rpm và state.auto_turn_rpm
py = py.replace('self.send_cmd("S 30.0 30.0", autonomous=False)', 'self.send_cmd(f"S {state.auto_fwd_rpm:.1f} {state.auto_fwd_rpm:.1f}", autonomous=False)')
py = py.replace('turn_dir = 22.0', 'turn_dir = state.auto_turn_rpm')
py = py.replace('self.send_cmd("S -22.0 -22.0", autonomous=False)', 'self.send_cmd(f"S {-state.auto_turn_rpm:.1f} {-state.auto_turn_rpm:.1f}", autonomous=False)')

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w', encoding='utf-8') as f:
    f.write(py)

print("SUCCESSFULLY UPDATED BACKEND agv_unified_brain.py FOR REALTIME AUTO SLIDER TUNING")
