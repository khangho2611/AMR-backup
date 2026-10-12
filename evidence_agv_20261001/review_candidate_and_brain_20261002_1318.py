"""Independent OFFLINE QA. Never imports ROS brain or opens physical Serial."""
import ast, concurrent.futures, hashlib, json, math, pathlib, sys, threading, time, types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import candidate_agv_motion_supervisor_runner_v08 as mod

FILES = ['candidate_agv_motion_supervisor_runner_v08.py', 'candidate_agv_serial_arbiter_bridge_v3_v08.py', 'agv_unified_brain.py']
def hashes():
    return {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}
BEFORE = hashes()
assert BEFORE[FILES[0]] == '907c5882620b2a65b78c7f69a21893e941c073102f5e3c56ba192370688a2750'
assert BEFORE[FILES[1]] == '95c8667ffd66a1076e68ce55a381afaee5f9618c7a705c991b61ae2e9978213d'
assert BEFORE[FILES[2]] == 'ff009266bc744da14b625c83b98f52c15f0cfd0d55cf3b047c2f541e7c1608e6'
OUT = ROOT/'evidence_agv_20261001/parent_candidate_brain_20261002_1318'
OUT.mkdir(exist_ok=False)
D0 = dict(safety='DISARMED', mode='PID', l_tgt=0., r_tgt=0., l_pwm=0, r_pwm=0, l_rpm=0., r_rpm=0., x=0., y=0., th=0., v=0., w=0.)

class UART:
    def __init__(self, case):
        self.case=case; self.armed=False; self.ack=False; self.closed=False; self.writes=[]; self.received=[]; self.first_v=None
        self.startup=[{'info':mod.EXACT_BOOT_BANNER}, {'info':mod.EXACT_I2C_SCAN_BANNER}, {'i2c_found':'0x42'}, {'vin_mv':12033}]
    def write(self, b):
        now=time.monotonic(); n=1 if self.case=='partial_STOP' and b==b'STOP\n' else len(b)
        self.writes.append(dict(t=now,bytes=b.decode(),written=n))
        if b==b'ARM\n': self.armed=True; self.ack=True
        if b.startswith(b'V ') and self.first_v is None: self.first_v=now
        # In partial case, independent zero D0 models an external stop, not acceptance of partial TX.
        if b in (b'STOP\n',b'DISARM\n'): self.armed=False
        return n
    def flush(self): pass
    def close(self): self.closed=True
    def readline(self):
        time.sleep(.02 if self.armed else .08)
        if self.startup: p=self.startup.pop(0)
        elif self.ack: self.ack=False; p={'ack':'ARM','state':'ARMED'}
        else:
            p=dict(D0,safety='ARMED' if self.armed else 'DISARMED')
            if self.armed and self.first_v is not None:
                elapsed=time.monotonic()-self.first_v
                if self.case=='overspeed': p.update(l_rpm=30.,r_rpm=30.)
                elif self.case=='stall': p.update(l_pwm=85,r_pwm=85)
                elif self.case=='mismatch': p.update(l_rpm=20.,r_rpm=2.)
                elif self.case=='invalid_PWM': p.update(l_pwm='BAD_PWM',r_pwm=85)
                else: p.update(l_rpm=10.,r_rpm=10.,l_pwm=30,r_pwm=30)
        self.received.append(dict(t=time.monotonic(),packet=p))
        return (json.dumps(p)+'\n').encode()

def candidate(case):
    u=UART(case)
    r=mod.HardwareMotionRunner(mock_serial=None,target_v=.08,nominal_time=1.,hard_time_cap=1.5,output_dir=str(OUT/case))
    # ONLY hardware open/lock seams replaced in normal and fault cases.
    r.acquire_port_lock=lambda:True
    def fake_open(): r.ser=u; r.transport=mod.TransportWrapper(u); return True
    r.open_transport=fake_open
    if case=='no_caller':
        # Caller stalls after ARM; actual reader/watchdog remain unmodified and run autonomously.
        original_start=mod.MotionSupervisor.start_motion
        def start_then_pause(s,now):
            ok=original_start(s,now)
            if ok: time.sleep(1.8)
            return ok
        # Instance assigned after creation via caller-side subclass seam, isolated from other cases.
        original_fake_open=fake_open
        # Execute this case separately to avoid mutating global class used by concurrent cases.
        mod.MotionSupervisor.start_motion=start_then_pause
    start=time.monotonic(); exception=None
    try: code=r.execute_lifecycle()
    except Exception as e: code=None; exception=repr(e)
    finally:
        if case=='no_caller': mod.MotionSupervisor.start_motion=original_start
    report=dict(case=case,exit=code,exception=exception,elapsed=time.monotonic()-start,final=r.final_report,
        preflight_passed=r.preflight_passed,postdiag_count=len(r.preflight_valid_samples),
        postdiag_span=r.preflight_last_mono-r.preflight_first_mono if r.preflight_first_mono is not None else None,
        gate_confirmed=r.arbiter.stop_confirmed,stop_confirmed=r.supervisor.stop_confirmed,
        fault=r.supervisor.fault_tripped,reason=r.supervisor.fault_reason,
        closed=u.closed,reader_alive=r.reader_thread.is_alive(),watchdog_alive=r.watchdog_thread.is_alive(),
        writes=u.writes,records=u.received)
    return report

