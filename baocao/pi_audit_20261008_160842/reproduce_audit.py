"""Read-only audit reproduction: imports captured Pi source, uses memory UART only."""
import pathlib, sys, json, time, math
from types import SimpleNamespace
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_agv_navigation_fix as loader
loader.ROOT=HERE
sys.path.insert(0,str(HERE))
for name in ('agv_navigation','agv_command_session','agv_preflight_static_collector'):
    sys.modules.pop(name,None)
from agv_command_session import CommandSession, NUMERIC
from agv_navigation import GridPlanner
brain=loader.load_brain()
class MemoryUART:
    def __init__(self):self.writes=[];self.is_open=True
    def write(self,data):self.writes.append(data.decode());return len(data)
    def flush(self):pass
class Clock:
    def __init__(self):self.now=100.
    def __call__(self):return self.now

def session():
    uart=MemoryUART();clock=Clock()
    s=CommandSession(uart,clock=clock,strict_preflight=False)
    s.stage=3;s.armed=True;s.autonomy_allowed=True
    s.scan_time=clock();s.rotation_clear=True;s.scan_clear=True;s.last_d0=clock()
    s.last_command=clock();s.latest=dict.fromkeys(NUMERIC,0)
    s.latest.update(safety='ARMED',mode='PID');return s,uart,clock

results=[]
def record(name,condition,details):
    results.append(dict(name=name,safety_expectation_passed=bool(condition),details=details))

s,u,c=session();s.request_stop(wait=False);c.now+=.01
s.ingest(dict(s.latest,safety='DISARMED'))
confirmed=s.stop_confirmed
ok,reason=s.drive('V 0.000 0.350',autonomous=True)
record('no_autonomous_motion_after_confirmed_user_stop',not ok,dict(stop_confirmed_before=confirmed,accepted=ok,reason=reason,writes=u.writes,autonomy_allowed=s.autonomy_allowed))

s,u,c=session();s.fault='STOP_UNCONFIRMED';s.latched=True
ok,reason=s.drive('V 0.000 0.350',autonomous=True)
record('unconfirmed_stop_blocks_motion',not ok,dict(accepted=ok,fault_after=s.fault,writes=u.writes))

s,u,c=session();s.scan_time=c.now-.5
ok,reason=s.drive('V 0.000 0.350',autonomous=True);s.watchdog_tick()
record('drive_and_watchdog_share_scan_freshness',not ok,dict(accepted_with_scan_age_s=.5,accepted=ok,fault_after_watchdog=s.fault,writes=u.writes))

s,u,c=session();s.armed=False;s.latest['safety']='DISARMED';s.last_d0=c.now-10
s.request_stop(wait=False);c.now+=.3;s.watchdog_tick()
record('stop_confirmation_requires_post_write_telemetry',not s.stop_confirmed,dict(stop_confirmed=s.stop_confirmed,d0_age_s=c.now-s.last_d0,writes=u.writes))

s,u,c=session();s.last_d0=c.now-10
ok,reason=s.drive('V 0.000 0.350',autonomous=True)
record('stale_motor_telemetry_blocks_motion',not ok,dict(accepted=ok,d0_age_s=10,writes=u.writes))

node=brain.AGVROSNode.__new__(brain.AGVROSNode);node.initialize_navigation()
node.control=SimpleNamespace(strict_preflight=False)
brain.state=brain.AGVSharedState();st=brain.state
st.body_bounds_m=(-.16,-.12,.10,.12);st.map_mono=st.scan_mono=time.monotonic();st.map_frame='map';st.map_version=1
st.ranges=[2.0]*360
# Point outside the initial rear edge, inside the rectangle after +0.175 rad rotation.
angle=round(math.degrees(math.atan2(.09,-.17)))%360
distance=math.hypot(.17,.09);st.ranges[angle]=distance
px=distance*math.cos(math.radians(angle));py=distance*math.sin(math.radians(angle))
a=.35*.5;lx=math.cos(a)*px+math.sin(a)*py;ly=-math.sin(a)*px+math.cos(a)*py
inside=(-.16 <= lx <= .10 and -.12 <= ly <= .12)
grid=GridPlanner(60,60,.05,(0.,0.,0.),[0]*3600,.20,.15,budget_s=1.)
node._grid=lambda:grid;node._pose_map=lambda:(1.5,1.5,0.)
accepted=node._escape_clear(0.,.35)
record('escape_rotation_checks_lidar_against_rotated_body',not(accepted and inside),dict(accepted=accepted,scan_angle_deg=angle,scan_distance_m=distance,point_inside_rotated_body=inside,point_at_final_body_frame=[lx,ly],map='synthetic known-free; obstacle only in fresh lidar'))

out={'source':'captured Pi source','hardware_opened':False,'results':results,'failed_safety_expectations':sum(not x['safety_expectation_passed'] for x in results)}
(HERE/'offline_repro_results.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
sys.exit(1 if out['failed_safety_expectations'] else 0)
