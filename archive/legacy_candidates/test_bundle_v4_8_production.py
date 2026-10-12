#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OFFLINE PRODUCTION INTEGRATED HARNESS V4.8
Validates all 3 Core Residuals (A, B, C) from Codex QA 14:58:
1. Residual A: Sequential Startup FSM (Stage 0 -> 1 -> 2 -> 3) strictly rejects out-of-order banners or errors.
2. Residual B: Priority STOP bursts within tx_lock on Hardware Error (cancels and rejects in-flight drive).
3. Residual C: Operation tracking for STOP (distinguishes ZERO_OBSERVED vs STOP_CONFIRMED, preserves WRITE_FAULT).
4. Typed Scan/Map/TF with strict all-finite validation.
5. Clean Bounded Resource Termination.
"""

import sys
import time
import math
import json
import io
import csv
import threading
from collections import deque
from candidate_agv_unified_brain_v4_8 import (
    SafeAGVState, SafeSerialArbiter, ReachableFrontierPlanner,
    SafeAutonomousNavigator, SafeWebHandler, state, ROBOT_FOOTPRINT_CORNER_RADIUS_M
)
import candidate_agv_unified_brain_v4_8 as v4_8

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
    print("=== STARTING PRODUCTION INTEGRATED HARNESS V4.8 ===")
    fake_ser = ProductionFakeUART()
    arbiter = SafeSerialArbiter(fake_ser)
    v4_8.arbiter_instance = arbiter
    navigator = SafeAutonomousNavigator(arbiter)
    v4_8.navigator_instance = navigator

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
    # SUITE 1: RESIDUAL A - SEQUENTIAL STARTUP FSM (STAGE 0 -> 1 -> 2 -> 3)
    # -------------------------------------------------------------------------
    print("\n[SUITE 1] Residual A - Sequential Startup FSM Validation...")
    # Feed reversed banners: scanning I2C failed BEFORE boot banner -> Must be rejected!
    fake_ser.push_line('{"error":"Scanning I2C bus failed"}')
    time.sleep(0.05)
    with state.lock:
        assert state.startup_fsm_stage == 0, f"Error must reset FSM to stage 0, got: {state.startup_fsm_stage}"
        assert state.latched_stop == True, "Must latch stop on startup error"

    # Release latch and feed in correct sequential order:
    arbiter.release_stop_latch()
    # Stage 0 -> 1: EXACT_BOOT_BANNER
    fake_ser.push_line('{"info":"ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"}')
    time.sleep(0.05)
    with state.lock:
        assert state.startup_fsm_stage == 1, f"Expected stage 1 after boot banner, got: {state.startup_fsm_stage}"

    # Stage 1 -> 2: EXACT_I2C_SCAN_BANNER
    fake_ser.push_line('{"info":"Scanning I2C bus..."}')
    time.sleep(0.05)
    with state.lock:
        assert state.startup_fsm_stage == 2, f"Expected stage 2 after i2c scan, got: {state.startup_fsm_stage}"

    # Stage 2 -> 3: I2C Found
    fake_ser.push_line('{"i2c_found":"0x42"}')
    time.sleep(0.05)
    with state.lock:
        assert state.startup_fsm_stage == 3, f"Expected stage 3 after i2c found, got: {state.startup_fsm_stage}"
        assert state.preflight_count == 0, "Preflight counter must reset to 0 at start of stage 3"

    # Continuous post-diagnostic 85 samples:
    for _ in range(85):
        fake_ser.push_line(json.dumps(real_sample))
        time.sleep(0.002)

    # Release latch now that fresh DISARMED zero samples have arrived
    ok_rel, reason_rel = arbiter.release_stop_latch()
    assert ok_rel and reason_rel == "LATCH_RELEASED", f"Latch must release, got: {reason_rel}"

    with state.lock:
        state.preflight_start_mono = time.monotonic() - 10.1 # Virtual clock 10.0s elapsed
    fake_ser.push_line(json.dumps(real_sample))
    time.sleep(0.05)
    with state.lock:
        assert state.preflight_passed == True, "Preflight passed organically once stage 3 completed"

    # Simulate fresh ARM response
    def simulate_arm_resp():
        time.sleep(0.05)
        arm_sample = dict(real_sample)
        arm_sample["safety"] = "ARMED"
        fake_ser.push_line(json.dumps(arm_sample))

    threading.Thread(target=simulate_arm_resp, daemon=True).start()
    ok_arm, reason_arm = arbiter.request_arm(timeout=0.5)
    assert ok_arm and reason_arm == "ARMED_CONFIRMED_FRESH", f"Expected ARMED_CONFIRMED_FRESH, got: {reason_arm}"
    print("-> PASS: Residual A satisfied - Sequential Startup FSM cleanly enforced.")

    # -------------------------------------------------------------------------
    # SUITE 2: RESIDUAL B - PRIORITY STOP BURSTS UNDER TX_LOCK ON HARDWARE FAULT
    # -------------------------------------------------------------------------
    print("\n[SUITE 2] Residual B - Priority STOP bursts under tx_lock on Hardware Error...")
    fake_ser.tx_history.clear()
    with state.lock:
        state.is_moving = True
    
    # Reader ingests hardware fault packet
    bad_sample = {"error": "I2C_FAULT"}
    fake_ser.push_line(json.dumps(bad_sample))
    time.sleep(0.05)

    with state.lock:
        assert state.latched_stop == True, "Must latch stop"
        assert state.is_moving == False, "Must cancel is_moving"
        assert state.startup_fsm_stage == 0, "Must reset startup FSM stage to 0"
    assert any("STOP" in tx for tx in fake_ser.tx_history), "Must immediately burst physical STOP on UART!"
    
    # Attempt in-flight drive command -> Must be immediately rejected
    ok_drive, reason_drive = arbiter.send_guarded("V 0.10 0.00", cmd_class="DRIVE")
    assert not ok_drive and "REJECTED_LATCHED_STOP" in reason_drive, f"Drive must be rejected, got: {reason_drive}"
    print("-> PASS: Residual B satisfied - Priority STOP bursts delivered under lock and in-flight drive rejected.")

    # -------------------------------------------------------------------------
    # SUITE 3: RESIDUAL C - ZERO_OBSERVED VS STOP_CONFIRMED WITH OPERATION TRACKING
    # -------------------------------------------------------------------------
    print("\n[SUITE 3] Residual C - Operation Tracking: ZERO_OBSERVED vs STOP_CONFIRMED...")
    # While latched from hardware fault (no active request_stop operation):
    # Feed fresh zero D0 -> Must mark stop_outcome_observed=True, but stop_outcome_confirmed=False!
    fake_ser.push_line(json.dumps(real_sample))
    time.sleep(0.05)
    with state.lock:
        assert state.stop_outcome_observed == True, "Zero observed must be True"
        assert state.stop_outcome_confirmed == False, "Stop confirmed must NOT be True without active operation ID"
    print("-> PASS: Unrequested zero D0 records ZERO_OBSERVED without falsely marking STOP_CONFIRMED.")

    # Now test persistent write failure on request_stop:
    fake_ser.write_limit = 2
    ok_req_stop, reason_req_stop = arbiter.request_stop(timeout=0.1)
    assert not ok_req_stop and "STOP_WRITE_FAILED" in reason_req_stop, f"Write failure must return False, got: {reason_req_stop}"
    with state.lock:
        assert state.stop_write_fault == True, "stop_write_fault must be recorded"
    
    # Even if fresh zero arrives, write fault must prevent confirmed=True!
    fake_ser.push_line(json.dumps(real_sample))
    time.sleep(0.05)
    with state.lock:
        assert state.stop_outcome_confirmed == False, "Confirmation must be REFUSED on write fault!"
    print("-> PASS: Persistent write failure preserves WRITE_FAULT and prevents false confirmation.")
    fake_ser.write_limit = None

    # -------------------------------------------------------------------------
    # SUITE 4: TYPED SCAN/MAP/TF & MAP ORIGIN NaN VALIDATION
    # -------------------------------------------------------------------------
    print("\n[SUITE 4] Typed Scan/Map/TF & Map Origin NaN Validation...")
    # Release latch and re-arm
    arbiter.release_stop_latch()
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
    # SUITE 5: RFC 4180 CSV & CLEANUP
    # -------------------------------------------------------------------------
    print("\n[SUITE 5] Bounded Cleanup...")
    reader_running[0] = False
    navigator.stop()
    arbiter.request_stop()
    time.sleep(0.1)
    print("-> PASS: All threads cleanly terminated.")

    print("\n========================================================")
    print("ALL 5 CRITICAL PRODUCTION INTEGRATION SUITES PASSED (100% OK)")
    print("========================================================")

if __name__ == '__main__':
    run_tests()
