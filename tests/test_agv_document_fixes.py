"""Regression cases from operator feedback; UART is fake, never physical."""
import time
import types
import unittest
from unittest.mock import patch
import test_agv_navigation_fix as f

class ManualSession(unittest.TestCase):
    setUp=f.SessionRegression.setUp
    d0=f.SessionRegression.d0
    ready=f.SessionRegression.ready
    arm=f.SessionRegression.arm

    def test_manual_does_not_require_lidar_but_auto_does(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=None
        self.assertTrue(self.s.drive('M 140 140')[0])
        self.s.watchdog_tick()
        self.assertIsNone(self.s.fault)
        self.s.autonomy_allowed=True
        self.assertFalse(self.s.drive('V 0.040 0.000',autonomous=True)[0])
        self.s.watchdog_tick()
        self.assertEqual(self.s.fault,'SCAN_TIMEOUT')

    def test_short_c1_scan_gap_is_tolerated_but_stale_scan_still_stops_auto(self):
        self.assertTrue(self.arm()[0])
        self.s.last_command = self.now
        self.s.scan_time = self.now - .30
        self.s.watchdog_tick()
        self.assertIsNone(self.s.fault)
        self.s.scan_time = self.now - .36
        self.s.watchdog_tick()
        self.assertEqual(self.s.fault, 'SCAN_TIMEOUT')

    def test_idle_session_keeps_mcu_alive_without_extending_motion(self):
        self.s.operator_idle_lease_s=2.
        self.assertTrue(self.arm()[0])
        self.s.autonomy_allowed=False  # Manual session; AUTO owns control otherwise.
        self.assertTrue(self.s.drive('V 0.000 0.000')[0])
        self.now+=.21;self.s.ingest(self.d0(safety='ARMED'))
        self.s.watchdog_tick()
        self.assertIsNone(self.s.fault)
        self.assertEqual(self.uart.writes[-1],b'V 0.000 0.000\n')
        self.assertTrue(self.s.drive('M 140 140')[0])
        self.now+=.21;self.s.ingest(self.d0(safety='ARMED',mode='MAN'))
        self.s.watchdog_tick()
        self.assertEqual(self.s.fault,'CALLER_TIMEOUT')

    def test_expired_idle_lease_disarms_normally_without_invented_fault(self):
        self.s.operator_idle_lease_s=2.
        self.assertTrue(self.arm()[0]);self.s.autonomy_allowed=False
        self.s.drive('V 0.000 0.000')
        self.now+=2.01;self.s.ingest(self.d0(safety='ARMED'))
        self.s.watchdog_tick()
        self.assertFalse(self.s.armed)
        self.assertIsNone(self.s.fault)
        self.assertEqual(self.uart.writes[-1],b'STOP\n')

class NavigationDiagnostics(unittest.TestCase):
    setUp=f.NavigationRegression.setUp
    grid=f.NavigationRegression.grid

    def test_frontier_timeout_is_unknown_not_room_complete(self):
        self.grid()
        self.node.initialize_navigation()
        grid=self.node._grid()
        with patch('agv_navigation.time.monotonic',side_effect=[100.,101.]):
            self.assertIsNone(grid.frontiers((1.,1.)))
        with patch.object(grid,'frontiers',return_value=None):
            self.assertIsNone(self.node.find_best_frontier(1.,1.))
        self.assertIsNone(self.m.state.frontier_reachable)

    def test_stale_lidar_does_not_stop_manual_owner(self):
        session=ManualSession();session.setUp();self.assertTrue(session.arm()[0])
        session.s.drive('M 140 140')
        self.node.control=session.s
        self.node._fresh_ros_header=lambda *a:False
        before=list(session.uart.writes)
        self.node.scan_cb(types.SimpleNamespace(header=object()))
        self.assertEqual(session.uart.writes,before)
        self.assertIsNone(session.s.fault)

    def test_map_collision_explains_unknown_vs_occupied(self):
        from agv_navigation import GridPlanner
        for cell,reason in ((100,'OCCUPIED_SWEEP'),(-1,'UNKNOWN_SWEEP')):
            data=[0]*1600;data[20*40+23]=cell
            g=GridPlanner(40,40,.05,(0.,0.,0.),data,.20,.15)
            self.assertEqual(g.swept_clear_result((1.,1.,0.),.04,0.),(False,reason))

    def test_blocked_arc_can_align_in_place_without_blacklisting_goal(self):
        self.grid(80,80,.05,[0]*6400)
        self.node._rotation_clear=lambda:True
        calls=[]
        def send(cmd,autonomous=False):
            calls.append(cmd)
            return (cmd.startswith('V 0.000 '),'SENT')
        self.node.send_cmd=send
        self.assertTrue(self.node._follow((1.025,1.025,-.20),(2.025,1.025)))
        self.assertGreater(len(calls),1)
        self.assertTrue(calls[-1].startswith('V 0.000 '))

    def test_yellow_corridor_uses_slow_clearance_without_shrinking_body(self):
        data=[0]*10000
        for y in range(100):data[y*100+44]=100;data[y*100+56]=100
        self.grid(100,100,.05,data)
        self.m.state.body_radius_m=.20
        self.node.initialize_navigation()
        pose=(2.525,2.525,0.)
        self.assertFalse(self.node._grid().swept_clear(pose,0.,0.))
        self.assertTrue(self.node._enter_cautious(pose))
        self.assertEqual(self.node._grid().body_radius,.20)
        self.assertAlmostEqual(self.node._grid().radius,.23)
        self.node._pose_map=lambda:pose
        self.assertFalse(self.node._forward_arc_clear(.20,0.))

    def test_cautious_mode_does_not_allow_body_collision(self):
        data=[0]*10000;data[50*100+52]=100
        self.grid(100,100,.05,data)
        self.m.state.body_radius_m=.20
        self.node.initialize_navigation()
        self.assertFalse(self.node._enter_cautious((2.525,2.525,0.)))

    def test_cautious_returns_to_normal_only_after_clear_hysteresis(self):
        self.grid(100,100,.05,[0]*10000)
        self.m.state.body_radius_m=.20
        self.node.initialize_navigation()
        pose=(2.525,2.525,0.)
        self.assertTrue(self.node._enter_cautious(pose))
        self.m.state.ranges = [2.] * 360
        now=time.monotonic()
        with patch.object(self.m.time,'monotonic',return_value=now):
            self.node._restore_normal_clearance(pose)
        self.assertTrue(self.node._cautious)
        # Advance the input map along with time, as a live publisher would.
        self.m.state.map_mono=now+2.1
        with patch.object(self.m.time,'monotonic',return_value=now+2.1):
            self.node._restore_normal_clearance(pose)
        self.assertFalse(self.node._cautious)
        with patch.object(self.m.time,'monotonic',return_value=now+2.1):
            self.assertAlmostEqual(self.node._grid().radius,.35)

    def test_cautious_follower_caps_speed_and_reuses_geometry(self):
        self.grid(100,100,.05,[0]*10000)
        self.m.state.body_radius_m=.20
        self.node.initialize_navigation()
        pose=(2.525,2.525,0.)
        self.assertTrue(self.node._enter_cautious(pose))
        narrow=self.node._grid()
        self.node._grid(margin=.15)
        self.assertIs(self.node._grid(),narrow)
        sent=[]
        self.node.send_cmd=lambda cmd,**kw:(sent.append(cmd) or True,'SENT')
        self.assertTrue(self.node._follow(pose,(3.525,2.525)))
        self.assertGreater(float(sent[-1].split()[1]),0.)
        self.assertLessEqual(float(sent[-1].split()[1]),.04)

if __name__=='__main__':unittest.main()
