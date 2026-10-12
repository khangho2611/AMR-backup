import sys, os
sys.path.insert(0, os.path.abspath('.'))
import unittest
import time
from agv_command_session import CommandSession

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
    def test_driver_off_then_on_auto_recovery(self):
        ser = FakeSerial()
        session = CommandSession(ser, strict_preflight=False)
        
        # 1. Startup normal D0 packets
        session.stage = 3
        session.ingest({"safety": "ARMED", "mode": "PID", "l_tgt": 0.0, "r_tgt": 0.0, "l_rpm": 0.0, "r_rpm": 0.0, "l_pwm": 0, "r_pwm": 0, "x": 0.0, "y": 0.0, "th": 0.0, "v": 0.0, "w": 0.0})
        self.assertTrue(session.armed)
        self.assertFalse(session.latched)
        self.assertIsNone(session.fault)

        # 2. Driver loses power -> ESP32 enters FAULT state
        session.ingest({"safety": "FAULT", "mode": "PID", "l_tgt": 0.0, "r_tgt": 0.0, "l_rpm": 0.0, "r_rpm": 0.0, "l_pwm": 0, "r_pwm": 0, "x": 0.0, "y": 0.0, "th": 0.0, "v": 0.0, "w": 0.0})
        self.assertEqual(session.fault, "MCU_FAULT")
        self.assertFalse(session.latched, "Vehicle must never latch in operator mode")

        # 3. Driver powered back on -> CLEAR_FAULT ACK received from ESP32
        session.ingest({"ack": "CLEAR_FAULT", "state": "DISARMED", "i2c": "RECOVERED"})
        self.assertIsNone(session.fault, "Fault must be cleared immediately upon CLEAR_FAULT ACK")
        self.assertFalse(session.latched)

        # 4. ARM ACK received
        session.ingest({"ack": "ARM", "state": "ARMED"})
        self.assertTrue(session.armed, "System must be ARMED immediately upon ARM ACK")
        self.assertFalse(session.latched)

        # 5. User immediately drives with M 140 140 -> Must succeed without any blocking
        ok, reason = session.drive("M 140 140")
        self.assertTrue(ok, f"Drive must succeed, got reason: {reason}")
        self.assertEqual(reason, "SENT")
        self.assertTrue(any(b"M 140 140" in w for w in ser.written))
        print("PASS test_driver_off_then_on_auto_recovery")

if __name__ == '__main__':
    unittest.main()
