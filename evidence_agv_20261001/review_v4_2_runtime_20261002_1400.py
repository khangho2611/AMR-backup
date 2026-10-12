"""Final V4.2 independent offline QA: actual main reader/HTTP/watchdog.
Serial.Serial is replaced with FakeUART; HTTP bind moved to localhost port 0.
No hardware port/ROS/process on Pi. Clock is real/unscaled. Main invocation
does NOT satisfy full typed SCAN/MAP/TF or 10s preflight acceptance.
"""
import csv, datetime, hashlib, http.client, importlib.util, io, json, math
import pathlib, queue, sys, threading, time, types
ROOT=pathlib.Path(__file__).resolve().parents[1]
SRC=ROOT/'candidate_agv_unified_brain_v4_2.py'
SHA='7953bef2af04338fc61d89dde3537b142103b952fdc7dfa814b6296684238bf1'
before=hashlib.sha256(SRC.read_bytes()).hexdigest(); assert before==SHA
spec=importlib.util.spec_from_file_location('qa_v42',SRC)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_pwm=0,r_pwm=0,
        l_rpm=0.,r_rpm=0.,x=0.,y=0.,th=0.,v=0.,w=0.)
cases,fixes={},{}
class FakeUART:
    def __init__(self,*args,**kwargs):
        self.is_open=True;self.count='full';self.tx=[];self.rx=queue.Queue()
        self.arm_response=False;self.tuning_sent=threading.Event();self.args=[args,kwargs]
    def write(self,b):
        n=len(b) if self.count=='full' else self.count
        self.tx.append({'mono':time.monotonic(),'line':b.decode().strip(),'expected':len(b),'written':n})
        if b.startswith(b'ARM') and self.arm_response:
            # Actual full D0, deliberately NO ARM ACK or startup banner/diagnostic.
            self.rx.put((json.dumps(dict(D0,safety='ARMED'))+'\r\n').encode())
        if b.startswith(b'TUNING'):self.tuning_sent.set()
        return n
    def readline(self):
        try:return self.rx.get(timeout=.05)
        except queue.Empty:return b''
    def flush(self):pass
    def close(self):self.is_open=False
def reset(uart=True):
    m.state=m.SafeAGVState();u=FakeUART() if uart else None
    a=m.SafeSerialArbiter(u);n=m.SafeAutonomousNavigator(a)
    return m.state,u,a,n
def d0(a,**kwargs):a.parse_line(json.dumps(dict(D0,**kwargs)))
def handler(path,a):
    m.arbiter_instance=a;h=object.__new__(m.SafeWebHandler);h.path=path;h.wfile=io.BytesIO()
    codes=[];h.send_response=lambda c:codes.append(c);h.send_header=lambda *x:None;h.end_headers=lambda:None
    h.do_GET();return {'codes':codes,'body':h.wfile.getvalue().decode()}

s,u,a,n=reset();d0(a,safety='ARMED');s.last_telemetry_mono=time.monotonic()-100
bad=a.send_guarded('V 0.08 0');assert not bad[0] and bad[1]=='REJECTED_STALE_TELEMETRY'
fixes['stale_drive_rejected']=bad
d0(a,safety='ARMED');u.count=1
bad=a.send_guarded('V 0.08 0');assert not bad[0] and s.latched_stop and s.fsm_state=='FAULT_STOP'
fixes['partial_drive_FAULT_latched']=bad

s,u,a,n=reset();d0(a,safety='ARMED');s.latched_stop=True
release=a.release_stop_latch();assert release[0]
cases['release_fresh_ARMED_zero_allowed']=release
s,u,a,n=reset();a.parse_line('{"x":0,"y":0,"th":0,"safety":"DISARMED"}')
s.latched_stop=True;release=a.release_stop_latch();assert release[0]
cases['minimal_D0_defaults_missing_fields_can_release']=dict(release=release,count=s.fresh_d0_count)

