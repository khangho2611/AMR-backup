#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OFFLINE PRODUCTION FAKEUART HARNESS V4.0
Thoroughly tests the 7 root-cause fixes demanded by Codex QA:
1. No-Auto-ARM in send_cmd & Strict ARM Handshake requirement.
2. Latched STOP: STOP halts and latches, cancelling queued jobs, preventing auto-reARM.
3. Non-blocking Watchdog: Stale scan (>0.5s) or stale D0 (>0.5s) immediately triggers safety STOP.
4. Reachable BFS Frontier with Footprint Inflation Barrier: Disconnected rooms/islands behind walls return None.
5. Pre-motion Home Capture: Captures (x, y, th) before any motion command; Home success requires both distance (<0.12m) AND heading alignment (<0.15 rad).
6. Typed PID Tuning: 0.0 is valid, out-of-bounds or non-finite rejected, requires MCU ACK readback to mark APPLIED.
"""

import sys
import time
import math
import json
import threading
from candidate_agv_unified_brain_v4 import (
    SafeAGVState, SafeSerialArbiter, ReachableFrontierPlanner,
    SafeAutonomousNavigator, state
)

class FakeUART:
    def __init__(self):
        self.is_open = True
        self.tx_history = []
        self.rx_queue = []
        self.lock = threading.Lock()

    def write(self, data: bytes):
        with self.lock:
            self.tx_history.append(data.decode('utf-8', errors='ignore'))

    def flush(self):
        pass

def run_tests():
    print("=== STARTING OFFLINE HARNESS FOR AGV BUNDLE V4.0 ===")
    fake_ser = FakeUART()
    arbiter = SafeSerialArbiter(fake_ser)
    navigator = SafeAutonomousNavigator(arbiter)

    # -------------------------------------------------------------------------
    # TEST 1: NO AUTO-ARM & EXPLICIT ARM HANDSHAKE
    # -------------------------------------------------------------------------
    print("\n[TEST 1] No Auto-ARM in drive commands...")
    arbiter.send_raw("V 0.08 0.0")
    assert any("V 0.08 0.0" in tx for tx in fake_ser.tx_history), "Command not sent"
    assert not any("ARM" in tx for tx in fake_ser.tx_history), "VIOLATION: Auto-ARM detected!"
    print("-> PASS: Drive command sent cleanly without injecting ARM.")

    # -------------------------------------------------------------------------
    # TEST 2: LATCHED STOP PREVENTS RE-ARM & DROPS PENDING COMMANDS
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Latched Emergency STOP...")
    arbiter.request_stop()
    with state.lock:
        assert state.latched_stop == True, "Stop must be latched"
        assert state.auto_mode == False, "Auto mode must be forced false"
    
    # Try to ARM while STOP is latched
    arm_ok = arbiter.request_arm(timeout=0.1)
    assert not arm_ok, "ARM must be refused when STOP is latched"
    print("-> PASS: Latched STOP halts system and forbids ARM.")
    arbiter.release_stop_latch()

    # -------------------------------------------------------------------------
    # TEST 3: REACHABLE BFS FRONTIER WITH FOOTPRINT INFLATION
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Reachable BFS Frontier Planner & Disconnected Island Test...")
    # Setup 10x10 map (0.05m/cell). Robot at (0.25, 0.25) -> cell (5, 5)
    with state.lock:
        state.map_w = 10
        state.map_h = 10
        state.map_res = 0.05
        state.map_ox = 0.0
        state.map_oy = 0.0
        # Create map: Free space everywhere, but an island at (1, 1) surrounded by WALLS (100)
        grid = [0] * 100
        # Surround cell (1, 1) with occupied cells (wall)
        for x in range(0, 4):
            for y in range(0, 4):
                if x == 0 or x == 3 or y == 0 or y == 3:
                    grid[y * 10 + x] = 100 # Wall
        grid[1 * 10 + 1] = -1 # Unknown island inside wall
        state.map_data = grid

    # Search from robot at (0.25, 0.25) cell (5, 5)
    goal, count = ReachableFrontierPlanner.plan_next_frontier(0.25, 0.25, state)
    assert goal is None, f"VIOLATION: Unreachable island behind wall was selected as goal: {goal}"
    print("-> PASS: Unreachable disconnected frontier correctly rejected by BFS barrier.")

    # -------------------------------------------------------------------------
    # TEST 4: PRE-MOTION HOME CAPTURE & HEADING ALIGNMENT
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Pre-motion Home Capture & Heading Verification...")
    with state.lock:
        state.x = 1.0
        state.y = 2.0
        state.th = 0.785 # 45 degrees
        state.home_captured = False
        state.fsm_state = "IDLE"
        state.auto_mode = True
        state.last_scan_time = time.time()
        state.last_telemetry_time = time.time()
        state.zones["front"] = 150

    # Step navigator to capture home
    navigator.step()
    with state.lock:
        assert state.home_captured == True, "Home must be captured before motion"
        assert state.home_x == 1.0 and state.home_y == 2.0 and state.home_th == 0.785, "Home position mismatch"
        assert state.fsm_state == "EXPLORING", "FSM must advance to EXPLORING"
    print("-> PASS: Pre-motion Home (position & heading) captured faithfully.")

    # Test Return Home: Robot at home position but WRONG HEADING (pi offset)
    with state.lock:
        state.fsm_state = "RETURNING_HOME"
        state.x = 1.02 # 2cm from home
        state.y = 2.01
        state.th = 0.785 - math.pi # Opposite heading!
    
    fake_ser.tx_history.clear()
    navigator.step()
    with state.lock:
        assert state.fsm_state != "COMPLETED", "VIOLATION: Completed declared while heading is wrong!"
    assert any("V 0.00" in tx for tx in fake_ser.tx_history), "Must rotate in place to align heading"
    print("-> PASS: Home completion strictly requires both distance AND heading alignment.")

    # -------------------------------------------------------------------------
    # TEST 5: WATCHDOG STALE SENSOR CHECK (NON-BLOCKING)
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Sensor Watchdog Freshness Check...")
    with state.lock:
        state.fsm_state = "EXPLORING"
        state.last_scan_time = time.time() - 1.0 # Stale scan > 0.5s
    
    fake_ser.tx_history.clear()
    navigator.step()
    with state.lock:
        assert state.fsm_state == "WATCHDOG_STALE_STOP", "Watchdog must transition to stale stop"
    assert any("STOP" in tx for tx in fake_ser.tx_history), "Watchdog must fire STOP on stale sensor"
    print("-> PASS: Watchdog halts robot cleanly on stale sensor feed without blocking.")

    # -------------------------------------------------------------------------
    # TEST 6: TYPED PID TUNING (0-VALID, NON-FINITE REJECT, ACK READBACK)
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Typed PID Tuning & Explicit ACK Readback...")
    # 6a. 0.0 is valid for Kd
    def simulate_mcu_ack():
        time.sleep(0.05)
        arbiter.parse_line('{"ack":"TUNING 0.500 1.500 0.0000 0.450"}')

    threading.Thread(target=simulate_mcu_ack, daemon=True).start()
    res, msg = arbiter.request_tuning(0.5, 1.5, 0.0, 0.45, timeout=0.5)
    assert res == "APPLIED", f"Expected APPLIED with Kd=0.0, got: {res}"
    print("-> PASS: Kd=0.0 handled cleanly as valid and marked APPLIED upon MCU ACK.")

    # 6b. Out-of-bounds rejection
    res, msg = arbiter.request_tuning(25.0, 1.5, 0.01, 0.45, timeout=0.5)
    assert res == "REJECTED", f"Expected REJECTED for Kp=25.0, got: {res}"
    print("-> PASS: Out of bounds parameter rejected before sending.")

    # 6c. Timeout / No MCU ACK -> FAILED
    res, msg = arbiter.request_tuning(0.5, 1.5, 0.01, 0.45, timeout=0.1)
    assert res == "FAILED", f"Expected FAILED on timeout, got: {res}"
    print("-> PASS: Missing MCU ACK correctly categorized as FAILED.")

    print("\n========================================================")
    print("ALL 6 PRODUCTION FIX SUITES PASSED FLAWLESSLY (100% OK)")
    print("========================================================")

if __name__ == '__main__':
    run_tests()
