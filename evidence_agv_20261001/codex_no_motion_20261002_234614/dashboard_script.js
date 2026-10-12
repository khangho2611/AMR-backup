
    const canvas = document.getElementById('viewCanvas');
    const ctx = canvas.getContext('2d');
    let currentView = 'radar';
    let isAutoRunning = false;
    let teleData = null;
    let mapData = null;

    function switchView(view) {
      currentView = view;
      document.getElementById('tabRadar').classList.toggle('active', view === 'radar');
      document.getElementById('tabSlam').classList.toggle('active', view === 'slam');

      if (view === 'slam') fetchMap();
    }

    // Persistent browser records also retain timeouts/disconnections.
    let pidHistory;
    try { pidHistory = JSON.parse(localStorage.getItem('agv_pid_history') || '[]'); }
    catch (_) { pidHistory = []; }
    if (!Array.isArray(pidHistory)) pidHistory = [];
    pidHistory.forEach(row => { if (row.status === 'PENDING') { row.status = 'FAILED'; row.reason = 'Trang tải lại: chưa xác nhận kết quả MCU'; } });
    let pidBusy = false;
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    function saveHistory() {
      pidHistory = pidHistory.slice(-500);
      try { localStorage.setItem('agv_pid_history', JSON.stringify(pidHistory)); } catch (_) {}
      renderHistory();
    }
    function renderHistory() {
      const tbody = document.getElementById('historyTableBody');
      const countLbl = document.getElementById('historyCount');
      if (!tbody) return;
      if (countLbl) countLbl.innerText = pidHistory.length + ' bản ghi';
      tbody.innerHTML = pidHistory.length ? pidHistory.slice(-10).reverse().map(row => {
        const status = row.status || 'UNVERIFIED';
        const color = status === 'APPLIED' ? 'var(--green)' : status === 'PENDING' ? 'var(--yellow)' : 'var(--red)';
        return `<tr><td>${escapeHtml(row.time)}</td><td>${escapeHtml(row.kp)}</td><td>${escapeHtml(row.ki)}</td><td>${escapeHtml(row.kd)}</td><td style="color:${color}" title="${escapeHtml(row.reason)}">${escapeHtml(status)}</td></tr>`;
      }).join('') : '<tr><td colspan="5">Chưa có bản ghi nào</td></tr>';
    }
    async function applyPidMini() {
      if (pidBusy) return;
      const fields = ['inputKpMini','inputKiMini','inputKdMini'];
      const strings = fields.map(id => document.getElementById(id).value.trim());
      const values = strings.map(Number);
      const lbl = document.getElementById('pidStatusMini');
      if (strings.some(v => v === '') || values.some((v,i) => !Number.isFinite(v) || v < 0 || v > [20,50,5][i])) {
        if (lbl) lbl.innerText = 'REJECTED: giá trị PID không hợp lệ';
        return;
      }
      const [kp,ki,kd] = values;
      const record = {time:new Date().toISOString(),kp,ki,kd,kf:.45,status:'PENDING',reason:'Chờ MCU xác nhận'};
      pidHistory.push(record); saveHistory();
      pidBusy = true;
      if (lbl) lbl.innerText = 'PENDING: chờ MCU';
      try {
        const response = await fetch(`/api/pid?kp=${kp}&ki=${ki}&kd=${kd}&kf=0.45`, {signal:AbortSignal.timeout(2500)});
        const result = await response.json();
        const accepted = response.ok && result.status === 'APPLIED';
        record.status = accepted ? 'APPLIED' : result.status === 'REJECTED' ? 'REJECTED' : 'FAILED';
        record.reason = result.reason || 'Không có xác nhận MCU hợp lệ';
      } catch (_) {
        record.status = 'FAILED';
        record.reason = 'Mất kết nối hoặc timeout; chưa xác nhận MCU';
      } finally {
        pidBusy = false;
        saveHistory();
        if (lbl) { lbl.innerText = record.status + ': ' + record.reason; lbl.style.color = record.status === 'APPLIED' ? 'var(--green)' : 'var(--red)'; }
      }
    }

    function applyPid() {
      applyPidMini();
    }

    function exportToExcel() {
      const columns = ['time','kp','ki','kd','kf','status','reason'];
      const quote = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
      const csv = [columns, ...pidHistory.map(row => columns.map(k => row[k]))].map(row => row.map(quote).join(',')).join('\r\n');
      const url = URL.createObjectURL(new Blob(['\ufeff' + csv], {type:'text/csv;charset=utf-8'}));
      const link = document.createElement('a'); link.href = url; link.download = 'agv_pid_history.csv'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function clearHistory() {
      if (confirm('Bạn có chắc muốn xóa sạch toàn bộ lịch sử đo đạc PID không?')) {
        pidHistory = [];
        localStorage.removeItem('agv_pid_history');
        renderHistory();
      }
    }

    // Tự động render lịch sử ban đầu
    setTimeout(renderHistory, 500);

    function commandFailure(data) {
      const labels = {
        NOT_ARMED:'MCU chưa xác nhận mở phiên', LATCHED:'Phiên đang bị khóa',
        FAULT:'Đang có lỗi điều khiển', D0_STALE:'Dữ liệu MCU quá cũ',
        SCAN_STALE:'Dữ liệu LiDAR quá cũ', CALLER_STALE:'Mất nhịp lệnh từ người điều khiển',
        MAP_NOT_READY:'Bản đồ thiếu, quá cũ hoặc chưa hợp lệ',
        TF_NOT_READY:'Chưa có tọa độ xe mới trong bản đồ',
        BODY_RADIUS_UNCONFIGURED:'Chưa cấu hình kích thước bao thân xe',
        TRIAL_EXPIRED:'Phiên thử đã hết thời gian'
      };
      const blockers = Array.isArray(data.blockers) ? data.blockers : [];
      return blockers.length ? blockers.map(b => (labels[b] || b) + ' (' + b + ')').join('; ') : (data.reason || 'Lệnh bị từ chối');
    }
    function showCommandMessage(text, data) {
      if (data && data.journal && !data.journal.saved) text += ' — Không ghi được nhật ký lệnh';
      document.getElementById('statusBadge').innerText = text;
      // Telemetry refreshes the vehicle badge; retain the command outcome in
      // its own area so the rejection does not disappear after 100 ms.
      document.getElementById('commandNotice').innerText = text;
    }
    async function sendCmd(cmd) {
      try {
        const response = await fetch('/api/cmd?val=' + encodeURIComponent(cmd), {signal:AbortSignal.timeout(1200)});
        const data = await response.json();
        if (!response.ok) {
          showCommandMessage(cmd + ' BỊ TỪ CHỐI: ' + commandFailure(data), data);
          if (sessionTimer) clearInterval(sessionTimer);
          sessionTimer = null;
          if (driveTimer) clearInterval(driveTimer);
          driveTimer = null; driveCmd = null;
        } else if (cmd === 'ARM') {
          showCommandMessage(data.reason === 'ARM_CONFIRMED' ? 'MCU ĐÃ XÁC NHẬN MỞ PHIÊN' : 'ARM ĐÃ GỬI — ĐANG CHỜ ACK MCU', data);
        }
        return response.ok;
      } catch (_) {
        if (sessionTimer) clearInterval(sessionTimer);
        sessionTimer = null;
        if (driveTimer) clearInterval(driveTimer);
        driveTimer = null; driveCmd = null;
        showCommandMessage('MẤT KẾT NỐI — DỪNG CHƯA XÁC NHẬN');
        return false;
      }
    }
    let sessionTimer = null;
    async function armControl() {
      if (await sendCmd('ARM')) {
        if (sessionTimer) clearInterval(sessionTimer);
        sessionTimer = setInterval(() => { if (!driveCmd && !isAutoRunning) sendCmd('V 0.000 0.000'); },150);
      }
    }

    async function toggleAuto() {
      const act = isAutoRunning ? 'STOP' : 'START';
      try {
        const response = await fetch('/api/auto?act=' + act, {signal:AbortSignal.timeout(1200)});
        const d = await response.json();
        if (!response.ok || d.status !== 'ok') {
          isAutoRunning = Boolean(d.auto);
          showCommandMessage('AUTO ' + act + ' BỊ TỪ CHỐI: ' + commandFailure(d), d);
          return;
        }
        isAutoRunning = d.auto;
        showCommandMessage(isAutoRunning ? 'ĐÃ NHẬN LỆNH AUTO' : 'ĐÃ XÁC NHẬN DỪNG AUTO', d);
        const btn = document.getElementById('btnAuto');
        const txt = document.getElementById('autoText');
        if (isAutoRunning) {
          btn.classList.add('active');
          txt.innerText = 'DỪNG QUÉT MAP';
          btn.style.background = '#d97706';
          btn.style.borderColor = '#f59e0b';
        } else {
          btn.classList.remove('active');
          txt.innerText = 'BẬT TỰ ĐỘNG QUÉT MAP';
          btn.style.background = '#064e3b';
          btn.style.borderColor = '#059669';
        }
      } catch (_) {
        showCommandMessage('AUTO MẤT KẾT NỐI — CHƯA XÁC NHẬN AN TOÀN');
      }
    }

    function emergencyStop() {
      // STOP endpoint also disables AUTO. One operation, one confirmation.
      stopDrive(true);
      isAutoRunning = false;
      const btn = document.getElementById('btnAuto');
      document.getElementById('autoText').innerText = 'BẬT TỰ ĐỘNG QUÉT MAP';
      btn.style.background = '#064e3b';
      btn.style.borderColor = '#059669';
    }

    function fetchMap() {
      fetch('/api/map_full').then(r=>r.json()).then(d=>{
        mapData = d;
      }).catch(()=>{});
    }

    // VẼ RADAR HOẶC BẢN ĐỒ SLAM
    function render() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;

      if (currentView === 'radar') {
        // 1. Vẽ vòng tròn Radar
        ctx.strokeStyle = '#1e293b';
        ctx.lineWidth = 1;
        for (let r = 50; r <= 250; r += 50) {
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Vẽ các tia trục
        ctx.beginPath();
        ctx.moveTo(cx - 250, cy); ctx.lineTo(cx + 250, cy);
        ctx.moveTo(cx, cy - 250); ctx.lineTo(cx, cy + 250);
        ctx.stroke();

        // 2. Vẽ đám mây điểm LaserScan
        if (teleData && teleData.ranges) {
          const scale = 75; // 75px = 1m (phạm vi ~3.5m)
          ctx.fillStyle = '#00f0ff';
          teleData.ranges.forEach((dist, deg) => {
            if (dist > 0.05 && dist < 4.0) {
              const rad = (deg - 90) * Math.PI / 180.0;
              const px = cx + dist * Math.cos(rad) * scale;
              const py = cy + dist * Math.sin(rad) * scale;
              
              if (dist < 0.35) ctx.fillStyle = '#ef4444';
              else if (dist < 0.70) ctx.fillStyle = '#f59e0b';
              else ctx.fillStyle = '#00f0ff';
              
              ctx.fillRect(px - 2, py - 2, 4, 4);
            }
          });
        }

        // 3. Vẽ vị trí xe Robot ở tâm
        ctx.fillStyle = '#10b981';
        ctx.beginPath();
        ctx.arc(cx, cy, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx, cy - 22); // Mũi tên tiến
        ctx.stroke();
      } 
      else if (currentView === 'slam' && mapData && mapData.data && mapData.data.length > 0) {
        // VẼ BẢN ĐỒ SLAM GRID THỰC TẾ
        const mw = mapData.w;
        const mh = mapData.h;
        const pSize = Math.max(1, Math.min(canvas.width / mw, canvas.height / mh));
        const ox = (canvas.width - mw * pSize) / 2;
        const oy = (canvas.height - mh * pSize) / 2;

        for (let y = 0; y < mh; y++) {
          for (let x = 0; x < mw; x++) {
            const val = mapData.data[(mh - 1 - y) * mw + x];
            if (val === -1) {
              ctx.fillStyle = '#0b0f19'; // Vùng chưa quét
            } else if (val === 0) {
              ctx.fillStyle = '#1e293b'; // Vùng trống tự do
            } else {
              ctx.fillStyle = '#00f0ff'; // Vật cản / Tường phòng
            }
            ctx.fillRect(ox + x * pSize, oy + y * pSize, pSize, pSize);
          }
        }
      }

      requestAnimationFrame(render);
    }

    function updateTrialUI(d) {
      const c = d.control;
      if (!c || c.motion_window_s == null) return;
      isAutoRunning = Boolean(d.auto);
      document.querySelectorAll('.dpad-btn').forEach(b => { b.disabled = true; });
      const pidButton = document.querySelector('button[onclick="applyPidMini()"]');
      if (pidButton) pidButton.disabled = true;
      const arm = document.getElementById('btnArm');
      arm.disabled = !c.preflight_ready || c.trial_used || Boolean(c.fault);
      arm.innerText = c.trial_used ? 'PHIÊN TEST ĐÃ DÙNG' : c.preflight_ready ? 'MỞ PHIÊN TEST 15 GIÂY' : 'ĐANG KIỂM TRA XE';
      document.getElementById('btnAuto').disabled = !c.armed || Boolean(c.fault);
      document.getElementById('autoText').innerText = d.auto ? 'DỪNG TEST AUTO' : 'BẬT TEST AUTO 15 GIÂY';
    }

    // ĐỌC TELEMETRY LIÊN TỤC 10HZ
    setInterval(() => {
      fetch('/api/telemetry').then(r=>r.json()).then(d=>{
        teleData = d;
        updateTrialUI(d);
        document.getElementById('valX').innerText = d.robot.x.toFixed(3);
        document.getElementById('valY').innerText = d.robot.y.toFixed(3);
        document.getElementById('valTh').innerText = (d.robot.th * 180 / Math.PI).toFixed(1) + '°';
        document.getElementById('valLRpm').innerText = Math.abs(d.robot.l_rpm).toFixed(1);
        document.getElementById('valRRpm').innerText = Math.abs(d.robot.r_rpm).toFixed(1);
        document.getElementById('valMinD').innerText = (d.min_m * 100).toFixed(0) + ' cm';
        document.getElementById('distIndicator').innerText = `VẬT CẢN: ${d.min_m.toFixed(2)}m (${d.min_ang}°)`;

        const badge = document.getElementById('statusBadge');
        if (d.status === 'OBSERVE_ONLY') {
          badge.className = 'status-badge badge-warn';
          badge.innerText = 'ĐANG XEM DỮ LIỆU XE — CHƯA BẬT CHẠY' +
            (d.control && d.control.fault ? ' / ' + d.control.fault : '');
        } else if (d.map_info && d.map_info.phase && d.auto) {
          badge.className = 'status-badge badge-warn';
          badge.innerText = 'TỰ HÀNH: ' + d.map_info.phase;
        } else if (d.status === 'DANGER_STOP') {
          badge.className = 'status-badge badge-danger';
          badge.innerText = 'CẢNH BÁO: QUÁ GẦN!';
        } else if (d.status === 'WARNING') {
          badge.className = 'status-badge badge-warn';
          badge.innerText = 'CẢNH BÁO VA CHẠM';
        } else if (d.control && (d.control.fault || d.control.latched)) {
          badge.className = 'status-badge badge-danger';
          badge.innerText = d.control.fault || 'ĐÃ KHÓA — CẦN MỞ PHIÊN RÕ RÀNG';
        } else {
          badge.className = 'status-badge badge-safe';
          badge.innerText = 'TELEMETRY ĐANG CẬP NHẬT';
        }
      }).catch(()=>{
        document.getElementById('statusBadge').innerText = 'MẤT TELEMETRY — CHƯA XÁC NHẬN AN TOÀN';
        ['valLRpm','valRRpm','valX','valY','valTh'].forEach(id => document.getElementById(id).innerText = '--');
        if (driveCmd) stopDrive();
      });
    }, 100);

    // ĐIỀU KHIỂN BÀN PHÍM WASD
    const SPEED = 110;
    let driveTimer = null;
    let driveCmd = null;

    function startDrive(c) {
      driveCmd = c;
      sendCmd(c);
      if (driveTimer) clearInterval(driveTimer);
      driveTimer = setInterval(()=>{ if (driveCmd) sendCmd(driveCmd); }, 150);
    }

    function stopDrive(force = false) {
      const active = Boolean(sessionTimer || driveCmd || driveTimer);
      if (sessionTimer) { clearInterval(sessionTimer); sessionTimer = null; }
      driveCmd = null;
      if (driveTimer) { clearInterval(driveTimer); driveTimer = null; }
      if (active || force === true) sendCmd('STOP');
      document.querySelectorAll('.dpad-btn').forEach(b => b.classList.remove('pressed'));
    }

    function bind(id, c) {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('pointerdown', (e)=>{ e.preventDefault(); el.classList.add('pressed'); startDrive(c); });
      const rel = (e)=>{ e.preventDefault(); el.classList.remove('pressed'); stopDrive(); };
      el.addEventListener('pointerup', rel);
      el.addEventListener('pointercancel', rel);
    }

    bind('btnW', 'M 140 140');
    bind('btnS', 'M -140 -140');
    bind('btnA', 'M -120 120');
    bind('btnD', 'M 120 -120');
    bind('btnQ', 'M -130 130');
    bind('btnE', 'M 130 -130');

    window.addEventListener('keydown', (e)=>{
      if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
      if (e.repeat) return;
      if (e.code === 'Space') { e.preventDefault(); emergencyStop(); return; }
      const k = { 'KeyW': 'M 140 140', 'KeyS': 'M -140 -140', 'KeyA': 'M -120 120', 'KeyD': 'M 120 -120', 'KeyQ': 'M -130 130', 'KeyE': 'M 130 -130' };
      if (k[e.code]) { e.preventDefault(); startDrive(k[e.code]); }
    });

    window.addEventListener('keyup', (e)=>{
      if (driveCmd && (e.code.startsWith('Key') || e.code === 'Space')) { e.preventDefault(); stopDrive(); }
    });

    window.addEventListener('blur', stopDrive);
    document.addEventListener('visibilitychange', () => { if (document.hidden) stopDrive(); });
    window.addEventListener('pointerup', () => { if (driveCmd) stopDrive(); });
    render();
  