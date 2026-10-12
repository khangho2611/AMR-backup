"""Independent NEW V4.8 QA; product unchanged, FakeUART/local HTTP only."""
import pathlib, sys, importlib.util, hashlib, json, time, queue, threading, types, http.client, ast, datetime
SRC=pathlib.Path(__file__).resolve().parent.parent/'candidate_agv_unified_brain_v4_8.py'
sys.path.insert(0,str(SRC.parent))
before=hashlib.sha256(SRC.read_bytes()).hexdigest()
assert before=='6034babff1c72211c20b01624cbe7b433686f3993f2eff554759ceb560b1bd9e'
spec=importlib.util.spec_from_file_location('parent_v48',SRC);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import agv_preflight_static_collector as collector
assert m.validate_telemetry_sample is collector.validate_telemetry_sample
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_rpm=0.,r_rpm=0.,l_pwm=0,r_pwm=0,x=0.,y=0.,th=0.,v=0.,w=0.)
fixes={};residuals={};main_runs=[]
class FakeUART:
    def __init__(self):
        self.is_open=True;self.rx=queue.Queue();self.tx=[];self.limit=None;self.blockV=False
        self.Ventered=threading.Event();self.Vrelease=threading.Event();self.onstop=None;self.armACK=False
    def write(self,b):
        if self.blockV and b.startswith(b'V'):
            self.Ventered.set();assert self.Vrelease.wait(1.5)
        n=min(len(b),self.limit) if self.limit is not None else len(b)
        self.tx.append(dict(mono=time.monotonic(),line=b.decode().strip(),attempted=len(b),written=n))
        if b.startswith(b'ARM') and n==len(b):
            if self.armACK:self.push(dict(ack='ARM',state='ARMED'))
            self.push(dict(D0,safety='ARMED'))
        if b.startswith(b'STOP') and self.onstop:self.onstop()
        return n
    def push(self,p):self.rx.put((json.dumps(p)+'\r\n').encode())
    def readline(self):
        try:return self.rx.get(timeout=.05)
        except queue.Empty:return b''
    def flush(self):pass
    def close(self):self.is_open=False
def reset():
    m.state=m.SafeAGVState();u=FakeUART();a=m.SafeSerialArbiter(u);n=m.SafeAutonomousNavigator(a)
    return m.state,u,a,n
def parse(a,**kw):a.parse_line(json.dumps(dict(D0,**kw)))
def waitfor(pred,bound=.4):
    until=time.monotonic()+bound
    while not pred() and time.monotonic()<until:time.sleep(.003)
    assert pred()
