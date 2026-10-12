with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Xóa hoàn toàn lệnh ma V 0.000 0.000 trong armControl
old_arm = """    let sessionTimer = null;
    async function armControl() {
      if (await sendCmd('ARM')) {
        if (sessionTimer) clearInterval(sessionTimer);
        sessionTimer = setInterval(() => { if (!driveCmd && !isAutoRunning) sendCmd('V 0.000 0.000'); },150);
      }
    }"""

new_arm = """    let sessionTimer = null;
    async function armControl() {
      await sendCmd('ARM');
    }"""

html = html.replace(old_arm, new_arm)

# 2. Xóa hoàn toàn lệnh ma V 0.000 0.000 trong stopDrive khi buông tay lái
old_stop = """    function stopDrive(force = false) {
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
    }"""

new_stop = """    function stopDrive(force = false) {
      driveCmd = null;
      if (driveTimer) { clearInterval(driveTimer); driveTimer = null; }
      if (sessionTimer) { clearInterval(sessionTimer); sessionTimer = null; }
      sendCmd('STOP');
      document.querySelectorAll('.dpad-btn').forEach(b => b.classList.remove('pressed'));
    }"""

html = html.replace(old_stop, new_stop)

# 3. Khi bấm phím hoặc nút lái mới -> Tự động xóa sạch thông báo lỗi cũ trên Web
old_start_action = """    function startDriveAction(action) {
      const cmd = getCommandForKey(action);
      if (!cmd) return;
      isAutoRunning = false;
      driveCmd = cmd;
      sendCmd(cmd);
      if (driveTimer) clearInterval(driveTimer);
      driveTimer = setInterval(() => { if (driveCmd) sendCmd(driveCmd); }, 150);
    }"""

new_start_action = """    function startDriveAction(action) {
      const cmd = getCommandForKey(action);
      if (!cmd) return;
      document.getElementById('commandNotice').innerText = `ĐANG LÁI: ${cmd}`;
      isAutoRunning = false;
      driveCmd = cmd;
      sendCmd(cmd);
      if (driveTimer) clearInterval(driveTimer);
      driveTimer = setInterval(() => { if (driveCmd) sendCmd(driveCmd); }, 150);
    }"""

html = html.replace(old_start_action, new_start_action)

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("CLEANED UP GHOST V COMMANDS AND REFRESHED UI NOTICES")
