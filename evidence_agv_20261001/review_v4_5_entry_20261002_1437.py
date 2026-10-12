"""Independent QA of NEW V4.5 seams. No hardware, deployment or product edits."""
import pathlib, importlib.util, hashlib, json, time, queue, threading, types, sys, http.client, ast, datetime
SRC=pathlib.Path(__file__).resolve().parent.parent/'candidate_agv_unified_brain_v4_5.py'
before=hashlib.sha256(SRC.read_bytes()).hexdigest()
assert before=='d9c1a1b677d0380eb3ce53cf048a4fb88798f35704f7cf02f454296bed1e5c1a'
spec=importlib.util.spec_from_file_location('parent_v45',SRC);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_rpm=0.,r_rpm=0.,l_pwm=0,r_pwm=0,x=0.,y=0.,th=0.,v=0.,w=0.)
fixes={};residuals={}
class FakeUART:
    def __init__(self):self.is_open=True;self.rx=queue.Queue();self.tx=[];self.limit=None;self.return_none=False;self.onstop=None
    def write(self,b):
        n=None if self.return_none else min(len(b),self.limit) if self.limit is not None else len(b)
        self.tx.append(dict(mono=time.monotonic(),line=b.decode().strip(),attempted=len(b),written=n))
        if b.startswith(b'ARM') and n==len(b):self.rx.put((json.dumps(dict(D0,safety='ARMED'))+'\r\n').encode())
        if b.startswith(b'STOP') and self.onstop:self.onstop()
        return n
    def readline(self):
        try:return self.rx.get(timeout=.05)
        except queue.Empty:return b''
    def flush(self):pass
    def close(self):self.is_open=False
def reset():
    m.state=m.SafeAGVState();u=FakeUART();a=m.SafeSerialArbiter(u);n=m.SafeAutonomousNavigator(a)
    return m.state,u,a,n
