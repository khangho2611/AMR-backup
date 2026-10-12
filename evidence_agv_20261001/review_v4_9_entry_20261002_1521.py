"""Independent NEW V4.9 entry/component QA. FakeUART only, no product edits."""
import pathlib,sys,importlib.util,hashlib,json,time,queue,threading,types,http.client,ast,datetime
SRC=pathlib.Path(__file__).resolve().parent.parent/'candidate_agv_unified_brain_v4_9.py';sys.path.insert(0,str(SRC.parent))
before=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before=='7cf850b304460b2195412510deab1d2075a1e707147b5670d410169f10050b8f'
spec=importlib.util.spec_from_file_location('parent_v49',SRC);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import agv_preflight_static_collector as collector
assert m.validate_telemetry_sample is collector.validate_telemetry_sample
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_rpm=0.,r_rpm=0.,l_pwm=0,r_pwm=0,x=0.,y=0.,th=0.,v=0.,w=0.)
fixes={};residuals={}
class FakeUART:
    def __init__(self):
        self.is_open=True;self.rx=queue.Queue();self.tx=[];self.limit=None;self.blockSTOP=False
        self.STOPentered=threading.Event();self.STOPrelease=threading.Event();self.onstop=None
    def write(self,b):
        if self.blockSTOP and b.startswith(b'STOP'):
            self.STOPentered.set();assert self.STOPrelease.wait(1.5)
        n=min(len(b),self.limit) if self.limit is not None else len(b)
        self.tx.append(dict(mono=time.monotonic(),line=b.decode().strip(),expected=len(b),written=n))
        if b.startswith(b'STOP') and self.onstop:self.onstop()
        return n
    def push(self,p):self.rx.put((json.dumps(p)+'\r\n').encode())
    def readline(self):
        try:return self.rx.get(timeout=.05)
        except queue.Empty:return b''
    def flush(self):pass
    def close(self):self.is_open=False
def reset():
    m.state=m.SafeAGVState();u=FakeUART();a=m.SafeSerialArbiter(u);return m.state,u,a
def parse(a,**kw):a.parse_line(json.dumps(dict(D0,**kw)))
def waitfor(pred,bound=.5):
    until=time.monotonic()+bound
    while not pred() and time.monotonic()<until:time.sleep(.003)
    assert pred()