s,u,a,n=reset();d0(a,safety='ARMED');s.last_scan_mono=time.monotonic()
a.send_guarded('V 0.04 0')
u.count=1;bad=a.send_guarded('V 0.08 0');u.count='full'
n.watchdog_thread.start();time.sleep(.13);n.stop();n.watchdog_thread.join(.3)
assert s.latched_stop and not any(t['line']=='STOP' for t in u.tx)
cases['partial_fault_latch_without_STOP_then_watchdog_skips']=dict(tx=u.tx,result=bad,
    latch=s.latched_stop,is_moving=s.is_moving,scope='mock commands; NOT MCU watchdog/physical STOP')

s,u,a,n=reset(uart=False);d0(a,safety='ARMED');s.last_scan_mono=time.monotonic();s.auto_mode=True
n.step();s.map_received=True;s.map_w=2;s.map_h=2;s.map_data=[0] # nonempty wrong length
n.step();middle=s.fsm_state;n.step()
assert middle=='RETURNING_HOME' and s.fsm_state=='COMPLETED'
cases['nonempty_bad_map_and_failed_STOP_completed']=dict(mid=middle,final=s.fsm_state,
    map_len=len(s.map_data),expected_map_len=4,UART=False,postSTOP_D0=False)
s,u,a,n=reset(uart=False)
stop=handler('/api/cmd?val=STOP',a);autostop=handler('/api/auto?act=STOP',a)
assert stop['codes']==[500] and autostop['codes']==[200]
fixes['cmd_STOP_noUART_failure_exposed']=stop
cases['auto_STOP_noUART_false_ok']=autostop

s,u,a,n=reset();results=[]
t=threading.Thread(target=lambda:results.append(a.request_tuning(.5,1.5,0.,.45,timeout=.06)))
t.start();assert u.tuning_sent.wait(.2);a.parse_line('{"error":"INVALID_TUNING_RANGE"}');t.join(.3)
assert results[0][0]=='REJECTED';fixes['PID_firmware_error_immediate']=results
u.tuning_sent.clear();results=[]
t=threading.Thread(target=lambda:results.append(a.request_tuning(.5,1.5,0.,.45,timeout=.06)))
t.start();assert u.tuning_sent.wait(.2);t.join(.3)
assert results[0][0]=='FAILED';oldhist=json.loads(json.dumps(s.tuning_history))
a.parse_line('{"ack":"TUNING 0.500 1.500 0.0000 0.450"}')
assert oldhist==s.tuning_history;fixes['late_ACK_no_active_tx_ignored']=True
u.tuning_sent.clear();results=[]
t=threading.Thread(target=lambda:results.append(a.request_tuning(.5,1.5,0.,.45,timeout=.2)))
t.start();assert u.tuning_sent.wait(.2)
a.parse_line('{"ack":"TUNING 19.000 49.000 4.0000 4.000"}');t.join(.4)
assert results[0][0]=='REJECTED'
csv_reply=handler('/api/history_csv',a)
rows=list(csv.reader(io.StringIO(csv_reply['body'].lstrip('\ufeff'))))
assert len(rows[-1])!=len(rows[0])
cases['history_CSV_unquoted_reason_columns']=dict(header_columns=len(rows[0]),
    mismatch_row_columns=len(rows[-1]),row=rows[-1])

s,u,a,n=reset();s.map_received=True;s.map_w=s.map_h=40;s.map_res=.05
s.map_data=[0]*1600
for y in range(40):s.map_data[y*40+32]=-1
goal,path,count=m.ReachableFrontierPlanner.plan_next_frontier_and_path(.3,1.,s)
assert goal is not None
unknown_distance=abs(1.6-goal[0]);assert unknown_distance<m.ROBOT_FOOTPRINT_RADIUS_M
cases['frontier_selected_with_body_overlap_unknown']=dict(goal=goal,path_count=len(path),
    frontier_count=count,unknown_nearest_distance_m=unknown_distance,radius_m=m.ROBOT_FOOTPRINT_RADIUS_M)
