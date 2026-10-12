"""Offline source QA using actual Node constructor and actual gate with FakeSerial."""
import json,hashlib,pathlib,sys
from types import SimpleNamespace as S
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import agv_ros2_runtime_adapter as r
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
files=['agv_ros2_runtime_adapter.py','agv_ros2_arbiter_bridge.py']
def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
before=hashes();cases=[]
d0=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0,r_rpm=0,l_pwm=0,r_pwm=0,x=0,y=0,th=0,v=0,w=0)
class FakeSerial:
    def __init__(self):self.writes=[];self.fail=False
    def write(self,data):
        self.writes.append(data.decode())
        if self.fail:raise OSError('offline_write_failure')
        return len(data)
    def flush(self):pass
def setup():
    s=FakeSerial();g=SerialArbiterGateV3(mock_serial=s)
    g.process_incoming_line(json.dumps(d0),100.)
    assert g.arm_control_session('authorized_test',100.01)[0]
    g.process_incoming_line('{"ack":"ARM","state":"ARMED"}',100.02)
    g.process_incoming_line(json.dumps(dict(d0,safety='ARMED')),100.03)
    n=r.AGVRos2RuntimeNode(serial_arbiter=g,is_mock=False)
    assert n.bridge.ingest_telemetry_packet(dict(d0,safety='ARMED',t=100.03),100.04)
    assert n.bridge.ingest_scan_packet(-1,1,.1,[1.]*21,100.04,now_mono=100.04)
    s.writes.clear();return n,g,s
for label,meta in [('D1_missing_stamp_epoch',{}),('D2_future_stamp',{'stamp':100.3}),('D3_age_350ms',{'stamp':99.7}),('D4_fractional_epoch',{'stamp':100.04,'epoch_delta':.5}),('D5_corrupt_epoch',{'stamp':100.04,'epoch':'bad'})]:
    n,g,s=setup();m=S(linear=S(x=.04),angular=S(z=0.),lease_id=g.active_token)
    for k,v in meta.items():
        if k=='epoch_delta':m.epoch=g.current_epoch+v
        else:setattr(m,k,v)
    if label not in ['D1_missing_stamp_epoch','D4_fractional_epoch','D5_corrupt_epoch']:m.epoch=g.current_epoch
    with patch.object(r.time,'monotonic',return_value=100.05):
        try:n.nav_sub.callback(m);error=None
        except Exception as e:error=type(e).__name__
    cases.append(dict(id=label,writes=list(s.writes),exception=error))
n,g,s=setup();s.fail=True
with patch.object(r.time,'monotonic',return_value=100.05):n.destroy_node()
cases.append(dict(id='D6_shutdown_write_failure',writes=list(s.writes),gate_state=g.safety_state,confirmed=g.stop_confirmed,reported_result=n.watchdog.last_stop_result,reported_failed=n.watchdog.last_stop_write_failed))
after=hashes();out=dict(scope='OFFLINE ONLY; real source constructor/Node callbacks, FakeSerial; no ROS or hardware runtime',before=before,after=after,stable=before==after,cases=cases)
with (ROOT/'evidence_agv_20261001/review_node_residual_2028.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(out,ensure_ascii=False))
