"""Source-linked Node QA; only injected clocks and FakeSerial, no hardware/ROS launch."""
import hashlib,json,pathlib,sys
from types import SimpleNamespace as S
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agv_ros2_runtime_adapter as r
from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3
FILES=['agv_ros2_runtime_adapter.py','agv_ros2_arbiter_bridge.py']
def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}
before=hashes();cases=[]
def scan(header=True,sec=100,frame='laser'):
    m=S(angle_min=-1.,angle_max=1.,angle_increment=.1,ranges=[1.]*21)
    if header:m.header=S(stamp=S(sec=sec,nanosec=0),frame_id=frame)
    return m
def check_scan(label,m,ros_clock=None):
    n=r.AGVRos2RuntimeNode(is_mock=True)
    if ros_clock is not None:n.get_clock().time_fn=lambda:ros_clock
    with patch.object(r.time,'monotonic',return_value=100.):
        try:n.scan_sub.callback(m);out={'accepted':n.bridge.last_scan_data is not None}
        except Exception as e:out={'exception':type(e).__name__}
    cases.append(dict(id=label,observed=out))
node=r.AGVRos2RuntimeNode(is_mock=True)
cases.append(dict(id='N1_constructor',observed='constructed'))
check_scan('Q1_fresh_ROS_epoch_clock',scan(sec=1700000000),1700000000.)
check_scan('Q2_missing_header',scan(header=False))
check_scan('Q3_unconfigured_camera_frame',scan(frame='camera'))
check_scan('Q4_corrupt_header_sec',scan(sec='bad'))
class SerialMock:
    def __init__(self):self.writes=[]
    def write(self,data):self.writes.append(data.decode());return len(data)
    def flush(self):pass
d0=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0,r_rpm=0,l_pwm=0,r_pwm=0,x=0,y=0,th=0,v=0,w=0)
def live_mock():
    s=SerialMock();g=SerialArbiterGateV3(mock_serial=s)
    g.process_incoming_line(json.dumps(d0),100.)
    assert g.arm_control_session('test_source',100.01)[0]
    g.process_incoming_line('{"ack":"ARM","state":"ARMED"}',100.02)
    g.process_incoming_line(json.dumps(dict(d0,safety='ARMED')),100.03)
    n=r.AGVRos2RuntimeNode(serial_arbiter=g,is_mock=False)
    n.bridge.ingest_telemetry_packet(dict(d0,safety='ARMED',t=100.03),100.04)
    n.bridge.ingest_scan_packet(-1,1,.1,[1.]*21,100.04,now_mono=100.04)
    s.writes.clear();return n,g,s
n,g,s=live_mock()
m=S(linear=S(x=.04),angular=S(z=0.),lease_id=g.active_token,stamp=0.,epoch=-1)
with patch.object(r.time,'monotonic',return_value=100.05):n.nav_sub.callback(m)
cases.append(dict(id='Q5_stale_stamp_wrong_epoch_valid_token',mock_writes=list(s.writes)))
cases.append(dict(id='Q6_Node_publisher_payload',odom_type=type(n.odom_pub.published_messages[-1]).__name__,tf_type=type(n.tf_pub.published_messages[-1]).__name__,stamp=n.odom_pub.published_messages[-1]['header']['stamp']))
s.writes.clear()
n.destroy_node()
cases.append(dict(id='Q7_destroy_node_armed_mock',mock_writes=s.writes,gate_state=g.safety_state,lease_active=n.bridge.active_lease_source is not None))
after=hashes();out=dict(scope='OFFLINE actual Node constructors/callbacks + FakeSerial only; no real ROS bus or hardware',before=before,after=after,stable=before==after,cases=cases)
with (ROOT/'evidence_agv_20261001/review_node_followup_2012_v2.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(out,ensure_ascii=False))
