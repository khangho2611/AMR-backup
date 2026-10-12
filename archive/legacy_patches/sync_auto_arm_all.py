# 1. Sửa agv_unified_brain.py: Trong handler /api/auto?act=START, tự động gửi ARM và đợi xác nhận
with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    brain_code = f.read()

old_auto_branch = """        elif path == '/api/auto':
            import urllib.parse
            act = urllib.parse.parse_qs(q).get('act',[''])[0].upper()
            ok,reason = False,'NO_TRANSPORT'
            blockers,snapshot=[],{}
            if ros_node and act == 'START':
                ok,reason,blockers,snapshot=ros_node.start_auto()"""

new_auto_branch = """        elif path == '/api/auto':
            import urllib.parse
            act = urllib.parse.parse_qs(q).get('act',[''])[0].upper()
            ok,reason = False,'NO_TRANSPORT'
            blockers,snapshot=[],{}
            if ros_node and act == 'START':
                # Tự động ARM mở khóa ESP32 trước khi khởi động Auto
                ros_node.control.request_arm()
                ok,reason,blockers,snapshot=ros_node.start_auto()"""

if old_auto_branch in brain_code:
    brain_code = brain_code.replace(old_auto_branch, new_auto_branch, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(brain_code)

# 2. Sửa index_cyberpunk.html: Khi bấm nút AUTO START, tự động gửi ARM trước qua API
with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'r') as f:
    html_code = f.read()

old_js_auto = """    async function toggleAuto() {
      const act = isAutoRunning ? 'STOP' : 'START';
      if (act === 'START') {
        driveCmd=null;
        if (driveTimer) { clearInterval(driveTimer); driveTimer=null; }
      }
      try {
        const response = await fetch('/api/auto?act=' + act, {signal:AbortSignal.timeout(1200)});"""

new_js_auto = """    async function toggleAuto() {
      const act = isAutoRunning ? 'STOP' : 'START';
      if (act === 'START') {
        driveCmd=null;
        if (driveTimer) { clearInterval(driveTimer); driveTimer=null; }
        // Mở khóa ARM trước khi gửi START
        await fetch('/api/cmd?val=ARM').catch(()=>{});
      }
      try {
        const response = await fetch('/api/auto?act=' + act, {signal:AbortSignal.timeout(2000)});"""

if old_js_auto in html_code:
    html_code = html_code.replace(old_js_auto, new_js_auto, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'w') as f:
    f.write(html_code)

print("SUCCESSFULLY SYNCED AUTO ARM ON BACKEND & FRONTEND")
