import json
import time
from agv_navigation import GridPlanner

d=json.load(open('planner_fixture.json'))
t=time.perf_counter()
p=GridPlanner(d['w'],d['h'],d['res'],(d['ox'],d['oy'],d['yaw']),d['data'],.20,budget_s=.05)
print(json.dumps({'build_s':time.perf_counter()-t,'safe_cells':sum(p.safe)}))
