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


def load_brain():
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
    sys.modules['rclpy.node'].Node = object
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

    def test_no_path_never_falls_back_to_direct_drive(self):
        self.grid()
        data=self.m.state.map_data
        for y in range(40): data[y*40+20]=100
        sent=[]
        self.node.send_cmd=lambda command,**kw: (sent.append(command) or True,'SENT')
        self.assertFalse(self.node._follow((.5,1.,0),(1.5,1.)))
        self.assertEqual(sent,[])

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
        return result[0]

    def test_positive_diag_ten_seconds_ack_arm_then_drive(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True;self.s.rotation_clear=True
        self.assertTrue(self.s.drive('V 0.040 0.000',autonomous=True)[0])
        self.assertEqual(self.uart.writes,[b'ARM\n',b'V 0.040 0.000\n'])

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
