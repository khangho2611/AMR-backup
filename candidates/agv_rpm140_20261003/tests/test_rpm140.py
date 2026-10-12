"""Candidate offline speed/geometry limits, not hardware acceptance."""
import math
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agv_speed_profile import MAX_LINEAR_MPS, limited_twist
from agv_navigation import twist_centres, GridPlanner
sys.path.insert(0,str(ROOT.parents[1]/'tests'))
import test_agv_navigation_fix as fixtures
fixtures.ROOT=ROOT
sys.path.insert(0,str(ROOT))

class Speed140(unittest.TestCase):
    def test_straight_and_turning_wheel_targets_remain_bounded(self):
        for v in (0.,.04,.2,.536,-.536,2.):
            for w in (-.35,0.,.35):
                linear,angular=limited_twist(v,w)
                rpm=[(linear+sign*angular*.1925/2)*60/(2*math.pi*.0366) for sign in (-1,1)]
                self.assertLessEqual(max(map(abs,rpm)),140.00001)
        self.assertEqual(limited_twist(.536,0.),(.536,0.))
        self.assertAlmostEqual(MAX_LINEAR_MPS,.536)

    def test_invalid_input_cannot_create_motion(self):
        for value in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError):limited_twist(value,0.)
            with self.assertRaises(ValueError):limited_twist(0.,value)

    def test_fast_geometry_checks_full_extended_sweep(self):
        samples=twist_centres(.536,0.)
        self.assertIsNotNone(samples)
        self.assertGreaterEqual(samples[0][-1][0],.536)
        data=[0]*10000
        # Obstacle beyond old .5s horizon, inside new 1s swept body.
        data[50*100+66]=100
        grid=GridPlanner(100,100,.05,(0.,0.,0.),data,.20,.15)
        self.assertFalse(grid.swept_clear((2.5,2.5,0.),.536,0.))

class Session140(unittest.TestCase):
    setUp=fixtures.SessionRegression.setUp
    d0=fixtures.SessionRegression.d0
    ready=fixtures.SessionRegression.ready
    arm=fixtures.SessionRegression.arm

    def test_target_command_requires_fresh_explicit_arm_and_retains_stop(self):
        self.assertFalse(self.s.drive('V 0.536 0.000')[0])
        self.assertTrue(self.arm()[0])
        # This component fixture explicitly grants AUTO ownership after MAN.
        self.s.autonomy_allowed=True
        self.s.scan_time=self.now
        self.s.scan_clear=True
        self.s.arc_validator=lambda v,w:True
        self.assertTrue(self.s.drive('V 0.536 0.000',autonomous=True)[0])
        self.assertFalse(self.s.drive('V 0.537 0.000')[0])
        self.assertFalse(self.s.drive('V 0.536 0.350')[0])
        self.now+=.26
        self.assertFalse(self.s.drive('V 0.536 0.000')[0])
        self.s.request_stop(wait=False)
        self.assertFalse(self.s.drive('V 0.536 0.000')[0])
        self.assertIn(b'STOP\n',self.uart.writes)

class Navigation140(unittest.TestCase):
    setUp=fixtures.NavigationRegression.setUp
    grid=fixtures.NavigationRegression.grid

    def test_actual_follow_uses_requested_cruise_on_straight_free_path(self):
        self.grid(100,100,.05,[0]*10000)
        sent=[]
        self.node.send_cmd=lambda cmd,autonomous=False:(sent.append(cmd) or (True,'SENT'))
        self.assertTrue(self.node._follow((1.025,1.025,0.),(3.025,1.025)))
        self.assertEqual(sent[-1],'V 0.536 0.000')

if __name__=='__main__':unittest.main()
