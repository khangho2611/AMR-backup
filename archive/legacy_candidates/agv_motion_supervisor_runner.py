#!/usr/bin/env python3
"""
agv_motion_supervisor_runner.py
=============================================================================
Module Giám Sát Chuyển Động Thực Thi (AGV Motion Supervisor Runner).
Điều khiển chuyển động ngắn có chốt chặn vật lý và bảo vệ đa tầng:
1. Chuyển đổi vận tốc -> Wheel RPM (R = 0.0366m).
2. Ramp rate bounded: Gia tốc mượt mà a <= 0.15 m/s^2.
3. Overspeed guard: E-Stop nếu v_odom > 1.15 * v_target hoặc RPM > 165.
4. RPM mismatch guard: E-Stop nếu |l_rpm - r_rpm| > 20 RPM khi đi thẳng (>100ms).
5. Hard Time Cap: Ngắt cứng khi chạm deadline (1.5s).
6. STOP completion lifecycle: Gửi STOP -> chờ fresh D0 DISARMED (timeout 200ms).
=============================================================================
"""

import argparse
import json
import math
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

def is_valid_finite(val: Any) -> bool:
    if val is None or isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    return math.isfinite(val)

WHEEL_RADIUS_M: float = 0.0366
TRACKWIDTH_M: float = 0.1875
MAX_ACCEL_MPS2: float = 0.15
MAX_WHEEL_RPM_CAP: float = 165.0
DEADMAN_TIMEOUT_S: float = 0.200
CONFIRMATION_TIMEOUT_S: float = 0.200

EXACT_BOOT_BANNER: str = "ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"
EXACT_I2C_SCAN_BANNER: str = "Scanning I2C bus..."
STARTUP_DEADLINE_S: float = 3.5
MAX_STARTUP_LINES: int = 35
SETTLING_DEADLINE_S: float = 2.0
MAX_SETTLING_LINES: int = 15
MAX_GAP_S: float = 1.5
MAX_AGE_S: float = 1.5
def speed_to_wheel_rpm(v_mps: float) -> float:
    """Quy đổi từ vận tốc dài (m/s) sang Wheel RPM với bán kính R = 0.0366m."""
    return (v_mps * 60.0) / (2.0 * math.pi * WHEEL_RADIUS_M)


def wheel_rpm_to_speed(rpm: float) -> float:
    """Quy đổi từ Wheel RPM sang vận tốc dài (m/s)."""
    return (rpm * 2.0 * math.pi * WHEEL_RADIUS_M) / 60.0


EXACT_BOOT_BANNER: str = "ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"
EXACT_I2C_SCAN_BANNER: str = "Scanning I2C bus..."


