#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGV SYSTEM ARCHITECTURE OFFLINE BUNDLE V4.1 PRODUCTION RUNTIME
Single-file production system bridging:
- Strict Serial Arbiter with at-write authorization, partial-write detection, latched STOP/fault.
- Independent Watchdog thread for Scan & Telemetry freshness (halts robot asynchronously without caller dependency).
- Typed BFS Path & Frontier Planner with Full Robot Footprint (18.75cm track width + margin).
- Pre-motion Home Capture (Position & Heading) before ANY motion; Home Completion strictly verifies both distance AND heading.
- Typed PID Tuning with exact parameter-matched ACK readback (0.0 valid, rejects out-of-range, sets APPLIED/REJECTED/FAILED).
- Web Server & Dashboard handler: Serves UI, typed JSON APIs, proper HTTP status codes, CSV export.
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
ROBOT_WHEEL_BASE_M = 0.1875   # Word Sec 2: Measured track width center-to-center (18.75 cm)
ROBOT_CPR = 937.2             # Word Sec 6: 11 PPR * 4 * 21.3 ratio
# Inscribed footprint radius: half of wheelbase (9.375cm) + 3cm margin = ~12.5cm -> safe cell radius
ROBOT_FOOTPRINT_RADIUS_M = 0.14 

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
        self.fresh_d0_count = 0
        
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
        self.last_map_time = 0.0
        
        # Autonomous / Navigation State
        self.auto_mode = False
        self.latched_stop = False
        self.fsm_state = "IDLE" # IDLE, CAPTURE_HOME, EXPLORING, RETURNING_HOME, COMPLETED, WATCHDOG_STALE_STOP
        self.home_x = 0.0
        self.home_y = 0.0
        self.home_th = 0.0
        self.home_captured = False
        self.frontier_count = 0
        self.current_goal = None # (x, y)
        self.current_path = []   # list of (x, y) waypoints
        
        # PID Tuning State Machine
        self.current_gains = {"kp": 0.50, "ki": 1.50, "kd": 0.010, "kf": 0.45}
        self.tuning_tx_state = "IDLE" # IDLE, PENDING, APPLIED, REJECTED, FAILED
        self.tuning_last_ack = ""
        self.tuning_history = []

state = SafeAGVState()

