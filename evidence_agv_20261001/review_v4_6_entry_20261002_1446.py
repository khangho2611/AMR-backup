"""QA only, NEW V4.6 changed seams and real-clock main/reader/HTTP FakeUART."""
import pathlib, importlib.util, hashlib, json, time, queue, threading, types, sys, http.client, ast, datetime
SRC=pathlib.Path(__file__).resolve().parent.parent/'candidate_agv_unified_brain_v4_6.py'
before=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before=='854813b8288254c845e05e5ce9a34be745b7709bdeaebe62ef298b1de45643c3'
spec=importlib.util.spec_from_file_location('parent_v46',SRC);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_rpm=0.,r_rpm=0.,l_pwm=0,r_pwm=0,x=0.,y=0.,th=0.,v=0.,w=0.)
fixes={};residuals={}
class FakeUART:
    def __init__(self):self.is_open=True;self.rx=queue.Queue();self.tx=[];self.onstop=None
    def write(self,b):
        self.tx.append(dict(mono=time.monotonic(),line=b.decode().strip(),attempted=len(b),written=len(b)))
        if b.startswith(b'ARM'):self.rx.put((json.dumps(dict(D0,safety='ARMED'))+'\r\n').encode())
        if b.startswith(b'STOP') and self.onstop:self.onstop()
        return len(b)
    def readline(self):
        try:return self.rx.get(timeout=.05)
        except queue.Empty:return b''
    def flush(self):pass
    def close(self):self.is_open=False
def reset():
    m.state=m.SafeAGVState();u=FakeUART();a=m.SafeSerialArbiter(u);n=m.SafeAutonomousNavigator(a)
    return m.state,u,a,n
def parse(a,**kw):a.parse_line(json.dumps(dict(D0,**kw)))
s,u,a,n=reset();parse(a);parse(a,error='I2C_FAULT');assert s.preflight_count==0 and not s.preflight_passed and s.latched_stop
fixes['mixed_error_reset_and_FAULT_latch']=dict(count=s.preflight_count,latch=s.latched_stop,fault=s.fault_code)
s,u,a,n=reset();parse(a,safety='ARMED');r=a.request_stop(timeout=.05)
assert not r[0] and r[1]=='STOP_UNCONFIRMED_TIMEOUT' and s.fault_code==r[1]
fixes['STOP_timeout_False_fault']=dict(reply=r,confirmed=s.stop_outcome_confirmed)
s,u,a,n=reset();parse(a,safety='ARMED');u.onstop=lambda:parse(a,l_tgt=100.,r_tgt=100.,v=1.,w=1.)
r=a.request_stop(timeout=.05);assert not r[0] and not s.stop_outcome_confirmed
fixes['nonzero_targets_vw_fresh_D0_not_confirmed']=dict(reply=r,observed=s.stop_outcome_observed,confirmed=s.stop_outcome_confirmed)
u.onstop=lambda:parse(a);r=a.request_stop(timeout=.05);assert r[0] and s.stop_outcome_confirmed
fixes['fresh_full_zero_after_STOP_confirmed']=dict(reply=r)
s,u,a,n=reset();parse(a,safety='ARMED');s.auto_mode=True;s.last_scan_mono=time.monotonic();n.step();s.map_received=True;s.map_w=s.map_h=3;s.map_data=[0]*9;s.map_res=float('nan');n.step()
assert s.fsm_state=='EXPLORING';fixes['map_NaN_resolution_HOLD']=True
s.map_res=.05;s.map_ox=float('nan')
try:n.step()
except ValueError as e:residuals['map_origin_NaN_crashes_despite_header']=str(e)
else:raise AssertionError('Expected incomplete finite map-origin check')
# Changed error/watchdog seam: real component thread, actual DRIVE, fresh mocked sensors.
s,u,a,n=reset();parse(a,safety='ARMED');assert a.send_guarded('V 0.04 0.00')[0];s.last_scan_mono=time.monotonic();n.watchdog_thread.start()
parse(a,safety='ARMED',error='I2C_FAULT');time.sleep(.18)
stops=[x for x in u.tx if x['line']=='STOP'];assert not stops and s.latched_stop and s.is_moving
residuals['fresh_sensor_I2C_FAULT_latch_without_immediate_STOP']=dict(tx=u.tx,latch=s.latched_stop,is_moving=s.is_moving,fault=s.fault_code,elapsed=.18)
n.stop();assert not n.watchdog_thread.is_alive()
# Changed watchdog claims monitor-until-zero, but first STOP clears motion flags.
s,u,a,n=reset();parse(a,safety='ARMED');assert a.send_guarded('V 0.04 0.00')[0];n.watchdog_thread.start()
deadline=time.monotonic()+1.5
while s.fault_code!='STALE_SENSOR_TIMEOUT' and time.monotonic()<deadline:time.sleep(.01)
assert s.fault_code=='STALE_SENSOR_TIMEOUT';before_stop_count=len([x for x in u.tx if x['line']=='STOP'])
parse(a);time.sleep(.18);assert not s.stop_outcome_confirmed
residuals['watchdog_not_monitoring_latched_pending_late_zero']=dict(stop_count=before_stop_count,later_stop_count=len([x for x in u.tx if x['line']=='STOP']),auto=s.auto_mode,is_moving=s.is_moving,confirmed=s.stop_outcome_confirmed,MCU_state=s.mcu_state,fault=s.fault_code)
n.stop();assert not n.watchdog_thread.is_alive()
# Actual entry: replace physical Serial OPEN and local ephemeral listener only.
m.state=m.SafeAGVState();uart=FakeUART();oldserial=sys.modules.get('serial');sys.modules['serial']=types.SimpleNamespace(Serial=lambda *a,**kw:uart)
HTTP=m.ThreadedHTTPServer;box=[];ready=threading.Event();errors=[]
def factory(addr,h):
    server=HTTP(('127.0.0.1',0),h);box.append(server);ready.set();return server