def validate_telemetry_sample(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Kiểm tra strict telemetry sample kế thừa từ collector 4b32."""
    forbidden_in_telemetry = ["error", "fault", "info", "ack", "status_msg"]
    for bad_key in forbidden_in_telemetry:
        if bad_key in payload:
            return False, f"MIXED_SCHEMA_FORBIDDEN_KEY_{bad_key.upper()}"

    required_keys = ["safety", "l_tgt", "r_tgt", "l_pwm", "r_pwm", "l_rpm", "r_rpm", "v", "w"]
    for k in required_keys:
        if k not in payload:
            return False, f"MISSING_KEY_{k}"

    safety = payload.get("safety")
    if not isinstance(safety, str) or safety != "DISARMED":
        return False, f"INVALID_SAFETY_STATE_{safety}"

    numeric_fields = ["l_tgt", "r_tgt", "l_pwm", "r_pwm", "l_rpm", "r_rpm", "v", "w", "x", "y", "th"]
    for f in numeric_fields:
        if f in payload and not is_valid_finite(payload[f]):
            return False, f"NON_FINITE_OR_INVALID_{f}"

    for pwm_key in ["l_pwm", "r_pwm"]:
        val = payload[pwm_key]
        if isinstance(val, float) and not val.is_integer():
            return False, f"FRACTIONAL_PWM_{pwm_key}_{val}"

    l_tgt = float(payload["l_tgt"])
    r_tgt = float(payload["r_tgt"])
    l_pwm = float(payload["l_pwm"])
    r_pwm = float(payload["r_pwm"])
    l_rpm = float(payload["l_rpm"])
    r_rpm = float(payload["r_rpm"])
    v = float(payload["v"])
    w = float(payload["w"])

    if l_tgt != 0.0 or r_tgt != 0.0:
        return False, f"NON_ZERO_TARGET: l={l_tgt}, r={r_tgt}"
    if l_pwm != 0.0 or r_pwm != 0.0:
        return False, f"NON_ZERO_PWM: l={l_pwm}, r={r_pwm}"
    if abs(l_rpm) > 1e-3 or abs(r_rpm) > 1e-3:
        return False, f"NON_ZERO_RPM: l={l_rpm}, r={r_rpm}"
    if abs(v) > 1e-4 or abs(w) > 1e-4:
        return False, f"NON_ZERO_VELOCITY: v={v}, w={w}"

    return True, "SAMPLE_VALID"


class TransportWrapper:
    """Wrapper bao bọc serial transport để ghi nhận chính xác toàn bộ TX logs."""

    def __init__(self, raw_serial: Any, clock_fn: Any = time.monotonic):
        self._ser = raw_serial
        self._clock = clock_fn
        self.tx_records: List[Dict[str, Any]] = []

    def write(self, data: bytes) -> int:
        t = self._clock()
        data_str = data.decode("utf-8", errors="replace")
        expected_len = len(data)
        try:
            n = self._ser.write(data)
            written = n if n is not None else 0
            is_full = (written == expected_len)
            self.tx_records.append({
                "t": t,
                "bytes": data_str,
                "expected": expected_len,
                "written": written,
                "success": is_full
            })
            return written
        except Exception as e:
            self.tx_records.append({
                "t": t,
                "bytes": data_str,
                "expected": expected_len,
                "written": 0,
                "error": str(e),
                "success": False
            })
            raise

    def readline(self) -> bytes:
        if hasattr(self._ser, "readline"):
            return self._ser.readline()
        return b""

    def flush(self) -> None:
        if hasattr(self._ser, "flush"):
            try:
                self._ser.flush()
            except Exception as e:
                self.tx_records.append({
                    "t": self._clock(),
                    "action": "flush",
                    "error": str(e),
                    "success": False
                })
                raise

    def close(self) -> None:
        if hasattr(self._ser, "close"):
            self._ser.close()


class MotionSupervisor:
    """Bộ điều phối và giám sát chu trình chuyển động fail-closed."""

    def __init__(
        self,
        serial_arbiter: Any,
        target_v: float = 0.05,
        target_dist_m: float = 0.050,
        nominal_time_s: float = 1.0,
        hard_time_cap_s: float = 1.5
    ) -> None:
        self.arbiter = serial_arbiter
        self.target_v = min(target_v, 0.05)  # Khóa cứng không vượt quá gate limit 0.05 m/s
        self.target_dist_m = target_dist_m
        self.nominal_time_s = nominal_time_s
        self.hard_time_cap_s = hard_time_cap_s

        self.start_mono: Optional[float] = None
        self.last_cycle_mono: Optional[float] = None
        self.current_cmd_v: float = 0.0
        self.is_active: bool = False
        self.fault_tripped: bool = False
        self.fault_reason: Optional[str] = None
        self.stop_requested_mono: Optional[float] = None
        self.stop_confirmed: bool = False
        self.stop_write_success: bool = False
        self.stop_write_failed: bool = False

    def check_stop_confirmation(self, rx_mono: float, latest_d0: Dict[str, Any]) -> bool:
        """Kiểm tra điều kiện xác nhận dừng từ luồng D0 fresh (Parser ONCE)."""
        if self.stop_confirmed:
            return True
        if self.stop_requested_mono is None:
            return False

        # Nếu lệnh STOP đã gửi bị lỗi ghi (partial / exception) -> Latch FAULT, cấm confirm PASS!
        if self.stop_write_failed:
            self.fault_tripped = True
            if self.fault_reason is None:
                self.fault_reason = "STOP_WRITE_FAILED"
            return False

        is_fresh = rx_mono > self.stop_requested_mono
        is_safe_zero = (
            latest_d0.get("safety") == "DISARMED"
            and float(latest_d0.get("l_tgt", 0.0)) == 0.0
            and float(latest_d0.get("r_tgt", 0.0)) == 0.0
            and float(latest_d0.get("l_pwm", 0.0)) == 0.0
            and float(latest_d0.get("r_pwm", 0.0)) == 0.0
        )
        gate_confirmed = getattr(self.arbiter, "stop_confirmed", False)
        gate_fault = getattr(self.arbiter, "local_fault", False) or getattr(self.arbiter, "safety_state", "") == "FAULT"

        if gate_fault:
            self.fault_tripped = True
            if self.fault_reason is None:
                self.fault_reason = "GATE_FAULT_TRIPPED"
            return False

        if is_fresh and is_safe_zero and gate_confirmed and self.stop_write_success:
            self.stop_confirmed = True
            return True
        return False

    def start_motion(self, now_mono: float) -> bool:
        if self.fault_tripped:
            return False
        # Chỉ start khi Gate đã ARMED thành công
        if hasattr(self.arbiter, "safety_state") and self.arbiter.safety_state != "ARMED":
            return False
        self.start_mono = now_mono
        self.current_cmd_v = 0.0
        self.is_active = True
        self.stop_confirmed = False
        return True

    def update_cycle(self, now_mono: float, latest_d0: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]:
        """
        Thực thi mỗi chu kỳ điều khiển:
        - R3 Guard: Kiểm tra bắt buộc latest_d0 đầy đủ các trường số học hữu hạn.
        - R4 Guard: Kiểm tra monotonic clock phải tiến về phía trước (now_mono > last_cycle_mono).
        - R1 & R2 Guard: Shared STOP confirmation với Gate. Chỉ chấp nhận confirm khi:
          * Gói D0 có timestamp rx_mono > stop_requested_mono
          * Gói D0 có l_tgt == 0, r_tgt == 0, l_pwm == 0, r_pwm == 0 và safety == 'DISARMED'
          * Trạng thái gate.stop_confirmed == True (đồng thuận 100% với gate)
        """
        if latest_d0 is None or not isinstance(latest_d0, dict) or not latest_d0:
            # T5 Fix: Không gọi trigger_estop làm dời stop_requested_mono nếu xe đã STOP
            if self.is_active:
                self.trigger_estop(now_mono, "REJECT_MISSING_TELEMETRY")
            elif self.stop_requested_mono is not None and not self.stop_confirmed:
                # Nếu đang chờ confirm STOP mà data bị missing -> kiểm tra deadline từ first_stop
                if (now_mono - self.stop_requested_mono) > CONFIRMATION_TIMEOUT_S:
                    self.fault_tripped = True
                    self.fault_reason = "STOP_CONFIRMATION_TIMEOUT"
                    return False, "STOP_CONFIRMATION_TIMEOUT"
            return False, "REJECT_MISSING_TELEMETRY"

        # R4 Fix: Kiểm tra thời gian phải tiến thực sự (dt > 0)
        if self.last_cycle_mono is not None and now_mono <= self.last_cycle_mono:
            self.trigger_estop(now_mono, "REJECT_NON_FORWARDING_CLOCK")
            return False, "REJECT_NON_FORWARDING_CLOCK"

        dt = now_mono - self.last_cycle_mono if self.last_cycle_mono is not None else 0.05
        self.last_cycle_mono = now_mono

        if not self.is_active:
            # Nếu đang chờ confirm STOP sau khi kết thúc
            if self.stop_requested_mono is not None and not self.stop_confirmed:
                if (now_mono - self.stop_requested_mono) > CONFIRMATION_TIMEOUT_S:
                    self.fault_tripped = True
                    self.fault_reason = "STOP_CONFIRMATION_TIMEOUT"
                    return False, "STOP_CONFIRMATION_TIMEOUT"

                # T4 Fix: Bắt buộc gói D0 phải mang timestamp rx_mono hợp lệ từ transport
                # Tuyệt đối cấm fabricate lấy now_mono gán vào rx_mono
                if "rx_mono" not in latest_d0 or not isinstance(latest_d0["rx_mono"], (int, float)):
                    return False, "STOP_UNCONFIRMED_MISSING_RX_MONO"

                rx_mono = float(latest_d0["rx_mono"])
                # Lưu ý: Tuyệt đối không gọi self.arbiter.process_incoming_line ở đây!
                # Reader loop đã là single parser duy nhất đưa raw bytes/string vào Gate!

                # R1 Fix: Kiểm tra độ tươi rx_mono > stop_requested_mono và target/pwm == 0
                is_fresh_d0 = rx_mono > self.stop_requested_mono
                is_safe_zero = (
                    latest_d0.get("safety") == "DISARMED"
                    and float(latest_d0.get("l_tgt", 0.0)) == 0.0
                    and float(latest_d0.get("r_tgt", 0.0)) == 0.0
                    and float(latest_d0.get("l_pwm", 0.0)) == 0.0
                    and float(latest_d0.get("r_pwm", 0.0)) == 0.0
                )
                gate_confirmed = getattr(self.arbiter, "stop_confirmed", False)

                if is_fresh_d0 and is_safe_zero and gate_confirmed:
                    self.stop_confirmed = True
                    return True, "STOP_CONFIRMED"
                else:
                    return False, "STOP_UNCONFIRMED_STALE_OR_UNSAFE"

            return True, "IDLE"

        if self.start_mono is None:
            self.start_mono = now_mono

        elapsed = now_mono - self.start_mono

        # 1. Hard Time Cap Guard
        if elapsed >= self.hard_time_cap_s:
            self.trigger_estop(now_mono, "HARD_TIME_CAP_EXCEEDED")
            return False, "HARD_TIME_CAP_EXCEEDED"

        # 2. R3, T1, T2, T3 Fix: Kiểm tra tính hữu hạn đầy đủ của các trường telemetry và độ tươi
        required_d0 = ["safety", "l_rpm", "r_rpm"]
        for k in required_d0:
            if k not in latest_d0:
                self.trigger_estop(now_mono, f"REJECT_MISSING_TELEMETRY_FIELD_{k}")
                return False, f"REJECT_MISSING_TELEMETRY_FIELD_{k}"

        # T1 & T2 Fix: Validate kiểu số hữu hạn cho l_rpm và r_rpm
        val_l = latest_d0.get("l_rpm")
        val_r = latest_d0.get("r_rpm")
        if (
            not isinstance(val_l, (int, float))
            or isinstance(val_l, bool)
            or not is_valid_finite(val_l)
            or not isinstance(val_r, (int, float))
            or isinstance(val_r, bool)
            or not is_valid_finite(val_r)
        ):
            self.trigger_estop(now_mono, "REJECT_INVALID_OR_NAN_RPM")
            return False, "REJECT_INVALID_OR_NAN_RPM"

        # T3 Fix: Kiểm tra độ tươi của telemetry (rx_mono không được quá cũ)
        if "rx_mono" in latest_d0:
            rx_mono_val = latest_d0.get("rx_mono")
            if not isinstance(rx_mono_val, (int, float)) or (now_mono - rx_mono_val) > 0.5:
                self.trigger_estop(now_mono, "REJECT_STALE_TELEMETRY")
                return False, "REJECT_STALE_TELEMETRY"

        l_rpm = float(val_l)
        r_rpm = float(val_r)
        current_max_rpm = max(abs(l_rpm), abs(r_rpm))

        target_rpm = speed_to_wheel_rpm(self.target_v)
        if current_max_rpm > (1.15 * target_rpm) or current_max_rpm > MAX_WHEEL_RPM_CAP:
            self.trigger_estop(now_mono, f"OVERSPEED_TRIPPED: max_rpm={current_max_rpm}")
            return False, "OVERSPEED_TRIPPED"

        # 4. RPM Mismatch Guard (Chặn lệch bánh khi đi thẳng)
        if abs(l_rpm - r_rpm) > 20.0:
            self.trigger_estop(now_mono, f"RPM_MISMATCH_TRIPPED: diff={abs(l_rpm - r_rpm)}")
            return False, "RPM_MISMATCH_TRIPPED"

        # 5. Ramp-up vận tốc mượt mà theo dt thực
        if self.current_cmd_v < self.target_v:
            self.current_cmd_v = min(self.target_v, self.current_cmd_v + MAX_ACCEL_MPS2 * dt)

        # 6. Kiểm tra thời gian danh định để chuyển sang phanh dừng
        if elapsed >= self.nominal_time_s:
            self.trigger_estop(now_mono, "NOMINAL_DURATION_REACHED")
            return True, "NOMINAL_DURATION_REACHED"

        # 7. Gửi lệnh vận tốc qua API chính thức của Gate
        if hasattr(self.arbiter, "send_velocity_command"):
            token = getattr(self.arbiter, "active_token", "")
            epoch = getattr(self.arbiter, "current_epoch", 0)
            deadline = now_mono + DEADMAN_TIMEOUT_S
            accepted, reason = self.arbiter.send_velocity_command(
                v=self.current_cmd_v,
                w=0.0,
                now_mono=now_mono,
                epoch=epoch,
                token=token,
                command_deadline=deadline
            )
            if not accepted:
                self.trigger_estop(now_mono, f"GATE_REJECTED_CMD: {reason}")
                return False, f"GATE_REJECTED_CMD: {reason}"

        return True, "RUNNING"

    def trigger_estop(self, now_mono: float, reason: str) -> None:
        """Kích hoạt phanh dừng khẩn cấp và chuyển gate sang giám sát STOP completion."""
        self.is_active = False
        if reason != "NOMINAL_DURATION_REACHED":
            self.fault_tripped = True
            if self.fault_reason is None:
                self.fault_reason = reason
        self.current_cmd_v = 0.0
        if self.stop_requested_mono is None:
            self.stop_requested_mono = now_mono

        write_ok = False
        if hasattr(self.arbiter, "request_emergency_stop"):
            res = self.arbiter.request_emergency_stop(now_mono)
            if isinstance(res, tuple):
                write_ok = bool(res[0])
            elif isinstance(res, bool):
                write_ok = res
            else:
                write_ok = True
        elif hasattr(self.arbiter, "send_stop"):
            res = self.arbiter.send_stop(now_mono)
            write_ok = bool(res) if res is not None else True

        if write_ok:
            self.stop_write_success = True
            self.stop_write_failed = False
        else:
            self.stop_write_success = False
            self.stop_write_failed = True
            self.fault_tripped = True
            if self.fault_reason is None:
                self.fault_reason = "STOP_WRITE_FAILED"


# =============================================================================
# HARDWARE EXECUTABLE RUNTIME VỚI THREAD READER & WATCHDOG ĐỘC LẬP
# =============================================================================

class HardwareMotionRunner:
    """Thực thi chu trình chuyển động hoàn chỉnh với Sole Serial Owner và Threads."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baud: int = 115200,
        target_v: float = 0.04,
        nominal_time: float = 1.0,
        hard_time_cap: float = 1.5,
        output_dir: str = "/home/khangho/evidence_motion_live",
        mock_serial: Optional[Any] = None,
        clock_fn: Any = time.monotonic,
    ):
        # 1. Chốt chặn CLI typed & finite bounds nghiêm ngặt
        if not is_valid_finite(target_v) or target_v <= 0 or target_v > 0.05:
            raise ValueError(f"target_v={target_v} không hợp lệ (phải hữu hạn, > 0 và <= 0.05 m/s)")
        if not is_valid_finite(nominal_time) or nominal_time <= 0:
            raise ValueError(f"nominal_time={nominal_time} không hợp lệ (phải hữu hạn và > 0)")
        if not is_valid_finite(hard_time_cap) or hard_time_cap < nominal_time:
            raise ValueError(f"hard_time_cap={hard_time_cap} không hợp lệ (phải >= nominal_time)")

        self.port = port
        self.baud = baud
        self.target_v = target_v
        self.nominal_time = nominal_time
        self.hard_time_cap = hard_time_cap
        self.output_dir = output_dir
        self.mock_serial = mock_serial
        self.clock = clock_fn

        self.ser = None
        self.transport = None
        self.lock_fd = None
        self.lock_path = f"/tmp/agv_runner_{os.path.basename(port)}.lock"
        self.arbiter = None
        self.supervisor = None

        self.running = False
        self.reader_thread = None
        self.watchdog_thread = None

        self.latest_d0: Optional[Dict[str, Any]] = None
        self.d0_lock = threading.Lock()
        self.d0_event = threading.Event()

        self.evidence_records: List[Dict[str, Any]] = []
        self.tx_records: List[Dict[str, Any]] = []
        self.final_report: Dict[str, Any] = {}

        # FSM Preflight State
        self.fsm_diag_state = 0
        self.preflight_open_mono: Optional[float] = None
        self.preflight_start_mono: Optional[float] = None
        self.preflight_first_mono: Optional[float] = None
        self.preflight_last_mono: Optional[float] = None
        self.preflight_valid_samples: List[Dict[str, Any]] = []
        self.preflight_failed = False
        self.preflight_fail_reason: Optional[str] = None
        self.preflight_passed = False

    def acquire_port_lock(self) -> bool:
        if self.mock_serial is not None:
            return True
        try:
            import fcntl
            self.lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o666)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except Exception as e:
            self.final_report["lock_error"] = str(e)
            return False

    def release_port_lock(self) -> None:
        if self.lock_fd is not None:
            try:
                import fcntl
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                os.close(self.lock_fd)
                if os.path.exists(self.lock_path):
                    os.unlink(self.lock_path)
            except Exception:
                pass
            self.lock_fd = None

    def open_transport(self) -> bool:
        if self.mock_serial is not None:
            self.ser = self.mock_serial
            self.transport = TransportWrapper(self.ser, clock_fn=self.clock)
            return True
        try:
            import serial
            raw_s = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=0.1,
                write_timeout=0.5
            )
            try:
                raw_s.exclusive = True
            except Exception:
                pass
            self.ser = raw_s
            self.transport = TransportWrapper(self.ser, clock_fn=self.clock)
            return True
        except Exception as e:
            self.final_report["transport_error"] = str(e)
            return False

    def reader_loop(self) -> None:
        """Reader duy nhất: đọc dòng, gán rx_mono ngay sau khi đọc, validate preflight, đẩy qua Gate."""
        while self.running:
            try:
                transport_obj = self.transport if self.transport is not None else self.ser
                if hasattr(transport_obj, "readline"):
                    line_bytes = transport_obj.readline()
                else:
                    time.sleep(0.01)
                    continue

                if not line_bytes:
                    now = self.clock()
                    if not self.preflight_passed and not self.preflight_failed and self.preflight_last_mono:
                        if (now - self.preflight_last_mono) > 1.5:
                            self.preflight_failed = True
                            self.preflight_fail_reason = f"PREFLIGHT_STREAM_GAP: {now - self.preflight_last_mono:.3f}s > 1.5s"
                    continue

                rx_mono = self.clock()
                line_str = line_bytes.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                rec = {
                    "rx_mono": rx_mono,
                    "raw_line": line_str
                }
                self.evidence_records.append(rec)

                # -------------------------------------------------------------
                # STARTUP FSM & PREFLIGHT VALIDATOR (Collector 4b32 logic)
                # -------------------------------------------------------------
                if self.preflight_open_mono is None:
                    self.preflight_open_mono = rx_mono
                lines_seen = len(self.evidence_records)
                startup_elapsed = rx_mono - self.preflight_open_mono

                parsed_json = None
                try:
                    parsed_json = json.loads(line_str)
                except Exception:
                    if not self.preflight_passed:
                        # Trong giai đoạn đầu cho phép corrupt ROM boot <= 2.0s và <= 15 dòng
                        if self.fsm_diag_state == 0 and startup_elapsed <= SETTLING_DEADLINE_S and lines_seen <= MAX_SETTLING_LINES:
                            rec["classification"] = "ROM_BOOT_CORRUPT"
                        else:
                            self.preflight_failed = True
                            self.preflight_fail_reason = "PREFLIGHT_CORRUPT_NON_JSON"
                    continue

                if not isinstance(parsed_json, dict):
                    if not self.preflight_passed:
                        self.preflight_failed = True
                        self.preflight_fail_reason = "PREFLIGHT_NON_DICT_JSON"
                    continue

                if "error" in parsed_json or parsed_json.get("fault") is True:
                    self.final_report["hardware_error"] = parsed_json.get("error", "HARDWARE_FAULT")
                    if not self.preflight_passed:
                        self.preflight_failed = True
                        self.preflight_fail_reason = f"PREFLIGHT_HARDWARE_ERROR: {parsed_json.get('error')}"
                    if self.supervisor:
                        self.supervisor.trigger_estop(rx_mono, f"HARDWARE_ERROR: {parsed_json.get('error')}")

                disallowed_in_diag = ["safety", "fault", "l_pwm", "r_pwm", "l_tgt", "r_tgt", "ack", "error"]
                has_bad_diag_keys = any(k in parsed_json for k in disallowed_in_diag)

                # 1. Boot Banner
                if not has_bad_diag_keys and set(parsed_json.keys()) == {"info"} and parsed_json.get("info") == EXACT_BOOT_BANNER:
                    if self.fsm_diag_state == 0 and startup_elapsed <= STARTUP_DEADLINE_S and lines_seen <= MAX_STARTUP_LINES:
                        self.fsm_diag_state = 1
                        rec["classification"] = "BOOT_BANNER"
                        self.preflight_last_mono = rx_mono
                        continue
                    else:
                        self.preflight_failed = True
                        self.preflight_fail_reason = f"PREFLIGHT_INVALID_BOOT_BANNER: state={self.fsm_diag_state}, elapsed={startup_elapsed:.3f}s"
                        continue

                # 2. I2C Scan Banner
                if not has_bad_diag_keys and set(parsed_json.keys()) == {"info"} and parsed_json.get("info") == EXACT_I2C_SCAN_BANNER:
                    if self.fsm_diag_state in [0, 1] and startup_elapsed <= STARTUP_DEADLINE_S and lines_seen <= MAX_STARTUP_LINES:
                        self.fsm_diag_state = 2
                        rec["classification"] = "I2C_SCAN_BANNER"
                        self.preflight_last_mono = rx_mono
                        continue
                    else:
                        self.preflight_failed = True
                        self.preflight_fail_reason = f"PREFLIGHT_INVALID_I2C_SCAN_BANNER: state={self.fsm_diag_state}, elapsed={startup_elapsed:.3f}s"
                        continue

                # 3. I2C Found
                if not has_bad_diag_keys and set(parsed_json.keys()) == {"i2c_found"}:
                    addr_val = parsed_json.get("i2c_found")
                    valid_addr = False
                    if isinstance(addr_val, str) and addr_val.startswith("0x") and len(addr_val) == 4:
                        try:
                            int_a = int(addr_val, 16)
                            if 1 <= int_a <= 127:
                                valid_addr = True
                        except ValueError:
                            pass
                    if self.fsm_diag_state == 2 and valid_addr and startup_elapsed <= STARTUP_DEADLINE_S and lines_seen <= MAX_STARTUP_LINES:
                        self.fsm_diag_state = 3
                        rec["classification"] = "I2C_FOUND"
                        self.preflight_last_mono = rx_mono
                        continue
                    else:
                        self.preflight_failed = True
                        self.preflight_fail_reason = f"PREFLIGHT_INVALID_I2C_FOUND: {addr_val}"
                        continue

                # 4. VIN_MV
                if not has_bad_diag_keys and set(parsed_json.keys()) == {"vin_mv"}:
                    vin_val = parsed_json.get("vin_mv")
                    valid_vin = isinstance(vin_val, int) and not isinstance(vin_val, bool) and 1 <= vin_val <= 4294967295
                    if self.fsm_diag_state == 3 and valid_vin and startup_elapsed <= STARTUP_DEADLINE_S and lines_seen <= MAX_STARTUP_LINES:
                        self.fsm_diag_state = 4
                        rec["classification"] = "VIN_MV"
                        self.preflight_last_mono = rx_mono
                        continue
                    else:
                        self.preflight_failed = True
                        self.preflight_fail_reason = f"PREFLIGHT_INVALID_VIN: {vin_val}"
                        continue

                # Nếu chưa pass preflight và đang trong giai đoạn preflight:
                if not self.preflight_passed:
                    # Chặn đứng trường hợp scan xong (state=2) mà không thấy I2C Found/Error đã nhảy sang D0
                    if self.fsm_diag_state == 2:
                        self.preflight_failed = True
                        self.preflight_fail_reason = "PREFLIGHT_MISSING_I2C_FOUND_AFTER_SCAN"

                    if self.preflight_last_mono and (rx_mono - self.preflight_last_mono) > MAX_GAP_S:
                        self.preflight_failed = True
                        self.preflight_fail_reason = f"PREFLIGHT_STREAM_GAP: {rx_mono - self.preflight_last_mono:.3f}s > {MAX_GAP_S}s"

                    is_valid_d0, d0_reason = validate_telemetry_sample(parsed_json)
                    if not is_valid_d0:
                        self.preflight_failed = True
                        self.preflight_fail_reason = f"PREFLIGHT_UNSAFE_TELEMETRY: {d0_reason}"
                    else:
                        if self.fsm_diag_state in [3, 4]:
                            self.fsm_diag_state = 5
                            self.preflight_first_mono = rx_mono
                            self.preflight_valid_samples.clear()

                        if self.preflight_first_mono is None:
                            self.preflight_first_mono = rx_mono
                        self.preflight_last_mono = rx_mono
                        self.preflight_valid_samples.append(parsed_json)

                        span = rx_mono - self.preflight_first_mono
                        if span >= 10.0 and len(self.preflight_valid_samples) >= 80:
                            self.preflight_passed = True

                # -------------------------------------------------------------
                # ĐẨY QUA GATE PARSE (DUY NHẤT 1 LẦN TRÊN READER)
                # -------------------------------------------------------------
                if hasattr(self.arbiter, "process_incoming_line"):
                    parsed_pkt = self.arbiter.process_incoming_line(line_str, rx_mono)
                else:
                    parsed_pkt = parsed_json

                if parsed_pkt and isinstance(parsed_pkt, dict) and "safety" in parsed_pkt:
                    parsed_pkt["rx_mono"] = rx_mono
                    parsed_pkt["raw_line"] = line_str
                    with self.d0_lock:
                        self.latest_d0 = parsed_pkt
                        self.d0_event.set()

                    if self.supervisor and not self.supervisor.stop_confirmed:
                        self.supervisor.check_stop_confirmation(rx_mono, parsed_pkt)

            except Exception as e:
                self.evidence_records.append({"error": f"READER_EXCEPTION: {str(e)}"})
                break

    def watchdog_loop(self) -> None:
        """Watchdog độc lập giám sát mất telemetry, caller im lặng, và hoàn tất STOP confirmation."""
        while self.running:
            time.sleep(0.02)
            now = self.clock()
            with self.d0_lock:
                last_pkt = self.latest_d0

            if not self.supervisor:
                continue

            # 1. Nếu supervisor đang active: kiểm soát mất telemetry và hard time cap
            if self.supervisor.is_active:
                if last_pkt and "rx_mono" in last_pkt:
                    if (now - last_pkt["rx_mono"]) > 0.250:
                        self.supervisor.trigger_estop(now, "WATCHDOG_TELEMETRY_LOSS")
                if self.supervisor.start_mono and (now - self.supervisor.start_mono) > self.hard_time_cap:
                    self.supervisor.trigger_estop(now, "WATCHDOG_HARD_TIME_CAP")

            # 2. SHARED STOP STATE OWNER: nếu đã phát STOP, tự động kiểm tra confirm và timeout 200ms
            if self.supervisor.stop_requested_mono is not None and not self.supervisor.stop_confirmed:
                if last_pkt and "rx_mono" in last_pkt:
                    self.supervisor.check_stop_confirmation(last_pkt["rx_mono"], last_pkt)

                if (now - self.supervisor.stop_requested_mono) > CONFIRMATION_TIMEOUT_S:
                    self.supervisor.fault_tripped = True
                    if self.supervisor.fault_reason is None:
                        self.supervisor.fault_reason = "STOP_CONFIRMATION_TIMEOUT"

    def execute_lifecycle(self) -> int:
        from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3

        # Kiểm tra bounds ngay khi execute_lifecycle để bảo vệ cả khi gán sau init
        if not is_valid_finite(self.target_v) or self.target_v <= 0 or self.target_v > 0.05:
            self.final_report["status"] = "FAIL_INVALID_TARGET_V"
            return 2
        if not is_valid_finite(self.nominal_time) or self.nominal_time <= 0:
            self.final_report["status"] = "FAIL_INVALID_NOMINAL_TIME"
            return 2
        if not is_valid_finite(self.hard_time_cap) or self.hard_time_cap < self.nominal_time:
            self.final_report["status"] = "FAIL_INVALID_HARD_TIME_CAP"
            return 2

        if not self.acquire_port_lock():
            self.final_report["status"] = "FAIL_PORT_LOCKED"
            return 1

        if not self.open_transport():
            self.release_port_lock()
            self.final_report["status"] = "FAIL_TRANSPORT_OPEN"
            return 1

        try:
            self.arbiter = SerialArbiterGateV3(mock_serial=self.transport)
            self.supervisor = MotionSupervisor(
                serial_arbiter=self.arbiter,
                target_v=self.target_v,
                nominal_time_s=self.nominal_time,
                hard_time_cap_s=self.hard_time_cap
            )

            self.preflight_open_mono = self.clock()
            self.running = True
            self.reader_thread = threading.Thread(target=self.reader_loop, daemon=True)
            self.watchdog_thread = threading.Thread(target=self.watchdog_loop, daemon=True)
            self.reader_thread.start()
            self.watchdog_thread.start()

            # 1. Khởi động Preflight Tĩnh nghiêm ngặt (>= 10.0s, >= 80 mẫu DISARMED fresh)
            # Tích hợp common startup FSM và preflight validator kế thừa từ collector 4b32
            start_pf = self.clock()
            preflight_timeout = 25.0
            while (self.clock() - start_pf) < preflight_timeout:
                if self.preflight_failed:
                    self.final_report["status"] = "FAIL_PREFLIGHT_VALIDATION_FAILED"
                    self.final_report["rejection_reason"] = self.preflight_fail_reason
                    return 1
                if self.preflight_passed:
                    self.final_report["preflight_status"] = "PASS_PREFLIGHT_VERIFIED"
                    break
                time.sleep(0.02)

            if not self.preflight_passed:
                self.final_report["status"] = "FAIL_PREFLIGHT_TIMEOUT"
                self.final_report["rejection_reason"] = self.preflight_fail_reason or "TIMEOUT"
                return 1

            # 2. Khởi tạo phiên điều khiển ARM
            session_token = f"TOKEN_{int(self.clock() * 1000)}"
            arm_req_time = self.clock()
            ok_req, arm_reason = self.arbiter.arm_control_session(session_token, arm_req_time)
            if not ok_req:
                self.final_report["status"] = "FAIL_ARM_REQUEST_REJECTED"
                self.final_report["rejection_reason"] = arm_reason
                return 1

            # Chờ Gate đạt ARMED (sau khi nhận ACK và fresh D0 ARMED)
            arm_start = self.clock()
            while (self.clock() - arm_start) < 2.0:
                if self.arbiter.safety_state == "ARMED" and not self.arbiter.stop_latched:
                    break
                time.sleep(0.02)

            if self.arbiter.safety_state != "ARMED" or self.arbiter.stop_latched:
                self.final_report["status"] = "FAIL_ARM_CONFIRMATION_TIMEOUT"
                return 1

            # 3. Kích hoạt Motion Supervisor
            now = self.clock()
            if not self.supervisor.start_motion(now):
                self.final_report["status"] = "FAIL_START_MOTION"
                return 1

            # 4. Vòng lặp điều khiển chính (Control Loop 20Hz / 50ms)
            while self.supervisor.is_active:
                now_cycle = self.clock()
                with self.d0_lock:
                    cur_d0 = self.latest_d0

                ok_cycle, status_msg = self.supervisor.update_cycle(now_cycle, cur_d0)
                if not ok_cycle:
                    break
                time.sleep(0.05)

            # 5. Phanh dừng và chờ Fresh D0 DISARMED xác nhận dừng (<= 200ms)
            stop_wait_start = self.clock()
            while (self.clock() - stop_wait_start) < (CONFIRMATION_TIMEOUT_S + 0.1):
                if self.supervisor.stop_confirmed:
                    break
                time.sleep(0.01)

        finally:
            self.running = False
            cleanup_now = self.clock()

            # Nếu xe chưa stop_confirmed thì mới gửi STOP trong cleanup
            if self.supervisor and not self.supervisor.stop_confirmed:
                try:
                    if self.arbiter and hasattr(self.arbiter, "request_emergency_stop"):
                        res = self.arbiter.request_emergency_stop(cleanup_now)
                        if isinstance(res, tuple) and not res[0]:
                            self.final_report["cleanup_stop_write_error"] = str(res[1])
                    elif self.transport and hasattr(self.transport, "write"):
                        self.transport.write(b"STOP\n")
                except Exception as e_stop:
                    self.final_report["cleanup_stop_write_error"] = str(e_stop)

            if self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=0.2)
            if self.watchdog_thread and self.watchdog_thread.is_alive():
                self.watchdog_thread.join(timeout=0.2)

            close_err = None
            if self.transport and hasattr(self.transport, "close"):
                try:
                    self.transport.close()
                except Exception as e_c:
                    close_err = str(e_c)
                    self.final_report["close_error"] = close_err

            self.release_port_lock()

            # Đánh giá status trước khi lưu evidence để file JSON có final status chuẩn
            is_stopped = getattr(self.supervisor, "stop_confirmed", False)
            is_fault = getattr(self.supervisor, "fault_tripped", False)
            has_cleanup_err = "cleanup_stop_write_error" in self.final_report
            has_hw_err = "hardware_error" in self.final_report
            has_close_err = "close_error" in self.final_report

            if "status" not in self.final_report or self.final_report["status"] is None:
                if has_close_err:
                    self.final_report["status"] = "FAIL_STREAM_CLOSE_ERROR"
                elif has_cleanup_err:
                    self.final_report["status"] = "FAIL_CLEANUP_STOP_WRITE_ERROR"
                elif has_hw_err:
                    self.final_report["status"] = "FAIL_HARDWARE_ERROR_REPORTED"
                elif is_stopped and not is_fault:
                    self.final_report["status"] = "PASS_MOTION_VERIFIED"
                elif is_stopped and is_fault:
                    self.final_report["status"] = "FAIL_MOTION_SAFETY_TRIPPED_BUT_STOPPED"
                else:
                    self.final_report["status"] = "FAIL_STOP_UNCONFIRMED"

            self.save_evidence()

        has_sink_err = "evidence_save_error" in self.final_report
        final_status = self.final_report.get("status")

        if has_sink_err:
            self.final_report["status"] = "FAIL_EVIDENCE_SINK_ERROR"
            return 1
        if final_status == "PASS_MOTION_VERIFIED":
            return 0
        return 1

    def save_evidence(self) -> None:
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            ts = int(time.time() * 1000)
            pid = os.getpid()
            ev_path = os.path.join(self.output_dir, f"motion_evidence_{ts}_{pid}.json")

            # Thu thập toàn bộ tx_records từ FakeSerial / Serial nếu có
            if hasattr(self.transport, "tx_records"):
                self.tx_records = list(self.transport.tx_records)
            elif hasattr(self.ser, "writes") and isinstance(self.ser.writes, list):
                self.tx_records = list(self.ser.writes)

            data = {
                "final_report": self.final_report,
                "target_v": self.target_v,
                "nominal_time_s": self.nominal_time,
                "hard_time_cap_s": self.hard_time_cap,
                "stop_confirmed": getattr(self.supervisor, "stop_confirmed", False),
                "fault_tripped": getattr(self.supervisor, "fault_tripped", False),
                "fault_reason": getattr(self.supervisor, "fault_reason", None),
                "evidence_count": len(self.evidence_records),
                "records": self.evidence_records,  # Lưu TOÀN BỘ records
                "tx_records": self.tx_records
            }
            with open(ev_path, "x", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
            self.final_report["evidence_file"] = ev_path
        except Exception as e:
            self.final_report["evidence_save_error"] = str(e)


def main():
    import argparse
    import sys
    import json
    from agv_serial_arbiter_bridge_v3 import SerialArbiterGateV3

    parser = argparse.ArgumentParser(description="AGV Motion Supervisor Executable Runner")
    parser.add_argument("--mock", action="store_true", help="Chạy chế độ mock pipeline kiểm thử độc lập")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Cổng Serial kết nối")
    parser.add_argument("--baud", type=int, default=115200, help="Tốc độ baud")
    parser.add_argument("--target-v", type=float, default=0.04, help="Vận tốc mục tiêu (<= 0.05 m/s)")
    parser.add_argument("--nominal-time", type=float, default=1.0, help="Thời gian chạy danh định (giây)")
    parser.add_argument("--hard-time-cap", type=float, default=1.5, help="Hard cap ngắt cứng (giây)")
    parser.add_argument("--output-dir", type=str, default="/home/khangho/evidence_motion_live", help="Thư mục ghi evidence")
    args = parser.parse_args()

    # Kiểm tra CLI bounds trước khi chạy
    if not is_valid_finite(args.target_v) or args.target_v <= 0 or args.target_v > 0.05:
        sys.stderr.write(f"[CLI ERROR] target-v={args.target_v} không hợp lệ (phải > 0 và <= 0.05)\n")
        sys.exit(2)
    if not is_valid_finite(args.nominal_time) or args.nominal_time <= 0:
        sys.stderr.write(f"[CLI ERROR] nominal-time={args.nominal_time} không hợp lệ (phải > 0)\n")
        sys.exit(2)
    if not is_valid_finite(args.hard_time_cap) or args.hard_time_cap < args.nominal_time:
        sys.stderr.write(f"[CLI ERROR] hard-time-cap={args.hard_time_cap} không hợp lệ (phải >= nominal-time)\n")
        sys.exit(2)

    if args.mock:
        print("[MOCK EXECUTION] Bắt đầu kiểm thử độc lập Mock Pipeline...")
        class MockSerialTransport:
            def __init__(self):
                self.writes = []
                self.closed = False
            def write(self, data: bytes) -> int:
                self.writes.append(data.decode("utf-8", errors="replace"))
                return len(data)
            def flush(self):
                pass
            def close(self):
                self.closed = True

        ser_mock = MockSerialTransport()
        gate_mock = SerialArbiterGateV3(mock_serial=ser_mock)
        runner_mock = MotionSupervisor(
            serial_arbiter=gate_mock,
            target_v=args.target_v,
            nominal_time_s=args.nominal_time,
            hard_time_cap_s=args.hard_time_cap
        )

        # 1. Pipeline thiết lập phiên ARM
        d0_raw = json.dumps({
            "safety": "DISARMED", "mode": "PID",
            "l_tgt": 0.0, "r_tgt": 0.0, "l_rpm": 0.0, "r_rpm": 0.0,
            "l_pwm": 0, "r_pwm": 0, "x": 0.0, "y": 0.0, "th": 0.0, "v": 0.0, "w": 0.0
        })
        gate_mock.process_incoming_line(d0_raw, 100.0)
        ok_req, _ = gate_mock.arm_control_session("MOCK_SESSION_TOKEN", 100.01)
        gate_mock.process_incoming_line('{"ack":"ARM","state":"ARMED"}', 100.02)
        d0_armed = json.dumps({
            "safety": "ARMED", "mode": "PID",
            "l_tgt": 0.0, "r_tgt": 0.0, "l_rpm": 0.0, "r_rpm": 0.0,
            "l_pwm": 0, "r_pwm": 0, "x": 0.0, "y": 0.0, "th": 0.0, "v": 0.0, "w": 0.0
        })
        gate_mock.process_incoming_line(d0_armed, 100.03)

        # 2. Khởi động motion
        started = runner_mock.start_motion(100.04)
        if not started:
            print("[MOCK FAIL] Không thể khởi động runner!")
            sys.exit(1)

        # 3. Chạy các chu kỳ điều khiển
        t = 100.05
        while t < 100.05 + args.nominal_time:
            pkt = json.loads(d0_armed)
            pkt["rx_mono"] = t
            # Cho Gate parse luồng telemetry để duy trì độ tươi (telemetry freshness)
            gate_mock.process_incoming_line(d0_armed, t)
            ok_cycle, status = runner_mock.update_cycle(t, pkt)
            if not ok_cycle:
                print(f"[MOCK FAIL] Cycle error tại {t}: {status}")
                sys.exit(1)
            t += 0.05

        # 4. Khi chạm nominal duration -> phát lệnh STOP
        pkt_stop = json.loads(d0_armed)
        pkt_stop["rx_mono"] = t
        ok_stop, status_stop = runner_mock.update_cycle(t, pkt_stop)
        print(f"[MOCK NOMINAL STOP] Status: {status_stop}, Active: {runner_mock.is_active}")

        # 5. Nhận fresh D0 DISARMED xác nhận dừng
        d0_disarm_confirm = json.dumps({
            "safety": "DISARMED", "mode": "PID",
            "l_tgt": 0.0, "r_tgt": 0.0, "l_rpm": 0.0, "r_rpm": 0.0,
            "l_pwm": 0, "r_pwm": 0, "x": 0.0, "y": 0.0, "th": 0.0, "v": 0.0, "w": 0.0
        })
        t_confirm = t + 0.02
        gate_mock.process_incoming_line(d0_disarm_confirm, t_confirm)
        pkt_disarm = json.loads(d0_disarm_confirm)
        pkt_disarm["rx_mono"] = t_confirm
        pkt_disarm["raw_line"] = d0_disarm_confirm
        ok_conf, status_conf = runner_mock.update_cycle(t_confirm, pkt_disarm)
        print(f"[MOCK STOP CONFIRMED] Status: {status_conf}, Confirmed: {runner_mock.stop_confirmed}")
        print(f"[MOCK COMPLETED] Tổng số lệnh ghi ra Serial: {len(ser_mock.writes)}")
        print(f"[MOCK COMPLETED] Lệnh cuối cùng: {ser_mock.writes[-1].strip()}")
        sys.exit(0)

    # -------------------------------------------------------------------------
    # CHẠY HARDWARE RUNTIME THỰC THI (ĐÃ CÓ EXECUTABLE ĐẦY ĐỦ)
    # -------------------------------------------------------------------------
    print(f"[EXECUTABLE START] Khởi tạo HardwareMotionRunner trên cổng {args.port}...")
    runner = HardwareMotionRunner(
        port=args.port,
        baud=args.baud,
        target_v=args.target_v,
        nominal_time=args.nominal_time,
        hard_time_cap=args.hard_time_cap,
        output_dir=args.output_dir
    )
    exit_code = runner.execute_lifecycle()
    print(json.dumps(runner.final_report, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