cases['new_source_footprint_provenance_unverified']=dict(source_lines='33-35',
    claimed_width_m=.2425,claimed_length_m=.28,claimed_radius_m=.16,
    rectangle_corner_radius_m=math.hypot(.2425,.28)/2,
    note='source newly labels MEASURED; no new human measurement in DB10611-10635; Word track is not body')

# Actual main -> actual Serial reader -> actual HTTP -> ARM -> manual V -> independent watchdog.
# ONLY fake physical Serial + local bind address; no typed ROS or preflight workaround.
m.state=m.SafeAGVState();main_ser=FakeUART();main_ser.arm_response=True
saved_serial=sys.modules.get('serial');sys.modules['serial']=types.SimpleNamespace(Serial=lambda *x,**kw:main_ser)
HTTPClass=m.ThreadedHTTPServer;server_box=[];ready=threading.Event()
def localhost_server(addr,handler_type):
    server=HTTPClass(('127.0.0.1',0),handler_type);server_box.append(server);ready.set();return server
m.ThreadedHTTPServer=localhost_server
errors=[]
def runmain():
    try:m.main()
    except Exception as e:errors.append(repr(e))
mainthread=threading.Thread(target=runmain,daemon=True);started=time.monotonic();mainthread.start()
assert ready.wait(2.)
server=server_box[0]
def req(path):
    c=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=2)
    try:c.request('GET',path);r=c.getresponse();return {'status':r.status,'body':r.read().decode()}
    finally:c.close()
try:
    before_ARM_count=m.state.fresh_d0_count
    ar= req('/api/cmd?val=ARM');elapsed=time.monotonic()-started
    assert ar['status']==200 and before_ARM_count==0
    cases['actual_main_ARM_before_ANY_preflight_without_ACK']=dict(reply=ar,
        count_before=before_ARM_count,count_after=m.state.fresh_d0_count,elapsed_s=elapsed,
        startup_raw_diagnostic=False,ARM_ACK_received=False,boot_session=m.state.boot_session_id,
        scope='actual main/reader/HTTP with FakeUART; no hardware, no full typed-stream acceptance')
    v=req('/api/cmd?val=V%200.08%200')
    deadline=time.monotonic()+.35
    while not m.state.latched_stop and time.monotonic()<deadline:time.sleep(.01)
    assert v['status']==200 and m.state.latched_stop and any(t['line']=='STOP' for t in main_ser.tx)
    fixes['actual_main_manual_watchdog_no_SCAN_STOP']=dict(reply=v,tx=list(main_ser.tx),
        fault=m.state.fault_code,last_scan_mono=m.state.last_scan_mono)
finally:
    server.shutdown();mainthread.join(2.);server.server_close()
    nav=m.navigator_instance
    nav.watchdog_thread.join(.4);nav.nav_thread.join(.4)
    m.ThreadedHTTPServer=HTTPClass
    if saved_serial is None:sys.modules.pop('serial',None)
    else:sys.modules['serial']=saved_serial
assert not mainthread.is_alive() and not main_ser.is_open and not errors
fixes['main_NORMAL_return_closes_fakeUART_stops_running']=dict(errors=errors,
    note='QA explicitly joins/ closes HTTP listener afterwards; no product join/deadline acceptance')
after=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before==after
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf-8') as f:
    json.dump({'time_local':datetime.datetime.now().isoformat(),'timezone':'Asia/Bangkok',
      'source_SHA_before':before,'source_SHA_after':after,'hardware_OPEN_TX':False,'ROS':False,
      'clock':'real/unscaled','scope':'actual main-reader-HTTP-watchdog + components; NOT full typed/preflight acceptance',
      'fixes_limited':fixes,'residuals':cases},f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'evidence':str(out),'fixes':len(fixes),'residuals':len(cases),'hash_stable':True,
                  'hardware':False},ensure_ascii=False))
