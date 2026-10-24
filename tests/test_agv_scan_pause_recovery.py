"""A delayed scan pauses operator AUTO without destroying its armed mission."""
import unittest

from agv_command_session import CommandSession, ZERO


class UART:
    is_open = True
    def __init__(self): self.writes = []
    def write(self, payload): self.writes.append(payload); return len(payload)


class ScanPauseRecovery(unittest.TestCase):
    def setUp(self):
        self.now = 10.
        self.ser = UART()
        self.s = CommandSession(self.ser, clock=lambda: self.now, strict_preflight=False)
        self.s.stage = 3
        self.s.armed = self.s.motion = True
        self.s.autonomy_allowed = True
        self.s.latest = dict(safety='ARMED', mode='PID', x=0.,y=0.,th=0., **{k:0 for k in ZERO})
        self.s.last_d0 = self.s.last_command = self.now
        self.s.scan_time = self.now - 1.
        self.s.scan_clear = self.s.rotation_clear = True
        self.s.arc_validator = lambda v,w: True

    def test_scan_gap_sends_zero_without_fault_latch_or_disarm(self):
        self.s.watchdog_tick()
        self.assertEqual(self.ser.writes, [b'V 0.000 0.000\n'])
        self.assertTrue(self.s.armed)
        self.assertFalse(self.s.motion)
        self.assertFalse(self.s.latched)
        self.assertIsNone(self.s.fault)
        self.assertTrue(self.s.health()['scan_holding'])

    def test_scan_pause_blocks_motion_then_allows_a_fresh_replanned_command(self):
        self.s.watchdog_tick()
        before=list(self.ser.writes)
        self.assertFalse(self.s.drive('V 0.080 0.000', autonomous=True)[0])
        self.assertEqual(self.ser.writes,before)
        self.now += .1
        self.s.scan_time=self.s.last_d0=self.now
        self.s.watchdog_tick()
        self.assertFalse(self.s.health()['scan_holding'])
        self.assertEqual(self.s.drive('V 0.080 0.000', autonomous=True),(True,'SENT'))

    def test_zero_hold_is_allowed_when_scan_is_stale(self):
        self.assertEqual(self.s.drive('V 0.000 0.000', autonomous=True),(True,'SENT'))

    def test_mcu_timeout_still_stops_and_never_auto_recovers(self):
        self.s.last_d0=self.now-1.
        self.s.watchdog_tick()
        self.assertEqual(self.s.fault,'TELEMETRY_TIMEOUT')
        self.assertFalse(self.s.armed)
        self.assertIn(b'STOP\n',self.ser.writes)

    def test_strict_profile_retains_scan_stop_behavior(self):
        self.s.strict_preflight=True
        self.s.watchdog_tick()
        self.assertEqual(self.s.fault,'SCAN_TIMEOUT')
        self.assertFalse(self.s.armed)
        self.assertIn(b'STOP\n',self.ser.writes)

    def test_user_stop_cancels_scan_pause_and_fresh_scan_cannot_rearm(self):
        self.s.watchdog_tick()
        self.s.request_stop(wait=False)
        self.now+=.1
        self.s.scan_time=self.s.last_d0=self.now
        self.s.watchdog_tick()
        self.assertFalse(self.s.armed)
        self.assertTrue(self.s.latched)


if __name__ == '__main__': unittest.main()