# Strictly changed startup component negatives, no product clock/state flags.
s,u,a=reset();a.parse_line(json.dumps(dict(info=m.EXACT_BOOT_BANNER,status_msg='extra')));assert s.startup_fsm_stage==0
a.parse_line(json.dumps(dict(info=m.EXACT_BOOT_BANNER)));a.parse_line(json.dumps(dict(info=m.EXACT_I2C_SCAN_BANNER)))
a.parse_line('{"i2c_found":"0x00"}');assert s.startup_fsm_stage==2
a.parse_line('{"vin_mv":0}');assert s.startup_fsm_stage==2 and not s.i2c_found_seen
fixes['mixed_boot_addr0_VIN0_without_found_refused']=dict(stage=s.startup_fsm_stage,found=s.i2c_found_seen,tx=u.tx)
# First STOP operation: previous V4.8 pre-TX-zero example now stays unconfirmed.
s,u,a=reset();parse(a,safety='ARMED');result={};a.tx_lock.acquire()
t=threading.Thread(target=lambda:result.update(stop=a.request_stop(timeout=.04)),daemon=True);t.start();time.sleep(.02);parse(a)
assert s.stop_op_id==0 and not s.stop_outcome_confirmed and not u.tx
waiting=dict(op=s.stop_op_id,confirmed=s.stop_outcome_confirmed,tx=list(u.tx));u.blockSTOP=True;a.tx_lock.release();assert u.STOPentered.wait(.4)
parse(a);assert s.stop_op_id==1 and s.stop_write_complete_mono==0 and not s.stop_outcome_confirmed
blocked=dict(op=s.stop_op_id,confirmed=s.stop_outcome_confirmed,completion=s.stop_write_complete_mono,tx=list(u.tx))
u.STOPrelease.set();t.join(1);assert not t.is_alive() and not result['stop'][0]
parse(a);assert s.stop_outcome_confirmed
fixes['first_STOP_preTX_zero_rejected_late_postTX_zero_confirmed']=dict(waiting_mutex=waiting,first_write_blocked=blocked,reply=result,late_confirmed=s.stop_outcome_confirmed,fault=s.fault_code,tx=u.tx)
# Old operation -> new partial reader fault allocates new op and retains writefault.
s,u,a=reset();parse(a,safety='ARMED');old=a.request_stop(timeout=.03);oldop=s.stop_op_id;u.limit=1;a.parse_line('{"error":"I2C_FAULT"}');parse(a)
assert s.stop_op_id==oldop+1 and s.stop_write_fault and not s.stop_outcome_confirmed and s.stop_outcome_observed
fixes['new_reader_FAULT_operation_partial_zero_not_confirmed']=dict(previous=old,oldop=oldop,newop=s.stop_op_id,write_fault=s.stop_write_fault,observed=s.stop_outcome_observed,confirmed=s.stop_outcome_confirmed,tx=u.tx)
# Dedicated tuning range rejection restored with real transaction and exact MCU error.
s,u,a=reset();result={};t=threading.Thread(target=lambda:result.update(tuning=a.request_tuning(.5,1.5,.01,.45,timeout=.1)),daemon=True);t.start();waitfor(lambda:a.active_tuning_tx is not None)
a.parse_line('{"error":"INVALID_TUNING_RANGE"}');t.join(.5);assert not t.is_alive() and result['tuning'][0]=='REJECTED' and not s.latched_stop
assert not any(x['line']=='STOP' for x in u.tx)
fixes['explicit_MCU_tuning_error_REJECTED_not_timeout_or_hardware_STOP']=dict(reply=result,history=s.tuning_history,tx=u.tx)
# NEW gate uses previous stop_write_complete_mono during a subsequent STOP write.
s,u,a=reset();parse(a,safety='ARMED');old=a.request_stop(timeout=.03);oldcompletion=s.stop_write_complete_mono;oldop=s.stop_op_id
u.blockSTOP=True;result={};t=threading.Thread(target=lambda:result.update(stop=a.request_stop(timeout=.04)),daemon=True);t.start();assert u.STOPentered.wait(.4)
parse(a);snapshot=dict(op=s.stop_op_id,oldop=oldop,completion=s.stop_write_complete_mono,oldcompletion=oldcompletion,confirmed=s.stop_outcome_confirmed,tx=list(u.tx))
assert snapshot['op']==oldop+1 and snapshot['completion']==oldcompletion and snapshot['confirmed'] and len(u.tx)==3
u.STOPrelease.set();t.join(1);assert not t.is_alive() and not result['stop'][0] and s.stop_outcome_confirmed
residuals['new_STOP_reuses_old_completion_preTX_CONFIRMED_and_timeout_disagree']=dict(before_new_TX=snapshot,final_reply=result,final_confirmed=s.stop_outcome_confirmed,tx=u.tx)
# Actual MAIN-reader-HTTP with organic ordered startup and full 10s attempt.
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
    uart.limit=1;r=req('/api/cmd?val=STOP');health=req('/api/telemetry');assert r['code']==500
    assert m.state.stop_write_fault and m.state.latched_stop and m.state.fault_code is None and m.state.first_fault_reason is None
    residuals['actual_MAIN_partial_STOP500_public_FAULT_null_immediate']=dict(reply=r,health=health,write_fault=m.state.stop_write_fault,fault=m.state.fault_code,first_reason=m.state.first_fault_reason,tx=list(uart.tx))
    uart.limit=None;uart.push(D0);waitfor(lambda:m.state.fresh_d0_count>0);release=req('/api/cmd?val=RELEASE_LATCH');assert release['code']==200
    boot=time.monotonic();uart.push(dict(info=m.EXACT_BOOT_BANNER));uart.push(dict(info=m.EXACT_I2C_SCAN_BANNER));uart.push(dict(i2c_found='0x42'));uart.push(dict(vin_mv=12033))
    waitfor(lambda:m.state.startup_fsm_stage==3);assert not m.state.latched_stop
    start=time.monotonic();sent=[];trip=None
    for i in range(82):
        delay=start+i*(10.15/81)-time.monotonic()
        if delay>0:time.sleep(delay)
        uart.push(D0);sent.append(time.monotonic())
        if trip is None and m.state.latched_stop:trip=dict(elapsed=time.monotonic()-boot,count=m.state.preflight_count,stage=m.state.startup_fsm_stage,fault=m.state.fault_code)
    waitfor(lambda:m.state.fresh_d0_count>=81)
    arm=req('/api/cmd?val=ARM');assert arm['code']==422 and not any(x['line']=='ARM' for x in uart.tx)
    assert m.state.fault_code=='HARDWARE_FAULT_OBSERVED: STARTUP_DEADLINE_EXCEEDED' and m.state.preflight_count==0
    residuals['actual_MAIN_valid_startup_3_5s_deadline_applied_to_10s_postdiag_FAIL']=dict(sent=82,sent_span=sent[-1]-sent[0],max_sent_gap=max(b-a for a,b in zip(sent,sent[1:])),trip=trip,preflight_count=m.state.preflight_count,stage=m.state.startup_fsm_stage,fresh_d0=m.state.fresh_d0_count,reply=arm,tx=list(uart.tx),scope='positive exact boot/scan/found/VIN+full zero stream; no unsafe packet needed')
    uart.onstop=lambda:uart.push(D0)
finally:
    server.shutdown();mt.join(3)
    cleanup=dict(main_alive=mt.is_alive(),UART_closed=not uart.is_open,errors=errors,nav_alive=m.navigator_instance.nav_thread.is_alive(),watchdog_alive=m.navigator_instance.watchdog_thread.is_alive(),stop_confirmed=m.state.stop_outcome_confirmed,final_fault=m.state.fault_code)
    server.server_close();m.navigator_instance.watchdog_thread.join(.5);m.navigator_instance.nav_thread.join(.5);m.ThreadedHTTPServer=HTTP
    if oldserial is None:sys.modules.pop('serial',None)
    else:sys.modules['serial']=oldserial
assert not mt.is_alive() and not uart.is_open and not errors
tree=ast.parse(SRC.read_text(encoding='utf8'));imports=[]
for x in ast.walk(tree):
    if isinstance(x,ast.ImportFrom) and x.module and x.module.startswith(('agv_','candidate_agv_')):imports.append(dict(module=x.module,names=[n.name for n in x.names]))
after=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before==after
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf8') as f:json.dump(dict(time_local=datetime.datetime.now().isoformat(),timezone='Asia/Bangkok',source_before=before,source_after=after,clock='real unscaled no product timestamp/count/passed assignments',hardware=False,ROS=False,fixes_limited=fixes,residuals=residuals,actual_imported_validator=m.validate_telemetry_sample.__module__,audited_imports=imports,normal_cleanup_limited=cleanup,scope='actual MAIN reader HTTP FakeUART plus NEW component STOP/classifier/PID seams; no positive ARM fullentry possible because startup trips before10s, no fulltyped/owner/crash/physicalgoal acceptance'),f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(dict(evidence=str(out),fixes=len(fixes),residuals=len(residuals),hash_stable=True,hardware=False)))