m.ThreadedHTTPServer=factory
def run():
    try:m.main()
    except Exception as e:errors.append(repr(e))
mt=threading.Thread(target=run,daemon=True);mt.start();assert ready.wait(2);server=box[0]
def req(path):
    c=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=3)
    try:c.request('GET',path);r=c.getresponse();return dict(code=r.status,body=r.read().decode())
    finally:c.close()
def organic_window():
    start=time.monotonic()
    for i in range(82):
        delay=start+i*(10.15/81)-time.monotonic()
        if delay>0:time.sleep(delay)
        uart.rx.put((json.dumps(D0)+'\r\n').encode())
    deadline=time.monotonic()+.25
    while (m.state.preflight_count<82 or not m.state.preflight_passed) and time.monotonic()<deadline:time.sleep(.005)
    span=m.state.preflight_last_sample_mono-m.state.preflight_start_mono
    assert m.state.preflight_passed and span>=10.
    return dict(count=m.state.preflight_count,span=span,clock='real unscaled, no flags/backdate')
try:
    window=organic_window();a=m.arbiter_instance;answer={};a.tx_lock.acquire()
    t=threading.Thread(target=lambda:answer.update(req('/api/cmd?val=ARM')),daemon=True);t.start()
    found=False;deadline=time.monotonic()+1.
    while not found and time.monotonic()<deadline:
        for fr in sys._current_frames().values():
            while fr:
                if fr.f_code.co_name=='request_arm' and fr.f_code.co_filename==str(SRC):found=True;break
                fr=fr.f_back
        time.sleep(.005)
    assert found;time.sleep(.65);age=time.monotonic()-m.state.preflight_last_sample_mono
    a.tx_lock.release();t.join(3);assert not t.is_alive() and answer['code']==422 and not any(x['line']=='ARM' for x in uart.tx)
    fixes['actual_HTTP_ARM_stale_after_TX_lock_refused']=dict(window=window,lastage_at_unlock=age,reply=answer,tx=list(uart.tx))
    window2=organic_window();armed=req('/api/cmd?val=ARM');assert armed['code']==200
    residuals['actual_MAIN_missing_bootdiag_ARMACK_session_still_ARM200']=dict(window=window2,reply=armed,boot_diagnostic_seen=m.state.boot_diagnostic_seen,ARM_ACK_received=False,MCU_session_bound=False,tx=list(uart.tx),fixture='only fresh ARMED D0 from fake transport')
    r=req('/api/cmd?val=STOP');assert r['code']==500 and 'STOP_UNCONFIRMED_TIMEOUT' in r['body']
    fixes['actual_HTTP_STOP_500_unconfirmed']=dict(reply=r,confirmed=m.state.stop_outcome_confirmed,fault=m.state.fault_code)
    r=req('/api/auto?act=STOP');assert r['code']==500
    fixes['actual_HTTP_auto_STOP_500_unconfirmed']=r
    uart.onstop=lambda:uart.rx.put((json.dumps(D0)+'\r\n').encode());r=req('/api/cmd?val=STOP');assert r['code']==200 and m.state.stop_outcome_confirmed
    fixes['actual_HTTP_fullzero_STOP_200_confirmed']=dict(reply=r,confirmed=True)
