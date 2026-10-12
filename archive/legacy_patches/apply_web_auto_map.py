with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'r') as f:
    code = f.read()

old_fetch_map = """    function fetchMap() {
      fetch('/api/map_full').then(r=>r.json()).then(d=>{
        mapData = d;
      }).catch(()=>{});
    }"""

new_fetch_map = """    function fetchMap() {
      fetch('/api/map_full').then(r=>r.json()).then(d=>{
        if (d && d.data) {
          mapData = d;
        }
      }).catch(()=>{});
    }

    // Tự động kéo bản đồ mới mỗi 1.5 giây khi đang xem SLAM hoặc đang bật Auto
    setInterval(() => {
      if (currentView === 'slam' || isAutoRunning) {
        fetchMap();
      }
    }, 1500);"""

if old_fetch_map in code:
    code = code.replace(old_fetch_map, new_fetch_map, 1)

with open('/home/khangho/agv_codex_reader_20261003_0652/index_cyberpunk.html', 'w') as f:
    f.write(code)

print("SUCCESSFULLY APPLIED AUTO FETCH MAP TO WEB DASHBOARD")
