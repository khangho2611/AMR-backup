import urllib.request
import json
import time

url = 'http://100.90.252.15:8080/api/map_full'
try:
    req = urllib.request.urlopen(url, timeout=5)
    data = json.loads(req.read().decode('utf-8'))
    print("Map info:", data['w'], data['h'], data['res'])
except Exception as e:
    print("Error:", e)
