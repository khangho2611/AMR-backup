import sys, os
sys.path.insert(0, os.path.abspath('.'))
import unittest
import time
import threading
from agv_command_session import CommandSession
from agv_preflight_static_collector import EXACT_I2C_SCAN_BANNER

class FakeSerial:
    def __init__(self):
        self.is_open = True
        self.written = []
    def write(self, data):
        self.written.append(data)
        return len(data)
    def flush(self):
        pass

class TestDriverPowerCycle(unittest.TestCase):
    def test_operator_boot_i2c_after_early_d0_is_valid_and_does_not_issue_stop(self):
        ser = FakeSerial()
        now = [10.0]
        session = CommandSession(ser, clock=lambda: now[0], strict_preflight=False)
        d0 = {"safety": "DISARMED", "mode": "PID", "l_tgt": 0.0,
              "r_tgt": 0.0, "l_rpm": 0.0, "r_rpm": 0.0, "l_pwm": 0,
              "r_pwm": 0, "x": 0.0, "y": 0.0, "th": 0.0,
              "v": 0.0, "w": 0.0}
        session.ingest(d0)
        self.assertEqual(session.stage, 3)
        now[0] += 1.2
        session.ingest(d0)
        session.ingest({'info': EXACT_I2C_SCAN_BANNER})
        session.ingest({'i2c_found': '0x42'})
        session.ingest({'vin_mv': 12033})
        self.assertIsNone(session.fault)
        self.assertFalse(session.latched)
        self.assertFalse(session.armed)
        self.assertEqual(session.stage, 3)
        self.assertTrue(session.operator_i2c_found_seen)
        self.assertEqual(ser.written, [])

    def test_operator_late_or_out_of_order_diagnostic_fails_closed(self):
        d0 = {"safety": "DISARMED", "mode": "PID", "l_tgt": 0.0,
              "r_tgt": 0.0, "l_rpm": 0.0, "r_rpm": 0.0, "l_pwm": 0,
              "r_pwm": 0, "x": 0.0, "y": 0.0, "th": 0.0,
              "v": 0.0, "w": 0.0}
        for unexpected, elapsed in (({'i2c_found':'0x42'}, 1.5),
                                    ({'info':EXACT_I2C_SCAN_BANNER}, 4.0),
                                    ({'info':'other boot message'}, 1.5)):
            with self.subTest(unexpected=unexpected, elapsed=elapsed):
                ser = FakeSerial()
                now = [10.0]
                session = CommandSession(ser, clock=lambda: now[0], strict_preflight=False)
                session.ingest(d0)
                now[0] += elapsed
                session.ingest(d0)
                session.ingest(unexpected)
                self.assertEqual(session.fault, 'UNCLASSIFIED_PACKET')
                self.assertTrue(session.latched)
                self.assertFalse(session.armed)
                self.assertTrue(any(w == b'STOP\n' for w in ser.written))
                kinds = [e['kind'] for e in session.diagnostics()['command_events']]
                self.assertIn('rx_unclassified', kinds)

    def test_driver_power_cycle_requires_explicit_recovery_and_arm(self):
        ser = FakeSerial()
        now = [10.0]
        session = CommandSession(ser, clock=lambda: now[0], strict_preflight=False)
        session.stage = 3
        d0 = {"safety": "DISARMED", "mode": "PID", "l_tgt": 0.0, "r_tgt": 0.0, "l_rpm": 0.0, "r_rpm": 0.0, "l_pwm": 0, "r_pwm": 0, "x": 0.0, "y": 0.0, "th": 0.0, "v": 0.0, "w": 0.0}
        session.ingest(d0)
        self.assertFalse(session.armed)
        self.assertIsNone(session.fault)
        session.ingest({**d0, "safety": "FAULT"})
        self.assertEqual(session.fault, "MCU_FAULT")
        self.assertTrue(session.latched)
        self.assertFalse(session.drive('M 140 140')[0])
        # Unsolicited recovery ACK must never clear the latch.
        session.ingest({"ack": "CLEAR_FAULT", "state": "DISARMED", "i2c": "RECOVERED"})
        self.assertEqual(session.fault, 'MCU_FAULT')
        self.assertTrue(session.request_clear_fault()[0])
        now[0] += .01
        session.ingest({"ack": "CLEAR_FAULT", "state": "DISARMED", "i2c": "RECOVERED"})
        now[0] += .01
        session.ingest(d0)
        self.assertIsNone(session.fault)
        self.assertTrue(session.latched)
        self.assertFalse(session.armed)
        # ARM requires an explicit request, MCU ACK, and a later ARMED D0.
        session.ingest({"ack": "ARM", "state": "ARMED"})
        self.assertFalse(session.armed)
        result = []
        worker = threading.Thread(target=lambda: result.append(session.request_arm()))
        worker.start()
        deadline = time.monotonic() + .25
        while b'ARM\n' not in ser.written and time.monotonic() < deadline:
            time.sleep(.001)
        self.assertIn(b'ARM\n', ser.written)
        now[0] += .01
        session.ingest({"ack": "ARM", "state": "ARMED"})
        now[0] += .01
        session.ingest({**d0, 'safety': 'ARMED'})
        worker.join(.5)
        self.assertEqual(result, [(True, 'ARM_CONFIRMED')])
        self.assertFalse(session.latched)
        ok, reason = session.drive("M 140 140")
        self.assertTrue(ok, f"Drive must succeed, got reason: {reason}")
        self.assertEqual(reason, "SENT")
        self.assertTrue(any(b"M 140 140" in w for w in ser.written))

if __name__ == '__main__':
    unittest.main()
