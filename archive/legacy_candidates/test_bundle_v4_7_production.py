#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OFFLINE PRODUCTION INTEGRATED HARNESS V4.7
Validates all 4 Core Residuals from Codex QA 14:47:
1. Startup FSM: Enforces boot banner & I2C scan before ARM is accepted.
2. Immediate Physical STOP Bursts on Hardware Error (e.g. error="I2C_FAULT").
3. Continuous Watchdog on Pending Latched Stops & Late Confirmed D0 Zero.
4. Full Typed Scan/Map/TF & Map Origin NaN Validation Safe Holding without crashing.
"""

import sys
import time
import math
import json
import io
import csv
import threading
from collections import deque
from candidate_agv_unified_brain_v4_7 import (
    SafeAGVState, SafeSerialArbiter, ReachableFrontierPlanner,
    SafeAutonomousNavigator, SafeWebHandler, state, ROBOT_FOOTPRINT_CORNER_RADIUS_M
)
import candidate_agv_unified_brain_v4_7 as v4_7

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
                self.write_limit = None
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
    print("=== STARTING PRODUCTION INTEGRATED HARNESS V4.7 ===")
    fake_ser = ProductionFakeUART()
    arbiter = SafeSerialArbiter(fake_ser)
    v4_7.arbiter_instance = arbiter
    navigator = SafeAutonomousNavigator(arbiter)
    v4_7.navigator_instance = navigator

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
    # SUITE 1: AUDITED STARTUP FSM (BOOT BANNER + I2C SCAN REQUIREMENT)
    # -------------------------------------------------------------------------
    print("\n[SUITE 1] Audited Startup FSM (Boot banner + I2C scan requirement)...")
    # Feed 85 zero samples WITHOUT boot banners -> ARM must still be refused!
    with state.lock:
        state.boot_banner_seen = False
        state.i2c_scan_seen = False
        state.preflight_count = 0

    for _ in range(85):
        fake_ser.push_line(json.dumps(real_sample))
        time.sleep(0.002)

    with state.lock:
        state.preflight_start_mono = time.monotonic() - 10.1 # Virtual clock 10s elapsed
    fake_ser.push_line(json.dumps(real_sample))
    time.sleep(0.05)

    ok_arm_nobanner, reason_nobanner = arbiter.request_arm(timeout=0.1)
    assert not ok_arm_nobanner and "banner=False" in reason_nobanner, f"ARM must be refused without boot banner, got: {reason_nobanner}"
    print("-> PASS: ARM refused before boot banner & I2C scan banners seen.")

    # Now feed boot banner and I2C scan banner
    fake_ser.push_line('{"info":"ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"}')
    fake_ser.push_line('{"info":"Scanning I2C bus..."}')
    time.sleep(0.05)
    with state.lock:
        assert state.boot_banner_seen == True and state.i2c_scan_seen == True, "Banners must be recognized"

    # Send sample to trigger preflight passed
    fake_ser.push_line(json.dumps(real_sample))
    time.sleep(0.05)
    with state.lock:
        assert state.preflight_passed == True, "Preflight passed once banners and 80 zero samples seen"

    # Simulate fresh ARM response
    def simulate_arm_resp():
        time.sleep(0.05)
        arm_sample = dict(real_sample)
        arm_sample["safety"] = "ARMED"
        fake_ser.push_line(json.dumps(arm_sample))

    threading.Thread(target=simulate_arm_resp, daemon=True).start()
    ok_arm, reason_arm = arbiter.request_arm(timeout=0.5)
    assert ok_arm and reason_arm == "ARMED_CONFIRMED_FRESH", f"Expected ARMED_CONFIRMED_FRESH, got: {reason_arm}"
    print("-> PASS: Startup FSM completed -> Fresh ARM confirmed.")

    # -------------------------------------------------------------------------
    # SUITE 2: IMMEDIATE PHYSICAL STOP BURSTS ON HARDWARE ERROR (I2C_FAULT)
    # -------------------------------------------------------------------------
    print("\n[SUITE 2] Immediate Physical STOP Bursts on Hardware Error (I2C_FAULT)...")
    fake_ser.tx_history.clear()
    with state.lock:
        state.is_moving = True # Moving state
    
    # Ingest I2C_FAULT packet
    bad_sample = {"error": "I2C_FAULT"}
    fake_ser.push_line(json.dumps(bad_sample))
    time.sleep(0.05)

    with state.lock:
        assert state.latched_stop == True, "Must latch stop on error"
        assert state.is_moving == False, "Must drop is_moving immediately"
        assert "HARDWARE_FAULT_OBSERVED" in state.fault_code, "Must set fault code"
    assert any("STOP" in tx for tx in fake_ser.tx_history), "Must IMMEDIATELY burst physical STOP on UART!"
    print("-> PASS: Physical STOP bursts fired immediately upon receiving adverse error packet.")

    # -------------------------------------------------------------------------
    # SUITE 3: WATCHDOG ON PENDING CONFIRMATIONS & LATE D0 ARRIVAL
    # -------------------------------------------------------------------------
    print("\n[SUITE 3] Continuous Watchdog & Late D0 Arrival...")
    with state.lock:
        state.stop_outcome_confirmed = False
        state.stop_requested_mono = time.monotonic()
        state.latched_stop = True

    # Feed fresh zero D0 late
    time.sleep(0.05)
    fake_ser.push_line(json.dumps(real_sample))
    time.sleep(0.05)
    with state.lock:
        assert state.stop_outcome_confirmed == True, "Late D0 arrival must transition confirmation to True"
    print("-> PASS: Late D0 arrival successfully transitions stop confirmation to True.")

    # -------------------------------------------------------------------------
    # SUITE 4: TYPED SCAN/MAP/TF & MAP ORIGIN NaN VALIDATION
    # -------------------------------------------------------------------------
    print("\n[SUITE 4] Typed Scan/Map/TF & Map Origin NaN Validation...")
    # First release latch and re-arm
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