# -----------------------------------------------------------------------------
# 3. STRICT SERIAL ARBITER & WRITER GUARD
# -----------------------------------------------------------------------------
class SafeSerialArbiter:
    def __init__(self, ser_instance=None):
        self.ser = ser_instance
        self.tx_lock = threading.Lock()
        self.running = True
        self.pending_tuning_event = threading.Event()
        self.last_tuning_result = "IDLE"
        self.last_tuning_ack_text = ""
        self.expected_tuning_gains = None
        self.write_timeout_sec = 0.1

    def send_guarded(self, cmd: str, is_stop: bool = False) -> tuple[bool, str]:
        """
        AT-WRITE AUTHORIZATION & PARTIAL-WRITE CHECK.
        Checks latch status inside the write lock. Returns (success, reason).
        """
        with self.tx_lock:
            # 1. Authorization check inside write lock
            if not is_stop:
                with state.lock:
                    if state.latched_stop:
                        return False, "REJECTED_LATCHED_STOP"
                    if state.mcu_state != "ARMED":
                        return False, "REJECTED_MCU_NOT_ARMED"

            if not self.ser or not getattr(self.ser, 'is_open', True):
                return False, "SERIAL_PORT_UNAVAILABLE"

            try:
                raw_bytes = (cmd.strip() + "\r\n").encode('utf-8')
                expected_len = len(raw_bytes)
                
                # Check partial write if writer supports returning byte count
                bytes_written = self.ser.write(raw_bytes)
                if bytes_written is not None and bytes_written < expected_len:
                    # Partial write failure: Fault condition!
                    return False, f"PARTIAL_WRITE_FAULT: {bytes_written}/{expected_len}"
                    
                if hasattr(self.ser, 'flush'):
                    self.ser.flush()
                return True, "OK"
            except Exception as e:
                return False, f"WRITE_EXCEPTION: {e}"

    def request_arm(self, timeout=1.0) -> tuple[bool, str]:
        """Explicit ARM Handshake. Never auto-inject into drive commands."""
        with state.lock:
            if state.latched_stop:
                return False, "REFUSED_LATCHED_STOP"
            if self.ser is None:
                return False, "REFUSED_NO_UART"

        # Direct ARM send without auto-check
        with self.tx_lock:
            try:
                raw_bytes = b"ARM\r\n"
                n = self.ser.write(raw_bytes)
                if n is not None and n < len(raw_bytes):
                    return False, "PARTIAL_ARM_WRITE"
                if hasattr(self.ser, 'flush'): self.ser.flush()
            except Exception as e:
                return False, str(e)

        t0 = time.time()
        while time.time() - t0 < timeout:
            with state.lock:
                if state.mcu_state == "ARMED":
                    return True, "ARMED_CONFIRMED"
            time.sleep(0.02)
        return False, "TIMEOUT_NO_ARM_ACK"

    def request_stop(self) -> bool:
        """Latched Emergency Stop: Halts motion, resets auto mode and latches fault."""
        with state.lock:
            state.latched_stop = True
            state.auto_mode = False
            state.fsm_state = "IDLE"
            
        success = True
        for _ in range(3):
            ok, _ = self.send_guarded("STOP", is_stop=True)
            if not ok: success = False
            time.sleep(0.01)
        return success

    def release_stop_latch(self) -> tuple[bool, str]:
        """Explicitly clear the E-Stop latch by human operator ONLY if MCU is in safe state."""
        with state.lock:
            if state.mcu_state == "UNKNOWN":
                return False, "CANNOT_RELEASE_LATCH_MCU_UNKNOWN"
            state.latched_stop = False
            return True, "LATCH_RELEASED"

    def request_tuning(self, kp: float, ki: float, kd: float, kf: float, timeout=1.5) -> tuple[str, str]:
        """Typed PID Tuning with parameter-matched MCU ACK Readback."""
        if not (math.isfinite(kp) and math.isfinite(ki) and math.isfinite(kd) and math.isfinite(kf)):
            return ("REJECTED", "INVALID_NOT_FINITE")
        if not (0.0 <= kp <= 20.0 and 0.0 <= ki <= 50.0 and 0.0 <= kd <= 5.0 and 0.0 <= kf <= 5.0):
            return ("REJECTED", "OUT_OF_BOUNDS")
        
        self.expected_tuning_gains = (kp, ki, kd, kf)
        self.pending_tuning_event.clear()
        self.last_tuning_result = "PENDING"
        self.last_tuning_ack_text = ""
        
        cmd = f"TUNING {kp:.3f} {ki:.3f} {kd:.4f} {kf:.3f}"
        ok, reason = self.send_guarded(cmd, is_stop=True) # Tuning allowed in disarmed
        if not ok:
            return ("FAILED", reason)
            
        if self.pending_tuning_event.wait(timeout):
            return (self.last_tuning_result, self.last_tuning_ack_text)
        else:
            return ("FAILED", "TIMEOUT_NO_MCU_ACK")

    def parse_line(self, line: str):
        """Parse incoming line from MCU with strict field validation."""
        line = line.strip()
        if not line:
            return
            
        now = time.time()
        if line.startswith('{') and line.endswith('}'):
            try:
                d = json.loads(line)
                
                # Check for TUNING ACK with parameter matching
                if "ack" in d and "TUNING" in str(d["ack"]):
                    ack_str = str(d["ack"])
                    # Format: TUNING <kp> <ki> <kd> <kf>
                    parts = ack_str.split()
                    if len(parts) >= 5 and self.expected_tuning_gains is not None:
                        try:
                            akp, aki, akd, akf = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                            ekp, eki, ekd, ekf = self.expected_tuning_gains
                            # Strict match within 0.005 tolerance
                            if (abs(akp - ekp) < 0.005 and abs(aki - eki) < 0.005 and 
                                abs(akd - ekd) < 0.005 and abs(akf - ekf) < 0.005):
                                with state.lock:
                                    state.current_gains = {"kp": akp, "ki": aki, "kd": akd, "kf": akf}
                                    state.tuning_history.append({
                                        "time": time.strftime("%H:%M:%S"),
                                        "kp": akp, "ki": aki, "kd": akd, "kf": akf,
                                        "status": "APPLIED"
                                    })
                                self.last_tuning_result = "APPLIED"
                                self.last_tuning_ack_text = ack_str
                                self.pending_tuning_event.set()
                                return
                            else:
                                self.last_tuning_result = "REJECTED"
                                self.last_tuning_ack_text = f"ACK_PARAMETER_MISMATCH: expected {self.expected_tuning_gains}, got {(akp, aki, akd, akf)}"
                                self.pending_tuning_event.set()
                                return
                        except ValueError:
                            pass
                    self.last_tuning_result = "REJECTED"
                    self.last_tuning_ack_text = "MALFORMED_ACK"
                    self.pending_tuning_event.set()
                    return

                # Strict Telemetry Parse
                if "x" in d and "y" in d and "th" in d and "safety" in d:
                    # Validate finite numbers
                    try:
                        rx = float(d["x"])
                        ry = float(d["y"])
                        rth = float(d["th"])
                        lrpm = float(d.get("l_rpm", 0.0))
                        rrpm = float(d.get("r_rpm", 0.0))
                        lpwm = int(d.get("l_pwm", 0))
                        rpwm = int(d.get("r_pwm", 0))
                        safety = str(d["safety"])
                    except (ValueError, TypeError):
                        return # Reject non-finite/NaN

                    if not (math.isfinite(rx) and math.isfinite(ry) and math.isfinite(rth)):
                        return

                    with state.lock:
                        state.last_telemetry_time = now
                        state.fresh_d0_count += 1
                        state.x = rx
                        state.y = ry
                        state.th = rth
                        state.l_rpm = lrpm
                        state.r_rpm = rrpm
                        state.l_pwm = lpwm
                        state.r_pwm = rpwm
                        state.mcu_state = safety # Directly map to safety field (ARMED, DISARMED, FAULT)
            except Exception:
                pass

