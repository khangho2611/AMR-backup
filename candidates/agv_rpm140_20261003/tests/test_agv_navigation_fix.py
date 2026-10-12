"""Offline regression tests. No ROS daemon, Serial open or motor commands."""
import importlib.util
import math
import pathlib
import sys
import threading
import time
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_brain(node_base=object):
    # Replace only unavailable hardware/ROS imports, never navigation methods.
    names = ['serial', 'rclpy', 'rclpy.node', 'rclpy.qos', 'rclpy.time',
             'rclpy.duration', 'sensor_msgs', 'sensor_msgs.msg', 'nav_msgs',
             'nav_msgs.msg', 'geometry_msgs', 'geometry_msgs.msg', 'tf2_ros']
    saved = {n: sys.modules.get(n) for n in names}
    for n in names:
        sys.modules[n] = types.ModuleType(n)
    def forbidden(*a, **kw):
        raise AssertionError('Physical Serial OPEN is forbidden in tests')
    sys.modules['serial'].Serial = forbidden
    sys.modules['rclpy.node'].Node = node_base
    sys.modules['rclpy.time'].Time = object
    sys.modules['rclpy.duration'].Duration = object
    for n in ['QoSProfile', 'ReliabilityPolicy', 'HistoryPolicy', 'DurabilityPolicy']:
        setattr(sys.modules['rclpy.qos'], n, object)
    sys.modules['sensor_msgs.msg'].LaserScan = object
    sys.modules['nav_msgs.msg'].OccupancyGrid = object
    sys.modules['geometry_msgs.msg'].TransformStamped = object
    for n in ['TransformBroadcaster', 'Buffer', 'TransformListener']:
        setattr(sys.modules['tf2_ros'], n, object)
    try:
        spec = importlib.util.spec_from_file_location('brain_test', ROOT / 'agv_unified_brain.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for n, old in saved.items():
            if old is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = old


class NavigationRegression(unittest.TestCase):
    def test_captured_red_side_map_allows_confirmed_rectangular_body_escape(self):
        import json
        from agv_navigation import GridPlanner
        m=json.loads((ROOT/'tests/fixtures/agv_red_side_map_20261003.json').read_text(encoding='utf-8-sig'))
        scan=json.loads((ROOT/'tests/fixtures/agv_red_side_scan_20261003.json').read_text(encoding='utf-8-sig'))
        g=GridPlanner(m['w'],m['h'],m['res'],(m['ox'],m['oy'],m['yaw']),m['data'],.20,.15)
        self.assertFalse(g.escape_swept_clear((0.,0.,0.),-.04,-.35))
        self.assertTrue(g.escape_swept_clear((0.,0.,0.),-.04,-.35,bounds=(-.16,-.12,.10,.12)))
        self.grid(m['w'],m['h'],m['res'],m['data'])
        s=self.m.state;s.map_origin_x=m['ox'];s.map_origin_y=m['oy'];s.body_radius_m=.20
        s.body_bounds_m=(-.16,-.12,.10,.12);s.ranges=scan;s.scan_mono=time.monotonic()
        self.node._pose_map=lambda:(0.,0.,0.)
        self.assertTrue(self.node._escape_clear(-.04,-.35))

    def test_oriented_rectangle_blocks_rear_corner_unknown_and_map_edge(self):
        from agv_navigation import GridPlanner
        data=[0]*10000
        data[48*100+46]=100
        g=GridPlanner(100,100,.05,(0,0,0),data,.20,.15)
        bounds=(-.16,-.12,.10,.12)
        self.assertFalse(g.box_swept_clear((2.5,2.5,0.),.04,.35,bounds))
        self.assertFalse(g.box_swept_clear((.16,.12,0.),-.04,0.,bounds))
        data[48*100+46]=-1
        g=GridPlanner(100,100,.05,(0,0,0),data,.20,.15)
        self.assertFalse(g.box_swept_clear((2.5,2.5,0.),.04,.35,bounds))
    def test_red_margin_can_escape_without_shrinking_body_or_normal_path_margin(self):
        from agv_navigation import GridPlanner
        data=[0]*10000
        for x in range(100):data[44*100+x]=100
        g=GridPlanner(100,100,.05,(0.,0.,0.),data,.20,.15)
        pose=(2.5,2.5,0.)
        self.assertFalse(g.swept_clear(pose,.04,.35))
        self.assertTrue(g.escape_swept_clear(pose,.04,.35))
        self.assertFalse(g.escape_swept_clear(pose,.04,-.35))
        self.assertFalse(g.escape_swept_clear(pose,0.,.35))
        self.assertEqual(g.radius,.35)

    def test_red_front_uses_clear_reverse_corridor_and_blocks_trapped_or_unknown_body(self):
        from agv_navigation import GridPlanner
        data=[0]*10000
        for y in range(100):data[y*100+55]=100
        g=GridPlanner(100,100,.05,(0.,0.,0.),data,.20,.15)
        pose=(2.5,2.5,0.)
        self.assertTrue(g.escape_swept_clear(pose,-.04,0.))
        self.assertFalse(g.escape_swept_clear(pose,.04,0.))
        data[50*100+46]=-1
        trapped=GridPlanner(100,100,.05,(0.,0.,0.),data,.20,.15)
        self.assertFalse(trapped.escape_swept_clear(pose,-.04,0.))

    def test_auto_red_side_escape_validates_map_scan_and_dispatches_to_guarded_writer(self):
        data=[0]*10000
        for x in range(100):data[44*100+x]=100
        self.grid(100,100,.05,data)
        self.m.state.body_radius_m=.20
        self.m.state.ranges=[2.]*360
        self.m.state.ranges[270]=.25
        self.m.state.scan_mono=time.monotonic()
        self.node._pose_map=lambda:(2.5,2.5,0.)
        calls=[]
        self.node.control=types.SimpleNamespace(drive=lambda command,**kw:(calls.append((command,kw)) or True,'SENT'),
                                               _event=lambda *a,**kw:None)
        self.assertTrue(self.node._try_escape())
        self.assertEqual(calls,[('V 0.040 0.350',{'autonomous':True,'escape':True})])
        self.assertIn('NÉ VÙNG ĐỎ',self.m.state.explore_phase)
        self.m.state.ranges[270]=.19
        self.assertFalse(self.node._try_escape())
        self.assertEqual(len(calls),1,'A physical body collision must not dispatch a reverse/spin')

    def setUp(self):
        self.m = load_brain()
        self.node = self.m.AGVROSNode.__new__(self.m.AGVROSNode)
        self.m.state = self.m.AGVSharedState()

    def grid(self, w=40, h=40, res=.05, data=None):
        s = self.m.state
        s.map_width, s.map_height, s.map_resolution = w, h, res
        s.map_data = [0] * (w*h) if data is None else data
        s.map_received = True
        s.map_frame = 'map'
        s.map_mono = time.monotonic()
        s.map_version = 1
        s.map_origin_yaw = 0.
        s.body_radius_m = .05
        s.wall_margin_m = .15

    def test_unknown_wall_is_not_a_drivable_shortcut(self):
        data = [0] * 1600
        for y in range(40):
            data[y*40+20] = -1
        self.grid(data=data)
        self.assertIsNone(self.node.plan_astar_path(.5, 1., 1.5, 1.))

    def test_live_room_costmap_fits_production_fifty_ms_budget(self):
        import json
        from agv_navigation import GridPlanner
        d=json.loads((ROOT/'tests/fixtures/agv_live_map_20261002.json').read_text(encoding='utf-8-sig'))
        g=GridPlanner(d['w'],d['h'],d['res'],(d['ox'],d['oy'],d['yaw']),d['data'],.20,budget_s=.05)
        self.assertEqual(len(g.safe),d['w']*d['h'])
        # This captured pose is near a wall; do not force it traversable just
        # to make the performance regression pass.
        self.assertFalse(g.traversable(g.world_to_cell(0.,0.)))

    def test_inflation_matches_distance_to_blocked_cell_rectangles(self):
        from agv_navigation import GridPlanner
        data=[0]*144
        for i in (26,43,57,81,96):data[i]=100
        g=GridPlanner(12,12,.05,(0.,0.,0.),data,.072,margin=.03)
        for y in range(12):
            for x in range(12):
                px,py=(x+.5)*.05,(y+.5)*.05
                distance=min(px,py,.6-px,.6-py)
                for i,val in enumerate(data):
                    if val==0:continue
                    bx,by=i%12,i//12
                    dx=max(bx*.05-px,0.,px-(bx+1)*.05)
                    dy=max(by*.05-py,0.,py-(by+1)*.05)
                    distance=min(distance,math.hypot(dx,dy))
                self.assertEqual(g.traversable((x,y)),data[y*12+x]==0 and distance>g.radius)

    def test_inflation_is_in_metres_not_fixed_cell_count(self):
        data = [0] * 10000
        data[50*100+50] = 100
        self.grid(100, 100, .01, data)
        self.assertIsNone(self.node.plan_astar_path(.30, .505, .555, .505))

    def test_invalid_map_stops_planning_without_crash(self):
        self.grid(res=0.)
        try:
            path = self.node.plan_astar_path(.5, .5, 1., 1.)
        except Exception as e:
            self.fail(f'Invalid map must fail closed, not raise {type(e).__name__}')
        self.assertIsNone(path)

    def test_negative_world_coordinate_is_outside(self):
        self.grid()
        self.assertIsNone(self.node.plan_astar_path(-.001, .5, .7, .5))

    def test_blocked_goal_is_not_silently_relocated(self):
        data = [0] * 1600
        data[20*40+20] = 100
        self.grid(data=data)
        self.assertIsNone(self.node.plan_astar_path(.5, .5, 1.025, 1.025))

    def test_detour_uses_only_safe_known_free_cells(self):
        from agv_navigation import GridPlanner
        data = [0] * (80*60)
        for y in range(45): data[y*80+40] = 100
        p = GridPlanner(80,60,.05,(0,0,0),data,.05,.15)
        path = p.path((.75,1.),(3.,1.))
        self.assertIsNotNone(path)
        self.assertGreater(max(y for x,y in path),2.4)
        self.assertTrue(all(p.traversable(p.world_to_cell(*wp)) for wp in path))

    def test_rotated_map_coordinate_roundtrip(self):
        from agv_navigation import GridPlanner
        p = GridPlanner(30,30,.05,(2,3,math.pi/2),[0]*900,.05,.05)
        for cell in [(5,5),(20,10),(15,25)]:
            self.assertEqual(p.world_to_cell(*p.cell_to_world(*cell)),cell)

    def test_corner_cutting_is_blocked(self):
        from agv_navigation import GridPlanner
        data=[0]*900
        data[14*30+15]=100
        data[15*30+14]=100
        p=GridPlanner(30,30,.05,(0,0,0),data,.001,0)
        self.assertNotIn(((15,15),math.sqrt(2)),list(p.neighbours((14,14))))

    def test_blacklisted_frontier_selects_another_area(self):
        self.grid(70,50,.05)
        for y in range(50):
            self.m.state.map_data[y*70] = -1
            self.m.state.map_data[y*70+69] = -1
        self.node.initialize_navigation()
        first = self.node.find_best_frontier(1.3,1.25)
        self.assertIsNotNone(first)
        self.node.blocked_goals=[(*first,2.5,time.monotonic()+30)]
        other = self.node.find_best_frontier(1.3,1.25)
        self.assertIsNotNone(other)
        self.assertGreaterEqual(math.dist(first,other),2.5)
        self.assertGreater(other[0],3.)

    def test_unreachable_unknown_island_is_not_selected(self):
        self.grid(70,50,.05)
        data=self.m.state.map_data
        for y in range(50): data[y*70+35]=100
        for y in range(50): data[y*70+69]=-1
        self.node.initialize_navigation()
        self.assertIsNone(self.node.find_best_frontier(.8,1.2))
        self.assertEqual(self.m.state.frontier_reachable,0)
        self.assertGreater(self.m.state.unknown_cells,0)

    def test_failed_goal_rejects_whole_frontier_region_not_next_wall_pixel(self):
        self.grid(70,50,.05)
        for y in range(50):
            self.m.state.map_data[y*70]=-1
            self.m.state.map_data[y*70+69]=-1
        self.node.initialize_navigation()
        first=self.node.find_best_frontier(1.3,1.25)
        self.assertLess(first[0],.5)
        self.node.goal=first
        self.node._exclude_goal(time.monotonic())
        other=self.node.find_best_frontier(1.3,1.25)
        self.assertIsNotNone(other)
        self.assertGreater(other[0],3.,'Do not select another pixel on the rejected left wall')

    def test_connected_perimeter_frontier_still_has_other_directions(self):
        self.grid(70,50,.05)
        for y in range(50):
            for x in range(70):
                if x in (0,69) or y in (0,49):self.m.state.map_data[y*70+x]=-1
        self.node.initialize_navigation()
        self.node.goal=self.node.find_best_frontier(.65,1.25)
        self.assertIsNotNone(self.node.goal)
        first=self.node.goal
        self.node._exclude_goal(time.monotonic())
        other=self.node.find_best_frontier(.65,1.25)
        self.assertIsNotNone(other,'A connected frontier around the room must not blacklist every direction')
        self.assertGreater(math.dist(first,other),1.)
        first_heading=math.atan2(first[1]-1.25,first[0]-.65)
        other_heading=math.atan2(other[1]-1.25,other[0]-.65)
        delta=abs((other_heading-first_heading+math.pi)%(2*math.pi)-math.pi)
        self.assertGreater(delta,math.pi/2,'Prefer a substantially different direction over a neighbouring wall pixel')
        self.assertIsNotNone(self.node.plan_astar_path(.65,1.25,*other))

    def test_no_path_never_falls_back_to_direct_drive(self):
        self.grid()
        data=self.m.state.map_data
        for y in range(40): data[y*40+20]=100
        sent=[]
        self.node.send_cmd=lambda command,**kw: (sent.append(command) or True,'SENT')
        self.assertFalse(self.node._follow((.5,1.,0),(1.5,1.)))
        self.assertEqual(sent,[])

    def test_yellow_rear_clearance_uses_slow_forward_arc_instead_of_spin(self):
        self.grid()
        events=[]
        self.node.control=types.SimpleNamespace(scan_clear=True,_event=lambda *a,**kw:events.append((a,kw)))
        self.node._rotation_clear=lambda:False
        self.node._pose_map=lambda:(.5,.5,-math.pi/2)
        self.m.state.scan_mono=time.monotonic()
        self.m.state.ranges=[2.]*360
        self.m.state.ranges[180]=.55
        sent=[]
        self.node.send_cmd=lambda command,**kw: (sent.append(command) or True,'SENT')
        self.assertTrue(self.node._follow((.5,.5,-math.pi/2), (1.5,.5)))
        self.assertEqual(len(sent),1)
        _,v,w=sent[0].split()
        self.assertGreater(float(v),0.)
        self.assertLessEqual(abs(float(w)),.12)

    def test_stuck_goal_is_rejected_after_window_and_not_each_tick(self):
        self.grid()
        self.node.initialize_navigation()
        self.node.home=(.5,.5,0)
        self.node.goal=(1.5,1.5)
        self.node._pose_map=lambda: (.5,.5,0)
        self.node._follow=lambda pose,goal: True
        sent=[]
        self.node.send_cmd=lambda command,**kw:(sent.append(command) or True,'SENT')
        self.m.state.auto_mode=True
        self.m.state.scan_mono=time.monotonic()
        self.node.progress.append((time.monotonic()-.5,(.5,.5,0)))
        self.node.auto_nav_loop()
        self.assertEqual(self.node.goal,(1.5,1.5))
        self.node.progress.clear()
        self.node.progress.append((time.monotonic()-1.6,(.5,.5,0)))
        self.node.auto_nav_loop()
        self.assertIsNone(self.node.goal)
        self.assertEqual(len(self.node.blocked_regions),1)
        self.assertEqual(sent[-1],'V 0.000 0.000')

    def test_home_heading_must_be_restored_before_stop(self):
        self.grid()
        self.node.initialize_navigation()
        self.node.home=(.5,.5,0)
        self.node.explore_state='RETURNING_HOME'
        self.node._pose_map=lambda:(.5,.5,math.pi)
        self.node._rotation_clear=lambda:True
        sent=[]
        self.node.send_cmd=lambda command,**kw:(sent.append(command) or True,'SENT')
        self.m.state.auto_mode=True
        self.m.state.scan_mono=time.monotonic()
        self.node.auto_nav_loop()
        self.assertEqual(self.node.explore_state,'RETURNING_HOME')
        self.assertTrue(sent and sent[0].startswith('V 0.000 '))


class FakeUART:
    is_open=True
    def __init__(self):
        self.writes=[]
        self.partial=False
        self.block=None
        self.entered=threading.Event()
    def write(self,data):
        self.entered.set()
        if self.block: self.block.wait(1)
        self.writes.append(data)
        return 1 if self.partial else len(data)


class SessionRegression(unittest.TestCase):
    def setUp(self):
        from agv_command_session import CommandSession
        self.now=100.
        self.uart=FakeUART()
        self.s=CommandSession(self.uart,clock=lambda:self.now)

    def d0(self,**changes):
        p=dict(safety='DISARMED',mode='PID',l_tgt=0,r_tgt=0,l_rpm=0.,r_rpm=0.,
               l_pwm=0,r_pwm=0,x=0.,y=0.,th=0.,v=0.,w=0.)
        p.update(changes);return p

    def ready(self):
        from agv_preflight_static_collector import EXACT_BOOT_BANNER,EXACT_I2C_SCAN_BANNER
        for p in ({'info':EXACT_BOOT_BANNER},{'info':EXACT_I2C_SCAN_BANNER},{'i2c_found':'0x42'},{'vin_mv':12033}):
            self.now+=.01;self.s.ingest(p)
        for i in range(81):
            self.now+=.125;self.s.ingest(self.d0())
        self.assertTrue(self.s.preflight_ready(self.now))

    def arm(self,ack=True):
        self.ready()
        result=[]
        thread=threading.Thread(target=lambda:result.append(self.s.request_arm()))
        thread.start()
        self.assertTrue(self.uart.entered.wait(.2))
        time.sleep(.01)
        self.now+=.001
        if ack:self.s.ingest({'ack':'ARM','state':'ARMED'})
        self.now+=.001;self.s.ingest(self.d0(safety='ARMED'))
        thread.join(1)
        # Protocol tests isolate UART/session behavior from the node's map
        # validator. Geometry tests replace this callback with the actual seam.
        self.s.arc_validator=lambda v,w: w==0
        return result[0]

    def test_positive_diag_ten_seconds_ack_arm_then_drive(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True;self.s.rotation_clear=True
        self.assertTrue(self.s.drive('V 0.040 0.000',autonomous=True)[0])
        self.assertEqual(self.uart.writes,[b'ARM\n',b'V 0.040 0.000\n'])

    def test_red_escape_requires_fresh_writer_validation_and_auto_caller(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=False;self.s.rotation_clear=False
        self.s.escape_validator=lambda v,w:True
        self.assertFalse(self.s.drive('V -0.040 0.000',escape=True)[0])
        self.assertTrue(self.s.drive('V -0.040 0.000',autonomous=True,escape=True)[0])
        self.s.escape_validator=lambda v,w:False
        self.assertFalse(self.s.drive('V -0.040 0.000',autonomous=True,escape=True)[0])

    def test_armed_d0_while_stop_write_is_inflight_is_not_an_unsafe_new_preflight(self):
        self.assertTrue(self.arm()[0])
        self.uart.entered.clear();self.uart.block=threading.Event()
        result=[]
        stopper=threading.Thread(target=lambda:result.append(self.s.request_stop(wait=False)))
        stopper.start();self.assertTrue(self.uart.entered.wait(.2))
        self.now+=.001;self.s.ingest(self.d0(safety='ARMED'))
        self.assertIsNone(self.s.fault)
        self.assertEqual(self.s.stop_op,1)
        self.uart.block.set();stopper.join(.5)
        self.now+=.01;self.s.ingest(self.d0())
        self.assertTrue(self.s.stop_confirmed)
        self.s.escape_validator=lambda v,w:True
        self.now+=.26
        self.assertFalse(self.s.drive('V -0.040 0.000',autonomous=True,escape=True)[0])

    def test_forward_arc_is_allowed_when_front_is_clear_but_full_rotation_is_not(self):
        from agv_navigation import GridPlanner
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True;self.s.rotation_clear=False
        grid=GridPlanner(80,80,.05,(0.,0.,0.),[0]*6400,.20,.15)
        self.s.arc_validator=lambda v,w:grid.swept_clear((1.,1.,0.),v,w)
        result=self.s.drive('V 0.020 0.120',autonomous=True)
        self.assertTrue(result[0], result)
        self.assertEqual(self.uart.writes[-1],b'V 0.020 0.120\n')

    def test_in_place_turn_still_requires_full_rotation_clearance(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True;self.s.rotation_clear=False
        result=self.s.drive('V 0.000 0.120',autonomous=True)
        self.assertFalse(result[0], result)
        self.assertIn('SWEEP_NOT_CLEAR', self.s.diagnostics()['events'][-1]['blockers'])
        self.assertNotIn(b'V 0.000 0.120\n',self.uart.writes)

    def test_bounded_trial_expires_despite_fresh_caller_and_sensor_streams(self):
        from agv_command_session import CommandSession
        self.s=CommandSession(self.uart,clock=lambda:self.now,motion_window_s=15.)
        self.assertTrue(self.arm()[0])
        for _ in range(152):
            self.now+=.10
            self.s.scan_time=self.now;self.s.scan_clear=True
            self.s.ingest(self.d0(safety='ARMED'))
            self.s.drive('V 0.040 0.000',autonomous=True)
            self.s.watchdog_tick()
            if self.s.fault: break
        self.assertEqual(self.s.fault,'TRIAL_WINDOW_COMPLETE')
        self.assertIn(b'STOP\n',self.uart.writes)
        self.assertFalse(self.s.armed)

    def test_continuous_control_exceeds_trial_duration_but_still_stops_on_data_loss(self):
        self.assertTrue(self.arm()[0])
        for _ in range(310):
            self.now+=.1
            self.s.scan_time=self.now;self.s.scan_clear=True
            self.s.ingest(self.d0(safety='ARMED'))
            self.assertTrue(self.s.drive('V 0.040 0.000',autonomous=True)[0])
            self.s.watchdog_tick()
        self.assertTrue(self.s.armed)
        self.assertIsNone(self.s.fault)
        self.assertIsNone(self.s.trial_deadline)
        self.now+=.26
        self.s.watchdog_tick()
        self.assertEqual(self.s.fault,'TELEMETRY_TIMEOUT')
        self.assertEqual(self.uart.writes[-1],b'STOP\n')

    def test_trial_rejects_manual_pwm_and_velocity_above_reviewed_limit(self):
        from agv_command_session import CommandSession
        self.s=CommandSession(self.uart,clock=lambda:self.now,motion_window_s=15.)
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True;self.s.rotation_clear=True
        before=len(self.uart.writes)
        self.assertFalse(self.s.drive('M 140 140')[0])
        self.assertFalse(self.s.drive('V 0.080 0.000')[0])
        self.assertEqual(len(self.uart.writes),before)

    def test_trial_cannot_rearm_after_early_user_stop(self):
        from agv_command_session import CommandSession
        self.s=CommandSession(self.uart,clock=lambda:self.now,motion_window_s=15.)
        self.assertTrue(self.arm()[0])
        self.s.request_stop(wait=False)
        for _ in range(81): self.now+=.125;self.s.ingest(self.d0())
        self.assertTrue(self.s.preflight_ready(self.now))
        self.assertEqual(self.s.request_arm(),(False,'TRIAL_ALREADY_USED'))
        self.assertEqual(self.uart.writes.count(b'ARM\n'),1)

    def test_trial_overspeed_triggers_stop_and_latches_fault(self):
        from agv_command_session import CommandSession
        self.s=CommandSession(self.uart,clock=lambda:self.now,motion_window_s=15.)
        self.assertTrue(self.arm()[0]);self.now+=.1
        self.s.ingest(self.d0(safety='ARMED',l_rpm=36.,r_rpm=36.))
        self.assertEqual(self.s.fault,'TRIAL_OVERSPEED')
        self.assertIn(b'STOP\n',self.uart.writes)

    def test_expired_trial_never_writes_another_drive_before_watchdog_tick(self):
        from agv_command_session import CommandSession
        self.s=CommandSession(self.uart,clock=lambda:self.now,motion_window_s=15.)
        self.assertTrue(self.arm()[0]);self.now+=15.01
        self.s.ingest(self.d0(safety='ARMED'));self.s.scan_time=self.now;self.s.scan_clear=True
        count=len(self.uart.writes)
        self.assertFalse(self.s.drive('V 0.040 0.000')[0])
        self.assertEqual(len(self.uart.writes),count)

    def test_no_ack_never_opens_drive_gate(self):
        self.assertFalse(self.arm(ack=False)[0])
        self.assertFalse(self.s.drive('V 0.040 0.000')[0])
        self.assertNotIn(b'V 0.040 0.000\n',self.uart.writes)

    def test_drive_never_implicitly_sends_arm(self):
        self.assertFalse(self.s.drive('M 140 140')[0])
        self.assertEqual(self.uart.writes,[])

    def test_second_stop_zero_before_new_write_cannot_confirm(self):
        self.s.request_stop(wait=False)
        self.now+=.01;self.s.ingest(self.d0())
        self.assertTrue(self.s.stop_confirmed)
        self.uart.entered.clear();self.uart.block=threading.Event()
        result=[]
        thread=threading.Thread(target=lambda:result.append(self.s.request_stop(wait=False)))
        thread.start();self.assertTrue(self.uart.entered.wait(.2))
        self.now+=.01;self.s.ingest(self.d0())
        self.assertFalse(self.s.stop_confirmed)
        self.uart.block.set();thread.join(1)
        self.now+=.01;self.s.ingest(self.d0())
        self.assertTrue(self.s.stop_confirmed)

    def test_partial_stop_zero_remains_observed_not_confirmed(self):
        self.uart.partial=True
        self.assertFalse(self.s.request_stop(wait=False)[0])
        self.now+=.01;self.s.ingest(self.d0())
        self.assertFalse(self.s.stop_confirmed)
        self.assertTrue(self.s.stop_observed_zero)
        self.assertEqual(self.s.health()['fault'],'STOP_WRITE_FAILED')

    def test_second_stop_waiting_for_mutex_invalidates_old_confirmation(self):
        self.s.request_stop(wait=False)
        self.now+=.01;self.s.ingest(self.d0())
        self.assertTrue(self.s.stop_confirmed)
        self.s.writer.acquire()
        t=threading.Thread(target=lambda:self.s.request_stop(wait=False));t.start()
        time.sleep(.02)
        self.now+=.01;self.s.ingest(self.d0())
        confirmed=self.s.stop_confirmed
        self.s.writer.release();t.join(1)
        self.assertFalse(confirmed,'Old operation must expire at STOP intent, before mutex')

    def test_stop_cancels_queued_drive_before_mutex_is_acquired(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True;self.s.rotation_clear=True
        self.s.writer.acquire()
        result=[]
        drive=threading.Thread(target=lambda:result.append(self.s.drive('V 0.040 0.000')))
        drive.start();time.sleep(.01)
        stop=threading.Thread(target=lambda:self.s.request_stop(wait=False));stop.start()
        time.sleep(.01);self.s.writer.release()
        drive.join(1);stop.join(1)
        self.assertFalse(result[0][0])
        self.assertNotIn(b'V 0.040 0.000\n',self.uart.writes)

    def test_independent_tick_stops_silent_caller(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now
        self.now+=.21
        self.s.scan_time=self.now;self.s.last_d0=self.now
        self.s.watchdog_tick()
        self.assertIn(b'STOP\n',self.uart.writes)
        self.assertEqual(self.s.fault,'CALLER_TIMEOUT')

    def test_fresh_armed_d0_stream_does_not_keep_silent_caller_alive(self):
        self.assertTrue(self.arm()[0])
        for _ in range(3):
            self.now+=.08
            self.s.scan_time=self.now
            self.s.ingest(self.d0(safety='ARMED'))
            self.s.watchdog_tick()
        self.assertEqual(self.s.fault,'CALLER_TIMEOUT')
        self.assertIn(b'STOP\n',self.uart.writes)

    def test_zero_pid_matching_ack_applied(self):
        result=[]
        t=threading.Thread(target=lambda:result.append(self.s.tuning(0,0,0)));t.start()
        self.assertTrue(self.uart.entered.wait(.2));time.sleep(.01);self.now+=.01
        self.s.ingest({'ack':'TUNING 0.000 0.000 0.0000 0.450'});t.join(1)
        self.assertEqual(result[0]['status'],'APPLIED')

    def test_pid_reject_does_not_become_fake_applied_or_motion(self):
        result=[]
        t=threading.Thread(target=lambda:result.append(self.s.tuning(.5,1.5,.01)));t.start()
        self.assertTrue(self.uart.entered.wait(.2));time.sleep(.01);self.now+=.01
        self.s.ingest({'error':'INVALID_TUNING_RANGE'});t.join(1)
        self.assertEqual(result[0]['status'],'REJECTED')
        self.assertNotIn(b'STOP\n',self.uart.writes)

    def test_timeout_late_ack_cannot_be_assigned_to_new_pid_request(self):
        result=self.s.tuning(.5,1.5,.01)
        self.assertEqual(result['status'],'FAILED')
        self.now+=1;self.s.ingest({'ack':result['cmd']})
        next_result=self.s.tuning(1,2,.02)
        self.assertEqual(next_result['reason'],'RECONNECT_REQUIRED')
        self.assertEqual(len(self.uart.writes),1)


if __name__ == '__main__':
    unittest.main()
