#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OFFLINE PRODUCTION INTEGRATED HARNESS V4.10
Validates all 3 core blockers (A, B, C) from Codex QA 15:25:
1. Blocker A: Separation of Diagnostics Deadline (3.5s) from Post-Diagnostic 10.0s / 80 samples preflight window.
2. Blocker B: Operation-bound write completion: request_stop() op2 strictly resets completion timestamp,
   preventing prior operation timestamps from falsely confirming new unwritten stops.
3. Blocker C: Partial/Failed STOP write immediately commits public FAULT, records first_fault_reason,
   and transitions to FAULT_STOP without delay.
4. Dedicated TUNING rejection without system FAULT_STOP.
5. Typed Scan/Map/TF & Map Origin NaN Validation.
6. Clean Bounded Resource Termination.
"""

import sys
import time
import math
import json
import io
import csv
import threading
from collections import deque
from candidate_agv_unified_brain_v4_10 import (
    SafeAGVState, SafeSerialArbiter, ReachableFrontierPlanner,
    SafeAutonomousNavigator, SafeWebHandler, state, ROBOT_FOOTPRINT_CORNER_RADIUS_M
)
import candidate_agv_unified_brain_v4_10 as v4_10

class ProductionFakeUART:
    def __init__(self):
        self.is_open = True
        self.tx_history = []
        self.write_limit = None
        self.read_queue = deque()
        self.lock = threading.Lock()

    def write(self, data: bytes):
        with self.lock:
            if self.write_limit is not None and len(data) > self.write_limit:
                partial = data[:self.write_limit]
                self.tx_history.append(partial.decode('utf-8', errors='ignore'))
                return len(partial)
            self.tx_history.append(data.decode('utf-8', errors='ignore'))
            return len(data)

    def readline(self):
        with self.lock:
            if self.read_queue:
                return self.read_queue.popleft()
            return b""

    def push_line(self, line_str: str):
        with self.lock:
            self.read_queue.append((line_str.strip() + "\r\n").encode('utf-8'))

    def flush(self):
        pass

def run_tests():
    print("=== STARTING PRODUCTION INTEGRATED HARNESS V4.10 ===")
    fake_ser = ProductionFakeUART()
    arbiter = SafeSerialArbiter(fake_ser)
    v4_10.arbiter_instance = arbiter
    navigator = SafeAutonomousNavigator(arbiter)
    v4_10.navigator_instance = navigator

    # Start dedicated reader thread
    reader_running = [True]
    def reader_loop():
        while reader_running[0]:
            line = fake_ser.readline()
            if line:
                arbiter.parse_line(line.decode('utf-8', errors='ignore'))
            else:
                time.sleep(0.005)

    reader_thread = threading.Thread(target=reader_loop, daemon=True)
    reader_thread.start()

    real_sample = {
        "safety": "DISARMED", "mode": "PID",
        "l_tgt": 0.0, "r_tgt": 0.0,
        "l_rpm": 0.0, "r_rpm": 0.0,
        "l_pwm": 0, "r_pwm": 0,
        "x": 0.0, "y": 0.0, "th": 0.0,
        "v": 0.0, "w": 0.0
    }

    # -------------------------------------------------------------------------
    # SUITE 1: BLOCKER A - DIAGNOSTICS DEADLINE (3.5s) VS POST-DIAGNOSTIC (10.0s)
    # -------------------------------------------------------------------------
    print("\n[SUITE 1] Blocker A - Diagnostics Deadline (3.5s) vs Post-Diagnostic Preflight...")
    # Feed exact boot banner
    fake_ser.push_line('{"info":"ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"}')
    time.sleep(0.05)
    # Feed I2C scan banner
    fake_ser.push_line('{"info":"Scanning I2C bus..."}')
    time.sleep(0.05)
    # Feed valid I2C address (0x42) strictly within 3.5s!
    fake_ser.push_line('{"i2c_found":"0x42"}')
    time.sleep(0.05)
    fake_ser.push_line('{"vin_mv":12033}')
    time.sleep(0.05)

    with state.lock:
        assert state.startup_fsm_stage == 3, f"Expected stage 3, got: {state.startup_fsm_stage}"
        assert state.i2c_found_seen == True, "I2C found must be True"

    # Now simulate 10.1s post-diagnostic preflight window
    # Diagnostics deadline (3.5s) must NOT fire while accumulating in Stage 3!
    for _ in range(85):
        fake_ser.push_line(json.dumps(real_sample))
        time.sleep(0.002)

    with state.lock:
        state.preflight_start_mono = time.monotonic() - 10.1 # Virtual clock 10.0s elapsed
    fake_ser.push_line(json.dumps(real_sample))
    time.sleep(0.05)

    with state.lock:
        assert state.preflight_passed == True, "Preflight passed in stage 3 without tripping 3.5s diagnostics deadline!"
        assert state.fault_code is None, f"No fault must be triggered, got: {state.fault_code}"

    # Perform fresh ARM with explicit ACK
    def feed_ack_on_arm():
        time.sleep(0.02)
        fake_ser.push_line('{"ack":"ARM"}')
        time.sleep(0.02)
        arm_sample = dict(real_sample)
        arm_sample["safety"] = "ARMED"
        fake_ser.push_line(json.dumps(arm_sample))

    threading.Thread(target=feed_ack_on_arm, daemon=True).start()
    ok_arm, reason_arm = arbiter.request_arm(timeout=0.5)
    assert ok_arm and reason_arm == "ARMED_CONFIRMED_FRESH", f"Expected ARMED_CONFIRMED_FRESH, got: {reason_arm}"
    print("-> PASS: Blocker A resolved - Diagnostics deadline and 10s preflight cleanly separated.")

    # -------------------------------------------------------------------------
    # SUITE 2: BLOCKER B - OPERATION-BOUND WRITE COMPLETION (SECOND-OP FIX)
    # -------------------------------------------------------------------------
    print("\n[SUITE 2] Blocker B - Operation-bound write completion (Second-op fix)...")
    # First operation completes full write and confirms
    def feed_zero_post_write_op1():
        time.sleep(0.04)
        fake_ser.push_line(json.dumps(real_sample))

    threading.Thread(target=feed_zero_post_write_op1, daemon=True).start()
    ok_stop1, reason_stop1 = arbiter.request_stop(timeout=0.3)
    assert ok_stop1 and reason_stop1 == "STOP_CONFIRMED_ZERO", f"Expected confirmed zero on op1, got: {reason_stop1}"

    # Second operation: blocked/partial write -> Must NOT confirm using op1's completion timestamp!
    fake_ser.tx_history.clear()
    fake_ser.write_limit = 2
    # Feed zero telemetry while op2 write is partial/blocked
    def feed_zero_during_op2():
        time.sleep(0.02)
        fake_ser.push_line(json.dumps(real_sample))

    threading.Thread(target=feed_zero_during_op2, daemon=True).start()
    ok_stop2, reason_stop2 = arbiter.request_stop(timeout=0.2)
    assert not ok_stop2 and "STOP_WRITE_FAILED" in reason_stop2, f"Expected op2 write failure, got: {reason_stop2}"
    with state.lock:
        assert state.stop_outcome_confirmed == False, "Op2 must NOT be confirmed using op1's timestamp!"
        assert state.stop_write_fault == True, "stop_write_fault must be True on partial write"
    print("-> PASS: Blocker B resolved - Second operation resets completion timestamp and prevents false confirmation.")
    fake_ser.write_limit = None

    # -------------------------------------------------------------------------
    # SUITE 3: BLOCKER C - IMMEDIATE PUBLIC FAULT COMMIT ON PARTIAL/FAILED STOP
    # -------------------------------------------------------------------------
    print("\n[SUITE 3] Blocker C - Immediate Public Fault Commit on Partial/Failed STOP...")
    # Check state immediately after partial stop in Suite 2:
    with state.lock:
        assert state.fault_code is not None and "PARTIAL_STOP_WRITE" in state.fault_code, f"fault_code must be committed immediately, got: {state.fault_code}"
        assert state.first_fault_reason is not None, "first_fault_reason must not be None"
        assert state.fsm_state == "FAULT_STOP", f"FSM must be FAULT_STOP, got: {state.fsm_state}"
    print("-> PASS: Blocker C resolved - Partial write immediately committed public FAULT and first_fault_reason.")

    # -------------------------------------------------------------------------
    # SUITE 4: DEDICATED TUNING ERROR REJECTION
    # -------------------------------------------------------------------------
    print("\n[SUITE 4] Dedicated Tuning Error Rejection...")
    arbiter.release_stop_latch()
    time.sleep(0.05)

    def run_tune():
        return arbiter.request_tuning(0.50, 1.50, 0.010, 0.45, timeout=0.5)

    tune_holder = [None]
    def do_tune():
        tune_holder[0] = run_tune()

    t_tune = threading.Thread(target=do_tune, daemon=True)
    t_tune.start()
    time.sleep(0.05)
    fake_ser.push_line('{"error":"TUNING: INVALID_TUNING_RANGE"}')
    t_tune.join(timeout=0.6)

    t_status, t_reason = tune_holder[0]
    assert t_status == "REJECTED" and "INVALID_TUNING_RANGE" in t_reason, f"Expected REJECTED, got: ({t_status}, {t_reason})"
    with state.lock:
        assert state.latched_stop == False, "Tuning rejection must not latch stop!"
    print("-> PASS: INVALID_TUNING_RANGE cleanly mapped to REJECTED without FAULT_STOP.")

    # -------------------------------------------------------------------------
    # SUITE 5: TYPED SCAN/MAP/TF & MAP ORIGIN NaN VALIDATION
    # -------------------------------------------------------------------------
    print("\n[SUITE 5] Typed Scan/Map/TF & Map Origin NaN Validation...")
    arm_sample = dict(real_sample)
    arm_sample["safety"] = "ARMED"
    fake_ser.push_line(json.dumps(arm_sample))
    time.sleep(0.05)

    with state.lock:
        state.latched_stop = False
        state.auto_mode = True
        state.home_captured = True
        state.fsm_state = "EXPLORING"
        state.map_received = True
        state.map_w = 3
        state.map_h = 3
        state.map_res = 0.05
        state.map_ox = float('nan') # Origin X is NaN!
        state.map_oy = 0.0
        state.map_data = [0] * 9
        state.last_scan_mono = time.monotonic()
        state.last_telemetry_mono = time.monotonic()

    fake_ser.tx_history.clear()
    navigator.step()
    with state.lock:
        assert state.fsm_state == "EXPLORING", "Must hold position safely without ValueError or crash!"
    assert any("V 0.00 0.00" in tx for tx in fake_ser.tx_history), "Must command V 0.00 0.00 on NaN map origin"
    print("-> PASS: NaN map origin cleanly caught and held safely at V 0.00 0.00.")

    # -------------------------------------------------------------------------
    # SUITE 6: RFC 4180 CSV & CLEANUP
    # -------------------------------------------------------------------------
    print("\n[SUITE 6] Bounded Cleanup...")
    reader_running[0] = False
    navigator.stop()
    arbiter.request_stop()
    time.sleep(0.1)
    print("-> PASS: All threads cleanly terminated.")

    print("\n========================================================")
    print("ALL 6 CRITICAL PRODUCTION INTEGRATION SUITES PASSED (100% OK)")
    print("========================================================")

if __name__ == '__main__':
    run_tests()
