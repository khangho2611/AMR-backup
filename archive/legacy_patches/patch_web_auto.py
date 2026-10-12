target = '/home/khangho/rplidar_c1_test/bridge/web/index.html'
with open(target, 'r', encoding='utf-8') as f:
    html = f.read()

# Nút Tự Hành Thông Minh & Nút DỪNG KHẨN CẤP To Bự
auto_controls_html = """
        <!-- CỤM TỰ ĐỘNG NÉ VẬT CẢN & NÚT DỪNG KHẨN CẤP -->
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-top:12px;">
          <button id="btn-auto-start" style="padding:12px; background:#065f46; border:2px solid #059669; border-radius:10px; color:#6ee7b7; font-weight:800; font-size:0.85rem; cursor:pointer;">
            🚀 BẬT TỰ NÉ (CHẬM)
          </button>
          <button id="btn-emergency-stop" style="padding:12px; background:#991b1b; border:2px solid #dc2626; border-radius:10px; color:#fecaca; font-weight:900; font-size:0.85rem; cursor:pointer; box-shadow:0 0 15px rgba(239,68,68,0.4);">
            🛑 DỪNG KHẨN CẤP
          </button>
        </div>
"""

auto_js = """
    // BẬT / TẮT TỰ ĐỘNG NÉ VẬT CẢN & DỪNG KHẨN CẤP
    const btnAuto = document.getElementById('btn-auto-start');
    const btnEStop = document.getElementById('btn-emergency-stop');
    let isAutoRunning = false;

    if (btnAuto) {
      btnAuto.addEventListener('click', () => {
        if (!isAutoRunning) {
          fetch('/api/auto?act=START').then(r=>r.json()).then(d=>{
            isAutoRunning = true;
            btnAuto.innerText = '⏸ TẮT TỰ HÀNH';
            btnAuto.style.background = '#d97706';
            btnAuto.style.borderColor = '#f59e0b';
            btnAuto.style.color = '#fff';
          });
        } else {
          emergencyStopAll();
        }
      });
    }

    function emergencyStopAll() {
      fetch('/api/auto?act=STOP').catch(()=>{});
      fetch('/api/cmd?val=STOP').catch(()=>{});
      isAutoRunning = false;
      if (btnAuto) {
        btnAuto.innerText = '🚀 BẬT TỰ NÉ (CHẬM)';
        btnAuto.style.background = '#065f46';
        btnAuto.style.borderColor = '#059669';
        btnAuto.style.color = '#6ee7b7';
      }
    }

    if (btnEStop) {
      btnEStop.addEventListener('click', emergencyStopAll);
    }
"""

if 'btn-emergency-stop' not in html:
    html = html.replace('</div>\n        <div class="dpad-grid">', auto_controls_html + '\n        <div class="dpad-grid">')

if 'emergencyStopAll' not in html:
    html = html.replace('</script>', auto_js + '\n  </script>')

with open(target, 'w', encoding='utf-8') as f:
    f.write(html)

print("SUCCESSFULLY INJECTED AUTO AVOIDANCE & EMERGENCY STOP TO WEB!")
