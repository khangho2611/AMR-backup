"""Operator directions, AUTO ownership and cruise geometry; no hardware."""
import time
import threading
import types
import unittest
import test_agv_navigation_fix as fixtures


class OperatorCommands(unittest.TestCase):
    setUp=fixtures.SessionRegression.setUp
    d0=fixtures.SessionRegression.d0
    ready=fixtures.SessionRegression.ready
    arm=fixtures.SessionRegression.arm

    def test_manual_directions_ignore_auto_obstacle_flags(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=False;self.s.rotation_clear=False
        for command in ('M 140 140','M -140 -140','M -120 120'):
            self.assertTrue(self.s.drive(command)[0],command)
            self.assertIn((command+'\n').encode(),self.uart.writes)

    def test_manual_takeover_cancels_subsequent_auto_commands(self):
        self.assertTrue(self.arm()[0]);self.s.scan_time=self.now
        self.s.scan_clear=self.s.rotation_clear=True
        self.s.autonomy_allowed=True
        self.assertTrue(self.s.drive('M 140 140')[0])
        before=list(self.uart.writes)
        self.assertFalse(self.s.drive('V 0.040 0.000',autonomous=True)[0])
        self.assertEqual(self.uart.writes,before)
        self.assertTrue(self.s.drive('V 0.000 0.000')[0])
        self.assertTrue(self.s.armed)

    def test_cruise_speed_has_swept_validator_and_preserves_stop(self):
        self.assertTrue(self.arm()[0]);self.s.scan_time=self.now;self.s.scan_clear=True
        self.s.arc_validator=lambda v,w: v==.20 and w==0
        self.assertTrue(self.s.drive('V 0.200 0.000',autonomous=True)[0])
        self.assertFalse(self.s.drive('V 0.210 0.000',autonomous=True)[0])
        self.s.request_stop(wait=False)
        self.assertFalse(self.s.drive('M 140 140')[0])

    def test_manual_takeover_cancels_auto_waiting_inside_geometry(self):
        self.assertTrue(self.arm()[0]);self.s.scan_time=self.now;self.s.scan_clear=True
        self.s.autonomy_allowed=True
        entered,release=threading.Event(),threading.Event()
        def validate(v,w):
            entered.set();release.wait(.3);return True
        self.s.arc_validator=validate
        auto_result=[];manual_result=[]
        auto=threading.Thread(target=lambda:auto_result.append(self.s.drive('V 0.040 0.120',autonomous=True)))
        auto.start();self.assertTrue(entered.wait(.2))
        manual=threading.Thread(target=lambda:manual_result.append(self.s.drive('M 140 140')))
        manual.start()
        deadline=time.perf_counter()+.08
        while self.s.autonomy_allowed is True and time.perf_counter()<deadline:time.sleep(.001)
        self.assertFalse(self.s.autonomy_allowed)
        release.set();auto.join(.5);manual.join(.5)
        self.assertFalse(auto_result[0][0]);self.assertTrue(manual_result[0][0])
        self.assertNotIn(b'V 0.040 0.120\n',self.uart.writes)
        self.assertIn(b'M 140 140\n',self.uart.writes)


class CruiseNavigation(unittest.TestCase):
    setUp=fixtures.NavigationRegression.setUp
    grid=fixtures.NavigationRegression.grid

    def test_missing_radar_bin_does_not_block_known_free_rotation(self):
        self.grid(80,80,.05,[0]*6400)
        s=self.m.state;s.body_radius_m=.20;s.ranges=[2.]*360;s.ranges[25]=0.;s.scan_mono=time.monotonic()
        self.node._pose_map=lambda:(1.,1.,0.)
        self.assertTrue(self.node._rotation_clear())
        s.ranges[90]=.30
        self.assertFalse(self.node._rotation_clear())
        s.ranges=[0.]*360
        self.assertFalse(self.node._rotation_clear())

    def test_clear_straight_path_reaches_cruise_not_cell_step_speed(self):
        self.grid(80,80,.05,[0]*6400)
        self.sent=[]
        self.node.send_cmd=lambda cmd,autonomous=False:(self.sent.append(cmd) or (True,'SENT'))
        self.assertTrue(self.node._follow((1.025,1.025,0.),(2.025,1.025)))
        self.assertIn('V 0.536 0.000',self.sent)

    def missing_mount(self,armed):
        session=fixtures.SessionRegression();session.setUp()
        session.s.armed=armed;session.s.latched=not armed
        self.node.control=session.s
        self.node._fresh_ros_header=lambda *a:True
        def missing(*a):raise LookupError('TF not delivered yet')
        self.node.tf_buffer=types.SimpleNamespace(lookup_transform=missing)
        msg=types.SimpleNamespace(header=types.SimpleNamespace(frame_id='laser'),
            angle_min=0.,angle_increment=.01,range_min=.05,range_max=16.,ranges=[2.]*360)
        self.node.scan_cb(msg)
        return session

    def test_initial_scan_before_static_tf_waits_without_fault_or_stop(self):
        session=self.missing_mount(False)
        self.assertIsNone(session.s.fault)
        self.assertIsNone(session.s.scan_time)
        self.assertEqual(session.uart.writes,[])

    def test_lost_mount_while_armed_still_stops(self):
        session=self.missing_mount(True)
        self.assertEqual(session.s.fault,'MISSING_SCAN_TF')
        self.assertIn(b'STOP\n',session.uart.writes)


if __name__=='__main__':unittest.main()