s,u,a,n=reset();parse(a);assert s.preflight_count==0
a.parse_line('{"error":"Scanning I2C bus failed"}');assert s.latched_stop and s.startup_fsm_stage==0
fixes['preboot_D0_ignored_error_substring_not_banner']=dict(count=s.preflight_count,stage=s.startup_fsm_stage,tx=u.tx)
s,u,a,n=reset();parse(a,safety='ARMED');u.limit=1;a.parse_line('{"error":"I2C_FAULT"}');parse(a)
assert s.stop_outcome_observed and not s.stop_outcome_confirmed and s.stop_op_id==0
fixes['unregistered_hardware_STOP_zero_OBSERVED_not_CONFIRMED']=dict(tx=u.tx,observed=s.stop_outcome_observed,confirmed=s.stop_outcome_confirmed,op=s.stop_op_id,write_fault=s.stop_write_fault)
s,u,a,n=reset();parse(a,safety='ARMED');u.limit=1;r=a.request_stop(timeout=.03);parse(a)
assert not r[0] and s.stop_write_fault and not s.stop_outcome_confirmed
fixes['registered_partial_STOP_retains_writefault']=dict(reply=r,confirmed=s.stop_outcome_confirmed,write_fault=s.stop_write_fault,tx=u.tx)
# Changed common writer: original completion order STOP-then-V is now prevented.
s,u,a,n=reset();parse(a,safety='ARMED');u.blockV=True;result={}
dt=threading.Thread(target=lambda:result.update(drive=a.send_guarded('V 0.04 0.00')),daemon=True);dt.start();assert u.Ventered.wait(.4)
ft=threading.Thread(target=lambda:a.parse_line('{"error":"I2C_FAULT"}'),daemon=True);ft.start();time.sleep(.06)
pending=dict(fault_thread_alive=ft.is_alive(),latched=s.latched_stop,fault=s.fault_code,tx=list(u.tx))
u.Vrelease.set();dt.join(1);ft.join(1);assert not dt.is_alive() and not ft.is_alive()
assert u.tx[0]['line'].startswith('V ') and all(x['line']=='STOP' for x in u.tx[1:]) and s.latched_stop and not s.is_moving
fixes['shared_TXmutex_removes_original_STOP_then_V_order']=dict(tx=u.tx,reply=result,pending_while_write_blocked=pending,scope='FakeUART completion order; not cancellation of a write already in progress or physical byte proof')
# New op ID is registered before obtaining the TX mutex; D0 can confirm before any STOP TX.
s,u,a,n=reset();parse(a,safety='ARMED');result={};a.tx_lock.acquire()
st=threading.Thread(target=lambda:result.update(stop=a.request_stop(timeout=.08)),daemon=True);st.start();waitfor(lambda:s.stop_op_id>0)
parse(a);preTX=dict(confirmed=s.stop_outcome_confirmed,observed=s.stop_outcome_observed,op=s.stop_op_id,tx=list(u.tx))
assert preTX['confirmed'] and not preTX['tx']
a.tx_lock.release();st.join(1);assert not st.is_alive() and result['stop'][0]
residuals['new_operation_CONFIRMED_before_first_STOP_TX']=dict(before_TX=preTX,final_reply=result,tx=u.tx)
# A previous registered op leaks into a new reader fault STOP with all writes partial.
s,u,a,n=reset();parse(a,safety='ARMED');old=a.request_stop(timeout=.03);assert not old[0] and s.stop_op_id==1
u.limit=1;a.parse_line('{"error":"I2C_FAULT"}');fault_tx=u.tx[-3:];parse(a)
assert all(x['written']==1 for x in fault_tx) and s.stop_outcome_confirmed and not s.stop_write_fault and s.stop_op_id==1
residuals['old_operation_reused_new_partial_reader_STOP_false_CONFIRMED']=dict(previous=old,new_fault_tx=fault_tx,op=s.stop_op_id,write_fault=s.stop_write_fault,confirmed=s.stop_outcome_confirmed,first_fault=s.first_fault_reason,fault=s.fault_code)
# Error-first change removed the tuning rejection path that V4.7 handled.
s,u,a,n=reset();result={}
tt=threading.Thread(target=lambda:result.update(tuning=a.request_tuning(.5,1.5,.01,.45,timeout=.08)),daemon=True);tt.start();waitfor(lambda:a.active_tuning_tx is not None)
a.parse_line('{"error":"INVALID_TUNING_RANGE"}');tt.join(1);assert not tt.is_alive()
assert result['tuning'][0]=='FAILED' and result['tuning'][1]=='TIMEOUT_NO_MCU_ACK' and s.latched_stop
residuals['tuning_explicit_REJECTED_error_now_timeout_FAILED']=dict(reply=result,history=s.tuning_history,fault=s.fault_code,tx=u.tx)
# Startup component negatives: not product timestamp assignments.
for label,found in [('VIN_without_found',dict(vin_mv=0)),('invalid_I2C_address',dict(i2c_found='0x00'))]:
    s,u,a,n=reset();a.parse_line(json.dumps(dict(info=m.EXACT_BOOT_BANNER)));a.parse_line(json.dumps(dict(info=m.EXACT_I2C_SCAN_BANNER)));a.parse_line(json.dumps(found))
    assert s.startup_fsm_stage==3 and s.i2c_found_seen
    residuals[label+'_accepted_stage3']=dict(input=found,stage=s.startup_fsm_stage,found_seen=s.i2c_found_seen,settling=s.settling_complete)