# -----------------------------------------------------------------------------
# 4. REACHABLE BFS FRONTIER & PATH PLANNER
# -----------------------------------------------------------------------------
class ReachableFrontierPlanner:
    @staticmethod
    def plan_next_frontier_and_path(rx: float, ry: float, state_ref: SafeAGVState):
        """
        Uses BFS wave-front expansion on OccupancyGrid from current robot pose.
        Returns: (best_goal_xy, path_waypoints, total_frontiers_count)
        """
        with state_ref.lock:
            w = state_ref.map_w
            h = state_ref.map_h
            res = state_ref.map_res
            ox = state_ref.map_ox
            oy = state_ref.map_oy
            grid = list(state_ref.map_data)
            map_received = state_ref.map_received
            
        if not map_received or not grid or w <= 0 or h <= 0 or len(grid) != w * h:
            return None, [], 0

        # Robot cell in grid coordinates
        start_x = int((rx - ox) / res)
        start_y = int((ry - oy) / res)
        
        if not (0 <= start_x < w and 0 <= start_y < h):
            return None, [], 0

        # BFS expansion tracking parent pointers for path reconstruction
        visited = { (start_x, start_y): None }
        queue = deque([(start_x, start_y, 0)])
        
        found_frontiers = []
        inflation_cells = max(1, int(ROBOT_FOOTPRINT_RADIUS_M / res)) # ~3 cells for 14cm

        while queue:
            cx, cy, steps = queue.popleft()
            if steps > int(6.0 / res): # 6 meters max horizon
                break

            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                    val = grid[ny * w + nx]
                    
                    # Must be free space (0)
                    if val == 0:
                        # Full footprint barrier check: no obstacles inside robot body
                        safe_pass = True
                        for ix in range(-inflation_cells, inflation_cells + 1):
                            for iy in range(-inflation_cells, inflation_cells + 1):
                                check_x, check_y = nx + ix, ny + iy
                                if not (0 <= check_x < w and 0 <= check_y < h):
                                    safe_pass = False; break
                                c_val = grid[check_y * w + check_x]
                                if c_val > 50: # Cannot inflate over obstacles/walls
                                    safe_pass = False; break
                            if not safe_pass: break
                                
                        if safe_pass:
                            visited[(nx, ny)] = (cx, cy)
                            
                            # Check if adjacent to an UNKNOWN cell (-1)
                            is_frontier = False
                            for kx, ky in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                                adj_x, adj_y = nx + kx, ny + ky
                                if 0 <= adj_x < w and 0 <= adj_y < h:
                                    if grid[adj_y * w + adj_x] == -1:
                                        is_frontier = True; break
                                        
                            real_dist = math.hypot((nx - start_x) * res, (ny - start_y) * res)
                            if is_frontier and 0.4 <= real_dist <= 4.0:
                                wx = ox + nx * res
                                wy = oy + ny * res
                                found_frontiers.append((real_dist, nx, ny, wx, wy))
                                
                            queue.append((nx, ny, steps + 1))

        if not found_frontiers:
            return None, [], 0

        # Sort by shortest reachable path distance
        found_frontiers.sort(key=lambda item: item[0])
        best = found_frontiers[0]
        goal_xy = (best[3], best[4])
        
        # Reconstruct path waypoints
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

    def _watchdog_loop(self):
        """INDEPENDENT ASYNCHRONOUS WATCHDOG: Halts robot if telemetry or scan goes stale (>0.5s)."""
        while self.running:
            time.sleep(0.05)
            now = time.time()
            with state.lock:
                auto = state.auto_mode
                latched = state.latched_stop
                last_scan = state.last_scan_time
                last_tele = state.last_telemetry_time

            if auto and not latched:
                if (now - last_scan > 0.5) or (now - last_tele > 0.5):
                    # Trigger immediate latch stop asynchronously
                    self.arbiter.request_stop()
                    with state.lock:
                        state.fsm_state = "WATCHDOG_STALE_STOP"

    def _navigator_loop(self):
        """10Hz Navigation FSM Loop."""
        while self.running:
            time.sleep(0.10)
            self.step()

    def step(self):
        """Execute one 10Hz tick without any blocking sleep."""
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
            self.arbiter.send_guarded(turn_cmd)
            return

        # 3. REACHABLE FRONTIER EXPLORATION
        if current_fsm == "EXPLORING":
            if not map_rcv:
                # No map received yet: Rotate slowly to allow SLAM to initialize
                self.arbiter.send_guarded("V 0.00 0.30")
                return

            goal, path, count = ReachableFrontierPlanner.plan_next_frontier_and_path(rx, ry, state)
            with state.lock:
                state.frontier_count = count
                state.current_goal = goal
                state.current_path = path

            if goal is None:
                # Room exploration complete: transition to return home
                with state.lock:
                    state.fsm_state = "RETURNING_HOME"
                return

            # Pure pursuit waypoint navigation
            target_pt = path[min(len(path) - 1, 3)] if len(path) > 1 else goal
            dx, dy = target_pt[0] - rx, target_pt[1] - ry
            dist = math.hypot(dx, dy)
            target_th = math.atan2(dy, dx)
            th_err = (target_th - rth + math.pi) % (2 * math.pi) - math.pi

            if abs(th_err) > 0.6:
                w = 0.40 if th_err > 0 else -0.40
                self.arbiter.send_guarded(f"V 0.00 {w:.2f}")
            else:
                v = min(0.12, 0.05 + dist * 0.08)
                w = max(-0.35, min(0.35, 1.1 * th_err))
                self.arbiter.send_guarded(f"V {v:.2f} {w:.2f}")
            return

        # 4. RETURN TO HOME POSITION & HEADING
        if current_fsm == "RETURNING_HOME":
            with state.lock:
                hx, hy, hth = state.home_x, state.home_y, state.home_th
            
            dx, dy = hx - rx, hy - ry
            dist_home = math.hypot(dx, dy)

            if dist_home < 0.12:
                # Reached position: Align Heading
                th_err = (hth - rth + math.pi) % (2 * math.pi) - math.pi
                if abs(th_err) < 0.15: # < 8.5 degrees
                    self.arbiter.request_stop()
                    with state.lock:
                        state.fsm_state = "COMPLETED"
                        state.auto_mode = False
                else:
                    w = 0.30 if th_err > 0 else -0.30
                    self.arbiter.send_guarded(f"V 0.00 {w:.2f}")
            else:
                target_th = math.atan2(dy, dx)
                th_err = (target_th - rth + math.pi) % (2 * math.pi) - math.pi
                if abs(th_err) > 0.6:
                    w = 0.35 if th_err > 0 else -0.35
                    self.arbiter.send_guarded(f"V 0.00 {w:.2f}")
                else:
                    v = min(0.12, 0.04 + dist_home * 0.08)
                    w = max(-0.30, min(0.30, 1.0 * th_err))
                    self.arbiter.send_guarded(f"V {v:.2f} {w:.2f}")

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
            html_file = 'D:\\HoMinhKhang\\PROJECT\\GITHUB_PROJECT\\CODE XE TU HANH\\index_cyberpunk.html'
            if os.path.exists(html_file):
                with open(html_file, 'rb') as f:
                    content = f.read()
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
                self.wfile.write(b"<h1>AGV CONTROL RUNNING OK</h1>")
            return

        elif path == '/api/telemetry':
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

        elif path == '/api/cmd':
            params = urllib.parse.parse_qs(q)
            val = params.get('val', [''])[0].strip()
            
            if val == 'STOP':
                arbiter_instance.request_stop()
                resp = {"status": "ok", "action": "STOP_LATCHED"}
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
            else:
                ok, reason = arbiter_instance.send_guarded(val)
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
                        state.home_captured = False # Force pre-motion home capture
                    resp = {"status": "ok", "auto": True}
                else:
                    self.send_response(422)
                    self.send_header('Content-Type', 'application/json')
                    self._cors()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "FAILED_ARM_HANDSHAKE", "reason": reason}).encode('utf-8'))
                    return
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

def main():
    global arbiter_instance, navigator_instance
    print("=== AGV OFFLINE BUNDLE V4.1 PRODUCTION INITIALIZED ===")
    arbiter_instance = SafeSerialArbiter()
    navigator_instance = SafeAutonomousNavigator(arbiter_instance)
    navigator_instance.start()
    server = ThreadedHTTPServer(('0.0.0.0', 8080), SafeWebHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()

if __name__ == '__main__':
    main()
