"""Independent QA only. Actual entry with FakeUART; no physical Serial/Pi/ROS."""
import sys, pathlib, importlib.util, json, time, threading, queue, types
import io, csv, hashlib, http.client, datetime
ROOT=pathlib.Path(__file__).resolve().parent.parent
SRC=ROOT/'candidate_agv_unified_brain_v4_3.py'
before=hashlib.sha256(SRC.read_bytes()).hexdigest()
assert before=='f573ae4f98c978f589709be1b03255921b1c195de0a88e0b58b673ec9a142aa1'
spec=importlib.util.spec_from_file_location('parent_v43',SRC)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
firmware=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_rpm=0.,r_rpm=0.,l_pwm=0,r_pwm=0,x=0.,y=0.,th=0.,v=0.,w=0.)
invented=dict(firmware,target_l_rpm=0.,target_r_rpm=0.)
del invented['l_tgt'];del invented['r_tgt']
fixes={};residuals={}
class FakeUART:
    def __init__(self):
        self.is_open=True;self.tx=[];self.rx=queue.Queue();self.limit=None;self.arm_response=False
    def write(self,b):
        n=len(b) if self.limit is None else min(self.limit,len(b))
        self.tx.append(dict(mono=time.monotonic(),line=b.decode().strip(),expected=len(b),written=n))
        if b.startswith(b'ARM') and self.arm_response:
            self.rx.put((json.dumps(dict(invented,safety='ARMED'))+'\r\n').encode())
        return n
    def readline(self):
        try:return self.rx.get(timeout=.05)
        except queue.Empty:return b''
    def flush(self):pass
    def close(self):self.is_open=False
def reset(has_uart=True):
    m.state=m.SafeAGVState();u=FakeUART() if has_uart else None
    a=m.SafeSerialArbiter(u);n=m.SafeAutonomousNavigator(a)
    return m.state,u,a,n
def parse(a,**kw):a.parse_line(json.dumps(dict(invented,**kw)))
def handler(path,a):
    m.arbiter_instance=a;h=object.__new__(m.SafeWebHandler);h.path=path;h.wfile=io.BytesIO()
    codes=[];h.send_response=lambda c:codes.append(c);h.send_header=lambda *x:None;h.end_headers=lambda:None
    h.do_GET();return dict(codes=codes,body=h.wfile.getvalue().decode())
s,u,a,n=reset();a.parse_line(json.dumps(firmware))
assert s.fresh_d0_count==0
residuals['actual_firmware_l_tgt_r_tgt_rejected']=dict(count=s.fresh_d0_count,mcu=s.mcu_state,source='main.cpp telemetry emit l_tgt/r_tgt/v/w; candidate requires target_l_rpm/target_r_rpm')
bad=a.request_arm(.05);assert not bad[0] and not u.tx
fixes['empty_preflight_ARM_refused']=bad
parse(a,safety='ARMED');s.latched_stop=True
bad=a.release_stop_latch();assert not bad[0]
fixes['ARMED_release_rejected']=bad
s,u,a,n=reset();a.parse_line('{"x":0,"y":0,"th":0,"safety":"DISARMED"}')
assert s.fresh_d0_count==0
fixes['minimal_schema_no_longer_refreshes']=True
s,u,a,n=reset();parse(a,safety='ARMED');a.send_guarded('V 0.04 0')
u.limit=1;bad=a.send_guarded('V 0.08 0');stops=[t for t in u.tx if t['line']=='STOP']
assert len(stops)==3 and all(t['written']==1 for t in stops) and not s.is_moving
residuals['persistent_partial_STOP_hidden_by_local_notmoving']=dict(result=bad,tx=u.tx,is_moving=s.is_moving,latch=s.latched_stop,has_confirmed_field=hasattr(s,'stop_confirmed'),physical_STOP=False)
fixes['partial_drive_now_attempts_three_STOP']=True
s,u,a,n=reset();parse(a,safety='ARMED');out=a.request_stop()
assert out[0] and s.mcu_state=='ARMED'
residuals['STOP_OK_without_DISARMED_confirmation']=dict(result=out,mcu=s.mcu_state,tx=u.tx)
s,u,a,n=reset(False)
r=handler('/api/auto?act=STOP',a);assert r['codes']==[500]
fixes['autoSTOP_noUART_500']=r
s.tuning_history=[dict(tx_id=1,time='14:15',kp=.5,ki=1.5,kd=0,kf=.45,status='REJECTED',reason='ACK_MISMATCH: expected (0.5, 1.5), got (19, 49)')]
r=handler('/api/history_csv',a);rows=list(csv.reader(io.StringIO(r['body'].lstrip('\ufeff'))))
assert [len(row) for row in rows]==[8,8]
fixes['actual_HTTP_CSV_quoted_8_columns']=dict(columns=[len(row) for row in rows])
s,u,a,n=reset(False);parse(a,safety='ARMED');s.auto_mode=True;s.last_scan_mono=time.monotonic();n.step()
s.map_received=True;s.map_w=s.map_h=2;s.map_data=[0];n.step()
assert s.fsm_state=='EXPLORING'
fixes['one_cell_malformedmap_HOLD']=True
s.map_w=s.map_h=3;s.map_data=[0,0];n.step();mid=s.fsm_state;n.step()
assert mid=='RETURNING_HOME' and s.fsm_state=='COMPLETED'
residuals['malformedmap_3x3_two_cells_false_COMPLETED']=dict(mid=mid,final=s.fsm_state,UART=False,postSTOP_D0=False)
s,u,a,n=reset();s.map_received=True;s.map_w=s.map_h=40;s.map_res=.05;s.map_data=[0]*1600
for y in range(40):s.map_data[y*40+32]=-1
goal,path,count=m.ReachableFrontierPlanner.plan_next_frontier_and_path(.3,1.,s)
assert goal is not None
distance=abs(1.6-goal[0]);assert distance>=m.ROBOT_FOOTPRINT_CORNER_RADIUS_M
fixes['vertical_unknown_frontier_standoff']=dict(goal=goal,distance=distance,radius=m.ROBOT_FOOTPRINT_CORNER_RADIUS_M,path_count=len(path))
residuals['footprint_provenance_math']=dict(track_word=.1875,body_length_unverified=.28,constant=.186,formula_result=((.1875/2)**2+(.28/2)**2)**.5+.02,note='Word track is not measured full body; no new human measurement')
# Actual main/reader/HTTP. ONLY replace physical Serial and local listener address.
m.state=m.SafeAGVState();main_ser=FakeUART();main_ser.arm_response=True
oldserial=sys.modules.get('serial');sys.modules['serial']=types.SimpleNamespace(Serial=lambda *a,**kw:main_ser)
HTTPClass=m.ThreadedHTTPServer;box=[];ready=threading.Event();errors=[]
def factory(addr,typ):
    sv=HTTPClass(('127.0.0.1',0),typ);box.append(sv);ready.set();return sv
