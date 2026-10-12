"""Independent QA of final V4.1. Actual components; NO hardware or ROS.

main() uses a fake HTTP server to inspect wiring and cleanup, not to claim full
production lifecycle. Parser uses source-linked MCU JSON. No runtime scaled.
"""
import datetime
import hashlib
import importlib.util
import io
import json
import math
import pathlib
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / 'candidate_agv_unified_brain_v4_1.py'
EXPECTED = '4f6e15627c36f1631fe52ebdaa51874c9abf483a1c8ef1004e80ffffa6d0fced'
before = hashlib.sha256(SRC.read_bytes()).hexdigest()
assert before == EXPECTED
spec = importlib.util.spec_from_file_location('qa_v41', SRC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
D0 = dict(safety='DISARMED', mode='PID', l_tgt=0., r_tgt=0.,
          l_pwm=0, r_pwm=0, l_rpm=0., r_rpm=0., x=0., y=0., th=0., v=0., w=0.)
cases, fixes = {}, {}

class FakeUART:
    is_open = True
    def __init__(self, count='full'):
        self.count = count
        self.tx = []
        self.first_tuning = threading.Event()
        self.second_tuning = threading.Event()
        self.ntuning = 0
    def write(self, data):
        n = len(data) if self.count == 'full' else self.count
        self.tx.append({'line':data.decode().strip(),'expected':len(data),'written':n})
        if data.startswith(b'TUNING'):
            self.ntuning += 1
            (self.first_tuning if self.ntuning == 1 else self.second_tuning).set()
        return n
    def flush(self): pass

def reset(uart=True):
    m.state = m.SafeAGVState()
    u = FakeUART() if uart else None
    a = m.SafeSerialArbiter(u)
    n = m.SafeAutonomousNavigator(a)
    return m.state, u, a, n
def d0(a, **kw): a.parse_line(json.dumps(dict(D0, **kw)))
def http(path, a):
    m.arbiter_instance = a
    h = object.__new__(m.SafeWebHandler)
    h.path, h.wfile = path, io.BytesIO()
    codes=[]
    h.send_response = lambda c: codes.append(c)
    h.send_header = lambda *args: None
    h.end_headers = lambda: None
    h.do_GET()
    return {'codes':codes, 'body':h.wfile.getvalue().decode()}

# Verify limited fixes, so old blockers are not repeated as still unfixed.
s,u,a,n=reset()
d0(a, safety='ARMED')
a.parse_line('{"ack":"PONG"}')
t0=s.last_telemetry_time
a.parse_line('{"x":"NaN","y":0,"th":0,"safety":"FAULT"}')
assert s.last_telemetry_time == t0 and s.x == 0
d0(a, safety='FAULT')
assert s.mcu_state == 'FAULT'
fixes['safety_field_PONG_pose_NaN'] = True
d0(a, safety='ARMED')
a.request_stop()
ok,reason=a.send_guarded('V 0.12 0')
assert not ok and reason == 'REJECTED_LATCHED_STOP'
fixes['write_guard_post_latch_V'] = dict(result=[ok,reason], tx=u.tx)

s,u,a,n=reset()
u.count=1
ok,reason=a.send_guarded('STOP',is_stop=True)
assert not ok and 'PARTIAL_WRITE_FAULT' in reason
fixes['partial_byte_count_reported'] = [ok,reason]
u.count=None
noneok=a.send_guarded('STOP',is_stop=True)
assert noneok[0]
cases['None_write_count_success'] = dict(result=noneok,tx=u.tx)

s,u,a,n=reset()
d0(a,safety='ARMED')
s.last_telemetry_time = time.time()-100
arm=a.request_arm(timeout=.05)
assert arm[0] and s.fresh_d0_count == 1
v=a.send_guarded('V 0.12 0')
assert v[0]
cases['stale_ARM_D0_no_ACK_preflight_and_manualV'] = dict(arm=arm,drive=v,tx=u.tx,
    d0_age_s=time.time()-s.last_telemetry_time,fresh_count=s.fresh_d0_count,auto=s.auto_mode)

s,u,a,n=reset()
d0(a,safety='ARMED')
u.count=1
failed=a.send_guarded('V 0.12 0')
assert not failed[0]
afterfailure={'latched':s.latched_stop,'auto':s.auto_mode,'fsm':s.fsm_state}
u.count='full'
nextv=a.send_guarded('V 0.12 0')
assert nextv[0] and not s.latched_stop
cases['partial_drive_failure_not_FAULT_latched'] = dict(failed=failed,
    state_after_failure=afterfailure,next_drive=nextv,tx=u.tx)

s,u,a,n=reset()
results={}
for safety in ['ARMED','FAULT','DISARMED']:
    d0(a,safety=safety,l_pwm=80,r_pwm=80,l_rpm=50,r_rpm=50)
    s.latched_stop=True
    s.last_telemetry_time=time.time()-100
    results[safety]=a.release_stop_latch()
    assert results[safety][0]
cases['release_ARMED_FAULT_stale_nonzero'] = results

s,u,a,n=reset()
a.parse_line('{"x":0,"y":0,"th":0,"safety":"ARMED"}')
minimal_count=s.fresh_d0_count
assert minimal_count == 1 and s.l_pwm == 0
d0(a,safety='ARMED',l_rpm='NaN',r_rpm='Infinity',l_pwm=9999)
assert math.isnan(s.l_rpm) and math.isinf(s.r_rpm) and s.l_pwm == 9999
cases['minimal_D0_defaultzero_nonfinite_RPM_badPWM'] = dict(minimal_count=minimal_count,
    total_count=s.fresh_d0_count,l_rpm_NaN=math.isnan(s.l_rpm),r_rpm_inf=math.isinf(s.r_rpm),
    l_pwm=s.l_pwm,mcu_state=s.mcu_state)

s,u,a,n=reset()
d0(a,safety='ARMED')
s.last_scan_time=time.time()-1
s.auto_mode=True
n.watchdog_thread.start() # no navigation/caller; actual independent loop
deadline=time.monotonic()+.4
while not s.latched_stop and time.monotonic()<deadline: time.sleep(.01)
n.running=False
n.watchdog_thread.join(.4)
assert s.latched_stop and not s.auto_mode and not n.watchdog_thread.is_alive()
fixes['independent_auto_watchdog_latches_STOP'] = dict(tx=u.tx,latched=s.latched_stop,auto=s.auto_mode)

s,u,a,n=reset()
d0(a,safety='ARMED')
s.last_scan_time=time.time()-1
s.last_telemetry_time=time.time()-1
s.auto_mode=False
n.watchdog_thread.start()
v=a.send_guarded('V 0.12 0')
time.sleep(.16)
n.running=False
n.watchdog_thread.join(.3)
assert v[0] and not any(t['line']=='STOP' for t in u.tx)
cases['manual_drive_ignored_by_watchdog'] = dict(drive=v,tx=u.tx,auto=s.auto_mode,latched=s.latched_stop)

s,u,a,n=reset(uart=False)
d0(a,safety='ARMED')
s.auto_mode=True
s.last_scan_time=time.time()
s.zones['front']=20
n.step()
assert s.home_captured
fixes['home_before_obstacle_branch'] = True
s.zones['front']=999
s.map_received=True # deliberately malformed map received, no data; component fixture
n.step()
mid=s.fsm_state
n.step()
assert mid=='RETURNING_HOME' and s.fsm_state=='COMPLETED'
cases['invalid_received_map_no_UART_completed'] = dict(intermediate=mid,final=s.fsm_state,
    map_received=s.map_received,map_width=s.map_w,postSTOPD0=False,uart_present=False)
reply=http('/api/cmd?val=STOP',a)
assert reply['codes']==[200] and json.loads(reply['body'])['status']=='ok'
cases['HTTP_STOP_no_uart_reports_ok'] = reply

s,u,a,n=reset()
result=[]
t=threading.Thread(target=lambda:result.append(a.request_tuning(.5,1.5,0.,.45,timeout=.15)))
t.start(); assert u.first_tuning.wait(.1)
a.parse_line('{"error":"INVALID_TUNING_RANGE"}')
t.join(.4)
assert result[0][0]=='FAILED' and result[0][1]=='TIMEOUT_NO_MCU_ACK'
hist_before=len(s.tuning_history)
a.parse_line('{"ack":"TUNING 0.500 1.500 0.0000 0.450"}')
assert len(s.tuning_history)==hist_before+1 and a.last_tuning_result=='APPLIED'
cases['PID_error_ignored_timeout_late_ACK_APPLIED'] = dict(request_return=result,
    after_late_ack=a.last_tuning_result,history=s.tuning_history)

s,u,a,n=reset()
resultA,resultB=[],[]
tA=threading.Thread(target=lambda:resultA.append(a.request_tuning(.5,1.5,0.,.45,timeout=.5)))
tB=threading.Thread(target=lambda:resultB.append(a.request_tuning(1.,2.,.1,.6,timeout=.5)))
tA.start(); assert u.first_tuning.wait(.2)
tB.start(); assert u.second_tuning.wait(.2)
a.parse_line('{"ack":"TUNING 1.000 2.000 0.1000 0.600"}')
tA.join(.6);tB.join(.6)
assert resultA[0][0]==resultB[0][0]=='APPLIED'
cases['concurrent_PID_B_ACK_APPLIES_A'] = dict(requestA=[.5,1.5,0.,.45],requestB=[1,2,.1,.6],
    returnA=resultA,returnB=resultB,tx=u.tx,history=s.tuning_history)

# Actual main wiring/cleanup inspection. NO live HTTP socket, no UART replacement.
m.state=m.SafeAGVState()
server_trace=[]
class FakeHTTPServer:
    def __init__(self,addr,handler): server_trace.append({'bind_argument':addr,'handler':handler.__name__})
    def serve_forever(self): server_trace.append({'main_UART':m.arbiter_instance.ser,
        'fresh_d0_count':m.state.fresh_d0_count,'map_received':m.state.map_received})
    def shutdown(self): server_trace.append({'shutdown':True})
saved=m.ThreadedHTTPServer
m.ThreadedHTTPServer=FakeHTTPServer
try: m.main()
finally: m.ThreadedHTTPServer=saved
nav=m.navigator_instance
alive_before_cleanup=[nav.watchdog_thread.is_alive(),nav.nav_thread.is_alive()]
assert m.arbiter_instance.ser is None and all(alive_before_cleanup) and nav.running
cases['actual_main_no_UART_reader_TF_unjoined_threads'] = dict(server=server_trace,
    threads_alive_after_main_return=alive_before_cleanup,running_after_main_return=nav.running,
    scope='main wiring/cleanup seam FakeHTTP; NOT full lifecycle acceptance')
nav.running=False
nav.watchdog_thread.join(.4);nav.nav_thread.join(.4)
assert not nav.watchdog_thread.is_alive() and not nav.nav_thread.is_alive()

after=hashlib.sha256(SRC.read_bytes()).hexdigest()
assert after==before
out=pathlib.Path(__file__).with_suffix('.json')
with out.open('x',encoding='utf-8') as f:
    json.dump({'time_local':datetime.datetime.now().isoformat(),'timezone':'Asia/Bangkok',
      'source':str(SRC),'sha_before':before,'sha_after':after,
      'hardware_OPEN_TX':False,'ROS_started':False,
      'scope':'actual components/parser/HTTP method/main wiring; no full production entry acceptance',
      'fixes_limited':fixes,'residuals':cases},f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'evidence':str(out),'limited_fixes':len(fixes),'residual_cases':len(cases),
                  'hash_stable':before==after,'hardware':False},ensure_ascii=False))
