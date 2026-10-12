
with open('/home/khangho/rplidar_c1_test/bridge/web/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

dpad_css = """
    /* CỤM ĐIỀU KHIỂN ROBOT AGV */
    .control-box {
      margin-top: 12px;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 14px;
    }
    .dpad-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      max-width: 260px;
      margin: 10px auto 0;
    }
    .dpad-btn {
      background: #1e293b;
      border: 1px solid #334466;
      border-radius: 10px;
      color: #fff;
      font-size: 1.1rem;
      font-weight: bold;
      padding: 14px 0;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      transition: all 0.15s;
    }
    .dpad-btn:active, .dpad-btn.active-key {
      background: var(--accent-cyan);
      color: #000;
      transform: scale(0.95);
      box-shadow: 0 0 15px var(--accent-cyan-glow);
    }
    .dpad-stop {
      background: #881337;
      border-color: #be123c;
      color: #fda4af;
    }
    .dpad-stop:active, .dpad-stop.active-key {
      background: #e11d48;
      color: #fff;
    }
    .dpad-sub {
      font-size: 0.65rem;
      font-weight: normal;
      opacity: 0.8;
    }
"""

dpad_html = """
      <!-- BẢNG ĐIỀU KHIỂN XE AGV TRỰC TIẾP (WASD HOẶC BẤM CHUỘT) -->
      <div class="control-box">
        <div class="card-title" style="display:flex; justify-content:space-between; align-items:center;">
          <span>🎮 Điều Khiển Xe Di Chuyển</span>
          <span style="font-size:0.7rem; color:var(--accent-cyan);">Phím W-A-S-D hoặc Chuột</span>
        </div>
        <div class="dpad-grid">
          <button class="dpad-btn" id="btn-turn-left"><span>↺</span><span class="dpad-sub">Q (Xoay T)</span></button>
          <button class="dpad-btn" id="btn-forward"><span>▲</span><span class="dpad-sub">W (Tiến)</span></button>
          <button class="dpad-btn" id="btn-turn-right"><span>↻</span><span class="dpad-sub">E (Xoay P)</span></button>

          <button class="dpad-btn" id="btn-left"><span>◄</span><span class="dpad-sub">A (Trái)</span></button>
          <button class="dpad-btn dpad-stop" id="btn-stop"><span>🛑</span><span class="dpad-sub">Space (Dừng)</span></button>
          <button class="dpad-btn" id="btn-right"><span>►</span><span class="dpad-sub">D (Phải)</span></button>

          <div></div>
          <button class="dpad-btn" id="btn-backward"><span>▼</span><span class="dpad-sub">S (Lùi)</span></button>
          <div></div>
        </div>
      </div>
"""

dpad_js = """
    // =========================================================================
    // ĐIỀU KHIỂN ROBOT AGV (CHUỘT + CẢM ỨNG + BÀN PHÍM WASD)
    // =========================================================================
    const ROBOT_SPEED = 120;
    let moveTimer = null;
    let activeCmd = null;

    function sendRobot(cmd) {
      fetch('/api/cmd?val=' + encodeURIComponent(cmd)).catch(()=>{});
    }

    function startDrive(cmd) {
      activeCmd = cmd;
      sendRobot(cmd);
      if (moveTimer) clearInterval(moveTimer);
      moveTimer = setInterval(() => {
        if (activeCmd) sendRobot(activeCmd);
      }, 150);
    }

    function stopDrive() {
      activeCmd = null;
      if (moveTimer) { clearInterval(moveTimer); moveTimer = null; }
      sendRobot('STOP');
      document.querySelectorAll('.dpad-btn').forEach(b => b.classList.remove('active-key'));
    }

    function bindDrive(btnId, cmd) {
      const el = document.getElementById(btnId);
      if (!el) return;
      el.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        try { el.setPointerCapture(e.pointerId); } catch(err){}
        el.classList.add('active-key');
        startDrive(cmd);
      });
      const release = (e) => {
        e.preventDefault();
        try { el.releasePointerCapture(e.pointerId); } catch(err){}
        el.classList.remove('active-key');
        stopDrive();
      };
      el.addEventListener('pointerup', release);
      el.addEventListener('pointercancel', release);
    }

    bindDrive('btn-forward', 'S ' + ROBOT_SPEED + ' ' + ROBOT_SPEED);
    bindDrive('btn-backward', 'S -' + ROBOT_SPEED + ' -' + ROBOT_SPEED);
    bindDrive('btn-left', 'S 0 ' + ROBOT_SPEED);
    bindDrive('btn-right', 'S ' + ROBOT_SPEED + ' 0');
    bindDrive('btn-turn-left', 'S -' + ROBOT_SPEED + ' ' + ROBOT_SPEED);
    bindDrive('btn-turn-right', 'S ' + ROBOT_SPEED + ' -' + ROBOT_SPEED);
    
    document.getElementById('btn-stop')?.addEventListener('click', stopDrive);

    const keyMap = {
      'KeyW': 'S ' + ROBOT_SPEED + ' ' + ROBOT_SPEED,
      'KeyS': 'S -' + ROBOT_SPEED + ' -' + ROBOT_SPEED,
      'KeyA': 'S 0 ' + ROBOT_SPEED,
      'KeyD': 'S ' + ROBOT_SPEED + ' 0',
      'KeyQ': 'S -' + ROBOT_SPEED + ' ' + ROBOT_SPEED,
      'KeyE': 'S ' + ROBOT_SPEED + ' -' + ROBOT_SPEED
    };

    window.addEventListener('keydown', (e) => {
      if (e.repeat) return;
      if (e.code === 'Space') {
        e.preventDefault();
        stopDrive();
        return;
      }
      if (keyMap[e.code]) {
        e.preventDefault();
        startDrive(keyMap[e.code]);
      }
    });

    window.addEventListener('keyup', (e) => {
      if (keyMap[e.code] || e.code === 'Space') {
        e.preventDefault();
        stopDrive();
      }
    });
"""

if '.control-box' not in html:
    html = html.replace('</style>', dpad_css + '\n  </style>')

if 'Điều Khiển Xe Di Chuyển' not in html:
    html = html.replace('<!-- LINK ĐẾN MIT APP -->', dpad_html + '\n      <!-- LINK ĐẾN MIT APP -->')

if 'sendRobot' not in html:
    html = html.replace('</script>', dpad_js + '\n  </script>')

with open('/home/khangho/rplidar_c1_test/bridge/web/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('SUCCESSFULLY PATCHED INDEX.HTML WITH DPAD!')
