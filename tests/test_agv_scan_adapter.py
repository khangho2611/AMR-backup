import math
import types
import unittest
from agv_navigation import slam_censored_ranges
import test_agv_brain_integration as integration


class CensoredScan(unittest.TestCase):
    def test_no_hit_traces_but_never_marks_fake_endpoint(self):
        values=[.56,math.inf,math.nan,-math.inf,0.,16.]
        out=slam_censored_ranges(values,.05,16.)
        self.assertEqual(out[0],.56)
        self.assertGreater(out[1],12.)
        self.assertLess(out[1],16.)
        self.assertFalse(out[1] < 12.-1e-6,'Karto must not mark a synthetic hit')
        self.assertTrue(math.isnan(out[2]))
        self.assertEqual(out[3:],values[3:])
        self.assertEqual(values[1],math.inf,'Input raw scan must not mutate')

    def test_incompatible_sensor_limits_hold(self):
        for maximum in (8.,12.,math.nan,math.inf):
            with self.assertRaises(ValueError):slam_censored_ranges([math.inf],.05,maximum)


class ScanCallback(unittest.TestCase):
    def test_actual_callback_preserves_header_and_raw_scan(self):
        fixture=integration.BrainIntegration()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.node=fixture.node
        published=[]
        self.node.pub_slam_scan=types.SimpleNamespace(publish=published.append)
        scan=fixture.scan();scan.range_max=16.;scan.ranges[20]=math.inf
        self.node.scan_cb(scan)
        self.assertEqual(len(published),1)
        self.assertEqual(published[0].header,scan.header)
        self.assertEqual(published[0].angle_increment,scan.angle_increment)
        self.assertEqual(scan.ranges[20],math.inf)
        self.assertGreater(published[0].ranges[20],12.)
        self.assertLess(published[0].ranges[20],16.)
