import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import urllib.request
import json
import time
from agv_navigation import GridPlanner

req = urllib.request.urlopen('http://100.90.252.15:8080/api/map_full', timeout=5)
map_json = json.loads(req.read().decode('utf-8'))
w, h, res = map_json['w'], map_json['h'], map_json['res']
ox, oy, yaw = map_json['ox'], map_json['oy'], map_json['yaw']
data = tuple(map_json['data'])

t0 = time.perf_counter()
planner = GridPlanner(w, h, res, (ox, oy, yaw), data, 0.20, 0.05, budget_s=1.0)
t_init = time.perf_counter() - t0
print(f"GridPlanner init time: {t_init*1000:.1f}ms")

t0 = time.perf_counter()
res_f = planner.frontiers((-1.668, 1.316), [], [])
t_frontiers = time.perf_counter() - t0
print(f"Frontiers calculation time: {t_frontiers*1000:.1f}ms")
if res_f:
    print(f"Goals found: {len(res_f.get('goals', []))}, reachable: {res_f.get('reachable_frontiers')}")
else:
    print("No frontiers returned (None)")
