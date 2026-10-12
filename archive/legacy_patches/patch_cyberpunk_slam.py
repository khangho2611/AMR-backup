target = '/home/khangho/rplidar_c1_test/bridge/web/index_cyberpunk.html'
with open(target, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Thêm nút [QUÉT MAP 360 TỰ ĐỘNG] vào cạnh nút BẬT TỰ NÉ
slam_btn_html = """        <div class="action-grid" style="grid-template-columns: 1fr 1fr 1fr; gap:6px;">
          <button class="btn-action btn-auto" id="btnAuto" onclick="toggleAuto()">
            <span style="font-size:15px;">🚀</span>
            <span id="autoText" style="font-size:10px;">TỰ NÉ</span>
          </button>
          <button class="btn-action" id="btnSlamAuto" onclick="toggleSlamAuto()" style="background:#1e1b4b; border:2px solid #6366f1; color:#c7d2fe;">
            <span style="font-size:15px;">🔄</span>
            <span id="slamAutoText" style="font-size:10px;">QUÉT 360°</span>
          </button>
          <button class="btn-action btn-estop" onclick="emergencyStop()">
            <span style="font-size:15px;">🛑</span>
            <span style="font-size:10px;">DỪNG LẠI</span>
          </button>
        </div>"""

if 'btnSlamAuto' not in html:
    html = html.replace("""        <div class="action-grid">
          <button class="btn-action btn-auto" id="btnAuto" onclick="toggleAuto()">
            <span style="font-size:16px;">🚀</span>
            <span id="autoText">BẬT TỰ NÉ (CHẬM)</span>
          </button>
          <button class="btn-action btn-estop" onclick="emergencyStop()">
            <span style="font-size:16px;">🛑</span>
            <span>DỪNG KHẨN CẤP</span>
          </button>
        </div>""", slam_btn_html)

# 2. Thêm logic JS cho toggleSlamAuto
slam_js = """    let isSlamRunning = false;
    function toggleSlamAuto() {
      const act = isSlamRunning ? 'STOP' : 'START';
      fetch('/api/slam_auto?act=' + act).then(r=>r.json()).then(d=>{
        isSlamRunning = d.auto_slam;
        const btn = document.getElementById('btnSlamAuto');
        const txt = document.getElementById('slamAutoText');
        if (isSlamRunning) {
          txt.innerText = 'DỪNG QUÉT';
          btn.style.background = '#d97706';
          btn.style.borderColor = '#f59e0b';
        } else {
          txt.innerText = 'QUÉT 360°';
          btn.style.background = '#1e1b4b';
          btn.style.borderColor = '#6366f1';
        }
      });
    }"""

if 'toggleSlamAuto' not in html:
    html = html.replace("function emergencyStop() {", slam_js + "\n    function emergencyStop() {\n      fetch('/api/slam_auto?act=STOP').catch(()=>{});")

with open(target, 'w', encoding='utf-8') as f:
    f.write(html)

print("SUCCESSFULLY INJECTED 360 SLAM BUTTON TO CYBERPUNK DASHBOARD!")