def brain_cases():
    # Compile exact methods from AST; no AGVROSNode.__init__, ROS import, hardware, or server.
    source=(ROOT/'agv_unified_brain.py').read_text(encoding='utf8')
    tree=ast.parse(source); cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='AGVROSNode')
    names=['send_cmd','scan_cb','find_best_frontier','auto_nav_loop']
    extracted=ast.Module(body=[x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name in names],type_ignores=[])
    ns={'math':math,'time':time,'json':json}
    exec(compile(ast.fix_missing_locations(extracted),'agv_unified_brain.py:exact_methods','exec'),ns)
    results=[]
    def fixture():
        s=types.SimpleNamespace(lock=threading.Lock(),auto_mode=True,zones={k:999 for k in ['front','front_right','front_left','right','left','back','back_left','back_right']},
          robot_x=0.,robot_y=0.,robot_th=0.,map_width=0,map_height=0,map_resolution=.2,map_origin_x=0.,map_origin_y=0.,map_data=[],map_received=False)
        ns['state']=s
        n=types.SimpleNamespace(explore_state='INITIAL_SPIN',spin_timer=0.,stuck_counter=0,last_pos=(0.,0.),home_x=0.,home_y=0.,home_th=0.)
        for name in names: setattr(n,name,types.MethodType(ns[name],n))
        n.commands=[]; n.send_cmd=n.commands.append
        return s,n
    s,n=fixture();n.auto_nav_loop()
    results.append(dict(case='NO_SCAN_NO_MAP_NO_FRESH_D0',commands=n.commands,phase=n.explore_state,violation=bool(n.commands)))
    s,n=fixture(); n.explore_state='EXPLORING';n.auto_nav_loop();s.robot_th=math.pi;n.auto_nav_loop()
    results.append(dict(case='NO_MAP_FALSE_COMPLETION_WRONG_HEADING',phase=n.explore_state,reported_phase=s.explore_phase,auto=s.auto_mode,commands=n.commands,violation=not s.auto_mode))
    s,n=fixture();s.map_width=s.map_height=11;s.map_data=[100]*121;s.map_data[5*11+5]=0;s.map_data[6*11+5]=-1
    goal=n.find_best_frontier(0.,0.)
    results.append(dict(case='ISOLATED_UNREACHABLE_FRONTIER',goal=goal,violation=goal is not None))
    s,n=fixture();msg=types.SimpleNamespace(angle_min=math.pi/2,angle_increment=1.,range_min=.01,range_max=12.,ranges=[.5]);n.scan_cb(msg)
    results.append(dict(case='ROS_PLUS90_LEFT_MAPPED_RIGHT',zones=s.zones,violation=s.zones['right']==50 and s.zones['left']==999))
    s,n=fixture();s.zones['front']=10
    class Sleeper:
        def sleep(self,duration):
            if s.auto_mode: s.auto_mode=False;n.commands.append('STOP')
    ns['time']=Sleeper();n.auto_nav_loop();ns['time']=time
    results.append(dict(case='STOP_DURING_BLOCKING_AVOIDANCE',commands=n.commands,auto=s.auto_mode,violation=n.commands[-1]!='STOP'))
    s,n=fixture()
    class Sink:
        is_open=True
        def __init__(self):self.writes=[]
        def write(self,b):self.writes.append(b.decode());return len(b)
    n.ser=Sink();n.send_cmd=types.MethodType(ns['send_cmd'],n);n.get_logger=lambda:types.SimpleNamespace(error=lambda s:None)
    n.send_cmd('M 120 120')
    results.append(dict(case='AUTO_ARM_NO_ACK_OR_PREFLIGHT',writes=n.ser.writes,violation=n.ser.writes==['ARM\r\n','M 120 120\r\n']))
    return results

if __name__=='__main__':
    brain=brain_cases()
    cases=['positive','overspeed','stall','mismatch','partial_STOP','invalid_PWM']
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: candidate_results=list(pool.map(candidate,cases))
    candidate_results.append(candidate('no_caller'))
    after=hashes();assert BEFORE==after,(BEFORE,after)
    result=dict(scope='OFFLINE real production execute_lifecycle/gate/reader/watchdog with real unscaled 10s/80; no-caller pauses start return; brain exact AST methods no ROS/import/init/hardware',before=BEFORE,after=after,stable=True,candidate=candidate_results,brain=brain)
    with (OUT/'review.json').open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(evidence=str(OUT/'review.json'),stable=True,brain=brain,candidate=[{k:v for k,v in c.items() if k not in ['records','writes']}|{'ARM_count':sum(x['bytes']=='ARM\n' for x in c['writes']),'V_count':sum(x['bytes'].startswith('V ') for x in c['writes']),'STOP_count':sum(x['bytes']=='STOP\n' for x in c['writes'])} for c in candidate_results]),ensure_ascii=False))
