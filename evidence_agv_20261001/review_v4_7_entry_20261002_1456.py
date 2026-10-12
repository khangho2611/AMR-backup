"""Independent QA NEW V4.7 seams, FakeUART/localhost only, no product edits."""
import pathlib, importlib.util, hashlib, json, time, queue, threading, types, sys, http.client, ast, datetime
SRC=pathlib.Path(__file__).resolve().parent.parent/'candidate_agv_unified_brain_v4_7.py'
before=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before=='0fd97a2a87dfb29735653c9f077d26265d8bc7da046ff9412a337046cabe0a16'
spec=importlib.util.spec_from_file_location('parent_v47',SRC);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_rpm=0.,r_rpm=0.,l_pwm=0,r_pwm=0,x=0.,y=0.,th=0.,v=0.,w=0.)
fixes={};residuals={}
class FakeUART:
    def __init__(self):self.is_open=True;self.rx=queue.Queue();self.tx=[];self.limit=None;self.Ventered=threading.Event();self.Vrelease=threading.Event();self.blockV=False;self.onstop=None
    def write(self,b):
        if self.blockV and b.startswith(b'V'):
            self.Ventered.set();assert self.Vrelease.wait(1)
        n=min(len(b),self.limit) if self.limit is not None else len(b)
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
s,u,a,n=reset();parse(a,safety='ARMED');assert a.send_guarded('V 0.04 0.00')[0];s.last_scan_mono=time.monotonic();a.parse_line('{"error":"I2C_FAULT"}')
assert len([x for x in u.tx if x['line']=='STOP'])==3 and s.latched_stop and not s.is_moving
fixes['fresh_sensor_error_immediate_three_STOP']=dict(tx=u.tx,first_fault=s.first_fault_reason)
residuals['fault_STOP_missing_shared_request_deadline']=dict(requested=s.stop_requested_mono,deadline=s.stop_deadline_mono,confirmed=s.stop_outcome_confirmed)
s,u,a,n=reset();parse(a,safety='ARMED');r=a.request_stop(timeout=.05);assert not r[0];reason=s.first_fault_reason;parse(a)
assert s.stop_outcome_confirmed and s.first_fault_reason==reason and s.fault_code=='STOP_UNCONFIRMED_TIMEOUT'
fixes['late_fullzero_updates_confirmation_retains_FAULT']=dict(reply=r,confirmed=s.stop_outcome_confirmed,first_fault=s.first_fault_reason,deadline=s.stop_deadline_mono)
s,u,a,n=reset();parse(a,safety='ARMED');u.limit=1;a.parse_line('{"error":"I2C_FAULT"}');assert all(x['written']==1 for x in u.tx);parse(a)
assert s.stop_outcome_confirmed and s.stop_requested_mono==0
residuals['new_late_handler_false_CONFIRMED_after_persistent_partial_fault_STOP']=dict(tx=u.tx,confirmed=s.stop_outcome_confirmed,requested=s.stop_requested_mono,deadline=s.stop_deadline_mono,first_fault=s.first_fault_reason)
# Actual writer seam: reader fault STOP bypasses the existing TX mutex.
s,u,a,n=reset();parse(a,safety='ARMED');u.blockV=True;result={}
t=threading.Thread(target=lambda:result.update(reply=a.send_guarded('V 0.04 0.00')),daemon=True);t.start();assert u.Ventered.wait(.5)
a.parse_line('{"error":"I2C_FAULT"}');assert s.latched_stop and not s.is_moving
u.Vrelease.set();t.join(1);assert not t.is_alive() and u.tx[-1]['line'].startswith('V ') and s.is_moving
residuals['reader_FAULT_STOP_races_inflight_DRIVE']=dict(tx=u.tx,drive_result=result,latched=s.latched_stop,is_moving=s.is_moving,scope='FakeUART completion order, not physical motor proof')
s,u,a,n=reset();parse(a,safety='ARMED');s.auto_mode=True;s.last_scan_mono=time.monotonic();n.step();s.map_received=True;s.map_w=s.map_h=3;s.map_data=[0]*9;s.map_ox=float('nan');n.step()
assert s.fsm_state=='EXPLORING' and any(x['line']=='V 0.00 0.00' for x in u.tx)
fixes['map_origin_NaN_HOLD_actual_step']=dict(fsm=s.fsm_state,tx=u.tx)
# Actual main-reader-HTTP, no state timestamp/count/passed assignments.
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
        delay=start+i*(10.15/81)-time.monotonic()
        if delay>0:time.sleep(delay)
        uart.rx.put((json.dumps(D0)+'\r\n').encode())
    deadline=time.monotonic()+.25
    while m.state.preflight_count<82 and time.monotonic()<deadline:time.sleep(.005)
    span=m.state.preflight_last_sample_mono-m.state.preflight_start_mono
    assert span>=10.
    missing=req('/api/cmd?val=ARM');assert missing['code']==422 and not any(x['line']=='ARM' for x in uart.tx)
    fixes['actual_MAIN_organic10s82_missing_banners_ARM_refused']=dict(count=m.state.preflight_count,span=span,reply=missing,tx=list(uart.tx))
    # Late malformed/substrings and reversed diagnostic order. No found address,
    # no post-diagnostic 10s window, no ARM ACK or firmware session reply.
    banners_at=time.monotonic()
    uart.rx.put(b'{"error":"Scanning I2C bus failed"}\r\n')
    uart.rx.put(b'BENCH SERIAL ONLY\r\n')
    uart.rx.put((json.dumps(D0)+'\r\n').encode());time.sleep(.04)
    a=m.arbiter_instance;passed=m.state.preflight_passed;count=m.state.preflight_count;armed=req('/api/cmd?val=ARM')
    assert armed['code']==200 and passed
    residuals['actual_MAIN_late_reversed_error_banner_preboot_window_ARM_noACK']=dict(preboot_span=span,preboot_count=82,banners_elapsed=banners_at-start,postbanner_before_ARM=time.monotonic()-banners_at,preflight_count=count,passed=passed,reply=armed,tx=list(uart.tx),boot_seen=m.state.boot_banner_seen,i2c_seen=m.state.i2c_scan_seen,settling=m.state.settling_complete,i2c_found=False,ARM_ACK_received=False,MCU_session_bound=False)
    # Actual reader fault path also skips lock/STOP operation registration.
    uart.rx.put(b'{"error":"I2C_FAULT"}\r\n');deadline=time.monotonic()+.3
    while not m.state.latched_stop and time.monotonic()<deadline:time.sleep(.005)
    assert m.state.latched_stop and len([x for x in uart.tx if x['line']=='STOP'])==3
    actual_first=m.state.first_fault_reason
    uart.rx.put((json.dumps(D0)+'\r\n').encode());deadline=time.monotonic()+.3
    while not m.state.stop_outcome_confirmed and time.monotonic()<deadline:time.sleep(.005)
    assert m.state.stop_outcome_confirmed and m.state.stop_requested_mono==0
    residuals['actual_reader_FAULT_zero_CONFIRMED_without_STOP_operation']=dict(tx=list(uart.tx),confirmed=m.state.stop_outcome_confirmed,requested=m.state.stop_requested_mono,deadline=m.state.stop_deadline_mono,first_fault=m.state.first_fault_reason)
    uart.onstop=lambda:uart.rx.put((json.dumps(D0)+'\r\n').encode())