finally:
    server.shutdown();mt.join(3)
    cleanup=dict(main_alive=mt.is_alive(),UART_closed=not uart.is_open,errors=errors,nav_alive=m.navigator_instance.nav_thread.is_alive(),watchdog_alive=m.navigator_instance.watchdog_thread.is_alive())
    server.server_close();m.navigator_instance.watchdog_thread.join(.5);m.navigator_instance.nav_thread.join(.5);m.ThreadedHTTPServer=HTTP
    if oldserial is None:sys.modules.pop('serial',None)
    else:sys.modules['serial']=oldserial
assert not mt.is_alive() and not uart.is_open and not errors
# Carry unchanged helpers by AST, not rerunning persistent write/CSV/UI tests.
oldtree=ast.parse((SRC.parent/'candidate_agv_unified_brain_v4_5.py').read_text(encoding='utf8'));tree=ast.parse(SRC.read_text(encoding='utf8'))
def body(tree,name):
    return ast.dump(next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name==name),include_attributes=False)
oldhelper=next(x for x in ast.walk(oldtree) if isinstance(x,ast.FunctionDef) and x.name=='_fire_physical_stop_internal')
newhelper=next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name=='_fire_physical_stop_internal')
unchanged=dict(STOP_helper_executable_body=ast.dump(ast.Module(body=oldhelper.body[1:],type_ignores=[]),include_attributes=False)==ast.dump(ast.Module(body=newhelper.body[1:],type_ignores=[]),include_attributes=False),main_only_banner_changes='source diff inspected',normal_cleanup_observed=cleanup)
assert unchanged['STOP_helper_executable_body']
imports=[]
for x in ast.walk(tree):
    if isinstance(x,ast.Import):imports.extend(n.name for n in x.names)
    elif isinstance(x,ast.ImportFrom):imports.append(x.module or '')
after=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before==after
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf8') as f:json.dump(dict(time_local=datetime.datetime.now().isoformat(),timezone='Asia/Bangkok',source_before=before,source_after=after,hardware=False,ROS=False,fixes_limited=fixes,residuals=residuals,unchanged_source_seams=unchanged,audited_imports=[x for x in imports if x.startswith(('agv_','candidate_agv_'))],scope='actual MAIN-reader-HTTP real clock + new component watchdog/map validation; no typed streams/owner lock/physical goal/crash cleanup acceptance'),f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(dict(evidence=str(out),fixes=len(fixes),residuals=len(residuals),hash_stable=True,hardware=False)))
