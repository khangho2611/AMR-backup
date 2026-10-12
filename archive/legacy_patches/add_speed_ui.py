with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Thêm thanh trượt / ô nhập Tốc độ (PWM) và Tốc độ góc quay ngay trên cụm D-Pad
ui_slider = """
        <!-- CỤM SETUP TỐC ĐỘ VÀ GÓC QUAY TRỰC QUAN -->
        <div style="margin: 8px 0; background: #0c121e; border: 1px solid #1e293b; border-radius: 8px; padding: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-size: 10px; font-weight: bold; color: var(--cyan); font-family: 'JetBrains Mono';">⚡ CÀI ĐẶT TỐC ĐỘ & GÓC QUAY</span>
            <span id="speedIndicator" style="font-size: 10px; color: var(--green); font-family: 'JetBrains Mono'; font-weight: bold;">TIẾN: 100 | QUAY: 80</span>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <div>
              <div style="display: flex; justify-content: space-between; font-size: 9px; color: var(--text-muted); margin-bottom: 2px;">
                <span>Tốc độ tiến/lùi (PWM)</span>
                <span id="valSpeedLbl" style="color:#fff; font-weight:bold;">100</span>
              </div>
              <input type="range" id="sliderSpeed" min="40" max="140" value="100" step="5" style="width: 100%; cursor: pointer;" oninput="updateDriveParams()">
            </div>
            <div>
              <div style="display: flex; justify-content: space-between; font-size: 9px; color: var(--text-muted); margin-bottom: 2px;">
                <span>Tốc độ góc quay (PWM)</span>
                <span id="valTurnLbl" style="color:#fff; font-weight:bold;">80</span>
              </div>
              <input type="range" id="sliderTurn" min="30" max="130" value="80" step="5" style="width: 100%; cursor: pointer;" oninput="updateDriveParams()">
            </div>
          </div>
        </div>
"""

# Chèn trước <div class="dpad-grid">
html = html.replace('<div class="dpad-grid">', ui_slider + '\n        <div class="dpad-grid">')

# 2. Cập nhật mã JavaScript để lấy giá trị từ slider khi bấm phím hoặc nút D-pad
old_js = """    // ĐIỀU KHIỂN BÀN PHÍM WASD
    const SPEED = 110;
    let driveTimer = null;
    let driveCmd = null;

    function startDrive(c) {
      isAutoRunning = false;
      driveCmd = c;
      sendCmd(c);
      if (driveTimer) clearInterval(driveTimer);
      driveTimer = setInterval(()=>{ if (driveCmd) sendCmd(driveCmd); }, 150);
    }

    function stopDrive(force = false) {
      const active = Boolean(sessionTimer || driveCmd || driveTimer);
      if (force === true && sessionTimer) { clearInterval(sessionTimer); sessionTimer = null; }\n      driveCmd = null;\n      if (driveTimer) { clearInterval(driveTimer); driveTimer = null; }\n      if (force === true) sendCmd('STOP');\n      else if (active) {\n        sendCmd('V 0.000 0.000');\n        if (!sessionTimer) sessionTimer = setInterval(() => { if (!driveCmd && !isAutoRunning) sendCmd('V 0.000 0.000'); },150);\n      }\n      document.querySelectorAll('.dpad-btn').forEach(b => b.classList.remove('pressed'));\n    }\n\n    function bind(id, c) {\n      const el = document.getElementById(id);\n      if (!el) return;\n      el.addEventListener('pointerdown', (e)=>{ e.preventDefault(); el.classList.add('pressed'); startDrive(c); });\n      const rel = (e)=>{ e.preventDefault(); el.classList.remove('pressed'); stopDrive(); };\n      el.addEventListener('pointerup', rel);\n      el.addEventListener('pointercancel', rel);\n    }\n\n    bind('btnW', 'M 140 140');\n    bind('btnS', 'M -140 -140');\n    bind('btnA', 'M -120 120');\n    bind('btnD', 'M 120 -120');\n    bind('btnQ', 'M -130 130');\n    bind('btnE', 'M 130 -130');\n\n    window.addEventListener('keydown', (e)=>{\n      if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;\n      if (e.repeat) return;\n      if (e.code === 'Space') { e.preventDefault(); emergencyStop(); return; }\n      const k = { 'KeyW': 'M 140 140', 'KeyS': 'M -140 -140', 'KeyA': 'M -120 120', 'KeyD': 'M 120 -120', 'KeyQ': 'M -130 130', 'KeyE': 'M 130 -130' };\n      if (k[e.code]) { e.preventDefault(); startDrive(k[e.code]); }\n    });"""