m.ThreadedHTTPServer=factory
def run():
    try:m.main()
    except Exception as e:errors.append(repr(e))
mt=threading.Thread(target=run,daemon=True);mt.start();assert ready.wait(2)
sv=box[0]
def req(path):
    c=http.client.HTTPConnection('127.0.0.1',sv.server_address[1],timeout=2)
    try:c.request('GET',path);r=c.getresponse();return dict(code=r.status,body=r.read().decode())
    finally:c.close()
try:
    first=req('/api/cmd?val=ARM');assert first['code']==422 and not main_ser.tx
    # Real protocol transported through the actual product reader is ignored.
    for i in range(5):main_ser.rx.put((json.dumps(firmware)+'\r\n').encode())
    deadline=time.monotonic()+.2
    while not main_ser.rx.empty() and time.monotonic()<deadline:time.sleep(.005)
    assert m.state.fresh_d0_count==0
    residuals['actual_main_reader_real_schema_count0']=dict(count=0,mcu=m.state.mcu_state,initial_ARM_reply=first)
    # No direct state assignment/preflight flag. Real clock with a gap > collector1.5s.
    # Deliberate wrong-schema samples have target100/RPM.2/nonzero v,w yet pass new guard.
    sample=dict(invented,target_l_rpm=100.,target_r_rpm=100.,l_rpm=.2,r_rpm=.2,v=1.,w=1.)
    start=time.monotonic()
    for i in range(81):
        scheduled=start if i==0 else start+1.7+(i-1)*(2.55/79)
        wait=scheduled-time.monotonic()
        if wait>0:time.sleep(wait)
        main_ser.rx.put((json.dumps(sample)+'\r\n').encode())
    deadline=time.monotonic()+.2
    while m.state.fresh_d0_count<81 and time.monotonic()<deadline:time.sleep(.005)
    assert m.state.preflight_passed
    before_arm=dict(count=m.state.preflight_disarmed_count,span=time.monotonic()-start,target=m.state.target_l_rpm,rpm=m.state.l_rpm,gap_s=1.7,preflight_passed=m.state.preflight_passed)
    # Last sample then ages out, but the cached flag continues authorizing ARM.
    time.sleep(.6);age=time.monotonic()-m.state.last_telemetry_mono
    armed=req('/api/cmd?val=ARM');assert armed['code']==200
    residuals['actual_main_4s_gap_nonzero_target_stale_ARM_noACK']=dict(before=before_arm,last_age_before_ARM=age,reply=armed,tx=list(main_ser.tx),ARM_ACK_received=False,startup_diag=False,session_mcu_bound=False)
finally:
    sv.shutdown();mt.join(2);sv.server_close()
    m.navigator_instance.watchdog_thread.join(.4);m.navigator_instance.nav_thread.join(.4)
    m.ThreadedHTTPServer=HTTPClass
    if oldserial is None:sys.modules.pop('serial',None)
    else:sys.modules['serial']=oldserial
assert not mt.is_alive() and not main_ser.is_open and not errors
after=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before==after
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf8') as f:
    json.dump(dict(time_local=datetime.datetime.now().isoformat(),timezone='Asia/Bangkok',source_before=before,source_after=after,hardware_OPEN_TX=False,ROS=False,clock='real/unscaled',scope='actual main-reader-HTTP with FakeUART + component/actual HTTP method tests; no typed-stream full acceptance',fixes_limited=fixes,residuals=residuals),f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(dict(evidence=str(out),fixes=len(fixes),residuals=len(residuals),hash_stable=True,hardware=False)))