finally:
    server.shutdown();mt.join(3)
    cleanup=dict(main_alive=mt.is_alive(),UART_closed=not uart.is_open,errors=errors,nav_alive=m.navigator_instance.nav_thread.is_alive(),watchdog_alive=m.navigator_instance.watchdog_thread.is_alive())
    server.server_close();m.navigator_instance.watchdog_thread.join(.5);m.navigator_instance.nav_thread.join(.5);m.ThreadedHTTPServer=HTTP
    if oldserial is None:sys.modules.pop('serial',None)
    else:sys.modules['serial']=oldserial
assert not mt.is_alive() and not uart.is_open and not errors
tree=ast.parse(SRC.read_text(encoding='utf8'));imports=[];uses={}
for x in ast.walk(tree):
    if isinstance(x,ast.ImportFrom) and x.module and x.module.startswith(('agv_','candidate_agv_')):imports.append(dict(module=x.module,names=[n.name for n in x.names]))
for name in ('EXACT_BOOT_BANNER','EXACT_I2C_SCAN_BANNER','STARTUP_DEADLINE_S'):
    uses[name]=len([x for x in ast.walk(tree) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load) and x.id==name])
after=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before==after
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf8') as f:json.dump(dict(time_local=datetime.datetime.now().isoformat(),timezone='Asia/Bangkok',source_before=before,source_after=after,hardware=False,ROS=False,clock='real unscaled no flags/backdating/count writes',fixes_limited=fixes,residuals=residuals,audited_imports=imports,imported_constants_load_count=uses,normal_cleanup_limited=cleanup,scope='actual MAIN-reader-HTTP FakeUART + changed component parser/write/map seams; no full typed-stream/lockownership/physicalgoal acceptance'),f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(dict(evidence=str(out),fixes=len(fixes),residuals=len(residuals),hash_stable=True,hardware=False)))
