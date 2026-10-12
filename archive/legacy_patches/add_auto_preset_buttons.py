with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'r', encoding='utf-8') as f:
    html = f.read()

# THIẾT KẾ CỤM 3 NÚT CHỌN PROFILE TỰ ĐỘNG [CHẬM] [TIÊU CHUẨN] [NHANH]
profile_buttons_html = """
            <!-- 3 MỨC PROFILE TỰ ĐỘNG (AUTO PRESETS) -->
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 10px;">
              <button type="button" onclick="setAutoProfile('slow')" style="background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; color: #10b981; border-radius: 4px; padding: 6px 2px; font-size: 10px; font-weight: bold; cursor: pointer; transition: all 0.2s;">
                🐢 CHẬM<br><span style="font-size: 8px; opacity: 0.8;">25 RPM / 0.35 PID</span>
              </button>
              <button type="button" onclick="setAutoProfile('normal')" style="background: rgba(0, 240, 255, 0.15); border: 1px solid #00f0ff; color: #00f0ff; border-radius: 4px; padding: 6px 2px; font-size: 10px; font-weight: bold; cursor: pointer; transition: all 0.2s;">
                ⚡ TIÊU CHUẨN<br><span style="font-size: 8px; opacity: 0.8;">50 RPM / 0.50 PID</span>
              </button>
              <button type="button" onclick="setAutoProfile('fast')" style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #ef4444; border-radius: 4px; padding: 6px 2px; font-size: 10px; font-weight: bold; cursor: pointer; transition: all 0.2s;">
                🚀 NHANH<br><span style="font-size: 8px; opacity: 0.8;">90 RPM / 0.70 PID</span>
              </button>
            </div>
"""

# Chèn vào ngay dưới tiêu đề ⚡ CẤU HÌNH TỰ ĐỘNG QUÉT MAP (AUTO PID)
html = html.replace('<div style="font-size: 10px; font-weight: bold; color: var(--cyan); margin-bottom: 6px; text-transform: uppercase;">⚡ CẤU HÌNH TỰ ĐỘNG QUÉT MAP (AUTO PID)</div>',
                    '<div style="font-size: 10px; font-weight: bold; color: var(--cyan); margin-bottom: 6px; text-transform: uppercase;">⚡ CẤU HÌNH TỰ ĐỘNG QUÉT MAP (AUTO PID)</div>' + profile_buttons_html)

# Thêm hàm JavaScript setAutoProfile(mode)
js_profile_func = """
    function setAutoProfile(mode) {
      let spd, turn, kp, ki, kd;
      if (mode === 'slow') {
        spd = 25; turn = 18; kp = 0.35; ki = 0.10; kd = 0.01;
      } else if (mode === 'fast') {
        spd = 90; turn = 45; kp = 0.70; ki = 0.15; kd = 0.05;
      } else { // normal
        spd = 50; turn = 30; kp = 0.50; ki = 0.20; kd = 0.02;
      }
      
      // 1. Cập nhật thanh trượt Auto
      document.getElementById('sliderAutoSpeed').value = spd;
      document.getElementById('sliderAutoTurn').value = turn;
      document.getElementById('valAutoSpeedLbl').innerText = spd + " RPM";
      document.getElementById('valAutoTurnLbl').innerText = turn + " RPM";
      
      // 2. Cập nhật 3 ô nhập PID trên Web
      const inpKp = document.getElementById('inKp');
      const inpKi = document.getElementById('inKi');
      const inpKd = document.getElementById('inKd');
      if (inpKp) inpKp.value = kp;
      if (inpKi) inpKi.value = ki;
      if (inpKd) inpKd.value = kd;
      
      // 3. Gửi đồng thời xuống Backend: Cả Tốc độ Auto và Nạp PID Flash STM32
      fetch(`/api/auto_config?speed=${spd}&turn=${turn}`).catch(e => console.error(e));
      fetch(`/api/pid?kp=${kp}&ki=${ki}&kd=${kd}`).catch(e => console.error(e));
    }
"""

html = html.replace('function updateAutoParams() {', js_profile_func + '\n    function updateAutoParams() {')

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("SUCCESSFULLY INJECTED 3 AUTO PRESET BUTTONS (SLOW, NORMAL, FAST) INTO WEB DASHBOARD")
