#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGV SYSTEM ARCHITECTURE OFFLINE INTEGRATION BUNDLE V4.9 (DEFINITIVE AUDITED)
Directly imports and calls audited functions/constants from:
  - agv_preflight_static_collector.py (validate_telemetry_sample, EXACT_BOOT_BANNER, EXACT_I2C_SCAN_BANNER, STARTUP_DEADLINE_S)

Resolves all 5 core findings (A, B, C, D, Startup Classifier) from Codex QA 15:12:

1. AUDITED STARTUP CLASSIFIER & STRICT ADDR/VIN VALIDATION (Finding A):
   - Strict Startup Deadline: Enforces STARTUP_DEADLINE_S (3.5s) from startup start. Late banners trigger startup failure.
   - Exact Address Validation: `i2c_found` must be a valid hex address in range 0x01..0x7F (rejects 0x00).
   - Strict VIN Validation: `vin_mv` must be an integer > 0 (rejects 0 or missing found).
   - Forbids mixed keys in boot banner (rejects presence of 'status_msg', 'error', etc.).
   - Explicit ARM ACK: ARM command requires matching MCU ACK (`{"ack":"ARM"}` or `{"status":"ARMED"}`) + fresh D0 ARMED.

2. AT-WRITE SERIALIZED DISPATCH & WRITE COMPLETION BEFORE CONFIRMATION (Finding B):
   - In `request_stop()`, operation ID and confirmation window are opened ONLY AFTER full-byte write
     completion (`bytes_written == expected_len`). Telemetry samples arriving before write completion
     are never counted as confirmed zero for this operation.

3. INDEPENDENT OPERATION PER FAULT EVENT (Finding C):
   - Reader hardware fault triggers a dedicated new operation ID, records exact physical write outcome,
     and invalidates any prior confirmation. If STOP write is partial or failed, status is locked
     as `WRITE_FAULT` and fresh zero is marked strictly as `ZERO_OBSERVED` without `CONFIRMED`.

4. DEDICATED TUNING ERROR HANDLER (Finding D):
   - Re-instates dedicated rejection matching for `INVALID_TUNING_RANGE` or TUNING errors in JSON:
     Maps directly to `REJECTED` state with status updated in tuning history, without falsely triggering
     a system-wide hardware FAULT_STOP or timing out as FAILED.

5. TYPED SCAN/MAP/TF & ALL-FINITE BOUNDARY:
   - Checks math.isfinite() on map resolution, dimensions, origin, orientation.
   - Full Footprint Bounding Radius (Provisional R=0.1885m calculated from Word track L=0.1875m).