def parse(a,**kw):a.parse_line(json.dumps(dict(D0,**kw)))
s,u,a,n=reset();parse(a);count=s.preflight_count;parse(a,error='I2C_FAULT')
assert s.preflight_count==count
fixes['mixed_error_not_incremented']=True
residuals['mixed_error_does_not_reset_or_latch']=dict(count=s.preflight_count,latch=s.latched_stop,fault=s.fault_code)
s,u,a,n=reset();u.return_none=True;parse(a,safety='ARMED');r=a.send_guarded('V 0.04 0.00');assert not r[0] and s.latched_stop
fixes['None_write_rejected_latched']=dict(reply=r,tx=u.tx)
s,u,a,n=reset();parse(a,safety='ARMED');r=a.request_stop(timeout=.05)
assert r[0] and not s.stop_outcome_confirmed
residuals['STOP_timeout_returns_True_no_FAULT']=dict(reply=r,confirmed=s.stop_outcome_confirmed,fault=s.fault_code,tx=u.tx)
s,u,a,n=reset();parse(a,safety='ARMED');u.onstop=lambda:parse(a,l_tgt=100.,r_tgt=100.,v=1.,w=1.)
r=a.request_stop(timeout=.05);assert r[0] and s.stop_outcome_confirmed
residuals['STOP_false_confirm_nonzero_targets_vw']=dict(reply=r,confirmed=s.stop_outcome_confirmed,l_tgt=s.l_tgt,r_tgt=s.r_tgt,v=s.v,w=s.w)
s,u,a,n=reset();parse(a,safety='ARMED');assert a.send_guarded('V 0.04 0.00')[0];u.limit=1;r=a.send_guarded('V 0.08 0.00')
stops=[t for t in u.tx if t['line']=='STOP'];assert len(stops)==3 and all(t['written']==1 for t in stops)
residuals['persistent_partial_STOP_outcome_ignored']=dict(reply=r,stop_attempts=stops,is_moving=s.is_moving,confirmed=s.stop_outcome_confirmed,fault=s.fault_code)
s,u,a,n=reset();parse(a,safety='ARMED');s.auto_mode=True;s.last_scan_mono=time.monotonic();n.step();s.map_received=True;s.map_w=s.map_h=3;s.map_data=[0]*9;s.map_res=0.;n.step()
assert s.fsm_state=='EXPLORING';fixes['map_res_zero_HOLD']=True
s.map_res=float('nan')
try:n.step()
except ValueError as e:residuals['nonfinite_map_res_crashes_step']=str(e)
else:raise AssertionError('Expected map NaN rejection failure')
# Actual main/reader/HTTP/normal shutdown. Replace physical OPEN and bind locally.
# No product flags, timestamps or preflight counters are assigned.
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
try:
    start=time.monotonic()
    for i in range(82):
        target=start+i*(10.15/81);delay=target-time.monotonic()
        if delay>0:time.sleep(delay)
        uart.rx.put((json.dumps(D0)+'\r\n').encode())
    deadline=time.monotonic()+.25
    while m.state.preflight_count<82 and time.monotonic()<deadline:time.sleep(.005)
    span=m.state.preflight_last_sample_mono-m.state.preflight_start_mono
    assert m.state.preflight_passed and span>=10.
    fixes['organic_actual_main_10s80']=dict(count=m.state.preflight_count,span=span)
    uart.rx.put((json.dumps(dict(D0,error='I2C_FAULT'))+'\r\n').encode());time.sleep(.03)
    residuals['actual_reader_fault_after_pass_ignored']=dict(passed=m.state.preflight_passed,count=m.state.preflight_count,latch=m.state.latched_stop,fault=m.state.fault_code)
    # Use the REAL product TX mutex. Inspect the blocked frame read-only to
    # prove request_arm captured now_mono BEFORE obtaining the mutex.
    a=m.arbiter_instance;answer={};a.tx_lock.acquire()
    t=threading.Thread(target=lambda:answer.update(req('/api/cmd?val=ARM')),daemon=True);t.start()
    captured=None;deadline=time.monotonic()+1.
    while captured is None and time.monotonic()<deadline:
        for fr in sys._current_frames().values():
            while fr:
                if fr.f_code.co_name=='request_arm' and fr.f_code.co_filename==str(SRC) and 'now_mono' in fr.f_locals:
                    captured=fr.f_locals['now_mono'];break
                fr=fr.f_back
        time.sleep(.005)
    assert captured is not None
    delay=captured+.65-time.monotonic()
    if delay>0:time.sleep(delay)
    age=time.monotonic()-m.state.preflight_last_sample_mono
    a.tx_lock.release();t.join(3);assert not t.is_alive() and answer['code']==200
    arms=[x for x in uart.tx if x['line']=='ARM'];assert len(arms)==1 and age>.5
    residuals['actual_HTTP_ARM_prelock_clock_stale_noACK_nodiag']=dict(last_age_at_unlock=age,clock_captured=captured,actual_ARM=arms,reply=answer,boot_diagnostic_seen=m.state.boot_diagnostic_seen,ARM_ACK_received=False,MCU_session_bound=False,fixture='fresh ARMED D0 only')
    response=req('/api/cmd?val=STOP');assert response['code']==200 and 'UNCONFIRMED' in response['body']
    residuals['actual_HTTP_STOP_200_unconfirmed']=dict(reply=response,confirmed=m.state.stop_outcome_confirmed,fault=m.state.fault_code)
finally:
    server.shutdown();mt.join(3)
    product_cleanup=dict(main_alive=mt.is_alive(),UART_closed=not uart.is_open,errors=errors,nav_alive=m.navigator_instance.nav_thread.is_alive(),watchdog_alive=m.navigator_instance.watchdog_thread.is_alive())
    # QA disposal after recording product result; not part of product PASS.
    server.server_close();m.navigator_instance.watchdog_thread.join(.5);m.navigator_instance.nav_thread.join(.5)
    m.ThreadedHTTPServer=HTTP
    if oldserial is None:sys.modules.pop('serial',None)
    else:sys.modules['serial']=oldserial
assert not mt.is_alive() and not uart.is_open and not errors
fixes['normal_actual_main_cleanup_limited']=product_cleanup
after=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before==after
tree=ast.parse(SRC.read_text(encoding='utf8'));imports=[]
for node in ast.walk(tree):
    if isinstance(node,ast.Import):imports.extend(x.name for x in node.names)
    elif isinstance(node,ast.ImportFrom):imports.append(node.module or '')
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf8') as f:json.dump(dict(time_local=datetime.datetime.now().isoformat(),timezone='Asia/Bangkok',source_before=before,source_after=after,hardware=False,ROS=False,clock='real/unscaled; no flag/backdating assignments',fixes_limited=fixes,residuals=residuals,audited_imports=[x for x in imports if x.startswith(('agv_','candidate_agv_'))],scope='actual main-reader-HTTP FakeUART + changed components; no typed streams, ownership, crash cleanup or physical acceptance'),f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(dict(evidence=str(out),fixes=len(fixes),residuals=len(residuals),hash_stable=True,hardware=False)))
