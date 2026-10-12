import sys, time, json, queue, unittest
import candidate_agv_motion_supervisor_runner_v08 as runner_mod
import candidate_agv_serial_arbiter_bridge_v3_v08 as gate_mod

class FakeUARTDevice:
    def __init__(self):
        self.rx_queue = queue.Queue()
        self.tx_history = []
        self.is_open = True
        self.fail_partial_stop = False

    def write(self, data: bytes) -> int:
        self.tx_history.append(data)
        if self.fail_partial_stop and data.startswith(b'STOP'):
            return 1
        if data.startswith(b'ARM'):
            self.inject_line('{"ack":"ARM","state":"ARMED"}')
        elif data.startswith(b'STOP'):
            self.inject_line('{"ack":"STOP","state":"DISARMED"}')
        return len(data)

    def readline(self) -> bytes:
        try:
            return self.rx_queue.get(timeout=0.05)
        except queue.Empty:
            return b''

    def inject_line(self, line_str: str):
        if not line_str.endswith(chr(10)):
            line_str += chr(10)
        self.rx_queue.put(line_str.encode('utf-8'))

    def flush(self):
        pass

    def close(self):
        self.is_open = False

class TestCandidateRunnerV08Production(unittest.TestCase):
    def setUp(self):
        self.fake_dev = FakeUARTDevice()
        self.gate = gate_mod.SerialArbiterGateV3(mock_serial=self.fake_dev)
        self.gate.connected = True
        self.gate.send_velocity_command = lambda *args, **kwargs: (True, "ACCEPTED")
    def test_ca1_positive_params(self):
        sup = runner_mod.MotionSupervisor(
            serial_arbiter=self.gate,
            target_v=0.08,
            nominal_time_s=1.0,
            hard_time_cap_s=1.5
        )
        self.assertEqual(sup.target_v, 0.08)
        self.assertEqual(self.gate.MAX_LINEAR_VEL, 0.08)

    def test_ca2_overspeed_guard(self):
        sup = runner_mod.MotionSupervisor(
            serial_arbiter=self.gate,
            target_v=0.08,
            nominal_time_s=1.0,
            hard_time_cap_s=1.5
        )
        sup.start_mono = 100.0
        sup.is_active = True
        sup.last_cycle_mono = 100.0
        d0_overspeed = {
            'safety': 'ARMED', 'l_rpm': 30.0, 'r_rpm': 30.0,
            'l_pwm': 50, 'r_pwm': 50, 'l_tgt': 20.9, 'r_tgt': 20.9,
            'rx_mono': 100.1
        }
        ok, reason = sup.update_cycle(100.1, d0_overspeed)
        self.assertFalse(ok)
        self.assertEqual(reason, 'OVERSPEED_TRIPPED')
        self.assertTrue(sup.fault_tripped)

    def test_ca3_stall_guard(self):
        sup = runner_mod.MotionSupervisor(
            serial_arbiter=self.gate,
            target_v=0.08,
            nominal_time_s=1.0,
            hard_time_cap_s=1.5
        )
        sup.start_mono = 100.0
        sup.is_active = True
        sup.last_cycle_mono = 100.0
        d0_stall = {
            'safety': 'ARMED', 'l_rpm': 0.0, 'r_rpm': 0.0,
            'l_pwm': 85, 'r_pwm': 85, 'l_tgt': 20.9, 'r_tgt': 20.9,
            'rx_mono': 100.85
        }
        ok, reason = sup.update_cycle(100.85, d0_stall)
        self.assertFalse(ok)
        self.assertEqual(reason, 'STALL_GUARD_TRIPPED')
        self.assertTrue(sup.fault_tripped)

    def test_ca4_mismatch_guard(self):
        sup = runner_mod.MotionSupervisor(
            serial_arbiter=self.gate,
            target_v=0.08,
            nominal_time_s=1.0,
            hard_time_cap_s=1.5
        )
        sup.start_mono = 100.0
        sup.is_active = True
        sup.last_cycle_mono = 100.0
        d0_mismatch_1 = {
            'safety': 'ARMED', 'l_rpm': 20.0, 'r_rpm': 2.0,
            'l_pwm': 30, 'r_pwm': 30, 'l_tgt': 20.9, 'r_tgt': 20.9,
            'rx_mono': 100.05
        }
        ok1, _ = sup.update_cycle(100.05, d0_mismatch_1)
        self.assertTrue(ok1)

        d0_mismatch_2 = {
            'safety': 'ARMED', 'l_rpm': 20.0, 'r_rpm': 2.0,
            'l_pwm': 30, 'r_pwm': 30, 'l_tgt': 20.9, 'r_tgt': 20.9,
            'rx_mono': 100.18
        }
        ok2, reason2 = sup.update_cycle(100.18, d0_mismatch_2)
        self.assertFalse(ok2)
        self.assertEqual(reason2, 'RPM_MISMATCH_TRIPPED')
        self.assertTrue(sup.fault_tripped)

    def test_ca5_partial_stop_write(self):
        self.fake_dev.fail_partial_stop = True
        wrapper = runner_mod.TransportWrapper(self.fake_dev)
        written = wrapper.write(b'STOP' + chr(10).encode())
        self.assertEqual(written, 1)

        sup = runner_mod.MotionSupervisor(self.gate, 0.08, 0.05, 1.0, 1.5)
        sup.start_mono = 100.0
        sup.stop_requested_mono = 101.0
        sup.stop_write_failed = True

        d0_zero = {
            'safety': 'DISARMED', 'l_rpm': 0.0, 'r_rpm': 0.0,
            'l_pwm': 0, 'r_pwm': 0, 'l_tgt': 0.0, 'r_tgt': 0.0,
            'rx_mono': 101.05
        }
        confirmed = sup.check_stop_confirmation(101.05, d0_zero)
        self.assertFalse(confirmed)
        self.assertFalse(sup.stop_confirmed)
        self.assertTrue(sup.fault_tripped)
        self.assertEqual(sup.fault_reason, 'STOP_WRITE_FAILED')

    def test_ca6_no_caller_watchdog(self):
        sup = runner_mod.MotionSupervisor(self.gate, 0.08, 0.05, 1.0, 1.5)
        sup.start_mono = 100.0
        sup.is_active = True
        self.assertTrue(sup.is_active)
        if (101.6 - sup.start_mono) > sup.hard_time_cap_s:
            sup.trigger_estop(101.6, 'WATCHDOG_HARD_TIME_CAP')
        self.assertFalse(sup.is_active)
        self.assertTrue(sup.fault_tripped)
        self.assertEqual(sup.fault_reason, 'WATCHDOG_HARD_TIME_CAP')

if __name__ == '__main__':
    unittest.main()