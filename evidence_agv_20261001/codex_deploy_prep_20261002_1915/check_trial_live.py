"""Read HTTP live data and run pure costmap; never dispatch control commands."""
import json
import pathlib
import time
import urllib.request
from agv_navigation import GridPlanner

def read(path):
    with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=3) as r:
        return json.load(r)

telemetry=read('/api/telemetry')
data=read('/api/map_full')
started=time.perf_counter()
planner=GridPlanner(data['w'],data['h'],data['res'],
                    (data['ox'],data['oy'],data['yaw']),data['data'],.20,budget_s=.05)
robot=telemetry['robot']
result={'time':time.time(),'telemetry':telemetry,'map':data,
        'planner_build_s':time.perf_counter()-started,
        'safe_cells':sum(planner.safe),
        'origin_traversable':planner.traversable(planner.world_to_cell(robot['x'],robot['y']))}
start=time.perf_counter()
result['frontier_result']=planner.frontiers((robot['x'],robot['y']))
result['frontier_compute_s']=time.perf_counter()-start
out=pathlib.Path('runtime_trial')/('live_'+str(time.time_ns())+'.json')
out.write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k not in ('telemetry','map')},ensure_ascii=False))
print(json.dumps({'control':telemetry['control'],'map_info':telemetry['map_info'],
                  'min_m':telemetry['min_m'],'hz':telemetry['hz'],'robot':robot,'evidence':str(out)},ensure_ascii=False))
