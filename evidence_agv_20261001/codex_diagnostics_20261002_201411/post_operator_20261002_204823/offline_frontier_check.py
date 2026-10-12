import json,sys
sys.path.insert(0, r'D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH')
from agv_navigation import GridPlanner
p=json.load(open(sys.argv[1],encoding='utf-8'))
g=GridPlanner(p['w'],p['h'],p['res'],(p['ox'],p['oy'],p.get('yaw',0.0)),tuple(p['data']),0.20,0.15,budget_s=.05)
summary=g.frontiers((0.0,0.0))
print(json.dumps({'summary':summary,'path_home':g.path((0.0,0.0),(0.0,0.0))},ensure_ascii=False,default=str))