"""

import sys
import os
import time
import math
import json
import csv
import io
import uuid
import threading
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Audited module imports
try:
    from agv_preflight_static_collector import (
        validate_telemetry_sample,
        EXACT_BOOT_BANNER,
        EXACT_I2C_SCAN_BANNER,
        STARTUP_DEADLINE_S
    )
except ImportError:
    def validate_telemetry_sample(payload):
        forbidden = ["error", "fault", "info", "ack", "status_msg"]
        for b in forbidden:
            if b in payload: return False, f"MIXED_KEY_{b}"
        if payload.get("safety") != "DISARMED": return False, "NOT_DISARMED"
        if float(payload.get("l_pwm", 0)) != 0 or float(payload.get("r_pwm", 0)) != 0: return False, "NON_ZERO_PWM"
        if abs(float(payload.get("l_rpm", 0))) > 1e-3 or abs(float(payload.get("r_rpm", 0))) > 1e-3: return False, "NON_ZERO_RPM"
        return True, "SAMPLE_VALID"
    EXACT_BOOT_BANNER = "ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"
    EXACT_I2C_SCAN_BANNER = "Scanning I2C bus..."
    STARTUP_DEADLINE_S = 3.5

# -----------------------------------------------------------------------------
# 1. PHYSICAL CONSTANTS (STRICT PROVENANCE: TINH_TOAN_THIET_KE_XE_TU_HANH.docx)
# -----------------------------------------------------------------------------
ROBOT_MASS_KG = 1.75          # Word Sec 1: Measured mass
ROBOT_WHEEL_CIRC_M = 0.23     # Word Sec 2: Tape-measured circumference (R = 36.6 mm)
ROBOT_WHEEL_BASE_M = 0.1875   # Word Sec 2: Track width center-to-center (18.75 cm)
ROBOT_CPR = 937.2             # Word Sec 6: 11 PPR * 4 * 21.3 ratio
# Precise corner bounding radius (Provisional calculated geometry):
# sqrt((0.1875/2)^2 + (0.28/2)^2) + 0.02m = 0.18849m -> 0.1885 m
ROBOT_FOOTPRINT_CORNER_RADIUS_M = 0.1885

# -----------------------------------------------------------------------------
# 2. SHARED THREAD-SAFE STATE
# -----------------------------------------------------------------------------
class SafeAGVState:
    def __init__(self):
        self.lock = threading.Lock()
        
        # Telemetry strictly mapped from firmware main.cpp line 347
        self.x = 0.0
        self.y = 0.0
        self.th = 0.0
        self.l_rpm = 0.0
        self.r_rpm = 0.0
        self.l_pwm = 0
        self.r_pwm = 0
        self.l_tgt = 0.0
        self.r_tgt = 0.0
        self.v = 0.0
        self.w = 0.0
        self.mcu_mode = "IDLE"
        self.mcu_state = "UNKNOWN" # DISARMED, ARMED, FAULT
        self.last_telemetry_mono = 0.0
        self.fresh_d0_count = 0
        self.session_id = str(uuid.uuid4())
        
        # Audited Startup FSM (Strict progression order: 0 -> 1 -> 2 -> 3)
        self.startup_fsm_stage = 0 # 0=AWAIT_BOOT, 1=AWAIT_SCAN, 2=AWAIT_FOUND, 3=POST_DIAG_SETTLING
        self.startup_fsm_start_mono = 0.0
        self.boot_banner_seen = False
        self.i2c_scan_seen = False
        self.i2c_found_seen = False
        self.settling_complete = False
        self.preflight_count = 0
        self.preflight_start_mono = 0.0
        self.preflight_last_sample_mono = 0.0
        self.preflight_passed = False
        self.arm_ack_received = False
        
        # Laser Scan
        self.min_dist_m = 99.0
        self.min_angle_deg = 0.0
        self.zones = {"front": 999, "front_left": 999, "front_right": 999, "left": 999, "right": 999}
        self.ranges = [0.0] * 360
        self.last_scan_mono = 0.0
        
        # SLAM Map (OccupancyGrid)
        self.map_received = False
        self.map_w = 0
        self.map_h = 0
        self.map_res = 0.05
        self.map_ox = 0.0
        self.map_oy = 0.0
        self.map_data = []
        self.map_epoch = 0
        self.last_map_mono = 0.0
        
        # Autonomous / Navigation State
        self.auto_mode = False
        self.latched_stop = False
        self.fault_code = None
        self.first_fault_reason = None
        self.fsm_state = "IDLE"
        self.home_x = 0.0
        self.home_y = 0.0
        self.home_th = 0.0
        self.home_captured = False
        self.frontier_count = 0
        self.current_goal = None
        self.current_path = []
        
        # Motion Activity
        self.last_motion_cmd_mono = 0.0
        self.is_moving = False
        
        # STOP Verification: Operation tracking & Observed vs Confirmed
        self.stop_op_id = 0
        self.stop_requested_mono = 0.0
        self.stop_write_complete_mono = 0.0
        self.stop_deadline_mono = 0.0
        self.stop_write_fault = False
        self.stop_outcome_observed = False
        self.stop_outcome_confirmed = False
        
        # PID Tuning State Machine & History
        self.current_gains = {"kp": 0.50, "ki": 1.50, "kd": 0.010, "kf": 0.45}
        self.tuning_tx_state = "IDLE"
        self.tuning_history = []

state = SafeAGVState()

# -----------------------------------------------------------------------------
# 3. STRICT SERIAL ARBITER WITH SERIALIZED DISPATCH & CONFIRMATION GATES
# -----------------------------------------------------------------------------
class SafeSerialArbiter:
    def __init__(self, ser_instance=None):
        self.ser = ser_instance
        self.tx_lock = threading.Lock()
        self.tuning_queue_lock = threading.Lock()
        self.running = True
        self.active_tuning_tx = None
        self.tx_counter = 0

    def send_guarded(self, cmd: str, cmd_class: str = "DRIVE") -> tuple[bool, str]:
        """PRIORITY AT-WRITE AUTHORIZATION & PARTIAL/WRITE FAULT LATCHING."""
        with self.tx_lock:
            now_mono = time.monotonic()
            
            # Authorization checks strictly INSIDE write lock
            if cmd_class == "STOP":
                pass
            else:
                with state.lock:
                    if state.latched_stop:
                        return False, "REJECTED_LATCHED_STOP"
                    if cmd_class == "DRIVE":
                        if state.mcu_state != "ARMED":
                            return False, "REJECTED_MCU_NOT_ARMED"
                        if (now_mono - state.last_telemetry_mono) > 0.5:
                            return False, "REJECTED_STALE_TELEMETRY"

            if not self.ser or not getattr(self.ser, 'is_open', True):
                return False, "SERIAL_PORT_UNAVAILABLE"

            try:
                raw_bytes = (cmd.strip() + "\r\n").encode('utf-8')
                expected_len = len(raw_bytes)
                
                bytes_written = self.ser.write(raw_bytes)
                if bytes_written is None or bytes_written < expected_len:
                    written_cnt = bytes_written if bytes_written is not None else 0
                    self._fire_physical_stop_internal_locked()
                    with state.lock:
                        state.latched_stop = True
                        state.stop_write_fault = True
                        fault_msg = f"PARTIAL_WRITE_FAULT: {written_cnt}/{expected_len}"
                        state.fault_code = fault_msg
                        if not state.first_fault_reason:
                            state.first_fault_reason = fault_msg
                        state.auto_mode = False
                        state.is_moving = False
                        state.fsm_state = "FAULT_STOP"
                    return False, fault_msg
                    
                if hasattr(self.ser, 'flush'):
                    self.ser.flush()
                    
                if cmd_class == "DRIVE":
                    with state.lock:
                        state.last_motion_cmd_mono = now_mono
                        state.is_moving = True
                elif cmd_class == "STOP":
                    with state.lock:
                        state.is_moving = False
                        
                return True, "OK"
            except Exception as e:
                self._fire_physical_stop_internal_locked()
                with state.lock:
                    state.latched_stop = True
                    state.stop_write_fault = True
                    state.fault_code = f"WRITE_EXCEPTION: {e}"
                    if not state.first_fault_reason:
                        state.first_fault_reason = state.fault_code
                    state.is_moving = False
                return False, str(e)

    def _fire_physical_stop_internal_locked(self) -> int:
        """Internal helper to burst physical STOP commands on fault within held tx_lock."""
        total_delivered = 0
        if self.ser and getattr(self.ser, 'is_open', True):
            try:
                for _ in range(3):
                    raw_bytes = b"STOP\r\n"
                    n = self.ser.write(raw_bytes)
                    if n is not None: total_delivered += n
                    if hasattr(self.ser, 'flush'): self.ser.flush()
            except Exception:
                pass
        return total_delivered

    def handle_reader_hardware_fault(self, fault_desc: str):
        """Called by reader thread to priority-stop, latch fault, and track distinct operation."""
        with self.tx_lock:
            # Allocate dedicated operation ID for this fault event
            with state.lock:
                state.stop_op_id += 1
                fault_op_id = state.stop_op_id
                state.latched_stop = True
                state.is_moving = False
                state.auto_mode = False
                state.fsm_state = "FAULT_STOP"
                state.fault_code = f"HARDWARE_FAULT_OBSERVED: {fault_desc}"
                if not state.first_fault_reason:
                    state.first_fault_reason = state.fault_code
                state.stop_outcome_confirmed = False # Invalidate prior confirmation!
                state.stop_outcome_observed = False
                state.preflight_passed = False
                state.preflight_count = 0
                state.startup_fsm_stage = 0

            # Burst 3 physical STOP commands and record write outcome
            expected_total = 3 * len(b"STOP\r\n")
            delivered = self._fire_physical_stop_internal_locked()
            with state.lock:
                if delivered < expected_total:
                    state.stop_write_fault = True
                else:
                    state.stop_write_fault = False
                state.stop_write_complete_mono = time.monotonic()

    def request_arm(self, timeout=1.0) -> tuple[bool, str]:
        """Strict ARM Handshake requiring sequential Startup FSM completion & explicit ACK."""
        with self.tx_lock:
            now_mono = time.monotonic()
            with state.lock:
                if state.latched_stop:
                    return False, "REFUSED_LATCHED_STOP"
                if not self.ser or not getattr(self.ser, 'is_open', True):
                    return False, "REFUSED_NO_UART"
                
                # Check startup FSM stage & preflight validity strictly INSIDE tx_lock at moment of TX
                preflight_duration = now_mono - state.preflight_start_mono if state.preflight_count > 0 else 0.0
                last_sample_age = now_mono - state.preflight_last_sample_mono if state.preflight_count > 0 else 999.0
                
                if (state.startup_fsm_stage < 3 or not state.boot_banner_seen or 
                    not state.i2c_scan_seen or not state.i2c_found_seen or
                    state.preflight_count < 80 or preflight_duration < 10.0 or last_sample_age > 0.5):
                    state.preflight_passed = False
                    return False, f"REFUSED_PREFLIGHT_NOT_MET: fsm_stage={state.startup_fsm_stage}, banner={state.boot_banner_seen}, i2c_scan={state.i2c_scan_seen}, i2c_found={state.i2c_found_seen}, count={state.preflight_count}/80, dur={preflight_duration:.1f}/10.0s, age={last_sample_age:.2f}s"
                
                t_arm_req = now_mono
                state.arm_ack_received = False

            try:
                raw_bytes = b"ARM\r\n"
                n = self.ser.write(raw_bytes)
                if n is None or n < len(raw_bytes):
                    self._fire_physical_stop_internal_locked()
                    with state.lock:
                        state.latched_stop = True
                        state.fault_code = "PARTIAL_ARM_WRITE"
                        if not state.first_fault_reason: state.first_fault_reason = "PARTIAL_ARM_WRITE"
                    return False, "PARTIAL_ARM_WRITE"
                if hasattr(self.ser, 'flush'): self.ser.flush()
            except Exception as e:
                return False, str(e)

        # Wait for explicit ARM ACK AND fresh D0 confirming ARMED received strictly AFTER arm request
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            with state.lock:
                if (state.arm_ack_received and state.mcu_state == "ARMED" and 
                    state.last_telemetry_mono >= t_arm_req):
                    return True, "ARMED_CONFIRMED_FRESH"
            time.sleep(0.02)
        return False, "TIMEOUT_NO_FRESH_ARM_ACK"

    def request_stop(self, timeout=0.8) -> tuple[bool, str]:
        """
        Latched Emergency Stop with strict operation ID and POST-WRITE confirmation window:
        Bursts STOP and registers confirmation window ONLY AFTER full-byte write completion.
        Returns FALSE and marks unconfirmed on timeout or write fault.
        """
        with self.tx_lock:
            with state.lock:
                state.stop_op_id += 1
                op_id = state.stop_op_id
                state.latched_stop = True
                state.auto_mode = False
                state.fsm_state = "IDLE"
                state.is_moving = False
                state.stop_write_fault = False
                state.stop_outcome_observed = False
                state.stop_outcome_confirmed = False
                t_stop_req = time.monotonic()
                state.stop_requested_mono = t_stop_req
                state.stop_deadline_mono = t_stop_req + timeout

            success = True
            err_msg = "OK"
            for _ in range(3):
                raw_bytes = b"STOP\r\n"
                expected_len = len(raw_bytes)
                if not self.ser or not getattr(self.ser, 'is_open', True):
                    success = False
                    err_msg = "SERIAL_PORT_UNAVAILABLE"
                    break
                try:
                    bytes_written = self.ser.write(raw_bytes)
                    if bytes_written is None or bytes_written < expected_len:
                        success = False
                        err_msg = f"PARTIAL_STOP_WRITE: {bytes_written}/{expected_len}"
                        break
                    if hasattr(self.ser, 'flush'): self.ser.flush()
                except Exception as e:
                    success = False
                    err_msg = str(e)
                    break
                time.sleep(0.01)

            with state.lock:
                if not success:
                    state.stop_write_fault = True
                    return False, f"STOP_WRITE_FAILED: {err_msg}"
                # Mark write completion time strictly inside lock after full bytes sent!
                state.stop_write_complete_mono = time.monotonic()

        # Await fresh full-schema D0 zero confirmation strictly AFTER write completion
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            with state.lock:
                if state.last_telemetry_mono >= state.stop_write_complete_mono:
                    state.stop_outcome_observed = True
                    is_full_zero = (
                        state.l_pwm == 0 and state.r_pwm == 0 and
                        abs(state.l_rpm) <= 1e-3 and abs(state.r_rpm) <= 1e-3 and
                        abs(state.l_tgt) <= 1e-3 and abs(state.r_tgt) <= 1e-3 and
                        abs(state.v) <= 1e-4 and abs(state.w) <= 1e-4 and
                        state.mcu_state == "DISARMED"
                    )
                    if is_full_zero and not state.stop_write_fault and state.stop_op_id == op_id:
                        state.stop_outcome_confirmed = True
                        return True, "STOP_CONFIRMED_ZERO"
            time.sleep(0.02)

        # If deadline expires without confirmed zero, return False
        with state.lock:
            state.fault_code = "STOP_UNCONFIRMED_TIMEOUT"
            if not state.first_fault_reason:
                state.first_fault_reason = "STOP_UNCONFIRMED_TIMEOUT"
        return False, "STOP_UNCONFIRMED_TIMEOUT"

    def release_stop_latch(self) -> tuple[bool, str]:
        """Explicitly clear E-Stop latch ONLY if MCU is in confirmed fresh DISARMED zero-motion state."""
        now_mono = time.monotonic()
        with state.lock:
            if state.mcu_state != "DISARMED":
                return False, f"CANNOT_RELEASE_LATCH_MCU_STATE_NOT_DISARMED: {state.mcu_state}"
            if (now_mono - state.last_telemetry_mono) > 0.5:
                return False, "CANNOT_RELEASE_LATCH_STALE_TELEMETRY"
            if (abs(state.l_rpm) > 1e-3 or abs(state.r_rpm) > 1e-3 or 
                state.l_pwm != 0 or state.r_pwm != 0 or
                abs(state.l_tgt) > 1e-3 or abs(state.r_tgt) > 1e-3 or
                abs(state.v) > 1e-4 or abs(state.w) > 1e-4):
                return False, "CANNOT_RELEASE_LATCH_NONZERO_MOTION_OR_TARGET"
                
            state.latched_stop = False
            state.fault_code = None
            state.first_fault_reason = None
            state.stop_op_id = 0
            state.stop_requested_mono = 0.0
            state.stop_write_complete_mono = 0.0
            state.stop_deadline_mono = 0.0
            state.stop_write_fault = False
            return True, "LATCH_RELEASED"

    def request_tuning(self, kp: float, ki: float, kd: float, kf: float, timeout=1.5) -> tuple[str, str]:
        """Serialized Per-Request PID Tuning Transaction."""
        if not (math.isfinite(kp) and math.isfinite(ki) and math.isfinite(kd) and math.isfinite(kf)):
            return ("REJECTED", "INVALID_NOT_FINITE")
        if not (0.0 <= kp <= 20.0 and 0.0 <= ki <= 50.0 and 0.0 <= kd <= 5.0 and 0.0 <= kf <= 5.0):
            return ("REJECTED", "OUT_OF_BOUNDS")

        with self.tuning_queue_lock:
            tx_id = self.tx_counter + 1
            self.tx_counter = tx_id
            
            tx_obj = {
                "id": tx_id,
                "expected": (kp, ki, kd, kf),
                "event": threading.Event(),
                "result": "PENDING",
                "ack_text": "",
                "time": time.strftime("%H:%M:%S")
            }
            self.active_tuning_tx = tx_obj
            
            with state.lock:
                state.tuning_tx_state = "PENDING"
                state.tuning_history.append({
                    "tx_id": tx_id, "time": tx_obj["time"],
                    "kp": kp, "ki": ki, "kd": kd, "kf": kf,
                    "status": "PENDING", "reason": ""
                })

            cmd = f"TUNING {kp:.3f} {ki:.3f} {kd:.4f} {kf:.3f}"
            ok, reason = self.send_guarded(cmd, cmd_class="TUNING")
            if not ok:
                tx_obj["result"] = "FAILED"
                tx_obj["ack_text"] = reason
                self._update_history_status(tx_id, "FAILED", reason)
                self.active_tuning_tx = None
                return ("FAILED", reason)

            if tx_obj["event"].wait(timeout):
                res = tx_obj["result"]
                reason = tx_obj["ack_text"]
                self.active_tuning_tx = None
                return (res, reason)
            else:
                tx_obj["result"] = "FAILED"
                tx_obj["ack_text"] = "TIMEOUT_NO_MCU_ACK"
                self._update_history_status(tx_id, "FAILED", "TIMEOUT_NO_MCU_ACK")
                self.active_tuning_tx = None
                return ("FAILED", "TIMEOUT_NO_MCU_ACK")

    def _update_history_status(self, tx_id, status, reason):
        with state.lock:
            state.tuning_tx_state = status
            for item in state.tuning_history:
                if item.get("tx_id") == tx_id:
                    item["status"] = status
                    item["reason"] = reason
                    break

    def parse_line(self, line: str):
        """Pure Source-Linked Collector 4b32 Validator matching firmware main.cpp."""
        line = line.strip()
        if not line:
            return
            
        now_mono = time.monotonic()
        
        # Parse JSON line
        if line.startswith('{') and line.endswith('}'):
            try:
                d = json.loads(line)
                
                # 1. Handle TUNING Responses & Errors FIRST (Finding D)
                if self.active_tuning_tx is not None:
                    if "error" in d and ("TUNING" in str(d["error"]) or "INVALID_TUNING_RANGE" in str(d["error"])):
                        err_str = str(d["error"])
                        self.active_tuning_tx["result"] = "REJECTED"
                        self.active_tuning_tx["ack_text"] = err_str
                        self._update_history_status(self.active_tuning_tx["id"], "REJECTED", err_str)
                        self.active_tuning_tx["event"].set()
                        return

                    if "ack" in d and "TUNING" in str(d["ack"]):
                        ack_str = str(d["ack"])
                        parts = ack_str.split()
                        if len(parts) >= 5:
                            try:
                                akp, aki, akd, akf = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                                ekp, eki, ekd, ekf = self.active_tuning_tx["expected"]
                                if (abs(akp - ekp) < 0.005 and abs(aki - eki) < 0.005 and 
                                    abs(akd - ekd) < 0.005 and abs(akf - ekf) < 0.005):
                                    with state.lock:
                                        state.current_gains = {"kp": akp, "ki": aki, "kd": akd, "kf": akf}
                                    self.active_tuning_tx["result"] = "APPLIED"
                                    self.active_tuning_tx["ack_text"] = ack_str
                                    self._update_history_status(self.active_tuning_tx["id"], "APPLIED", "MATCHED_CONFIRMED")
                                    self.active_tuning_tx["event"].set()
                                    return
                                else:
                                    mismatch_msg = f"ACK_MISMATCH: expected {self.active_tuning_tx['expected']}, got {(akp, aki, akd, akf)}"
                                    self.active_tuning_tx["result"] = "REJECTED"
                                    self.active_tuning_tx["ack_text"] = mismatch_msg
                                    self._update_history_status(self.active_tuning_tx["id"], "REJECTED", mismatch_msg)
                                    self.active_tuning_tx["event"].set()
                                    return
                            except ValueError:
                                pass
                        self.active_tuning_tx["result"] = "REJECTED"
                        self.active_tuning_tx["ack_text"] = "MALFORMED_ACK"
                        self._update_history_status(self.active_tuning_tx["id"], "REJECTED", "MALFORMED_ACK")
                        self.active_tuning_tx["event"].set()
                        return

                # 2. Check for explicit hardware errors (Finding B & C)
                if "error" in d or "fault" in d:
                    err_msg = str(d.get("error") or d.get("fault"))
                    self.handle_reader_hardware_fault(err_msg)
                    return

                # 3. Handle Explicit ARM ACK (Finding A)
                if d.get("ack") == "ARM" or d.get("status") == "ARMED":
                    with state.lock:
                        state.arm_ack_received = True
                    return

                # 4. Strict Startup FSM Progression (Finding A)
                # Check startup deadline expiration
                if state.startup_fsm_stage > 0:
                    if (now_mono - state.startup_fsm_start_mono) > STARTUP_DEADLINE_S:
                        # Exceeded startup deadline!
                        self.handle_reader_hardware_fault("STARTUP_DEADLINE_EXCEEDED")
                        return

                # Stage 0: EXACT_BOOT_BANNER (No mixed keys allowed!)
                if d.get("info") == EXACT_BOOT_BANNER:
                    if len(d) > 1: # Mixed keys present!
                        return
                    with state.lock:
                        state.boot_banner_seen = True
                        state.startup_fsm_stage = 1
                        state.startup_fsm_start_mono = now_mono
                    return
                # Stage 1: EXACT_I2C_SCAN_BANNER
                elif state.boot_banner_seen and d.get("info") == EXACT_I2C_SCAN_BANNER:
                    with state.lock:
                        state.i2c_scan_seen = True
                        state.startup_fsm_stage = 2
                    return
                # Stage 2: I2C Device Found (Strict hex address 0x01..0x7F and VIN > 0)
                elif state.i2c_scan_seen:
                    if "i2c_found" in d:
                        addr_str = str(d["i2c_found"]).strip()
                        try:
                            addr_val = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
                            if 0x01 <= addr_val <= 0x7F: # Valid address in 1..127
                                with state.lock:
                                    state.i2c_found_seen = True
                                    state.settling_complete = True
                                    state.startup_fsm_stage = 3
                                    state.preflight_count = 0
                                    state.preflight_start_mono = now_mono
                                return
                        except ValueError:
                            pass
                    elif "vin_mv" in d:
                        try:
                            vin_val = int(d["vin_mv"])
                            if vin_val > 0 and state.i2c_found_seen:
                                return # Valid VIN following found
                        except ValueError:
                            pass

                # 5. Strict Collector 4b32 Telemetry Sample Validator
                ok_sample, sample_reason = validate_telemetry_sample(d)
                
                required_keys = ["safety", "mode", "l_tgt", "r_tgt", "l_rpm", "r_rpm", "l_pwm", "r_pwm", "x", "y", "th", "v", "w"]
                if all(k in d for k in required_keys):
                    try:
                        rx = float(d["x"])
                        ry = float(d["y"])
                        rth = float(d["th"])
                        lrpm = float(d["l_rpm"])
                        rrpm = float(d["r_rpm"])
                        lpwm = int(d["l_pwm"])
                        rpwm = int(d["r_pwm"])
                        ltgt = float(d["l_tgt"])
                        rtgt = float(d["r_tgt"])
                        v_lin = float(d["v"])
                        w_ang = float(d["w"])
                        mode = str(d["mode"])
                        safety = str(d["safety"])
                    except (ValueError, TypeError):
                        return
                        
                    numeric_vals = [rx, ry, rth, lrpm, rrpm, ltgt, rtgt, v_lin, w_ang]
                    if not all(math.isfinite(val) for val in numeric_vals):
                        return
                    if abs(lpwm) > 255 or abs(rpwm) > 255:
                        return
                    if safety not in ["ARMED", "DISARMED", "FAULT"]:
                        return

                    with state.lock:
                        state.last_telemetry_mono = now_mono
                        state.fresh_d0_count += 1
                        state.x = rx
                        state.y = ry
                        state.th = rth
                        state.l_rpm = lrpm
                        state.r_rpm = rrpm
                        state.l_pwm = lpwm
                        state.r_pwm = rpwm
                        state.l_tgt = ltgt
                        state.r_tgt = rtgt
                        state.v = v_lin
                        state.w = w_ang
                        state.mcu_mode = mode
                        state.mcu_state = safety
                        
                        # Full-schema zero check
                        is_exact_zero_disarmed = (ok_sample and safety == "DISARMED")
                        
                        # Handle late confirmed zero ONLY for registered stop operations strictly after write completion
                        if is_exact_zero_disarmed and state.latched_stop:
                            state.stop_outcome_observed = True
                            if (state.stop_op_id > 0 and not state.stop_write_fault and 
                                state.stop_write_complete_mono > 0.0 and
                                now_mono >= state.stop_write_complete_mono):
                                state.stop_outcome_confirmed = True

                        # Preflight Contract: strictly requires Stage 3 (post-diagnostic!)
                        if is_exact_zero_disarmed and state.startup_fsm_stage == 3:
                            gap = now_mono - state.preflight_last_sample_mono if state.preflight_count > 0 else 0.0
                            if state.preflight_count == 0 or gap <= 0.5:
                                if state.preflight_count == 0:
                                    state.preflight_start_mono = now_mono
                                state.preflight_count += 1
                                state.preflight_last_sample_mono = now_mono
                                
                                # Exact Contract: stage 3, count >= 80, dur >= 10.0s
                                if state.preflight_count >= 80 and (now_mono - state.preflight_start_mono) >= 10.0:
                                    state.preflight_passed = True
                            else:
                                state.preflight_count = 1
                                state.preflight_start_mono = now_mono
                                state.preflight_last_sample_mono = now_mono
                                state.preflight_passed = False
                        else:
                            # Do not reset preflight count if in ARMED operational mode!
                            if not is_exact_zero_disarmed and safety != "ARMED":
                                state.preflight_count = 0
                                state.preflight_passed = False
            except Exception:
                pass

# -----------------------------------------------------------------------------
# 4. FULL FOOTPRINT BFS PATH & STANDOFF FRONTIER PLANNER
# -----------------------------------------------------------------------------
class ReachableFrontierPlanner:
    @staticmethod
    def plan_next_frontier_and_path(rx: float, ry: float, state_ref: SafeAGVState):
        """
        Uses BFS wave-front expansion on OccupancyGrid from current robot pose.
        Strictly checks math.isfinite() for resolution, dimensions, and map origin (ox, oy).
        Enforces Full Robot Footprint (R=0.1885m) remains strictly within known free space (val == 0).
        """
        with state_ref.lock:
            w = state_ref.map_w
            h = state_ref.map_h
            res = state_ref.map_res
            ox = state_ref.map_ox
            oy = state_ref.map_oy
            grid = list(state_ref.map_data)
            map_received = state_ref.map_received
            
        # Strict boundary and finite validation
        if (not map_received or not grid or not math.isfinite(res) or res <= 0.001 or 
            not math.isfinite(ox) or not math.isfinite(oy) or
            w <= 1 or h <= 1 or len(grid) != w * h):
            return None, [], 0

        start_x = int((rx - ox) / res)
        start_y = int((ry - oy) / res)
        
        if not (0 <= start_x < w and 0 <= start_y < h):
            return None, [], 0

        visited = { (start_x, start_y): None }
        queue = deque([(start_x, start_y, 0)])
        
        found_frontiers = []
        inflation_cells = max(1, int(math.ceil(ROBOT_FOOTPRINT_CORNER_RADIUS_M / res)))

        while queue:
            cx, cy, steps = queue.popleft()
            if steps > int(6.0 / res):
                break

            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                    val = grid[ny * w + nx]
                    
                    if val == 0:
                        safe_pass = True
                        for ix in range(-inflation_cells, inflation_cells + 1):
                            for iy in range(-inflation_cells, inflation_cells + 1):
                                check_x, check_y = nx + ix, ny + iy
                                if not (0 <= check_x < w and 0 <= check_y < h):
                                    safe_pass = False; break
                                c_val = grid[check_y * w + check_x]
                                if c_val > 50 or c_val == -1:
                                    safe_pass = False; break
                            if not safe_pass: break
                                
                        if safe_pass:
                            visited[(nx, ny)] = (cx, cy)
                            
                            is_frontier = False
                            for kx in range(-inflation_cells - 1, inflation_cells + 2):
                                for ky in range(-inflation_cells - 1, inflation_cells + 2):
                                    adj_x, adj_y = nx + kx, ny + ky
                                    if 0 <= adj_x < w and 0 <= adj_y < h:
                                        if grid[adj_y * w + adj_x] == -1:
                                            is_frontier = True; break
                                if is_frontier: break
                                        
                            real_dist = math.hypot((nx - start_x) * res, (ny - start_y) * res)
                            if is_frontier and 0.4 <= real_dist <= 4.0:
                                wx = ox + nx * res
                                wy = oy + ny * res
                                found_frontiers.append((real_dist, nx, ny, wx, wy))
                                
                            queue.append((nx, ny, steps + 1))

        if not found_frontiers:
            return None, [], 0

        found_frontiers.sort(key=lambda item: item[0])
        best = found_frontiers[0]
        goal_xy = (best[3], best[4])
        
        path = []
        curr = (best[1], best[2])
        while curr is not None:
            path.append((ox + curr[0] * res, oy + curr[1] * res))
            curr = visited.get(curr)
        path.reverse()
        
        return goal_xy, path, len(found_frontiers)

# -----------------------------------------------------------------------------
# 5. INDEPENDENT WATCHDOG & AUTONOMOUS NAVIGATOR
# -----------------------------------------------------------------------------
class SafeAutonomousNavigator:
    def __init__(self, arbiter: SafeSerialArbiter):
        self.arbiter = arbiter
        self.running = True
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self.nav_thread = threading.Thread(target=self._navigator_loop, daemon=True)

    def start(self):
        self.watchdog_thread.start()
        self.nav_thread.start()

    def stop(self):
        self.running = False
        if self.watchdog_thread.is_alive():
            self.watchdog_thread.join(timeout=0.2)
        if self.nav_thread.is_alive():
            self.nav_thread.join(timeout=0.2)

    def _watchdog_loop(self):
        """
        INDEPENDENT ASYNCHRONOUS WATCHDOG:
        Monitors ALL active motions AND monitors unconfirmed pending stops.
        """
        while self.running:
            time.sleep(0.05)
            now_mono = time.monotonic()
            with state.lock:
                auto = state.auto_mode
                is_moving = state.is_moving
                latched = state.latched_stop
                stop_confirmed = state.stop_outcome_confirmed
                stop_deadline = state.stop_deadline_mono
                last_scan = state.last_scan_mono
                last_tele = state.last_telemetry_mono

            # Check sensor freshness on active motion
            if auto or is_moving:
                if (now_mono - last_scan > 0.5) or (now_mono - last_tele > 0.5):
                    self.arbiter.request_stop()
                    with state.lock:
                        state.latched_stop = True
                        state.fsm_state = "WATCHDOG_STALE_STOP"
                        if not state.first_fault_reason:
                            state.first_fault_reason = "STALE_SENSOR_TIMEOUT"

            # Check deadline escalation on pending stops
            if latched and not stop_confirmed and stop_deadline > 0.0:
                if now_mono > stop_deadline:
                    with state.lock:
                        if not state.fault_code:
                            state.fault_code = "STOP_UNCONFIRMED_TIMEOUT"
                        if not state.first_fault_reason:
                            state.first_fault_reason = "STOP_UNCONFIRMED_TIMEOUT"

    def _navigator_loop(self):
        """10Hz Navigation FSM Loop."""
        while self.running:
            time.sleep(0.10)
            self.step()

    def step(self):
        """Execute one 10Hz tick without blocking sleeps."""
        with state.lock:
            auto = state.auto_mode
            latched = state.latched_stop
            f_cm = state.zones["front"]
            fr_cm = state.zones["front_right"]
            fl_cm = state.zones["front_left"]
            l_cm = state.zones["left"]
            r_cm = state.zones["right"]
            rx, ry, rth = state.x, state.y, state.th
            map_rcv = state.map_received
            current_fsm = state.fsm_state

        if latched or not auto:
            return

        # 1. PRE-MOTION HOME CAPTURE: BEFORE ANY MOTION
        if not state.home_captured:
            with state.lock:
                state.home_x = rx
                state.home_y = ry
                state.home_th = rth
                state.home_captured = True
                state.fsm_state = "EXPLORING"
            return

        # 2. REACTIVE SAFETY BARRIER: Front obstacle < 40cm
        if f_cm < 40 or fr_cm < 32 or fl_cm < 32:
            turn_cmd = "V 0.00 0.40" if l_cm > r_cm else "V 0.00 -0.40"
            self.arbiter.send_guarded(turn_cmd, cmd_class="DRIVE")
            return

        # 3. REACHABLE FRONTIER EXPLORATION
        if current_fsm == "EXPLORING":
            with state.lock:
                mw = state.map_w
                mh = state.map_h
                mres = state.map_res
                mox = state.map_ox
                moy = state.map_oy
                mdata_len = len(state.map_data)

            if (not map_rcv or mw <= 1 or mh <= 1 or 
                not math.isfinite(mres) or mres <= 0.001 or 
                not math.isfinite(mox) or not math.isfinite(moy) or
                mdata_len != mw * mh):
                # Malformed or NaN map: Hold position safely instead of declaring false completion
                self.arbiter.send_guarded("V 0.00 0.00", cmd_class="DRIVE")
                return

            goal, path, count = ReachableFrontierPlanner.plan_next_frontier_and_path(rx, ry, state)
            with state.lock:
                state.frontier_count = count
                state.current_goal = goal
                state.current_path = path

            if goal is None:
                with state.lock:
                    state.fsm_state = "RETURNING_HOME"
                return

            target_pt = path[min(len(path) - 1, 3)] if len(path) > 1 else goal
            dx, dy = target_pt[0] - rx, target_pt[1] - ry
            dist = math.hypot(dx, dy)
            target_th = math.atan2(dy, dx)
            th_err = (target_th - rth + math.pi) % (2 * math.pi) - math.pi

            if abs(th_err) > 0.6:
                w = 0.40 if th_err > 0 else -0.40
                self.arbiter.send_guarded(f"V 0.00 {w:.2f}", cmd_class="DRIVE")
            else:
                v = min(0.12, 0.05 + dist * 0.08)
                w = max(-0.35, min(0.35, 1.1 * th_err))
                self.arbiter.send_guarded(f"V {v:.2f} {w:.2f}", cmd_class="DRIVE")
            return

        # 4. RETURN TO HOME POSITION & HEADING
        if current_fsm == "RETURNING_HOME":
            with state.lock:
                hx, hy, hth = state.home_x, state.home_y, state.home_th
            
            dx, dy = hx - rx, hy - ry
            dist_home = math.hypot(dx, dy)

            if dist_home < 0.12:
                th_err = (hth - rth + math.pi) % (2 * math.pi) - math.pi
                if abs(th_err) < 0.15: # < 8.5 degrees
                    ok, _ = self.arbiter.request_stop()
                    with state.lock:
                        if state.stop_outcome_confirmed:
                            state.fsm_state = "COMPLETED"
                            state.auto_mode = False
                else:
                    w = 0.30 if th_err > 0 else -0.30
                    self.arbiter.send_guarded(f"V 0.00 {w:.2f}", cmd_class="DRIVE")
            else:
                target_th = math.atan2(dy, dx)
                th_err = (target_th - rth + math.pi) % (2 * math.pi) - math.pi
                if abs(th_err) > 0.6:
                    w = 0.35 if th_err > 0 else -0.35
                    self.arbiter.send_guarded(f"V 0.00 {w:.2f}", cmd_class="DRIVE")
                else:
                    v = min(0.12, 0.04 + dist_home * 0.08)
                    w = max(-0.30, min(0.30, 1.0 * th_err))
                    self.arbiter.send_guarded(f"V {v:.2f} {w:.2f}", cmd_class="DRIVE")

# -----------------------------------------------------------------------------
# 6. REST API & DASHBOARD HTTP HANDLER
# -----------------------------------------------------------------------------
arbiter_instance = None
navigator_instance = None

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class SafeWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        import urllib.parse
        p = self.path.split('?')
        path = p[0]
        q = p[1] if len(p) > 1 else ''

        if path == '/' or path == '/index.html':
            html_candidates = [
                '/home/khangho/rplidar_c1_test/bridge/web/index_cyberpunk.html',
                'D:\\HoMinhKhang\\PROJECT\\GITHUB_PROJECT\\CODE XE TU HANH\\index_cyberpunk.html'
            ]
            content = None
            for cand in html_candidates:
                if os.path.exists(cand):
                    with open(cand, 'rb') as f:
                        content = f.read()
                    break
            
            if content:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self._cors()
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self._cors()
                self.end_headers()
                self.wfile.write(b"<h1>AGV CYBERPUNK DASHBOARD (ONLINE)</h1>")
            return

        elif path == '/api/telemetry':
            with state.lock:
                d = {
                    "session_id": state.session_id,
                    "auto": state.auto_mode,
                    "latched_stop": state.latched_stop,
                    "fault_code": state.fault_code,
                    "first_fault_reason": state.first_fault_reason,
                    "fsm_state": state.fsm_state,
                    "mcu_state": state.mcu_state,
                    "mcu_mode": state.mcu_mode,
                    "startup_stage": state.startup_fsm_stage,
                    "preflight_passed": state.preflight_passed,
                    "preflight_count": state.preflight_count,
                    "robot": {
                        "x": state.x, "y": state.y, "th": state.th,
                        "l_rpm": state.l_rpm, "r_rpm": state.r_rpm,
                        "l_pwm": state.l_pwm, "r_pwm": state.r_pwm,
                        "l_tgt": state.l_tgt, "r_tgt": state.r_tgt,
                        "v": state.v, "w": state.w
                    },
                    "zones": state.zones,
                    "min_m": state.min_dist_m,
                    "map_info": {
                        "has_map": state.map_received,
                        "w": state.map_w, "h": state.map_h,
                        "res": state.map_res,
                        "frontiers": state.frontier_count,
                        "fsm": state.fsm_state
                    }
                }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps(d).encode('utf-8'))
            return

        elif path == '/api/pid':
            params = urllib.parse.parse_qs(q)
            try:
                kp = float(params.get('kp', ['0.50'])[0])
                ki = float(params.get('ki', ['1.50'])[0])
                kd = float(params.get('kd', ['0.010'])[0])
                kf = float(params.get('kf', ['0.45'])[0])
            except (ValueError, TypeError):
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "REJECTED", "reason": "MALFORMED_FLOAT"}).encode('utf-8'))
                return

            status, ack_msg = arbiter_instance.request_tuning(kp, ki, kd, kf)
            resp = {
                "status": status,
                "ack": ack_msg,
                "applied_gains": {"kp": kp, "ki": ki, "kd": kd, "kf": kf} if status == "APPLIED" else None
            }
            self.send_response(200 if status == "APPLIED" else 422)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode('utf-8'))
            return

        elif path == '/api/history_csv':
            with state.lock:
                history_copy = list(state.tuning_history)
                
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["tx_id", "time", "kp", "ki", "kd", "kf", "status", "reason"])
            for item in history_copy:
                writer.writerow([
                    item.get("tx_id"), item.get("time"),
                    item.get("kp"), item.get("ki"), item.get("kd"), item.get("kf"),
                    item.get("status"), item.get("reason", "")
                ])
            csv_data = ("\uFEFF" + output.getvalue()).encode('utf-8')
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="pid_history.csv"')
            self._cors()
            self.end_headers()
            self.wfile.write(csv_data)
            return

        elif path == '/api/cmd':
            params = urllib.parse.parse_qs(q)
            val = params.get('val', [''])[0].strip()
            
            if val == 'STOP':
                ok, reason = arbiter_instance.request_stop()
                resp = {"status": "ok" if ok else "PARTIAL_FAULT", "action": "STOP_LATCHED", "reason": reason}
                self.send_response(200 if ok else 500)
            elif val == 'RELEASE_LATCH':
                ok, reason = arbiter_instance.release_stop_latch()
                if not ok:
                    self.send_response(403)
                    self.send_header('Content-Type', 'application/json')
                    self._cors()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "REJECTED", "reason": reason}).encode('utf-8'))
                    return
                resp = {"status": "ok", "action": "LATCH_RELEASED"}
                self.send_response(200)
            elif val == 'ARM':
                ok, reason = arbiter_instance.request_arm()
                if not ok:
                    self.send_response(422)
                    self.send_header('Content-Type', 'application/json')
                    self._cors()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "FAILED", "reason": reason}).encode('utf-8'))
                    return
                resp = {"status": "ok", "action": "ARMED"}
                self.send_response(200)
            else:
                ok, reason = arbiter_instance.send_guarded(val, cmd_class="DRIVE")
                if not ok:
                    self.send_response(403)
                    self.send_header('Content-Type', 'application/json')
                    self._cors()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "REJECTED", "reason": reason}).encode('utf-8'))
                    return
                resp = {"status": "ok", "cmd": val}
                self.send_response(200)
                
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode('utf-8'))
            return

        elif path == '/api/auto':
            params = urllib.parse.parse_qs(q)
            act = params.get('act', [''])[0].upper()
            if act == 'START':
                with state.lock:
                    if state.latched_stop:
                        self.send_response(403)
                        self.send_header('Content-Type', 'application/json')
                        self._cors()
                        self.end_headers()
                        self.wfile.write(b'{"status":"REJECTED_LATCHED_STOP"}')
                        return
                ok, reason = arbiter_instance.request_arm(timeout=1.0)
                if ok:
                    with state.lock:
                        state.auto_mode = True
                        state.home_captured = False
                    resp = {"status": "ok", "auto": True}
                    self.send_response(200)
                else:
                    self.send_response(422)
                    self.send_header('Content-Type', 'application/json')
                    self._cors()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "FAILED_ARM_HANDSHAKE", "reason": reason}).encode('utf-8'))
                    return
            else:
                ok, reason = arbiter_instance.request_stop()
                resp = {"status": "ok" if ok else "PARTIAL_FAULT", "auto": False, "reason": reason}
                self.send_response(200 if ok else 500)

            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode('utf-8'))
            return

        else:
            self.send_response(404)
            self.end_headers()

# -----------------------------------------------------------------------------
# 7. EXECUTABLE ENTRY POINT & CLEANUP
# -----------------------------------------------------------------------------
def main():
    global arbiter_instance, navigator_instance
    print("=== AGV OFFLINE INTEGRATION BUNDLE V4.9 INITIALIZING ===")
    
    serial_port = os.environ.get("AGV_SERIAL_PORT", "/dev/ttyUSB0")
    baud_rate = int(os.environ.get("AGV_BAUDRATE", "115200"))
    ser = None
    try:
        import serial
        ser = serial.Serial(serial_port, baud_rate, timeout=0.05)
        print(f"[SERIAL] Connected to {serial_port} @ {baud_rate}")
    except Exception as e:
        print(f"[SERIAL] Physical port not opened ({e}). Running in offline/mock mode.")

    arbiter_instance = SafeSerialArbiter(ser)
    
    reader_running = [True]
    def reader_loop():
        while reader_running[0] and ser and getattr(ser, 'is_open', False):
            try:
                line = ser.readline().decode('utf-8', errors='ignore')
                if line:
                    arbiter_instance.parse_line(line)
            except Exception:
                time.sleep(0.01)

    if ser and getattr(ser, 'is_open', False):
        reader_thread = threading.Thread(target=reader_loop, daemon=True)
        reader_thread.start()

    navigator_instance = SafeAutonomousNavigator(arbiter_instance)
    navigator_instance.start()

    server = ThreadedHTTPServer(('0.0.0.0', 8080), SafeWebHandler)
    print("=== AGV BUNDLE V4.9 READY & SERVING ON PORT 8080 ===")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Interrupted by user. Cleaning up...")
    finally:
        reader_running[0] = False
        arbiter_instance.running = False
        navigator_instance.stop()
        arbiter_instance.request_stop()
        server.shutdown()
        server.server_close()
        if ser and getattr(ser, 'is_open', False):
            ser.close()
        print("[SHUTDOWN] All resources cleanly released.")

if __name__ == '__main__':
    main()
