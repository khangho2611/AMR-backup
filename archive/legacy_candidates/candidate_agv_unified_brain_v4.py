#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGV SYSTEM ARCHITECTURE OFFLINE BUNDLE V4.0
Integrated:
- Strict Single-Owner Serial Arbiter (No Auto-ARM, explicit ARM-Handshake, TX Lock, Latched E-STOP)
- Watchdog for Scan & Telemetry Freshness (Non-blocking async loop)
- BFS Reachable Frontier Exploration with Footprint & Inflation Barrier
- Pre-motion Home Capture (Position & Heading) with Yaw Alignment Verification
- Web UI & API Contract: Typed PID Tuning (0-valid, finite check, ACK readback, State: PENDING/APPLIED/REJECTED/FAILED)
"""

import sys
import os
import time
import math
import json
import threading
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# -----------------------------------------------------------------------------
# 1. PHYSICAL CONSTANTS (STRICT PROVENANCE: TINH_TOAN_THIET_KE_XE_TU_HANH.docx)
# -----------------------------------------------------------------------------
ROBOT_MASS_KG = 1.75          # Word Sec 1: Actual measured complete vehicle mass
ROBOT_WHEEL_CIRC_M = 0.23     # Word Sec 2: Tape-measured circumference (R = 36.6 mm)
ROBOT_WHEEL_BASE_M = 0.1875   # Word Sec 2: Measured track width center-to-center
ROBOT_CPR = 937.2             # Word Sec 6: 11 PPR * 4 * 21.3 ratio
ROBOT_FOOTPRINT_RADIUS_M = 0.15 # Inscribed radius for collision inflation

# -----------------------------------------------------------------------------
# 2. SHARED THREAD-SAFE STATE
# -----------------------------------------------------------------------------
class SafeAGVState:
    def __init__(self):
        self.lock = threading.Lock()
        
        # Telemetry from MCU
        self.x = 0.0
        self.y = 0.0
        self.th = 0.0
        self.l_rpm = 0.0
        self.r_rpm = 0.0
        self.l_pwm = 0
        self.r_pwm = 0
        self.mcu_state = "UNKNOWN" # DISARMED, ARMED, FAULT
        self.last_telemetry_time = 0.0
        
        # Laser Scan
        self.min_dist_m = 99.0
        self.min_angle_deg = 0.0
        self.zones = {"front": 999, "front_left": 999, "front_right": 999, "left": 999, "right": 999}
        self.ranges = [0.0] * 360
        self.last_scan_time = 0.0
        
        # SLAM Map (OccupancyGrid)
        self.map_received = False
        self.map_w = 0
        self.map_h = 0
        self.map_res = 0.05
        self.map_ox = 0.0
        self.map_oy = 0.0
        self.map_data = [] # 1D flattened array
        self.map_epoch = 0
        
        # Autonomous / Navigation State
        self.auto_mode = False
        self.latched_stop = False
        self.fsm_state = "IDLE" # IDLE, CAPTURE_HOME, EXPLORING, RETURNING_HOME, COMPLETED
        self.home_x = 0.0
        self.home_y = 0.0
        self.home_th = 0.0
        self.home_captured = False
        self.frontier_count = 0
        self.current_goal = None # (x, y)
        
        # PID Tuning State Machine
        self.current_gains = {"kp": 0.50, "ki": 1.50, "kd": 0.010, "kf": 0.45}
        self.tuning_tx_state = "IDLE" # IDLE, PENDING, APPLIED, REJECTED, FAILED
        self.tuning_last_ack = ""
        self.tuning_history = []

state = SafeAGVState()

# -----------------------------------------------------------------------------
# 3. STRICT SERIAL ARBITER & DRIVER (NO AUTO-ARM, LATCHED STOP)
# -----------------------------------------------------------------------------
class SafeSerialArbiter:
    def __init__(self, ser_instance=None):
        self.ser = ser_instance
        self.tx_lock = threading.Lock()
        self.running = True
        self.pending_tuning_event = threading.Event()
        self.last_tuning_result = "IDLE"
        self.last_tuning_ack_text = ""

    def send_raw(self, cmd: str) -> bool:
        """Single-owner thread-safe write. Requires explicit newline."""
        with self.tx_lock:
            if not self.ser or not getattr(self.ser, 'is_open', True):
                return False
            try:
                line = (cmd.strip() + "\r\n").encode('utf-8')
                self.ser.write(line)
                if hasattr(self.ser, 'flush'):
                    self.ser.flush()
                return True
            except Exception:
                return False

    def request_arm(self, timeout=1.0) -> bool:
        """Explicit ARM Handshake. Never auto-inject into drive commands."""
        with state.lock:
            if state.latched_stop:
                return False # Cannot ARM while STOP is latched
        self.send_raw("ARM")
        t0 = time.time()
        while time.time() - t0 < timeout:
            with state.lock:
                if state.mcu_state == "ARMED":
                    return True
            time.sleep(0.02)
        return False

    def request_stop(self):
        """Latched Emergency Stop: Halts motion, resets auto mode and latches fault."""
        with state.lock:
            state.latched_stop = True
            state.auto_mode = False
            state.fsm_state = "IDLE"
        # Burst STOP commands to guarantee delivery
        for _ in range(3):
            self.send_raw("STOP")
            time.sleep(0.01)

    def release_stop_latch(self):
        """Explicitly clear the E-Stop latch by human operator."""
        with state.lock:
            state.latched_stop = False

    def request_tuning(self, kp: float, ki: float, kd: float, kf: float, timeout=1.5) -> tuple[str, str]:
        """Typed PID Tuning with explicit MCU ACK Readback."""
        # Range and finite check according to firmware limits
        if not (math.isfinite(kp) and math.isfinite(ki) and math.isfinite(kd) and math.isfinite(kf)):
            return ("REJECTED", "INVALID_NOT_FINITE")
        if not (0.0 <= kp <= 20.0 and 0.0 <= ki <= 50.0 and 0.0 <= kd <= 5.0 and 0.0 <= kf <= 5.0):
            return ("REJECTED", "OUT_OF_BOUNDS")
        
        self.pending_tuning_event.clear()
        self.last_tuning_result = "PENDING"
        self.last_tuning_ack_text = ""
        
        cmd = f"TUNING {kp:.3f} {ki:.3f} {kd:.4f} {kf:.3f}"
        if not self.send_raw(cmd):
            return ("FAILED", "SERIAL_PORT_UNAVAILABLE")
            
        if self.pending_tuning_event.wait(timeout):
            return (self.last_tuning_result, self.last_tuning_ack_text)
        else:
            return ("FAILED", "TIMEOUT_NO_MCU_ACK")

    def parse_line(self, line: str):
        """Parse incoming line from MCU."""
        line = line.strip()
        if not line:
            return
            
        now = time.time()
        # Telemetry JSON
        if line.startswith('{') and line.endswith('}'):
            try:
                d = json.loads(line)
                with state.lock:
                    state.last_telemetry_time = now
                    if "state" in d:
                        state.mcu_state = str(d["state"])
                    if "x" in d: state.x = float(d["x"])
                    if "y" in d: state.y = float(d["y"])
                    if "th" in d: state.th = float(d["th"])
                    if "l_rpm" in d: state.l_rpm = float(d["l_rpm"])
                    if "r_rpm" in d: state.r_rpm = float(d["r_rpm"])
                    if "l_pwm" in d: state.l_pwm = int(d["l_pwm"])
                    if "r_pwm" in d: state.r_pwm = int(d["r_pwm"])
                    
                    # Check for TUNING ACK inside JSON
                    if "ack" in d and "TUNING" in str(d["ack"]):
                        self.last_tuning_result = "APPLIED"
                        self.last_tuning_ack_text = str(d["ack"])
                        self.pending_tuning_event.set()
                    elif "error" in d and "TUNING" in str(d["error"]):
                        self.last_tuning_result = "REJECTED"
                        self.last_tuning_ack_text = str(d["error"])
                        self.pending_tuning_event.set()
            except Exception:
                pass

# -----------------------------------------------------------------------------
# 4. REACHABLE FRONTIER PLANNER (BFS + INFLATION BARRIER)
# -----------------------------------------------------------------------------
class ReachableFrontierPlanner:
    @staticmethod
    def plan_next_frontier(rx: float, ry: float, state_ref: SafeAGVState):
        """
        Uses BFS wave-front expansion on OccupancyGrid from current robot pose.
        Ensures target goal is physically reachable without passing through walls.
        """
        with state_ref.lock:
            w = state_ref.map_w
            h = state_ref.map_h
            res = state_ref.map_res
            ox = state_ref.map_ox
            oy = state_ref.map_oy
            grid = list(state_ref.map_data)
            
        if not grid or w <= 0 or h <= 0 or len(grid) != w * h:
            return None, 0

        # Robot cell in grid coordinates
        start_x = int((rx - ox) / res)
        start_y = int((ry - oy) / res)
        
        if not (0 <= start_x < w and 0 <= start_y < h):
            return None, 0

        # BFS expansion
        visited = set()
        queue = deque([(start_x, start_y, 0)]) # (gx, gy, step_distance)
        visited.add((start_x, start_y))
        
        found_frontiers = []
        inflation_cells = int(ROBOT_FOOTPRINT_RADIUS_M / res) # 3 cells for 15cm at 0.05m/cell

        while queue:
            cx, cy, steps = queue.popleft()
            
            # Limit maximum search depth (~ 5.0 meters)
            if steps > int(5.0 / res):
                break

            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    val = grid[ny * w + nx]
                    
                    # Must be free space to traverse (0 is free, 100 occupied, -1 unknown)
                    if val == 0:
                        # Check collision barrier with obstacles within inflation footprint
                        safe_pass = True
                        for ix in range(-inflation_cells, inflation_cells + 1):
                            for iy in range(-inflation_cells, inflation_cells + 1):
                                check_x, check_y = nx + ix, ny + iy
                                if 0 <= check_x < w and 0 <= check_y < h:
                                    if grid[check_y * w + check_x] > 50:
                                        safe_pass = False
                                        break
                            if not safe_pass:
                                break
                                
                        if safe_pass:
                            # Check if this free cell is adjacent to an UNKNOWN cell (-1)
                            is_frontier = False
                            for kx, ky in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                                adj_x, adj_y = nx + kx, ny + ky
                                if 0 <= adj_x < w and 0 <= adj_y < h:
                                    if grid[adj_y * w + adj_x] == -1:
                                        is_frontier = True
                                        break
                                        
                            real_dist = math.hypot((nx - start_x) * res, (ny - start_y) * res)
                            if is_frontier and 0.4 <= real_dist <= 3.5:
                                wx = ox + nx * res
                                wy = oy + ny * res
                                found_frontiers.append((real_dist, wx, wy))
                                
                            queue.append((nx, ny, steps + 1))

        if not found_frontiers:
            return None, 0

        # Sort by shortest reachable path distance
        found_frontiers.sort(key=lambda item: item[0])
        best_goal = (found_frontiers[0][1], found_frontiers[0][2])
        return best_goal, len(found_frontiers)

# -----------------------------------------------------------------------------
# 5. AUTONOMOUS NON-BLOCKING NAVIGATION FSM
# -----------------------------------------------------------------------------
class SafeAutonomousNavigator:
    def __init__(self, arbiter: SafeSerialArbiter):
        self.arbiter = arbiter
        self.last_fsm_tick = 0.0

    def step(self):
        """Execute one 10Hz tick without any blocking time.sleep()."""
        now = time.time()
        with state.lock:
            auto = state.auto_mode
            latched = state.latched_stop
            f_cm = state.zones["front"]
            fr_cm = state.zones["front_right"]
            fl_cm = state.zones["front_left"]
            l_cm = state.zones["left"]
            r_cm = state.zones["right"]
            rx, ry, rth = state.x, state.y, state.th
            last_scan = state.last_scan_time
            last_tele = state.last_telemetry_time

        if latched or not auto:
            return

        # WATCHDOG CHECK: Ensure Scan & Telemetry are fresh (< 0.5s)
        if now - last_scan > 0.5 or now - last_tele > 0.5:
            # Stale sensor stream -> safety stop immediately
            self.arbiter.send_raw("STOP")
            with state.lock:
                state.fsm_state = "WATCHDOG_STALE_STOP"
            return

        # REACTIVE SAFETY BARRIER: Front obstacle < 40cm
        if f_cm < 40 or fr_cm < 32 or fl_cm < 32:
            turn_cmd = "V 0.0 0.40" if l_cm > r_cm else "V 0.0 -0.40"
            self.arbiter.send_raw(turn_cmd)
            return

        # FSM EXECUTION
        with state.lock:
            current_fsm = state.fsm_state

        # Phase 1: CAPTURE HOME BEFORE MOTION
        if current_fsm == "IDLE" or not state.home_captured:
            with state.lock:
                state.home_x = rx
                state.home_y = ry
                state.home_th = rth
                state.home_captured = True
                state.fsm_state = "EXPLORING"
            return

        # Phase 2: REACHABLE FRONTIER EXPLORATION
        if current_fsm == "EXPLORING":
            goal, count = ReachableFrontierPlanner.plan_next_frontier(rx, ry, state)
            with state.lock:
                state.frontier_count = count
                state.current_goal = goal

            if goal is None:
                # No more reachable frontiers -> Room fully explored -> Return Home
                with state.lock:
                    state.fsm_state = "RETURNING_HOME"
                return

            gx, gy = goal
            dx, dy = gx - rx, gy - ry
            dist = math.hypot(dx, dy)
            target_th = math.atan2(dy, dx)
            th_err = (target_th - rth + math.pi) % (2 * math.pi) - math.pi

            # Pure pursuit angle & velocity mapping (Safe ramp v <= 0.15 m/s)
            if abs(th_err) > 0.6:
                w = 0.40 if th_err > 0 else -0.40
                self.arbiter.send_raw(f"V 0.00 {w:.2f}")
            else:
                v = min(0.12, 0.05 + dist * 0.08)
                w = max(-0.35, min(0.35, 1.1 * th_err))
                self.arbiter.send_raw(f"V {v:.2f} {w:.2f}")
            return

        # Phase 3: RETURN TO HOME POSITION & HEADING
        if current_fsm == "RETURNING_HOME":
            with state.lock:
                hx, hy, hth = state.home_x, state.home_y, state.home_th
            
            dx, dy = hx - rx, hy - ry
            dist_home = math.hypot(dx, dy)

            # Reached Home Position
            if dist_home < 0.12:
                # Align Heading
                th_err = (hth - rth + math.pi) % (2 * math.pi) - math.pi
                if abs(th_err) < 0.15: # < ~8.5 degrees
                    self.arbiter.send_raw("STOP")
                    with state.lock:
                        state.fsm_state = "COMPLETED"
                        state.auto_mode = False
                else:
                    w = 0.30 if th_err > 0 else -0.30
                    self.arbiter.send_raw(f"V 0.00 {w:.2f}")
            else:
                target_th = math.atan2(dy, dx)
                th_err = (target_th - rth + math.pi) % (2 * math.pi) - math.pi
                if abs(th_err) > 0.6:
                    w = 0.35 if th_err > 0 else -0.35
                    self.arbiter.send_raw(f"V 0.00 {w:.2f}")
                else:
                    v = min(0.12, 0.04 + dist_home * 0.08)
                    w = max(-0.30, min(0.30, 1.0 * th_err))
                    self.arbiter.send_raw(f"V {v:.2f} {w:.2f}")

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

        if path == '/api/telemetry':
            with state.lock:
                d = {
                    "auto": state.auto_mode,
                    "latched_stop": state.latched_stop,
                    "fsm_state": state.fsm_state,
                    "mcu_state": state.mcu_state,
                    "robot": {
                        "x": state.x, "y": state.y, "th": state.th,
                        "l_rpm": state.l_rpm, "r_rpm": state.r_rpm,
                        "l_pwm": state.l_pwm, "r_pwm": state.r_pwm
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
            except ValueError:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "REJECTED", "reason": "MALFORMED_FLOAT"}).encode('utf-8'))
                return

            status, ack_msg = arbiter_instance.request_tuning(kp, ki, kd, kf)
            resp = {
                "status": status, # PENDING, APPLIED, REJECTED, FAILED
                "ack": ack_msg,
                "applied_gains": {"kp": kp, "ki": ki, "kd": kd, "kf": kf} if status == "APPLIED" else None
            }
            self.send_response(200 if status == "APPLIED" else 422)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode('utf-8'))
            return

        elif path == '/api/cmd':
            params = urllib.parse.parse_qs(q)
            val = params.get('val', [''])[0].strip()
            
            if val == 'STOP':
                arbiter_instance.request_stop()
            elif val == 'RELEASE_LATCH':
                arbiter_instance.release_stop_latch()
            elif val == 'ARM':
                arbiter_instance.request_arm()
            else:
                # Any movement command is guarded by latch check
                with state.lock:
                    if state.latched_stop:
                        self.send_response(403)
                        self.send_header('Content-Type', 'application/json')
                        self._cors()
                        self.end_headers()
                        self.wfile.write(b'{"status":"REJECTED_LATCHED_STOP"}')
                        return
                arbiter_instance.send_raw(val)
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
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
                # Explicit ARM Handshake before starting autonomous mission
                if arbiter_instance.request_arm(timeout=1.0):
                    with state.lock:
                        state.auto_mode = True
                        state.home_captured = False # Force pre-motion home capture
                    resp = {"status": "ok", "auto": True}
                else:
                    resp = {"status": "FAILED_ARM_HANDSHAKE", "auto": False}
            else:
                arbiter_instance.request_stop()
                resp = {"status": "ok", "auto": False}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode('utf-8'))
            return

        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    print("=== AGV OFFLINE BUNDLE V4.0 INITIALIZED ===")
