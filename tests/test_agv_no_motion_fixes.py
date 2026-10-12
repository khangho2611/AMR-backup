"""Offline regressions for swept clearance and retained command outcomes."""
import math
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

import test_agv_navigation_fix as fixtures
from agv_navigation import GridPlanner


class SweptClearance(unittest.TestCase):
    def swept(self, grid, pose, v, w):
        self.assertTrue(hasattr(grid, 'swept_clear'),
                        'A moving arc needs a geometric footprint check')
        return grid.swept_clear(pose, v, w)

    def grid(self, data=None, origin=(0., 0., 0.)):
        return GridPlanner(80, 80, .05, origin,
                           [0]*6400 if data is None else data, .20, .15)

    def test_clear_arc_and_rotated_map_use_the_same_metric_footprint(self):
        for origin, pose in [((0.,0.,0.), (1.,1.,0.)),
                             ((2.,3.,math.pi/2), (1.,4.,math.pi/2))]:
            self.assertTrue(self.swept(self.grid(origin=origin),pose,.02,.12))

    def test_obstacle_or_unknown_inside_body_margin_blocks_even_a_forward_arc(self):
        for value in (-1,100):
            data=[0]*6400
            data[26*80+20]=value  # 30 cm to the side, outside the front cone.
            self.assertFalse(self.swept(self.grid(data),(1.025,1.025,0.),.02,.12))

    def test_curve_cannot_enter_a_cell_that_the_starting_footprint_clears(self):
        data=[0]*6400
        data[20*80+27]=100
        grid=self.grid(data)
        self.assertTrue(self.swept(grid,(.98,1.025,0.),0.,0.))
        self.assertFalse(self.swept(grid,(.98,1.025,0.),.08,.35))

    def test_subcell_edge_and_invalid_twist_fail_closed(self):
        grid=self.grid()
        self.assertFalse(self.swept(grid,(.34,1.,0.),.02,.12))
        self.assertFalse(self.swept(grid,(1.,1.,0.),math.nan,.12))


class ArcSession(unittest.TestCase):
    setUp=fixtures.SessionRegression.setUp
    d0=fixtures.SessionRegression.d0
    ready=fixtures.SessionRegression.ready
    arm=fixtures.SessionRegression.arm

    def test_front_flag_alone_cannot_authorize_a_turning_forward_command(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True;self.s.rotation_clear=False
        before=list(self.uart.writes)
        self.assertFalse(self.s.drive('V 0.020 0.120',autonomous=True)[0])
        self.assertEqual(self.uart.writes,before)

    def test_freshness_is_rechecked_after_geometry_and_before_tx(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True;self.s.rotation_clear=False
        called=[]
        def validate(v,w):
            called.append((v,w));self.now+=.26
            return True
        self.s.arc_validator=validate
        before=list(self.uart.writes)
        self.assertFalse(self.s.drive('V 0.020 0.120',autonomous=True)[0])
        self.assertEqual(called,[(.02,.12)])
        self.assertEqual(self.uart.writes,before)

    def test_stop_can_cancel_an_arc_while_geometry_is_in_progress(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time=self.now;self.s.scan_clear=True
        entered,release=threading.Event(),threading.Event()
        def validate(v,w):
            entered.set();release.wait(.3);return True
        self.s.arc_validator=validate
        result=[]
        drive=threading.Thread(target=lambda:result.append(self.s.drive('V 0.020 0.120',autonomous=True)))
        drive.start();self.assertTrue(entered.wait(.2))
        stop=threading.Thread(target=lambda:self.s.request_stop(wait=False));stop.start()
        deadline=time.perf_counter()+.1
        while not self.s.latched and time.perf_counter()<deadline:time.sleep(.001)
        self.assertTrue(self.s.latched,'STOP must latch without waiting for geometry')
        release.set();drive.join(1);stop.join(1)
        self.assertFalse(drive.is_alive());self.assertFalse(stop.is_alive())
        self.assertFalse(result[0][0])
        self.assertNotIn(b'V 0.020 0.120\n',self.uart.writes)
        self.assertIn(b'STOP\n',self.uart.writes)


class NodeArcClearance(unittest.TestCase):
    def setUp(self):
        self.m=fixtures.load_brain();self.m.state=self.m.AGVSharedState()
        self.node=self.m.AGVROSNode.__new__(self.m.AGVROSNode)
        s=self.m.state
        s.map_width=s.map_height=80;s.map_resolution=.05;s.map_data=[0]*6400
        s.map_received=True;s.map_frame='map';s.map_mono=time.monotonic();s.map_version=1
        s.body_radius_m=.20;s.scan_mono=time.monotonic();s.ranges=[2.]*360
        self.node._pose_map=lambda:(1.,1.,0.)

    def clear(self):
        self.assertTrue(hasattr(self.node,'_forward_arc_clear'),
                        'The actual writer must call the node geometry validator')
        return self.node._forward_arc_clear(.02,.12)

    def test_yellow_rear_obstacle_does_not_block_clear_forward_sweep(self):
        self.m.state.ranges[180]=.55
        self.assertTrue(self.clear())

    def test_scan_obstacle_to_side_blocks_arc_even_if_map_has_not_caught_up(self):
        self.m.state.ranges[90]=.30
        self.assertFalse(self.clear())

    def test_missing_pose_or_stale_map_does_not_validate_an_arc(self):
        self.node._pose_map=lambda:None
        self.assertFalse(self.clear())
        self.node._pose_map=lambda:(1.,1.,0.)
        self.m.state.map_mono=time.monotonic()-2.1
        self.assertFalse(self.clear())


class RetainedCommands(unittest.TestCase):
    setUp=fixtures.SessionRegression.setUp
    d0=fixtures.SessionRegression.d0
    ready=fixtures.SessionRegression.ready
    arm=fixtures.SessionRegression.arm

    def test_nonfault_arm_ack_and_drive_survive_long_idle_d0_stream(self):
        self.assertTrue(self.arm()[0]);self.s.scan_time=self.now;self.s.scan_clear=True
        self.s.drive('V 0.040 0.000',autonomous=True)
        for _ in range(1500):
            self.now+=.1;self.s.ingest(self.d0(safety='ARMED'))
        report=self.s.diagnostics()
        self.assertTrue('command_events' in report,'D0 must not erase command history')
        commands=report['command_events']
        self.assertTrue(any(e['kind']=='tx' and e['command']=='ARM' for e in commands))
        self.assertTrue(any(e['kind']=='rx_ack' and e['ack']=='ARM' for e in commands))
        self.assertTrue(any(e['kind']=='drive' and e['accepted'] for e in commands))
        self.assertFalse(any(e['kind']=='rx_d0' for e in commands))
        commands.clear()
        self.assertTrue(self.s.diagnostics()['command_events'])


if __name__=='__main__':
    unittest.main()