def run_main(label,bad=False):
    m.state=m.SafeAGVState();uart=FakeUART();oldserial=sys.modules.get('serial');sys.modules['serial']=types.SimpleNamespace(Serial=lambda *a,**kw:uart)
    HTTP=m.ThreadedHTTPServer;box=[];ready=threading.Event();errors=[]
    def factory(addr,h):
        srv=HTTP(('127.0.0.1',0),h);box.append(srv);ready.set();return srv
    m.ThreadedHTTPServer=factory
    def run():
        try:m.main()
        except Exception as e:errors.append(repr(e))
    mt=threading.Thread(target=run,daemon=True);mt.start();assert ready.wait(2);srv=box[0];entry=time.monotonic()
    def req(path):
        c=http.client.HTTPConnection('127.0.0.1',srv.server_address[1],timeout=3)
        try:c.request('GET',path);r=c.getresponse();return dict(code=r.status,body=r.read().decode())
        finally:c.close()
    try:
        if bad:time.sleep(3.6)
        boot=time.monotonic();uart.push(dict(info=m.EXACT_BOOT_BANNER,**({'status_msg':'MIXED'} if bad else {})))
        uart.push(dict(info=m.EXACT_I2C_SCAN_BANNER));uart.push(dict(vin_mv=0) if bad else dict(i2c_found='0x42'))
        waitfor(lambda:m.state.startup_fsm_stage==3)
        stage3_at=time.monotonic();start=time.monotonic()
        for i in range(82):
            delay=start+i*(10.15/81)-time.monotonic()
            if delay>0:time.sleep(delay)
            uart.push(D0)
        waitfor(lambda:m.state.preflight_count>=82)
        snapshot=dict(count=m.state.preflight_count,span=m.state.preflight_last_sample_mono-m.state.preflight_start_mono,stage=m.state.startup_fsm_stage,passed=m.state.preflight_passed,boot_delay=boot-entry,after_found=stage3_at-boot)
        assert snapshot['span']>=10 and snapshot['passed'];reply=req('/api/cmd?val=ARM');assert reply['code']==200
        residuals[label]=dict(preARM=snapshot,reply=reply,tx=list(uart.tx),ARM_ACK_received=False,MCU_session_bound=False,scope='Actual MAIN reader HTTP, FakeUART only; ARM reply injects fresh ARMED D0 without ACK')
        if not bad:
            uart.push(dict(error='I2C_FAULT'));waitfor(lambda:m.state.latched_stop);uart.push(D0);waitfor(lambda:m.state.stop_outcome_observed)
            assert not m.state.stop_outcome_confirmed and m.state.stop_op_id==0
            fixes['actual_MAIN_reader_FAULT_zero_OBSERVED_no_op_CONFIRMED']=dict(op=m.state.stop_op_id,observed=m.state.stop_outcome_observed,confirmed=m.state.stop_outcome_confirmed,tx=list(uart.tx))
        uart.onstop=lambda:uart.push(D0)
    finally:
        srv.shutdown();mt.join(3)
        cleanup=dict(main_alive=mt.is_alive(),UART_closed=not uart.is_open,errors=errors,nav_alive=m.navigator_instance.nav_thread.is_alive(),watchdog_alive=m.navigator_instance.watchdog_thread.is_alive())
        srv.server_close();m.navigator_instance.watchdog_thread.join(.5);m.navigator_instance.nav_thread.join(.5);m.ThreadedHTTPServer=HTTP
        if oldserial is None:sys.modules.pop('serial',None)
        else:sys.modules['serial']=oldserial
    assert not mt.is_alive() and not uart.is_open and not errors
    main_runs.append(dict(label=label,normal_cleanup_limited=cleanup))
run_main('actual_MAIN_valid_diagnostic_organic10s_ARM_without_ACK')
run_main('actual_MAIN_late_mixed_boot_VIN0_without_found_organic10s_ARM',bad=True)
tree=ast.parse(SRC.read_text(encoding='utf8'));imports=[];uses={}
for x in ast.walk(tree):
    if isinstance(x,ast.ImportFrom) and x.module and x.module.startswith(('agv_','candidate_agv_')):imports.append(dict(module=x.module,names=[n.name for n in x.names]))
for name in ('validate_telemetry_sample','EXACT_BOOT_BANNER','EXACT_I2C_SCAN_BANNER','STARTUP_DEADLINE_S'):
    uses[name]=len([x for x in ast.walk(tree) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load) and x.id==name])
after=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before==after
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf8') as f:json.dump(dict(time_local=datetime.datetime.now().isoformat(),timezone='Asia/Bangkok',source_before=before,source_after=after,hardware=False,ROS=False,clock='real unscaled no flags/timestamp backdating/count assignments',actual_imported_validator=m.validate_telemetry_sample.__module__,fixes_limited=fixes,residuals=residuals,audited_imports=imports,imported_load_count=uses,main_runs=main_runs,scope='Actual MAIN-reader-localhost HTTP FakeUART plus NEW component seams; not full typed-stream/owner/crash cleanup/physicalgoal acceptance'),f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(dict(evidence=str(out),fixes=len(fixes),residuals=len(residuals),hash_stable=True,hardware=False)))
