import json,math,pathlib,sys,urllib.request
sys.path.insert(0,'/home/khangho/agv_codex_escape_20261003_0044')
from agv_navigation import GridPlanner,twist_centres
def get(name):return json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/'+name,timeout=3))
d=get('telemetry');m=get('map_full');pose=(0.,0.,0.)
g=GridPlanner(m['w'],m['h'],m['res'],(m['ox'],m['oy'],m['yaw']),m['data'],.20,.15,budget_s=.15)
near=[]
px,py=-m['ox'],-m['oy']
for y in range(m['h']):
    for x in range(m['w']):
        val=m['data'][y*m['w']+x]
        if val==0:continue
        dx=max(x*m['res']-px,0.,px-(x+1)*m['res'])
        dy=max(y*m['res']-py,0.,py-(y+1)*m['res'])
        near.append({'distance':math.hypot(dx,dy),'value':val,'cell':[x,y],'world':g.cell_to_world(x,y)})
points=[(r*math.cos(math.radians(deg)),r*math.sin(math.radians(deg)),r)
        for deg,r in enumerate(d['ranges']) if isinstance(r,(int,float)) and 0<r<16.]
cases=[]
for v,w in ((.04,.35),(.04,-.35),(.04,0.),(-.04,0.),(-.04,-.35),(-.04,.35)):
    centres,padding=twist_centres(v,w)
    gaps=[min(math.hypot(px-x,py-y)-r*math.sin(math.radians(.5)) for px,py,r in points) for x,y in centres]
    cases.append({'v':v,'w':w,'map_escape_ok':g.escape_swept_clear(pose,v,w),'scan_gaps':gaps,
                  'scan_nondecreasing':all(b>=a-1e-7 for a,b in zip(gaps,gaps[1:])),'padding':padding})
print(json.dumps({'telemetry':d,'map':m,'nearest_blocked':sorted(near,key=lambda p:p['distance'])[:16],
                  'origin_cell':g.world_to_cell(0.,0.),'origin_safe':g.traversable(g.world_to_cell(0.,0.)),'cases':cases}))
