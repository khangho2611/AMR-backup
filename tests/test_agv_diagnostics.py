"""Offline diagnostic regressions: real session, virtual time, FakeUART only."""
import json
import unittest
import test_agv_navigation_fix as fixtures


class DiagnosticRegression(unittest.TestCase):
    setUp = fixtures.SessionRegression.setUp
    d0 = fixtures.SessionRegression.d0
    ready = fixtures.SessionRegression.ready
    arm = fixtures.SessionRegression.arm

    def report(self):
        self.assertTrue(hasattr(self.s, 'diagnostics'), 'Session must expose bounded read-only diagnostic history')
        return self.s.diagnostics()

    def test_timeout_freezes_original_gap_and_transmitted_command(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time = self.now
        self.s.scan_clear = True
        self.assertTrue(self.s.drive('V 0.040 0.000', autonomous=True)[0])
        self.now += .30
        self.s.scan_time = self.now
        self.s.watchdog_tick()
        self.assertEqual(self.s.fault, 'TELEMETRY_TIMEOUT')
        report = self.report()
        fault = report['first_fault']
        self.assertEqual(fault['reason'], 'TELEMETRY_TIMEOUT')
        self.assertAlmostEqual(fault['d0_age_s'], .30)
        tx = [e for e in report['first_fault_events'] if e['kind'] == 'tx']
        self.assertEqual(tx[-1]['command'], 'V 0.040 0.000')
        self.assertTrue(tx[-1]['full_write'])
        self.now += .01
        self.s.ingest(self.d0())
        self.s.request_stop('LATER_FAILURE', wait=False)
        self.assertEqual(self.report()['first_fault'], fault)
        self.assertTrue(self.s.latched)

    def test_partial_stop_is_recorded_as_partial_and_not_confirmed(self):
        self.uart.partial = True
        self.assertFalse(self.s.request_stop(wait=False)[0])
        tx = [e for e in self.report()['events'] if e['kind'] == 'tx'][-1]
        self.assertEqual((tx['requested_bytes'], tx['written_bytes']), (5, 1))
        self.assertFalse(tx['full_write'])
        self.assertEqual(self.s.fault, 'STOP_WRITE_FAILED')
        self.now += .01
        self.s.ingest(self.d0())
        self.assertFalse(self.s.stop_confirmed)

    def test_rejected_drive_records_blocker_without_hardware_write(self):
        self.assertTrue(self.arm()[0])
        self.s.scan_time = self.now
        self.s.scan_clear = False
        before = list(self.uart.writes)
        self.assertFalse(self.s.drive('V 0.040 0.000', autonomous=True)[0])
        event = self.report()['events'][-1]
        self.assertEqual(event['kind'], 'drive')
        self.assertFalse(event['accepted'])
        self.assertIn('FORWARD_NOT_CLEAR', event['blockers'])
        self.assertEqual(before, self.uart.writes)

    def test_bounded_history_keeps_first_fault_after_idle_stream_overwrites_ring(self):
        self.ready()
        self.s.request_stop('DIAGNOSTIC_TEST', wait=False)
        original = self.report()['first_fault_events']
        for _ in range(1500):
            self.now += .1
            self.s.ingest(self.d0())
        report = self.report()
        self.assertLessEqual(len(report['events']), 256)
        self.assertEqual(report['first_fault_events'], original)
        self.assertGreater(report['events'][0]['sequence'], 1)
        json.dumps(report, allow_nan=False)

    def test_rx_gap_is_captured_before_last_timestamp_is_updated(self):
        self.ready()
        self.now += .38
        self.s.ingest(self.d0())
        event = self.report()['events'][-1]
        self.assertEqual(event['kind'], 'rx_d0')
        self.assertAlmostEqual(event['gap_s'], .38)
        self.assertEqual(self.s.last_d0, self.now)

    def test_diagnostic_reads_cannot_mutate_control_or_emit_commands(self):
        self.ready()
        self.s.request_stop('DIAGNOSTIC_TEST', wait=False)
        before = list(self.uart.writes)
        report = self.report()
        report['first_fault']['reason'] = 'MODIFIED'
        report['events'].clear()
        report['first_fault_events'].clear()
        self.assertEqual(self.report()['first_fault']['reason'], 'DIAGNOSTIC_TEST')
        self.assertTrue(self.report()['events'])
        self.assertEqual(before, self.uart.writes)

    def test_navigation_failure_explains_why_no_drive_was_transmitted(self):
        m = fixtures.load_brain()
        m.state = m.AGVSharedState()
        node = m.AGVROSNode.__new__(m.AGVROSNode)
        node.control = self.s
        node.initialize_navigation()
        self.assertFalse(node._follow((0.,0.,0.),(1.,1.)))
        events = self.report()['events']
        self.assertTrue(events,'No safe path must have a diagnostic reason')
        self.assertEqual(events[-1]['reason'],'NO_SAFE_PATH')
        self.assertEqual(self.uart.writes,[])


if __name__ == '__main__':
    unittest.main()
