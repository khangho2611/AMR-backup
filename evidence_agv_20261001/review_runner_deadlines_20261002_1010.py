"""OFFLINE followup on startup deadline and independent STOP; no physical OPEN."""
import pathlib,sys,time,json,tempfile,hashlib,threading
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
# Reuse only QA definitions, without executing the previous test batch or overwriting evidence.
source=(ROOT/'evidence_agv_20261001/review_runner_bundle_20261002_1006.py').read_text(encoding='utf8')
exec(compile(source.split('with concurrent.futures.ThreadPoolExecutor')[0],str(ROOT/'evidence_agv_20261001/review_runner_bundle_20261002_1006.py'),'exec'),globals())
class LateUART(UART):
 def readline(self):
  if self.n==0:time.sleep(4.1)
  return super().readline()
u=LateUART('late_ready_then_diag');r=mod.HardwareMotionRunner(mock_serial=None,output_dir=tempfile.mkdtemp(prefix='agv_OFFLINE_late1010_'),nominal_time=.15,hard_time_cap=.5)
r.acquire_port_lock=lambda:True
def fake_open():r.ser=u;r.transport=mod.TransportWrapper(u);return True
r.open_transport=fake_open
t=time.monotonic();code=r.execute_lifecycle()
cases=[dict(case='late_ready_after4s_full_unscaled_entry',exit=code,elapsed=time.monotonic()-t,first_rx_delay=u.received[0]['t']-t,arm_count=sum(x['bytes']=='ARM\n' for x in u.writes),report=r.final_report,closed=u.closed,writes=u.writes)]
# Isolated reader/watchdog component: preflight deliberately excluded from this scope.
# Actual ARM request -> ACK -> fresh ARMED through actual parser; no fabricated gate flags.
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
u=UART('component');u.startup=[]
r=mod.HardwareMotionRunner(mock_serial=u,hard_time_cap=.15,nominal_time=.1)
r.ser=u;r.transport=mod.TransportWrapper(u);r.preflight_passed=True
r.arbiter=SerialArbiterGateV3(mock_serial=r.transport);r.supervisor=mod.MotionSupervisor(r.arbiter,nominal_time_s=.1,hard_time_cap_s=.15)
r.running=True;r.reader_thread=threading.Thread(target=r.reader_loop,daemon=True);r.reader_thread.start()
assert r.d0_event.wait(1);assert r.arbiter.arm_control_session('OFFLINE_NOCALLER_1010',time.monotonic())[0]
deadline=time.monotonic()+1
while r.arbiter.stop_latched and time.monotonic()<deadline:time.sleep(.01)
assert not r.arbiter.stop_latched;assert r.supervisor.start_motion(time.monotonic())
r.watchdog_thread=threading.Thread(target=r.watchdog_loop,daemon=True);r.watchdog_thread.start()
time.sleep(.5)
cases.append(dict(case='component_no_update_calls',gate_confirmed=r.arbiter.stop_confirmed,runner_confirmed=r.supervisor.stop_confirmed,fault=r.supervisor.fault_reason,stop_write_success=r.supervisor.stop_write_success,writes=list(u.writes)))
r.running=False;r.reader_thread.join(.2);r.watchdog_thread.join(.2);u.close()
class Partial:
 def write(self,b):return 1
 def flush(self):pass
w=mod.TransportWrapper(Partial());w.write(b'STOP\n')
cases.append(dict(case='partial_write_TX_metadata_only',records=w.tx_records))
after=hashlib.sha256(P.read_bytes()).hexdigest();assert before==after
result=dict(scope='OFFLINE full unscaled late-startup entry plus separately declared no-caller component and TX logger unit; no hardware',before=before,after=after,stable=True,cases=cases)
with (ROOT/'evidence_agv_20261001/review_runner_deadlines_20261002_1010.json').open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
