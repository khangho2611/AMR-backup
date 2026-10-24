"""Regression for the observed repeated 40/-40 escape loop."""
from types import SimpleNamespace as N
import math
import time
from test_agv_ai_integration import node_fixture


def recovery():
    brain,node,_=node_fixture()
    clock=[10.]
    brain.time=N(monotonic=lambda:clock[0])
    sent=[]
    node.control.latest={'x':0.,'y':0.,'th':0.}
    node.control.drive=lambda cmd,**kw:(sent.append(tuple(map(float,cmd.split()[1:]))) or (True,'MOCK_ONLY'))
    node.control._event=lambda *a,**kw:None
    node._escape_clear=lambda v,w:True
    brain.state.ranges=[.3]*360
    brain.state.min_dist_m=.3;brain.state.min_angle_deg=0
    return brain,node,clock,sent


def test_repeated_escape_cannot_restart_spin_without_translation():
    _,node,clock,sent=recovery()
    assert node._try_escape()
    assert sent[-1][0]!=0 and sent[-1][1]==0
    clock[0]+=3.
    assert node._try_escape()
    assert sent[-1][0]!=0, 'Operator recovery must remain translational on every retry'


def test_when_only_rotation_is_clear_do_not_spin_forever():
    _,node,clock,sent=recovery()
    node._escape_clear=lambda v,w:v==0
    assert not node._try_escape()
    clock[0]+=3.
    assert not node._try_escape()
    assert len(sent)==0


def test_real_translation_cannot_reenable_an_unplanned_spin():
    _,node,clock,sent=recovery()
    assert node._try_escape()
    clock[0]+=3.
    node.control.latest['x']=.15
    assert node._try_escape()
    assert sent[-1][0]!=0 and sent[-1][1]==0


def test_reaching_clear_space_returns_control_to_navigation_without_extra_escape():
    brain,node,sent=node_fixture()
    node._cautious=True
    node.control.latest={'x':.03,'y':-.078,'th':-1.61}
    node._spin_recovery=dict(anchor=(0.,0.),yaw=-1.61,angle=math.pi+.2,started=time.monotonic()-4.)
    node._try_escape=lambda:False
    node.auto_nav_loop()
    assert sent and sent[-1]!='V 0.000 0.000', 'Clear robot must resume its A* goal'
    assert getattr(node,'_spin_recovery',None) is None
