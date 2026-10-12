"""QA only: changed seams + actual entry with FakeUART, no hardware/ROS."""
import sys,pathlib,importlib.util,json,time,threading,queue,types,hashlib,http.client,datetime
SRC=pathlib.Path(__file__).resolve().parent.parent/'candidate_agv_unified_brain_v4_4.py'
before=hashlib.sha256(SRC.read_bytes()).hexdigest()
assert before=='56e9e4cbcb070363fd3d29612fa0452cb435455b03ec2a2476c7bb7ba6fe7f15'
sp=importlib.util.spec_from_file_location('parent_v44',SRC);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
D0=dict(safety='DISARMED',mode='PID',l_tgt=0.,r_tgt=0.,l_rpm=0.,r_rpm=0.,l_pwm=0,r_pwm=0,x=0.,y=0.,th=0.,v=0.,w=0.)
fixes={};residuals={}
class FakeUART:
    def __init__(self):self.is_open=True;self.rx=queue.Queue();self.tx=[]
    def write(self,b):
        self.tx.append(dict(mono=time.monotonic(),line=b.decode().strip(),written=len(b)))
        if b.startswith(b'ARM'):self.rx.put((json.dumps(dict(D0,safety='ARMED'))+'\r\n').encode())
        return len(b)
    def readline(self):
        try:return self.rx.get(timeout=.05)
        except queue.Empty:return b''
    def flush(self):pass
    def close(self):self.is_open=False
def reset(u=True):
    m.state=m.SafeAGVState();uart=FakeUART() if u else None
    a=m.SafeSerialArbiter(uart);n=m.SafeAutonomousNavigator(a)
    return m.state,uart,a,n
def parse(a,**kw):a.parse_line(json.dumps(dict(D0,**kw)))
s,u,a,n=reset();parse(a);assert s.fresh_d0_count==1 and s.mcu_state=='DISARMED'
fixes['actual_firmware_schema_parser']=dict(count=s.fresh_d0_count,l_tgt=s.l_tgt,v=s.v)
parse(a,l_tgt=100.);assert not s.preflight_passed and s.preflight_count==0
fixes['nonzero_target_resets_preflight']=True
parse(a,v=.2);assert s.preflight_count==0
fixes['nonzero_v_resets_preflight']=True
parse(a);time.sleep(.56);parse(a);assert s.preflight_count==1 and not s.preflight_passed
fixes['gap_more_than_source_half_second_resets']=True
old=s.preflight_count
parse(a,error='I2C_FAULT');assert s.preflight_count==old+1
residuals['full_D0_plus_error_accepted_not_fault_latched']=dict(preflight_count=s.preflight_count,latch=s.latched_stop,error_input='I2C_FAULT')
s,u,a,n=reset(False);parse(a,safety='ARMED');s.auto_mode=True;s.last_scan_mono=time.monotonic();n.step()
s.map_received=True;s.map_w=s.map_h=3;s.map_data=[0,0];n.step();assert s.fsm_state=='EXPLORING'
fixes['malformed_3x3_data2_HOLD']=dict(fsm=s.fsm_state)
s.map_res=0;s.map_data=[0]*9
try:n.step()
except ZeroDivisionError:residuals['shape_valid_map_res0_crashes_step']='ZeroDivisionError'
else:raise AssertionError('Expected unvalidated map resolution')
fixes['footprint_formula_constant_only']=dict(radius=m.ROBOT_FOOTPRINT_CORNER_RADIUS_M,formula=((.1875/2)**2+(.28/2)**2)**.5+.02,provenance_full_body_unverified=True)
# Actual main-reader-server: only physical Serial fake and localhost ephemeral bind.
m.state=m.SafeAGVState();uart=FakeUART();oldserial=sys.modules.get('serial')
sys.modules['serial']=types.SimpleNamespace(Serial=lambda *a,**kw:uart)
HTTP=m.ThreadedHTTPServer;box=[];ready=threading.Event();errors=[]
def factory(addr,h):
    server=HTTP(('127.0.0.1',0),h);box.append(server);ready.set();return server
m.ThreadedHTTPServer=factory
def run():
    try:m.main()
    except Exception as e:errors.append(repr(e))
mt=threading.Thread(target=run,daemon=True);mt.start();assert ready.wait(2);server=box[0]
def req(path):
    c=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=2)
    try:c.request('GET',path);r=c.getresponse();return dict(code=r.status,body=r.read().decode())
    finally:c.close()
try:
    start=time.monotonic()
    for i in range(81):
        delay=start+i*(9.55/80)-time.monotonic()
        if delay>0:time.sleep(delay)
        uart.rx.put((json.dumps(D0)+'\r\n').encode())
    deadline=time.monotonic()+.2
    while m.state.preflight_count<81 and time.monotonic()<deadline:time.sleep(.005)
    span=m.state.preflight_last_sample_mono-m.state.preflight_start_mono
    assert m.state.preflight_passed and span<10.0
    fixes['actual_main_reader_firmware_D0_count81']=dict(count=m.state.fresh_d0_count,span=span)
    residuals['actual_entry_passes_before_10s_without_boot_diag']=dict(span=span,count=m.state.preflight_count,passed=m.state.preflight_passed,BOOT_banner=False,diag=False,clock='real/unscaled, no state timestamp writes')
    time.sleep(.6);age=time.monotonic()-m.state.last_telemetry_mono
    armed=req('/api/cmd?val=ARM');assert armed['code']==200
    residuals['actual_entry_cached_stale_preflight_ARM_noACK']=dict(last_age=age,reply=armed,tx=list(uart.tx),ARM_ACK_received=False,session_MCU_bound=False)
finally:
    server.shutdown();mt.join(2);server.server_close()
    m.navigator_instance.watchdog_thread.join(.4);m.navigator_instance.nav_thread.join(.4)
    m.ThreadedHTTPServer=HTTP
    if oldserial is None:sys.modules.pop('serial',None)
    else:sys.modules['serial']=oldserial
assert not mt.is_alive() and not uart.is_open and not errors
after=hashlib.sha256(SRC.read_bytes()).hexdigest();assert before==after
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf8') as f:
    json.dump(dict(time_local=datetime.datetime.now().isoformat(),timezone='Asia/Bangkok',source_before=before,source_after=after,hardware=False,ROS=False,clock='real/unscaled',scope='actual main-reader-HTTP FakeUART + changed component seams; no full typed-stream or ownership acceptance',fixes_limited=fixes,residuals=residuals,unchanged_STOP_runtime_UI_residuals='V4.3 review carried by diff/source inspection; not rerun'),f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(dict(evidence=str(out),fixes=len(fixes),residuals=len(residuals),hash_stable=True,hardware=False)))
