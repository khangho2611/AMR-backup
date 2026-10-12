"""Independent offline QA of the FINAL ecf2 v4 snapshot; no hardware or ROS.

FakeUART is the only transport. Assertions confirm reproductions, NOT product PASS.
HTTP handler is executed with an in-memory response sink, not a network server.
The planner barrier wraps the actual planner and preserves its actual result.
"""
import datetime
import hashlib
import importlib.util
import io
import json
import math
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'candidate_agv_unified_brain_v4.py'
EXPECTED = 'ecf2fabc531cb201729670c056851bb142255203a455e2d0f809445e8e059bc5'
OUT = pathlib.Path(__file__).with_suffix('.json')
before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
assert before == EXPECTED, 'snapshot changed: do not QA editing source'
spec = importlib.util.spec_from_file_location('qa_v4_snapshot', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class FakeUART:
    is_open = True
    def __init__(self, partial=False):
        self.partial = partial
        self.tx = []
        self.tuning_written = threading.Event()
    def write(self, data):
        self.tx.append({'time': time.monotonic(), 'line': data.decode().strip(),
                        'expected': len(data), 'written': 1 if self.partial else len(data)})
        if data.startswith(b'TUNING'): self.tuning_written.set()
        return 1 if self.partial else len(data)
    def flush(self): pass

D0 = dict(safety='DISARMED', mode='PID', l_tgt=0., r_tgt=0.,
          l_pwm=0, r_pwm=0, l_rpm=0., r_rpm=0., x=0., y=0., th=0., v=0., w=0.)
cases = {}
def reset(uart=True):
    m.state = m.SafeAGVState()
    u = FakeUART() if uart else None
    a = m.SafeSerialArbiter(u)
    n = m.SafeAutonomousNavigator(a)
    return m.state, u, a, n
def fresh_fixture(s, a):
    # Valid actual D0 protocol; scan timestamp alone is a component fixture.
    a.parse_line(json.dumps(D0))
    s.last_scan_time = time.time()
    s.auto_mode = True
def handler(path, a):
    m.arbiter_instance = a
    h = object.__new__(m.SafeWebHandler)
    h.path = path
    h.wfile = io.BytesIO()
    codes = []
    h.send_response = lambda code: codes.append(code)
    h.send_header = lambda *args: None
    h.end_headers = lambda: None
    h.do_GET()
    return {'http': codes, 'body': h.wfile.getvalue().decode()}

# Production entry contains no runtime startup; safe to run locally once.
r = subprocess.run([sys.executable, '-B', str(SOURCE)], capture_output=True,
                   text=True, timeout=3)
assert r.returncode == 0 and 'INITIALIZED' in r.stdout
cases['entry_exits_without_runtime'] = dict(exit_code=r.returncode, stdout=r.stdout,
    source_main='print only; no UART reader, scheduler/watchdog, HTTP serve, ROS/TF startup')

s, u, a, n = reset()
u.partial = True
ok = a.send_raw('STOP')
assert ok is True and u.tx[-1]['written'] == 1
cases['partial_stop_false_success'] = dict(send_raw_return=ok, tx=u.tx)

s, u, a, n = reset(uart=False)
a.parse_line('{"ack":"ARM","state":"ARMED"}')
ack_state = s.mcu_state
for safety in ['DISARMED', 'FAULT']:
    a.parse_line(json.dumps(dict(D0, safety=safety)))
    assert s.mcu_state == 'ARMED'
arm_ok = a.request_arm(timeout=.05)
assert arm_ok is True
cases['actual_safety_ignored_stale_arm_no_uart'] = dict(ack_state=ack_state,
    actual_D0_safety=['DISARMED', 'FAULT'], parsed_state=s.mcu_state,
    uart_present=False, request_arm_return=arm_ok)

s, u, a, n = reset()
a.parse_line('{"info":"PONG"}')
pong_age = time.time() - s.last_telemetry_time
assert pong_age < .1 and s.mcu_state == 'UNKNOWN'
a.parse_line('{"x":"NaN"}')
assert math.isnan(s.x)
cases['non_d0_refresh_nan'] = dict(pong_age_s=pong_age, mcu_state=s.mcu_state,
                                  pose_nan_accepted=math.isnan(s.x))

s, u, a, n = reset()
fresh_fixture(s, a)
s.zones['front'] = 20
n.step()
assert u.tx and u.tx[-1]['line'].startswith('V') and not s.home_captured
cases['obstacle_turn_before_home_capture'] = dict(tx=u.tx, home_captured=s.home_captured,
                                               mcu_state=s.mcu_state)

s, u, a, n = reset(uart=False)
fresh_fixture(s, a)
n.step()  # captures home with NO map, no valid ARM state
n.step()  # no map -> RETURNING_HOME
middle = s.fsm_state
n.step()  # STOP returns False -> COMPLETED anyway
assert middle == 'RETURNING_HOME' and s.fsm_state == 'COMPLETED'
cases['no_map_no_uart_false_completion'] = dict(map_received=s.map_received,
    intermediate=middle, final=s.fsm_state, auto=s.auto_mode, mcu_state=s.mcu_state,
    uart_present=False, fresh_post_STOP_D0=False)

s, u, a, n = reset()
fresh_fixture(s, a)
s.last_scan_time = time.time() - 1.
n.step()
assert s.fsm_state == 'WATCHDOG_STALE_STOP' and s.auto_mode and not s.latched_stop
s.last_scan_time = time.time()
s.last_telemetry_time = time.time()
s.zones['front'] = 20
n.step()
assert u.tx[-1]['line'].startswith('V')
cases['stale_stop_unlatched_then_motion'] = dict(tx=u.tx, auto=s.auto_mode,
                                              latched=s.latched_stop, fsm=s.fsm_state)

s, u, a, n = reset()
fresh_fixture(s, a)
# No navigator calls: the advertised watchdog is only an inline step() check.
a.send_raw('V 0.08 0.0')
time.sleep(.65)
assert not any(t['line'] == 'STOP' for t in u.tx)
cases['no_caller_no_independent_watchdog'] = dict(wait_s=.65, tx=u.tx,
    scan_and_D0_age_s=time.time()-s.last_telemetry_time,
    scope='actual components without caller; NOT firmware-watchdog or physical STOP test')

# Deterministic STOP race: actual BFS result, pause only at caller scheduling seam.
s, u, a, n = reset()
fresh_fixture(s, a)
s.x, s.y = .30, 1.0
s.home_captured, s.fsm_state = True, 'EXPLORING'
s.map_w, s.map_h, s.map_res = 40, 40, .05
s.map_data = [0] * 1600
for gy in range(40): s.map_data[gy * 40 + 32] = -1
s.map_received = True
original = m.ReachableFrontierPlanner.plan_next_frontier
arrived, resume = threading.Event(), threading.Event()
planner_result = []
def barrier(*args):
    answer = original(*args)
    planner_result.append(answer)
    arrived.set()
    assert resume.wait(1.)
    return answer
m.ReachableFrontierPlanner.plan_next_frontier = staticmethod(barrier)
errors = []
def nav_thread():
    try: n.step()
    except Exception as e: errors.append(repr(e))
t = threading.Thread(target=nav_thread)
t.start()
assert arrived.wait(1.) and planner_result[0][0] is not None
a.request_stop()
resume.set()
t.join(1.)
m.ReachableFrontierPlanner.plan_next_frontier = staticmethod(original)
assert not t.is_alive() and not errors
lines = [tx['line'] for tx in u.tx]
assert lines[:3] == ['STOP'] * 3 and lines[-1].startswith('V') and s.latched_stop
cases['actual_nav_V_after_latched_STOP'] = dict(tx=u.tx, actual_planner_result=planner_result,
    latched=s.latched_stop, auto=s.auto_mode, scheduling_seam_only=True, errors=errors)

s, u, a, n = reset()
result = []
t = threading.Thread(target=lambda: result.append(a.request_tuning(.5, 1.5, 0., .45, timeout=.3)))
t.start()
assert u.tuning_written.wait(.2)
a.parse_line('{"ack":"TUNING 19.000 49.000 4.0000 4.000"}')
t.join(.5)
assert result[0][0] == 'APPLIED'
cases['wrong_pid_readback_APPLIED'] = dict(request=[.5,1.5,0.,.45], result=result,
    tx=u.tx, current_gains=s.current_gains, history_count=len(s.tuning_history))

s, u, a, n = reset(uart=False)
reply = handler('/api/cmd?val=V%200.12%200', a)
assert reply['http'] == [200] and json.loads(reply['body'])['status'] == 'ok'
cases['http_drive_no_uart_false_ok'] = dict(reply=reply, mcu_state=s.mcu_state)
s.latched_stop = True
reply2 = handler('/api/cmd?val=RELEASE_LATCH', a)
assert not s.latched_stop
cases['http_release_without_fresh_DISARMED'] = dict(reply=reply2, mcu_state=s.mcu_state,
                                                  latch_after=s.latched_stop)

after = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
assert before == after
data = {'time_local':datetime.datetime.now().isoformat(), 'timezone':'Asia/Bangkok',
        'source':str(SOURCE), 'sha_before':before, 'sha_after':after,
        'hardware_open_or_tx':False, 'ROS_started':False,
        'scope':'offline actual v4 components/protocol/HTTP method; NOT full production lifecycle',
        'assertions':'reproduction confirmed, not product passing', 'cases':cases}
with OUT.open('x', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
print(json.dumps({'evidence':str(OUT), 'case_count':len(cases), 'stable':before==after,
                  'hardware':False}, ensure_ascii=False))
