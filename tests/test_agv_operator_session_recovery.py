"""Regressions for a manual MCU disarm leaving stale host motion/ARM state.

Runs with a fake UART and clock. It never contacts the robot.
"""
import unittest
from unittest.mock import patch

from agv_command_session import CommandSession, ZERO


class FakeUART:
    is_open = True

    def __init__(self):
        self.writes = []

    def write(self, payload):
        self.writes.append(payload)
        return len(payload)


class OperatorSessionRecovery(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.uart = FakeUART()
        self.session = CommandSession(self.uart, clock=lambda: self.now,
                                      strict_preflight=False)
        self.session.autonomy_allowed = False
        self.d0 = dict(safety='DISARMED', mode='MAN', x=0.583, y=0.455,
                       th=1.507, **{key: 0 for key in ZERO})
        self.session.ingest(self.d0)

    def arm(self):
        def receive_ack_and_d0(timeout):
            self.now += .01
            self.session.ingest(dict(ack='ARM', state='ARMED'))
            self.now += .01
            self.session.ingest({**self.d0, 'safety': 'ARMED'})
            return self.session.arm_event.is_set()

        with patch.object(self.session.arm_event, 'wait', side_effect=receive_ack_and_d0):
            self.assertEqual(self.session.request_arm(), (True, 'ARM_CONFIRMED'))

    def drive_then_mcu_disarm(self):
        self.arm()
        self.assertEqual(self.session.drive('M 200 200'), (True, 'SENT'))
        self.assertTrue(self.session.motion)
        self.now += .1
        self.session.ingest(self.d0)

    def test_manual_mcu_disarm_releases_host_motion_and_pending_arm(self):
        self.drive_then_mcu_disarm()
        self.assertFalse(self.session.armed)
        self.assertFalse(self.session.motion)
        self.assertIsNone(self.session.arm_sent)
        self.assertFalse(self.session.arm_ack)
        self.assertIsNone(self.session.fault)

    def test_reset_after_disarm_no_longer_reports_motion_session_active(self):
        self.drive_then_mcu_disarm()
        self.assertEqual(self.session.request_clear_fault(),
                         (True, 'RESET_SENT_AWAIT_ACK_AND_ZERO_D0'))
        self.assertEqual(self.uart.writes[-1], b'CLEAR_FAULT\n')

    def test_new_explicit_arm_after_disarm_and_old_ack_cannot_rearm(self):
        self.drive_then_mcu_disarm()
        before = list(self.uart.writes)
        self.now += .01
        self.session.ingest(dict(ack='ARM', state='ARMED'))
        self.now += .01
        self.session.ingest({**self.d0, 'safety': 'ARMED'})
        self.assertFalse(self.session.armed, 'An old ARM transaction cannot reopen the session')
        self.assertEqual(self.uart.writes, before)
        self.now += .01
        self.session.ingest(self.d0)
        self.arm()
        self.assertEqual(self.session.drive('M -190 -190'), (True, 'SENT'))

    def test_fault_during_drive_still_latches_and_cannot_be_cleared_by_arm(self):
        self.arm()
        self.session.drive('M 200 200')
        self.now += .01
        self.session.ingest({**self.d0, 'safety': 'FAULT'})
        self.assertEqual(self.session.fault, 'MCU_FAULT')
        self.assertTrue(self.session.latched)
        self.assertFalse(self.session.request_arm()[0])
        self.assertFalse(self.session.drive('M 200 200')[0])


if __name__ == '__main__':
    unittest.main()
