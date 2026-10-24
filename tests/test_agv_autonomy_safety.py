"""Autonomy must fail closed even with the operator-control web profile.

All checks use a fake UART and never open a physical serial port.
"""
import time
import unittest

from agv_command_session import CommandSession, ZERO


class FakeSerial:
    is_open = True

    def __init__(self):
        self.writes = []

    def write(self, payload):
        self.writes.append(payload)
        return len(payload)


class OperatorAutonomySafety(unittest.TestCase):
    def setUp(self):
        self.ser = FakeSerial()
        self.now = 10.0
        self.s = CommandSession(self.ser, clock=lambda: self.now, strict_preflight=False)
        self.s.stage = 3
        self.s.autonomy_allowed = True
        self.s.armed = True
        self.s.latest = {'safety': 'ARMED', **{k: 0 for k in ZERO}}
        self.s.last_d0 = self.now
        self.s.scan_time = self.now
        self.s.scan_clear = True
        self.s.rotation_clear = True
        self.s.arc_validator = lambda v, w: True
        self.s.escape_validator = lambda v, w: True

    def rejected_without_uart(self, command='V 0.100 0.000', escape=False):
        before = list(self.ser.writes)
        ok, reason = self.s.drive(command, autonomous=True, escape=escape)
        self.assertFalse(ok, reason)
        self.assertEqual(before, self.ser.writes)
        return self.s.command_events[-1].get('blockers', [])

    def test_operator_auto_rejects_stale_telemetry(self):
        self.s.last_d0 = self.now - 2
        self.assertIn('D0_STALE', self.rejected_without_uart())

    def test_operator_auto_rejects_stale_scan(self):
        self.s.scan_time = self.now - 2
        self.assertIn('SCAN_STALE', self.rejected_without_uart())

    def test_operator_auto_rejects_blocked_front(self):
        self.s.scan_clear = False
        self.assertIn('FORWARD_NOT_CLEAR', self.rejected_without_uart())

    def test_operator_auto_rejects_invalid_arc(self):
        self.s.arc_validator = lambda v, w: False
        self.assertIn('ARC_NOT_VALIDATED', self.rejected_without_uart())

    def test_operator_auto_rejects_unsafe_rotation(self):
        self.s.rotation_clear = False
        self.assertIn('SWEEP_NOT_CLEAR', self.rejected_without_uart('V 0.000 0.500'))

    def test_operator_auto_never_clears_fault_or_rearms(self):
        self.s.fault = 'MCU_FAULT'
        self.s.latest['safety'] = 'FAULT'
        self.assertIn('FAULT', self.rejected_without_uart())
        self.assertEqual(self.s.fault, 'MCU_FAULT')

    def test_operator_manual_cannot_clear_fault_by_driving(self):
        self.s.fault = 'STOP_UNCONFIRMED'
        before = list(self.ser.writes)
        self.assertFalse(self.s.drive('V 0.040 0.000')[0])
        self.assertEqual(self.ser.writes, before)
        self.assertEqual(self.s.fault, 'STOP_UNCONFIRMED')

    def test_manual_ignores_lidar_proximity_and_scan_age(self):
        """LiDAR warns manual operators; only AUTO uses its geometry gate."""
        self.s.autonomy_allowed = False
        self.s.scan_time = self.now - 5.0
        self.s.scan_clear = False
        self.s.rotation_clear = False
        self.assertEqual(self.s.drive('M 200 200'), (True, 'SENT'))
        self.assertIn(b'M 200 200\n', self.ser.writes)
        self.s.last_command = self.now
        self.s.watchdog_tick()
        self.assertNotIn(b'STOP\n', self.ser.writes)

    def test_idle_manual_zero_cannot_steal_auto_owner(self):
        """Regression: browser's late 120ms idle keepalive after AUTO_START."""
        generation = self.s.generation
        before = list(self.ser.writes)
        self.assertEqual(self.s.drive('V 0.000 0.000'), (False, 'AUTO_OWNS_CONTROL'))
        self.assertEqual(self.s.generation, generation)
        self.assertTrue(self.s.autonomy_allowed)
        self.assertEqual(self.ser.writes, before)
        self.assertEqual(self.s.drive('V 0.080 0.000', autonomous=True), (True, 'SENT'))
        self.assertEqual(self.ser.writes[-1], b'V 0.080 0.000\n')

    def test_manual_takeover_and_explicit_stop_remain_available(self):
        self.assertEqual(self.s.drive('M 120 120'), (True, 'SENT'))
        self.assertFalse(self.s.autonomy_allowed)
        self.assertEqual(self.s.drive('V 0.000 0.000'), (True, 'SENT'))
        self.s.autonomy_allowed = True
        self.s.request_stop('USER_STOP', wait=False)
        self.assertIn(b'STOP\n', self.ser.writes)
        self.assertFalse(self.s.armed)

    def test_auto_still_blocks_same_stale_scan_and_obstacle(self):
        self.s.scan_time = self.now - 5.0
        self.s.scan_clear = False
        blockers = self.rejected_without_uart()
        self.assertIn('SCAN_STALE', blockers)
        self.assertIn('FORWARD_NOT_CLEAR', blockers)

    def test_operator_stop_requires_post_write_zero_d0(self):
        self.s.stop_event.wait = lambda timeout: False
        ok, reason = self.s.request_stop('USER_STOP', wait=True)
        self.assertFalse(ok)
        self.assertEqual(reason, 'STOP_UNCONFIRMED')
        self.assertFalse(self.s.stop_confirmed)

    def test_operator_watchdog_pauses_on_stale_scan_without_faulting_the_mission(self):
        self.s.scan_time = self.now - 2
        self.s.motion = True
        self.s.last_command = self.now
        self.s.watchdog_tick()
        self.assertEqual(self.ser.writes, [b'V 0.000 0.000\n'])
        self.assertTrue(self.s.armed)
        self.assertFalse(self.s.motion)
        self.assertIsNone(self.s.fault)

    def test_mcu_error_latches_operator_and_blocks_drive(self):
        self.s.ingest({'error': 'DISARMED_REJECT_V'})
        self.assertEqual(self.s.fault, 'DISARMED_REJECT_V')
        self.assertTrue(self.s.latched)
        self.assertFalse(self.s.armed)
        self.rejected_without_uart()

    def test_unsolicited_ack_cannot_clear_fault(self):
        self.s.ingest({'error': 'DRIVER_OFF_OR_FAULT'})
        self.s.ingest({'ack': 'CLEAR_FAULT', 'state': 'DISARMED', 'i2c': 'RECOVERED'})
        self.assertEqual(self.s.fault, 'DRIVER_OFF_OR_FAULT')
        self.assertTrue(self.s.latched)

    def test_unsolicited_arm_ack_or_d0_cannot_arm_operator(self):
        self.s.armed = False
        self.s.ingest({'ack': 'ARM', 'state': 'ARMED'})
        self.assertFalse(self.s.armed)
        self.s.ingest({'safety': 'ARMED', 'mode': 'PID', **{k: 0 for k in ZERO},
                       'x': 0, 'y': 0, 'th': 0})
        self.assertFalse(self.s.armed)

    def test_explicit_clear_fault_requires_ack_and_later_zero_d0(self):
        self.s.ingest({'error': 'DRIVER_OFF_OR_FAULT'})
        self.s.latest['safety'] = 'FAULT'
        self.assertTrue(self.s.request_clear_fault()[0])
        self.assertEqual(self.ser.writes[-1], b'CLEAR_FAULT\n')
        self.s.ingest({'ack': 'CLEAR_FAULT', 'state': 'DISARMED', 'i2c': 'RECOVERED'})
        self.assertEqual(self.s.fault, 'DRIVER_OFF_OR_FAULT')
        self.now += .01
        self.s.ingest({'safety': 'DISARMED', 'mode': 'PID', **{k: 0 for k in ZERO},
                       'x': 0, 'y': 0, 'th': 0})
        self.assertIsNone(self.s.fault)
        self.assertTrue(self.s.latched)  # Recovery is never an implicit ARM.
        self.assertFalse(self.s.armed)

    def test_recovery_rejects_stale_or_physically_armed_telemetry(self):
        self.s.armed = False
        self.s.latest['safety'] = 'FAULT'
        self.s.last_d0 = self.now - 3
        self.assertEqual(self.s.request_clear_fault()[1], 'MCU_ZERO_DISARMED_OR_FAULT_REQUIRED')
        self.assertEqual(self.ser.writes, [])
        self.s.last_d0 = self.now
        self.s.latest['safety'] = 'ARMED'
        self.assertFalse(self.s.request_clear_fault()[0])
        self.assertEqual(self.ser.writes, [])

    def test_recovery_timeout_cannot_be_rescued_by_late_ack(self):
        self.s.ingest({'error': 'DRIVER_OFF_OR_FAULT'})
        self.s.latest['safety'] = 'FAULT'
        self.assertTrue(self.s.request_clear_fault()[0])
        self.now += 1.21
        self.s.watchdog_tick()
        self.assertFalse(self.s.clear_fault_pending)
        self.assertEqual(self.s.fault, 'DRIVER_OFF_OR_FAULT')
        self.s.ingest({'ack': 'CLEAR_FAULT', 'state': 'DISARMED'})
        self.now += .01
        self.s.ingest({'safety': 'DISARMED', 'mode': 'PID', **{k: 0 for k in ZERO},
                       'x': 0, 'y': 0, 'th': 0})
        self.assertEqual(self.s.fault, 'DRIVER_OFF_OR_FAULT')
        self.assertTrue(self.s.latched)

    def test_stop_cancels_pending_reset(self):
        self.s.ingest({'error': 'DRIVER_OFF_OR_FAULT'})
        self.s.latest['safety'] = 'FAULT'
        self.assertTrue(self.s.request_clear_fault()[0])
        self.s.request_stop('USER_STOP', wait=False)
        self.assertFalse(self.s.clear_fault_pending)
        self.now += .01
        self.s.ingest({'ack': 'CLEAR_FAULT', 'state': 'DISARMED'})
        self.now += .01
        self.s.ingest({'safety': 'DISARMED', 'mode': 'PID', **{k: 0 for k in ZERO},
                       'x': 0, 'y': 0, 'th': 0})
        self.assertEqual(self.s.fault, 'DRIVER_OFF_OR_FAULT')

    def test_operator_cannot_arm_against_stale_or_fault_mcu(self):
        self.s.armed = False
        self.s.last_d0 = self.now - 10.
        self.assertFalse(self.s.request_arm()[0])
        self.s.last_d0 = self.now
        self.s.latest['safety'] = 'FAULT'
        self.assertFalse(self.s.request_arm()[0])


if __name__ == '__main__':
    unittest.main()
