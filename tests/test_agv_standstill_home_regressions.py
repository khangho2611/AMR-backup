"""Observed turn/gate/HOME inconsistencies, hardware-free regressions."""
import math
import json
import threading
import time
from types import SimpleNamespace as N

from agv_navigation import twist_centres
from agv_command_session import CommandSession
from test_agv_ai_integration import node_fixture


def test_configured_40rpm_turn_is_supported_by_sweep_sampler():
    assert twist_centres(.04, 1.6) is not None
    assert twist_centres(0., -1.6) is not None
    assert twist_centres(.04, 2.7) is None


def test_forward_scan_gate_matches_cautious_body_clearance():
    brain, node, _ = node_fixture()
    node._cautious = True
    brain.state.body_radius_m = .20
    brain.state.wall_margin_m = .15
    node.control = N(strict_preflight=False, lock=threading.RLock(), clock=time.monotonic,
                     armed=False, motion=False, autonomy_allowed=False)
    node._fresh_ros_header = lambda *args: True
    node._rotation_clear = lambda: True
    msg = N(header=N(frame_id='base_footprint'), angle_min=-math.pi,
            angle_increment=math.pi/180., range_min=.05, range_max=8., ranges=[.32]*360)
    node.scan_cb(msg)
    assert node.control.scan_clear, '32 cm is beyond the unchanged 23 cm cautious footprint'
    msg.ranges=[.18]*360
    node.scan_cb(msg)
    assert not node.control.scan_clear
    msg.ranges=[math.inf]*360
    node.scan_cb(msg)
    assert not node.control.scan_clear


def test_home_follower_respects_cautious_speed_like_exploration():
    _, node, commands = node_fixture()
    node._cautious = True
    node._goal_type = 'HOME'
    assert node._follow((0.,0.,0.), (2.,0.))
    assert 0 < float(commands[-1].split()[1]) <= .04


def test_home_does_not_timeout_while_still_translating_on_a_long_route():
    brain, node, _ = node_fixture()
    node.home=(2.,0.,0.)
    node._goal_type='HOME'
    node._goal_time=time.monotonic()-50.
    node._goal_progress=(node.goal,(-.1,0.),time.monotonic()-2.)
    node._follow=lambda *args: True
    node.control.request_stop=lambda *args,**kwargs: None
    node.auto_nav_loop()
    assert brain.state.auto_mode
    assert node.goal==(2.,0.)
    assert node.explore_state != 'HOME_FAILED'


def test_auto_resume_keeps_original_home_and_trace_without_reloading_models():
    brain, node, _ = node_fixture()
    node._pose_map=lambda:(1.,1.,0.)
    node._scan_tf_valid=True
    c=CommandSession(None, strict_preflight=False)
    c.stage=3;c.armed=True;c.latest={'safety':'ARMED'}
    c.scan_time=c.last_d0=c.last_command=c.clock()
    node.control=c
    reloaded=[]
    node.initialize_navigation=lambda: reloaded.append(True)
    brain.state.path_history.extend([[0.,0.],[.5,.5]])
    result=node.start_auto()
    assert result[0], result
    assert node.home==(0.,0.,0.)
    assert list(brain.state.path_history)==[[0.,0.],[.5,.5]]
    assert not reloaded


def test_one_time_restart_checkpoint_preserves_home_only_for_same_slam_process(tmp_path):
    for token, accepted in [('same-slam', True), ('different-slam', False)]:
        brain, node, _ = node_fixture()
        node._slam_process_token = lambda pid: token
        data=dict(slam_pid=123, slam_token='same-slam',home=[.6,-1.4,1.8],
                  map_info=dict(w=40,h=40,res=.1,ox=-2.,oy=-2.,yaw=0.,frame='map'),
                  trajectory=dict(path=[[.6,-1.4],[.5,-1.3]],distance_m=.14),
                  cautious=True)
        path=tmp_path/'resume.json';path.write_text(json.dumps(data),encoding='utf8')
        assert node._restore_restart_checkpoint(str(path)) is accepted
        assert node.home == ((.6,-1.4,1.8) if accepted else (0.,0.,0.))
        assert not path.exists(), 'A restart checkpoint must be consumed only once'


def test_exhausted_excluded_frontiers_return_home_as_partial_instead_of_waiting_forever():
    brain, node, _ = node_fixture()
    node.goal=None
    node.home=(-1.,0.,0.)
    node._last_frontier_search=0.
    node.blocked_regions=[(2.,0.,.35,time.monotonic()+60.)]
    brain.state.frontier_reachable=1
    node.find_best_frontier=lambda *args: None
    node._get_safe_home_target=lambda pose: (-1.,0.)
    node._follow=lambda *args: True
    node.auto_nav_loop()
    assert node.goal==(-1.,0.)
    assert node._goal_type=='HOME'
    assert node._explore_partial
    assert brain.state.auto_mode


def test_planning_timeout_does_not_fabricate_exploration_exhaustion():
    brain, node, _ = node_fixture()
    node.goal=None
    node._last_frontier_search=0.
    node.blocked_regions=[(2.,0.,.35,time.monotonic()+60.)]
    brain.state.frontier_reachable=None
    node.find_best_frontier=lambda *args: None
    node.auto_nav_loop()
    assert node.goal is None
    assert node._goal_type=='FRONTIER'


def test_controller_restart_keeps_odom_frame_continuous_if_mcu_resets():
    _, node, _ = node_fixture()
    node._odom_resume_pose=(1.8,-1.7,.8)
    first=node._continuous_odom_pose(dict(x=0.,y=0.,th=0.))
    assert math.dist(first[:2],(1.8,-1.7))<1e-9
    assert abs(first[2]-.8)<1e-9
    second=node._continuous_odom_pose(dict(x=.1,y=0.,th=.2))
    assert math.dist(second[:2],(1.8+.1*math.cos(.8),-1.7+.1*math.sin(.8)))<1e-9
    assert abs(second[2]-1.)<1e-9


def test_retired_latched_escape_is_discarded_before_route_resume():
    brain, node, commands = node_fixture()
    brain.state.ranges=[.30]*360
    node._escape_latch_until=time.monotonic()+1.
    node._last_escape_cmd=(-.06,.8)
    node.control.drive=lambda *args,**kwargs:(False,'SESSION_OR_SENSOR_NOT_READY')
    node.auto_nav_loop()
    assert node._escape_latch_until==0.
    assert node._last_escape_cmd is None
    assert len(commands) == 1
    assert float(commands[0].split()[1]) > 0.
    assert float(commands[0].split()[2]) == 0.
    assert node.goal==(2.,0.)


def test_starting_twenty_cm_from_home_still_requests_the_final_home_leg():
    brain, node, _ = node_fixture()
    node.goal=None;node.home=(.2,0.,0.)
    node._last_frontier_search=0.
    brain.state.frontier_reachable=0;brain.state.unknown_cells=0
    node.find_best_frontier=lambda *args: None
    node._get_safe_home_target=lambda pose:(.2,0.)
    node._follow=lambda *args: True
    node.control.request_stop=lambda *args,**kwargs: None
    node.auto_nav_loop()
    assert node.goal==(.2,0.)
    assert node._goal_type=='HOME'