new_js = """    // ĐIỀU KHIỂN BÀN PHÍM WASD D-PAD VỚI TỐC ĐỘ SETUP ĐƯỢC
    let currentFwdSpeed = 100;
    let currentTurnSpeed = 80;
    let driveTimer = null;
    let driveCmd = null;

    function updateDriveParams() {
      const s = parseInt(document.getElementById('sliderSpeed').value);
      const t = parseInt(document.getElementById('sliderTurn').value);
      currentFwdSpeed = s;
      currentTurnSpeed = t;
      document.getElementById('valSpeedLbl').innerText = s;
      document.getElementById('valTurnLbl').innerText = t;
      document.getElementById('speedIndicator').innerText = `TIẾN: ${s} | QUAY: ${t}`;
    }

    function getCommandForKey(action) {
      const s = currentFwdSpeed;
      const t = currentTurnSpeed;
      if (action === 'W') return `M ${s} ${s}`;
      if (action === 'S') return `M -${s} -${s}`;
      if (action === 'A') return `M -${t} ${t}`;
      if (action === 'D') return `M ${t} -${t}`;
      if (action === 'Q') return `M -${t} ${t}`;
      if (action === 'E') return `M ${t} -${t}`;
      return null;
    }

    function startDriveAction(action) {
      const cmd = getCommandForKey(action);
      if (!cmd) return;
      isAutoRunning = false;
      driveCmd = cmd;
      sendCmd(cmd);
      if (driveTimer) clearInterval(driveTimer);
      driveTimer = setInterval(() => { if (driveCmd) sendCmd(driveCmd); }, 150);
    }

    function stopDrive(force = false) {
      const active = Boolean(sessionTimer || driveCmd || driveTimer);
      if (force === true && sessionTimer) { clearInterval(sessionTimer); sessionTimer = null; }
      driveCmd = null;
      if (driveTimer) { clearInterval(driveTimer); driveTimer = null; }
      if (force === true) sendCmd('STOP');
      else if (active) {
        sendCmd('V 0.000 0.000');
        if (!sessionTimer) sessionTimer = setInterval(() => { if (!driveCmd && !isAutoRunning) sendCmd('V 0.000 0.000'); }, 150);
      }
      document.querySelectorAll('.dpad-btn').forEach(b => b.classList.remove('pressed'));
    }

    function bind(id, action) {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('pointerdown', (e) => { e.preventDefault(); el.classList.add('pressed'); startDriveAction(action); });
      const rel = (e) => { e.preventDefault(); el.classList.remove('pressed'); stopDrive(); };
      el.addEventListener('pointerup', rel);
      el.addEventListener('pointercancel', rel);
    }

    bind('btnW', 'W');
    bind('btnS', 'S');
    bind('btnA', 'A');
    bind('btnD', 'D');
    bind('btnQ', 'Q');
    bind('btnE', 'E');

    window.addEventListener('keydown', (e) => {
      if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
      if (e.repeat) return;
      if (e.code === 'Space') { e.preventDefault(); emergencyStop(); return; }
      const keyMap = { 'KeyW': 'W', 'KeyS': 'S', 'KeyA': 'A', 'KeyD': 'D', 'KeyQ': 'Q', 'KeyE': 'E' };
      if (keyMap[e.code]) { e.preventDefault(); startDriveAction(keyMap[e.code]); }
    });"""

html = html.replace(old_js, new_js)

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("SUCCESSFULLY INJECTED SPEED & TURN SLIDERS INTO WEB DASHBOARD")
