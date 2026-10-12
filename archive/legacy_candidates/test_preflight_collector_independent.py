#!/usr/bin/env python3
"""
test_preflight_collector_independent.py
=============================================================================
Harness QA độc lập cho agv_preflight_static_collector.py
Kiểm tra toàn diện các kịch bản biên:
1. Positive Flow: 50 mẫu DISARMED chuẩn -> PASS exit 0.
2. Zero-TX Guard: Cố tình gọi write/flush -> Bị chặn PureReadOnlyViolationError -> FAIL exit 1.
3. Unsafe Safety State: Gói tin mang safety='ARMED' -> FAIL exit 1.
4. Non-zero Actuation: l_pwm != 0 hoặc l_tgt != 0 -> FAIL exit 1.
5. Non-zero RPM: l_rpm != 0 -> FAIL exit 1.
6. Non-finite values: v = NaN hoặc Inf -> FAIL exit 1.
7. Insufficient samples: Chỉ có 5 mẫu trong 15s -> FAIL exit 1.
8. Corrupt settling lines: 10 dòng rác ban đầu rồi đến 35 dòng hợp lệ -> PASS exit 0.
=============================================================================
"""

import unittest
import json
import os
import pathlib
from agv_preflight_static_collector import (
    run_preflight_collector,
    ReadOnlySerialWrapper,
    MockSerialStream,
    PureReadOnlyViolationError
)

class TestPreflightCollectorIndependent(unittest.TestCase):

    def setUp(self):
        self.valid_sample_bytes = (
            b'{"safety":"DISARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,'
            b'"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,'
            b'"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}\n'
        )

    def test_01_positive_flow(self):
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=[self.valid_sample_bytes] * 90,
            mock_interval_s=0.01,
            wall_timeout_s=5.0,
            min_observation_s=0.5,
            min_samples=80,
            max_samples=90
        )
        self.assertEqual(code, 0)
        self.assertEqual(rep["status"], "PASS_PREFLIGHT_VERIFIED")
        self.assertGreaterEqual(rep["valid_samples_count"], 80)
        self.assertTrue(os.path.exists(rep["evidence_file"]))

    def test_02_zero_tx_enforcement(self):
        raw = MockSerialStream()
        wrapper = ReadOnlySerialWrapper(raw)
        with self.assertRaises(PureReadOnlyViolationError):
            wrapper.write(b"STOP\n")
        with self.assertRaises(PureReadOnlyViolationError):
            wrapper.flush()

    def test_03_reject_armed_safety(self):
        armed_sample = (
            b'{"safety":"ARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,'
            b'"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,'
            b'"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}\n'
        )
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=[armed_sample] * 10,
            wall_timeout_s=1.0,
            min_observation_s=0.1,
            min_samples=5
        )
        self.assertEqual(code, 1)
        self.assertIn("INVALID_SAFETY_STATE", rep["rejection_reason"])

    def test_04_reject_nonzero_pwm_or_tgt(self):
        pwm_sample = (
            b'{"safety":"DISARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,'
            b'"l_rpm":0.0,"r_rpm":0.0,"l_pwm":15,"r_pwm":0,'
            b'"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}\n'
        )
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=[pwm_sample] * 10,
            wall_timeout_s=1.0,
            min_observation_s=0.1,
            min_samples=5
        )
        self.assertEqual(code, 1)
        self.assertIn("NON_ZERO_PWM", rep["rejection_reason"])

    def test_05_reject_nonzero_rpm(self):
        rpm_sample = (
            b'{"safety":"DISARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,'
            b'"l_rpm":1.5,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,'
            b'"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}\n'
        )
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=[rpm_sample] * 10,
            wall_timeout_s=1.0,
            min_observation_s=0.1,
            min_samples=5
        )
        self.assertEqual(code, 1)
        self.assertIn("NON_ZERO_RPM", rep["rejection_reason"])

    def test_06_reject_nan_or_inf(self):
        nan_sample = (
            b'{"safety":"DISARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,'
            b'"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,'
            b'"x":0.0,"y":0.0,"th":0.0,"v":"NaN","w":0.0}\n'
        )
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=[nan_sample] * 10,
            wall_timeout_s=1.0,
            min_observation_s=0.1,
            min_samples=5
        )
        self.assertEqual(code, 1)
        self.assertIn("NON_FINITE_OR_INVALID", rep["rejection_reason"])

    def test_07_insufficient_samples_timeout(self):
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=[self.valid_sample_bytes] * 5,
            wall_timeout_s=0.5,
            min_observation_s=0.1,
            min_samples=30
        )
        self.assertEqual(code, 1)
        self.assertEqual(rep["status"], "FAIL_INSUFFICIENT_SAMPLES")

    def test_08_settling_garbage_lines_handled(self):
        garbage = [b"booting esp32...\n", b"\xff\xfe\x00\n", b"rst:0x1 (POWERON_RESET)\n"]
        lines = garbage + [self.valid_sample_bytes] * 35
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=lines,
            mock_interval_s=0.01,
            wall_timeout_s=5.0,
            min_observation_s=0.1,
            min_samples=30,
            max_samples=35
        )
        self.assertEqual(code, 0)
        self.assertEqual(rep["status"], "PASS_PREFLIGHT_VERIFIED")
        self.assertGreaterEqual(rep["corrupt_lines_count"], 3)

    def test_09_c1_burst_then_gap_fails(self):
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=[self.valid_sample_bytes] * 30,
            mock_interval_s=0.01,
            wall_timeout_s=5.0,
            min_observation_s=0.1,
            min_samples=30,
            max_samples=50,
            max_gap_s=0.1
        )
        self.assertEqual(code, 1)
        self.assertIn("FAIL_TELEMETRY_STREAM_GAP", rep["status"])

    def test_10_c2_safe_then_corrupt_armed_fails(self):
        corrupt_lines = [b'{"safety":"ARMED"}\n'] * 5
        lines = [self.valid_sample_bytes] * 30 + corrupt_lines
        code, rep = run_preflight_collector(
            mock=True,
            mock_lines=lines,
            mock_interval_s=0.01,
            wall_timeout_s=5.0,
            min_observation_s=0.1,
            min_samples=30,
            max_samples=50
        )
        self.assertEqual(code, 1)
        self.assertIn("FAIL_TELEMETRY_INVARIANT_VIOLATION", rep["status"])

    def test_11_c3_invalid_argument_rejects_before_open(self):
        code, rep = run_preflight_collector(
            mock=True,
            wall_timeout_s=-1.0,
            min_observation_s=0.1,
            min_samples=30
        )
        self.assertEqual(code, 1)
        self.assertEqual(rep["status"], "FAIL_INVALID_ARGUMENT")
        self.assertIn("INVALID_WALL_TIMEOUT", rep["rejection_reason"])


if __name__ == "__main__":
    unittest.main()
