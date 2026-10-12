with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Không bao giờ disable nút BẬT TỰ ĐỘNG QUÉT MAP
old_btn_auto = "document.getElementById('btnAuto').disabled = !active;"
new_btn_auto = "document.getElementById('btnAuto').disabled = false;"
html = html.replace(old_btn_auto, new_btn_auto)

# Khi bấm nút toggleAuto: Luôn gửi ARM trước khi gửi START nếu chưa ARM
old_toggle = """    async function toggleAuto() {
      const act = isAutoRunning ? 'STOP' : 'START';
      if (act === 'START') {
        driveCmd=null;
        if (driveTimer) { clearInterval(driveTimer); driveTimer=null; }
      }"""

new_toggle = """    async function toggleAuto() {
      const act = isAutoRunning ? 'STOP' : 'START';
      if (act === 'START') {
        driveCmd = null;
        if (driveTimer) { clearInterval(driveTimer); driveTimer = null; }
        await sendCmd('ARM');
      }"""

html = html.replace(old_toggle, new_toggle)

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("UNLOCKED AUTO BUTTON ON WEB")
