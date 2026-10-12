import urllib.request
import json

url = 'http://100.90.252.15:8080/api/diagnostics'
try:
    req = urllib.request.urlopen(url, timeout=5)
    data = json.loads(req.read().decode('utf-8'))
    events = data.get('command_events', [])
    drives = [e for e in events if e.get('kind') == 'drive']
    print(f"Total drive events: {len(drives)}")
    for e in drives[-40:]:
        print(f"mono={e.get('mono'):.2f}: cmd={e.get('command')} accepted={e.get('accepted')} reason={e.get('reason')} d0_age={e.get('d0_age_s')} scan_age={e.get('scan_age_s')}")
except Exception as ex:
    print("Error:", ex)
