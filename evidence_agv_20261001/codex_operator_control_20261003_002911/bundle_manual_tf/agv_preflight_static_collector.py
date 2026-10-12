#!/usr/bin/env python3
"""
agv_preflight_static_collector.py
=============================================================================
Module thu thập Telemetry thụ động có giới hạn thời gian (Bounded No-TX).
Đặc tả kỹ thuật:
- Thuần túy READ-ONLY / Zero-TX: Tuyệt đối không gọi write/flush/ARM/STOP.
- Thiết lập rts=False, dtr=False trước khi mở cổng Serial nhằm giảm thiểu
  nguy cơ reset chip nạp (ESP32/CH340/CP2102).
  *Cảnh báo an toàn*: Trên một số mạch chuyển đổi USB-UART, việc mở cổng driver
  vẫn có thể gây xung sườn toggle DTR/RTS vật lý, do đó không coi đây là cơ chế
  triệt tiêu reset 100%. Phải kiểm tra gói D0 fresh settling sau khi kết nối.
- Ràng buộc thu thập:
  + wall_timeout_s = 15.0s
  + min_samples_required = 30 mẫu
  + max_samples_cap = 150 mẫu (ở tần số ~10Hz)
  + max_line_bytes = 256 bytes
- Kiểm duyệt an toàn từng mẫu JSON (Fail-Closed):
  + safety bắt buộc bằng 'DISARMED'. Không suy diễn từ l_pwm=0/r_pwm=0.
  + l_tgt == 0.0, r_tgt == 0.0, l_pwm == 0, r_pwm == 0.
  + l_rpm == 0.0, r_rpm == 0.0 (hoặc |rpm| < 1e-3).
  + Toàn bộ giá trị số phải hữu hạn (finite), loại trừ NaN/Inf/bool.
  + Không suy diễn biến thiên x/y là encoder ticks nếu gói tin không có ticks.
- Trả về mã exit code: 0 nếu đạt chuẩn, 1 nếu phát hiện bất thường hoặc không đủ mẫu.
=============================================================================
"""

import argparse
import json
import math
import os
import pathlib
import sys
import time
from typing import Any, Dict, Optional, List, Tuple

try:
    import fcntl
except ImportError:
    fcntl = None


# -----------------------------------------------------------------------------
# ĐẶC TẢ GIAO THỨC KHỞI ĐỘNG CỦA FIRMWARE F5BF (main.cpp: 70-88, 488-495)
# -----------------------------------------------------------------------------
# Giai đoạn Startup FSM gồm:
# 1. ROM bootloader lines (rst:0x1, configsip, load...) -> SETTLING_CORRUPT
# 2. Ready banner: {"info":"ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"}
# 3. Một số gói D0 ban đầu (từ 0ms -> 1500ms)
# 4. Khi current_ms >= 1500ms, hàm Scan_I2C_Bus() phát tuần tự:
#    - Dòng 1: {"info":"Scanning I2C bus..."}
#    - Dòng 2 (nếu tìm thấy): {"i2c_found":"0x42"}
#    - Dòng 3 (nếu đọc được VIN): {"vin_mv":<uint>}
#    - Hoặc (nếu không tìm thấy): {"error":"No I2C device found"} -> LỖI PHẦN CỨNG!
# 5. Sau khi quét I2C hoàn tất: Chuyển sang STABLE_D0_STREAM liên tục.
# -----------------------------------------------------------------------------
EXACT_BOOT_BANNER: str = "ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"
EXACT_I2C_SCAN_BANNER: str = "Scanning I2C bus..."
STARTUP_DEADLINE_S: float = 3.5  # Firmware quét I2C lúc 1.5s, dành tối đa 3.5s cho startup phase
MAX_STARTUP_LINES: int = 35

DEFAULT_PORT: str = "/dev/ttyUSB0"
DEFAULT_BAUD: int = 115200
WALL_TIMEOUT_S: float = 15.0
MIN_OBSERVATION_S: float = 10.0
MIN_SAMPLES: int = 80       # Tần số ~10Hz trong 10-15s
MAX_SAMPLES: int = 200
MAX_LINE_BYTES: int = 256
MAX_GAP_S: float = 1.5
MAX_AGE_S: float = 1.5
SETTLING_DEADLINE_S: float = 2.0
MAX_SETTLING_LINES: int = 15


class PureReadOnlyViolationError(RuntimeError):
    """Ném ra khi phát hiện bất kỳ hành vi phát xung/ghi lệnh TX nào."""
    pass


class PortContentionError(RuntimeError):
    """Ném ra khi cổng Serial đang bị tiến trình khác chiếm dụng."""
    pass


def acquire_port_lock(port: str) -> Tuple[Optional[Any], Optional[pathlib.Path]]:
    """
    Khóa cổng độc quyền bằng fcntl trên Linux/Pi hoặc lockfile nguyên tử trên Windows.
    Đảm bảo sole-owner thực sự.
    """
    clean_name = port.replace("/", "_").replace("\\", "_").replace(":", "")
    lockfile_path = pathlib.Path(f"/tmp/agv_collector_{clean_name}.lock") if os.name != "nt" else pathlib.Path(f"C:/Temp/agv_collector_{clean_name}.lock")
    try:
        lockfile_path.parent.mkdir(parents=True, exist_ok=True)
        if fcntl and hasattr(fcntl, "flock"):
            fd = open(lockfile_path, "w")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd, lockfile_path
        else:
            # Atomic creation trên Windows / non-fcntl
            # Cờ 'x' đảm bảo thất bại nếu file đã tồn tại
            fd = open(lockfile_path, "x")
            fd.write(f"pid={os.getpid()}\n")
            fd.flush()
            return fd, lockfile_path
    except (IOError, OSError, FileExistsError) as e:
        raise PortContentionError(f"Cổng {port} đang bị tiến trình khác chiếm quyền hoặc khóa độc quyền thất bại: {e}")


def cleanup_lock(lock_fd: Optional[Any], lock_path: Optional[pathlib.Path]) -> None:
    if lock_fd:
        try:
            lock_fd.close()
        except Exception:
            pass
    if lock_path and os.name == "nt":
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass
class ReadOnlySerialWrapper:
    """Wrapper bảo vệ nghiêm ngặt: Chặn đứng mọi thao tác ghi dữ liệu (Zero-TX Guard)."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self.bytes_read_total = 0
        self.lines_read_total = 0

    def read(self, size: int = 1) -> bytes:
        data = self._stream.read(size)
        self.bytes_read_total += len(data)
        return data

    def readline(self, size: int = -1) -> bytes:
        line = self._stream.readline(size)
        self.bytes_read_total += len(line)
        self.lines_read_total += 1
        return line

    def write(self, *args: Any, **kwargs: Any) -> int:
        raise PureReadOnlyViolationError("VI PHẠM AN TOÀN: Thao tác 'write' bị cấm tuyệt đối trong chế độ No-TX!")

    def writelines(self, *args: Any, **kwargs: Any) -> None:
        raise PureReadOnlyViolationError("VI PHẠM AN TOÀN: Thao tác 'writelines' bị cấm tuyệt đối trong chế độ No-TX!")

    def flush(self) -> None:
        # Không cho phép gọi flush vì có thể kích hoạt các cờ điều khiển dòng
        raise PureReadOnlyViolationError("VI PHẠM AN TOÀN: Thao tác 'flush' bị cấm trong chế độ No-TX!")

    def close(self) -> None:
        if hasattr(self._stream, "close"):
            self._stream.close()

    @property
    def is_open(self) -> bool:
        return getattr(self._stream, "is_open", True)


class MockSerialStream:
    """Mock Serial Stream chuẩn 10Hz phục vụ kiểm thử Offline độc lập."""

    def __init__(self, sample_lines: Optional[List[bytes]] = None, sample_interval_s: float = 0.10) -> None:
        self.is_open = True
        self.dtr = False
        self.rts = False
        self.timeout = 0.5
        self.sample_interval_s = sample_interval_s
        if sample_lines is not None:
            self._lines = list(sample_lines)
        else:
            sample_d0 = (
                b'{"safety":"DISARMED","mode":"PID","l_tgt":0.0,"r_tgt":0.0,'
                b'"l_rpm":0.0,"r_rpm":0.0,"l_pwm":0,"r_pwm":0,'
                b'"x":0.0,"y":0.0,"th":0.0,"v":0.0,"w":0.0}\n'
            )
            self._lines = [sample_d0] * 120
        self._idx = 0

    def readline(self, size: int = -1) -> bytes:
        if self._idx < len(self._lines):
            time.sleep(self.sample_interval_s)
            line = self._lines[self._idx]
            self._idx += 1
            if 0 <= size < len(line):
                return line[:size]
            return line
        time.sleep(self.timeout)
        return b""

    def read(self, size: int = 1) -> bytes:
        line = self.readline(size)
        return line[:size]

    def write(self, data: bytes) -> int:
        raise PureReadOnlyViolationError("MockSerial: TX write denied.")

    def flush(self) -> None:
        raise PureReadOnlyViolationError("MockSerial: TX flush denied.")

    def close(self) -> None:
        self.is_open = False


def is_valid_finite(val: Any) -> bool:
    if val is None or isinstance(val, bool):
        return False
    try:
        f = float(val)
        return not (math.isnan(f) or math.isinf(f))
    except (ValueError, TypeError):
        return False


def validate_telemetry_sample(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Kiểm tra tính an toàn tuyệt đối của từng mẫu telemetry:
    - Bắt buộc safety == 'DISARMED'. Không suy diễn từ l_pwm=0.
    - Cấm tuyệt đối các trường lỗi, cảnh báo, fault, banner, ack trong payload telemetry:
      không cho phép mixed schema kiểu D0 + error / fault / info.
    - Bắt buộc target và pwm == 0.
    - Bắt buộc tốc độ thực tế rpm == 0 (hoặc sai số nhiễu vi mô < 1e-3).
    - Toàn bộ giá trị số phải hữu hạn.
    """
    # Reject ngay lập tức nếu chứa bất kỳ khóa lỗi/trạng thái bất thường nào
    forbidden_in_telemetry = ["error", "fault", "info", "ack", "status_msg"]
    for bad_key in forbidden_in_telemetry:
        if bad_key in payload:
            return False, f"MIXED_SCHEMA_FORBIDDEN_KEY_{bad_key.upper()}"

    required_keys = ["safety", "l_tgt", "r_tgt", "l_pwm", "r_pwm", "l_rpm", "r_rpm", "v", "w"]
    for k in required_keys:
        if k not in payload:
            return False, f"MISSING_KEY_{k}"

    # 1. Trạng thái an toàn bắt buộc
    safety = payload.get("safety")
    if not isinstance(safety, str) or safety != "DISARMED":
        return False, f"INVALID_SAFETY_STATE_{safety}"

    # 2. Kiểm tra PWM và Target Actuation = 0
    numeric_fields = ["l_tgt", "r_tgt", "l_pwm", "r_pwm", "l_rpm", "r_rpm", "v", "w", "x", "y", "th"]
    for f in numeric_fields:
        if f in payload and not is_valid_finite(payload[f]):
            return False, f"NON_FINITE_OR_INVALID_{f}"

    # Kiểm tra PWM là số nguyên hoặc float tương đương nguyên
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


def run_preflight_collector(
    port: str = DEFAULT_PORT,
    baudrate: int = DEFAULT_BAUD,
    mock: bool = False,
    mock_lines: Optional[List[bytes]] = None,
    mock_interval_s: float = 0.10,
    wall_timeout_s: float = WALL_TIMEOUT_S,
    min_observation_s: float = MIN_OBSERVATION_S,
    min_samples: int = MIN_SAMPLES,
    max_samples: int = MAX_SAMPLES,
    max_gap_s: float = MAX_GAP_S,
    max_age_s: float = MAX_AGE_S,
    settling_deadline_s: float = SETTLING_DEADLINE_S,
    max_settling_lines: int = MAX_SETTLING_LINES,
    output_dir: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Điều phối quy trình thu thập telemetry thụ động có giới hạn thời gian.
    Trả về: (exit_code, report_dict)
    """
    report: Dict[str, Any] = {
        "status": "UNKNOWN",
        "valid_samples_count": 0,
        "corrupt_lines_count": 0,
        "elapsed_time_s": 0.0,
        "observation_time_s": 0.0,
        "rejection_reason": None,
        "evidence_file": None,
        "first_sample": None,
        "last_sample": None
    }

    # -------------------------------------------------------------------------
    # 1. VALIDATE TOÀN BỘ ĐỐI SỐ ĐẦU VÀO TRƯỚC KHI CHẠM VÀO PHẦN CỨNG/PORT
    # -------------------------------------------------------------------------
    params_positive_finite = [
        ("wall_timeout_s", wall_timeout_s),
        ("min_observation_s", min_observation_s),
        ("max_gap_s", max_gap_s),
        ("max_age_s", max_age_s),
        ("settling_deadline_s", settling_deadline_s)
    ]
    for name, val in params_positive_finite:
        if not is_valid_finite(val) or float(val) <= 0.0:
            report["status"] = "FAIL_INVALID_ARGUMENT"
            report["rejection_reason"] = f"INVALID_{name.upper()}: {val} must be positive finite"
            return 1, report

    params_positive_int = [
        ("min_samples", min_samples),
        ("max_samples", max_samples),
        ("baudrate", baudrate),
        ("max_settling_lines", max_settling_lines)
    ]
    for name, val in params_positive_int:
        if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
            report["status"] = "FAIL_INVALID_ARGUMENT"
            report["rejection_reason"] = f"INVALID_{name.upper()}: {val} must be positive int"
            return 1, report

    if max_samples < min_samples:
        report["status"] = "FAIL_INVALID_ARGUMENT"
        report["rejection_reason"] = f"INVALID_MAX_SAMPLES: {max_samples} must be >= min_samples ({min_samples})"
        return 1, report

    if wall_timeout_s < min_observation_s:
        report["status"] = "FAIL_INVALID_ARGUMENT"
        report["rejection_reason"] = f"INVALID_WALL_TIMEOUT: {wall_timeout_s}s must be >= min_observation_s ({min_observation_s}s)"
        return 1, report

    # -------------------------------------------------------------------------
    # 2. KHỞI TẠO TIME BUDGET TOÀN DIỆN VÀ KHÓA CỔNG ĐỘC QUYỀN
    # -------------------------------------------------------------------------
    start_time = time.monotonic()
    lock_fd = None
    lock_path = None
    raw_ser = None
    stream = None

    if not mock:
        try:
            lock_fd, lock_path = acquire_port_lock(port)
        except Exception as e_lock:
            report["status"] = "FAIL_PORT_CONTENTION"
            report["rejection_reason"] = str(e_lock)
            return 1, report

    if mock:
        raw_stream = MockSerialStream(sample_lines=mock_lines, sample_interval_s=mock_interval_s)
        stream = ReadOnlySerialWrapper(raw_stream)
    else:
        try:
            import serial
            raw_ser = serial.Serial()
            raw_ser.port = port
            raw_ser.baudrate = baudrate
            raw_ser.exclusive = True  # POSIX TIOCEXCL
            remaining_init = wall_timeout_s - (time.monotonic() - start_time)
            if remaining_init <= 0:
                report["status"] = "FAIL_TIMEOUT_BEFORE_OPEN"
                report["rejection_reason"] = "Hết thời gian budget trước khi mở cổng Serial"
                if raw_ser:
                    try: raw_ser.close()
                    except Exception: pass
                cleanup_lock(lock_fd, lock_path)
                return 1, report
            raw_ser.timeout = min(0.5, remaining_init)
            raw_ser.dtr = False
            raw_ser.rts = False
            raw_ser.open()
            raw_ser.dtr = False
            raw_ser.rts = False
            stream = ReadOnlySerialWrapper(raw_ser)
        except Exception as e_open:
            report["status"] = "FAIL_PORT_OPEN_ERROR"
            report["rejection_reason"] = f"PORT_OPEN_EXCEPTION: {str(e_open)}"
            if raw_ser:
                try: raw_ser.close()
                except Exception: pass
            cleanup_lock(lock_fd, lock_path)
            return 1, report

    if (time.monotonic() - start_time) >= wall_timeout_s:
        stream.close()
        if lock_fd:
            try: lock_fd.close()
            except Exception: pass
        report["status"] = "FAIL_OPEN_TIMEOUT_EXCEEDED"
        report["rejection_reason"] = f"Thời gian mở port vượt quá wall_timeout_s ({wall_timeout_s}s)"
        report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
        return 1, report

    valid_samples: List[Dict[str, Any]] = []
    evidence_records: List[Dict[str, Any]] = []
    last_sample_mono: Optional[float] = None
    first_sample_mono: Optional[float] = None
    settling_done = False
    lines_seen = 0

    try:
        fsm_diag_state = 0
        while True:
            now = time.monotonic()
            elapsed = now - start_time

            if elapsed >= wall_timeout_s:
                break
            if len(valid_samples) >= max_samples:
                break

            if settling_done and last_sample_mono is not None and (now - last_sample_mono) > max_gap_s:
                report["status"] = "FAIL_TELEMETRY_STREAM_GAP"
                report["rejection_reason"] = f"Mất kết nối telemetry: gap {now - last_sample_mono:.3f}s > {max_gap_s}s"
                report["valid_samples_count"] = len(valid_samples)
                report["elapsed_time_s"] = round(elapsed, 3)
                save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                return 1, report

            if not settling_done and elapsed > settling_deadline_s:
                report["status"] = "FAIL_INITIAL_SETTLING_TIMEOUT"
                report["rejection_reason"] = f"Quá hạn settling ban đầu {elapsed:.3f}s > {settling_deadline_s}s không nhận được mẫu hợp lệ"
                report["elapsed_time_s"] = round(elapsed, 3)
                report["valid_samples_count"] = len(valid_samples)
                save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                return 1, report

            remaining = wall_timeout_s - elapsed
            if remaining <= 0:
                break
            if not mock and hasattr(stream._stream, "timeout"):
                stream._stream.timeout = min(0.5, remaining)

            try:
                line_bytes = stream.readline(MAX_LINE_BYTES)
            except Exception as e_read:
                report["status"] = "FAIL_READ_ERROR"
                report["rejection_reason"] = f"READ_EXCEPTION: {str(e_read)}"
                report["valid_samples_count"] = len(valid_samples)
                save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                return 1, report

            rx_mono_timestamp = time.monotonic()
            if (rx_mono_timestamp - start_time) > wall_timeout_s:
                break

            if not line_bytes:
                time.sleep(0.01)
                continue

            lines_seen += 1

            # Ghi nhận raw record NGAY LẬP TỨC TRƯỚC KHI VALIDATE cho mọi dòng nhận được
            raw_rec = {
                "line_idx": lines_seen,
                "rx_mono": rx_mono_timestamp,
                "raw_bytes_len": len(line_bytes),
                "raw_hex": line_bytes.hex(),
                "payload": None,
                "error": None
            }
            evidence_records.append(raw_rec)

            try:
                line_str = line_bytes.decode("utf-8", errors="replace").strip()
            except Exception:
                line_str = ""

            is_json = bool(line_str and line_str.startswith("{") and line_str.endswith("}"))

            if not is_json:
                if not settling_done and (elapsed <= settling_deadline_s) and (lines_seen <= max_settling_lines):
                    report["corrupt_lines_count"] += 1
                    raw_rec["error"] = "SETTLING_CORRUPT"
                    continue
                else:
                    report["status"] = "FAIL_CORRUPT_LINE_AFTER_SETTLING"
                    report["rejection_reason"] = f"Dòng dữ liệu hỏng sau settling (line {lines_seen}): {line_str[:50]}"
                    report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                    report["valid_samples_count"] = len(valid_samples)
                    raw_rec["error"] = "FAIL_CORRUPT_LINE_AFTER_SETTLING"
                    save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                    return 1, report

            try:
                payload = json.loads(line_str)
            except Exception as e_json:
                if not settling_done and (elapsed <= settling_deadline_s) and (lines_seen <= max_settling_lines):
                    report["corrupt_lines_count"] += 1
                    raw_rec["error"] = "SETTLING_JSON_PARSE_ERROR"
                    continue
                else:
                    report["status"] = "FAIL_JSON_PARSE_ERROR"
                    report["rejection_reason"] = f"Lỗi parse JSON sau settling (line {lines_seen}): {e_json}"
                    report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                    report["valid_samples_count"] = len(valid_samples)
                    raw_rec["error"] = "FAIL_JSON_PARSE_ERROR"
                    save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                    return 1, report

            if not isinstance(payload, dict):
                report["status"] = "FAIL_NON_DICT_PAYLOAD"
                report["rejection_reason"] = "Payload không phải là JSON object"
                report["valid_samples_count"] = len(valid_samples)
                raw_rec["error"] = "FAIL_NON_DICT_PAYLOAD"
                save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                return 1, report

            raw_rec["payload"] = payload

            # -----------------------------------------------------------------
            # STARTUP FSM PROTOCOL CLASSIFICATION (main.cpp: 70-88, 488-495)
            # -----------------------------------------------------------------
            # FSM States:
            # 0: INIT_BOOT -> 1: READY_BANNER -> 2: I2C_SCANNING -> 3: I2C_FOUND -> 4: VIN_MV -> 5: DIAG_DONE
            disallowed_in_diag = ["safety", "fault", "l_pwm", "r_pwm", "l_tgt", "r_tgt", "ack", "error"]
            has_bad_keys = any(k in payload for k in disallowed_in_diag)

            # Nếu có 'error' trong payload -> LỖI PHẦN CỨNG!
            if "error" in payload:
                report["status"] = "FAIL_HARDWARE_ERROR_REPORTED"
                report["rejection_reason"] = f"Phần cứng báo lỗi: {payload.get('error')}"
                report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                report["valid_samples_count"] = len(valid_samples)
                raw_rec["error"] = "FAIL_HARDWARE_ERROR_REPORTED"
                save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                return 1, report

            # 1. Nhánh Ready Boot Banner (chỉ nhận khi ở state 0)
            if not has_bad_keys and set(payload.keys()) == {"info"} and payload.get("info") == EXACT_BOOT_BANNER:
                if fsm_diag_state == 0 and (elapsed <= STARTUP_DEADLINE_S) and (lines_seen <= MAX_STARTUP_LINES):
                    fsm_diag_state = 1
                    raw_rec["classification"] = "BOOT_BANNER"
                    raw_rec["error"] = "SETTLING_INFO_BANNER"
                    last_sample_mono = rx_mono_timestamp
                    continue
                else:
                    report["status"] = "FAIL_INVALID_BOOT_BANNER"
                    report["rejection_reason"] = f"Lặp hoặc sai thứ tự boot banner (state {fsm_diag_state})"
                    report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                    report["valid_samples_count"] = len(valid_samples)
                    raw_rec["error"] = "FAIL_INVALID_BOOT_BANNER"
                    save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                    return 1, report

            # 2. Nhánh I2C Scanning Info (chỉ nhận sau khi đã ready banner, state 1 hoặc 0 nếu không boot banner)
            if not has_bad_keys and set(payload.keys()) == {"info"} and payload.get("info") == EXACT_I2C_SCAN_BANNER:
                if fsm_diag_state in [0, 1] and (elapsed <= STARTUP_DEADLINE_S) and (lines_seen <= MAX_STARTUP_LINES):
                    fsm_diag_state = 2
                    raw_rec["classification"] = "I2C_SCANNING_INFO"
                    raw_rec["error"] = "STARTUP_I2C_DIAG"
                    last_sample_mono = rx_mono_timestamp
                    continue
                else:
                    report["status"] = "FAIL_INVALID_BOOT_BANNER"
                    report["rejection_reason"] = f"Lặp scan hoặc sai thứ tự I2C scan banner (state {fsm_diag_state})"
                    report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                    report["valid_samples_count"] = len(valid_samples)
                    raw_rec["error"] = "FAIL_INVALID_BOOT_BANNER"
                    save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                    return 1, report

            # 3. Nhánh I2C Found (BẮT BUỘC ĐÃ QUA I2C_SCANNING state 2, địa chỉ hex 0x01..0x7F)
            if not has_bad_keys and set(payload.keys()) == {"i2c_found"}:
                addr_val = payload.get("i2c_found")
                is_valid_hex_addr = False
                if (
                    isinstance(addr_val, str)
                    and addr_val.startswith("0x")
                    and len(addr_val) == 4
                    and all(c in "0123456789abcdefABCDEF" for c in addr_val[2:])
                ):
                    try:
                        int_addr = int(addr_val, 16)
                        # MKE_M18_Scan quét từ 1 đến 127 (0x01 đến 0x7F)
                        if 1 <= int_addr <= 127:
                            is_valid_hex_addr = True
                    except ValueError:
                        is_valid_hex_addr = False

                if fsm_diag_state == 2 and is_valid_hex_addr and (elapsed <= STARTUP_DEADLINE_S) and (lines_seen <= MAX_STARTUP_LINES):
                    fsm_diag_state = 3
                    raw_rec["classification"] = "I2C_FOUND"
                    raw_rec["error"] = "STARTUP_I2C_DIAG"
                    last_sample_mono = rx_mono_timestamp
                    continue
                else:
                    report["status"] = "FAIL_INVALID_I2C_DIAGNOSTIC"
                    report["rejection_reason"] = f"i2c_found không hợp lệ hoặc xuất hiện ngoài thứ tự (state {fsm_diag_state}, addr {addr_val})"
                    report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                    report["valid_samples_count"] = len(valid_samples)
                    raw_rec["error"] = "FAIL_INVALID_I2C_DIAGNOSTIC"
                    save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                    return 1, report

            # 4. Nhánh VIN_MV (BẮT BUỘC ĐÃ QUA I2C_FOUND state 3, uint32 1..4294967295)
            if not has_bad_keys and set(payload.keys()) == {"vin_mv"}:
                vin_val = payload.get("vin_mv")
                is_valid_vin = (
                    isinstance(vin_val, int)
                    and not isinstance(vin_val, bool)
                    and 1 <= vin_val <= 4294967295
                )
                if fsm_diag_state == 3 and is_valid_vin and (elapsed <= STARTUP_DEADLINE_S) and (lines_seen <= MAX_STARTUP_LINES):
                    fsm_diag_state = 4
                    raw_rec["classification"] = "VIN_MV"
                    raw_rec["error"] = "STARTUP_I2C_DIAG"
                    last_sample_mono = rx_mono_timestamp
                    continue
                else:
                    report["status"] = "FAIL_INVALID_I2C_DIAGNOSTIC"
                    report["rejection_reason"] = f"vin_mv không hợp lệ hoặc ngoài thứ tự (state {fsm_diag_state}, val {vin_val})"
                    report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                    report["valid_samples_count"] = len(valid_samples)
                    raw_rec["error"] = "FAIL_INVALID_I2C_DIAGNOSTIC"
                    save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                    return 1, report

            # Nếu có 'info' nhưng không thuộc allowlist hoặc đến sau startup deadline
            if "info" in payload:
                report["status"] = "FAIL_INVALID_BOOT_BANNER"
                report["rejection_reason"] = f"Chuỗi 'info' không hợp lệ hoặc ngoài startup phase: {payload.get('info')}"
                report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                report["valid_samples_count"] = len(valid_samples)
                raw_rec["error"] = "FAIL_INVALID_BOOT_BANNER"
                save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                return 1, report

            # F1 Fix: Nếu FSM đang ở state 2 (đang scan) nhưng chưa có found (state 3) hoặc VIN (state 4)
            # mà đã nhảy sang gói D0 -> FAIL_INVALID_BOOT_BANNER vì quét dở dang
            if fsm_diag_state == 2:
                report["status"] = "FAIL_INVALID_BOOT_BANNER"
                report["rejection_reason"] = "Quá trình quét I2C chưa hoàn tất (thiếu i2c_found hoặc error)"
                report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                report["valid_samples_count"] = len(valid_samples)
                raw_rec["error"] = "FAIL_INVALID_BOOT_BANNER"
                save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                return 1, report

            # -----------------------------------------------------------------
            # 3. Nhánh Telemetry Chuẩn (Chỉ hợp lệ khi có đầy đủ D0)
            # -----------------------------------------------------------------
            ok_sample, reason = validate_telemetry_sample(payload)
            if not ok_sample:
                report["status"] = "FAIL_TELEMETRY_INVARIANT_VIOLATION"
                report["rejection_reason"] = reason
                report["elapsed_time_s"] = round(time.monotonic() - start_time, 3)
                report["valid_samples_count"] = len(valid_samples)
                raw_rec["error"] = reason
                save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
                return 1, report

            processing_mono_timestamp = time.monotonic()
            raw_rec["processing_mono"] = processing_mono_timestamp

            # Nếu I2C diagnostic xuất hiện sau khi đã nhận D0 ban đầu (current_ms >= 1500)
            # thì khi chuyển sang stable D0 stream, ta reset lại bộ đếm quan sát tĩnh
            if fsm_diag_state in [2, 3, 4]:
                fsm_diag_state = 5  # DIAG_DONE -> chuyển sang STABLE_D0_STREAM
                first_sample_mono = rx_mono_timestamp
                valid_samples.clear()

            settling_done = True
            last_sample_mono = rx_mono_timestamp
            if first_sample_mono is None:
                first_sample_mono = rx_mono_timestamp

            valid_samples.append(payload)

    except PureReadOnlyViolationError as e_tx:
        report["status"] = "FAIL_SAFETY_TX_ATTEMPT"
        report["rejection_reason"] = str(e_tx)
        return 1, report
    finally:
        if stream:
            try:
                stream.close()
            except Exception as e_sc:
                if not report["status"].startswith("FAIL"):
                    report["status"] = "FAIL_STREAM_CLOSE_ERROR"
                    report["rejection_reason"] = f"STREAM_CLOSE_EXCEPTION: {e_sc}"
        if raw_ser and raw_ser is not getattr(stream, "_stream", None):
            try:
                raw_ser.close()
            except Exception:
                pass
        cleanup_lock(lock_fd, lock_path)

    elapsed_final = time.monotonic() - start_time
    report["elapsed_time_s"] = round(elapsed_final, 3)
    report["valid_samples_count"] = len(valid_samples)

    if first_sample_mono is not None and last_sample_mono is not None:
        observation_duration = last_sample_mono - first_sample_mono
    else:
        observation_duration = 0.0
    report["observation_time_s"] = round(observation_duration, 3)

    if observation_duration < min_observation_s:
        report["status"] = "FAIL_INSUFFICIENT_OBSERVATION_TIME"
        report["rejection_reason"] = f"Thời gian quan sát thực tế {observation_duration:.2f}s chưa đạt mức tối thiểu ({min_observation_s}s)"
        save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
        return 1, report

    if len(valid_samples) < min_samples:
        report["status"] = "FAIL_INSUFFICIENT_SAMPLES"
        report["rejection_reason"] = f"Thu thập được {len(valid_samples)} mẫu, yêu cầu tối thiểu >= {min_samples}"
        save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
        return 1, report

    if last_sample_mono is not None:
        last_age = (start_time + elapsed_final) - last_sample_mono
        if last_age > max_age_s:
            report["status"] = "FAIL_TELEMETRY_STREAM_STALE_AT_END"
            report["rejection_reason"] = f"Mẫu cuối cùng quá hạn tại thời điểm kết thúc: {last_age:.3f}s > {max_age_s}s"
            save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
            return 1, report

    if report["status"] == "UNKNOWN":
        report["status"] = "PASS_PREFLIGHT_VERIFIED"
    report["first_sample"] = valid_samples[0]
    report["last_sample"] = valid_samples[-1]

    save_evidence_file(report, evidence_records, valid_samples, start_time, port, baudrate, mock, wall_timeout_s, min_observation_s, output_dir)
    if report["status"].startswith("FAIL"):
        return 1, report

    return 0, report


def save_evidence_file(
    report: Dict[str, Any],
    evidence_records: List[Dict[str, Any]],
    valid_samples: List[Dict[str, Any]],
    start_time: float,
    port: str,
    baudrate: int,
    mock: bool,
    wall_timeout_s: float,
    min_observation_s: float,
    output_dir: Optional[str]
) -> None:
    """Ghi dữ liệu evidence độc quyền nguyên tử (cờ 'x'), bảo đảm không bao giờ ghi đè."""
    out_dir = pathlib.Path(output_dir) if output_dir else pathlib.Path(__file__).parent / "evidence_agv_20261001"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e_mk:
        report["status"] = "FAIL_EVIDENCE_SINK_ERROR"
        report["rejection_reason"] = f"MKDIR_ERROR: {e_mk}"
        report["evidence_file"] = f"WRITE_ERROR: {e_mk}"
        return

    # Sinh filename độc nhất vô nhị: timestamp + pid + counter
    for attempt in range(100):
        timestamp_tag = int(time.time() * 1000)
        evidence_filename = f"preflight_raw_evidence_{timestamp_tag}_{os.getpid()}_{attempt}.json"
        evidence_path = out_dir / evidence_filename
        if not evidence_path.exists():
            break

    evidence_data = {
        "metadata": {
            "timestamp_epoch": time.time(),
            "port": port,
            "baudrate": baudrate,
            "mock": mock,
            "wall_timeout_s": wall_timeout_s,
            "min_observation_s": min_observation_s,
            "status": report.get("status"),
            "rejection_reason": report.get("rejection_reason"),
            "valid_samples_count": len(valid_samples),
            "corrupt_lines_count": report.get("corrupt_lines_count", 0)
        },
        "records": evidence_records
    }

    try:
        # Sử dụng cờ 'x' (exclusive creation): ném FileExistsError nếu trùng file, không bao giờ ghi đè
        with open(evidence_path, "x", encoding="utf-8") as fp:
            json.dump(evidence_data, fp, indent=2, ensure_ascii=False)
            fp.flush()
            if hasattr(os, "fsync"):
                os.fsync(fp.fileno())
        report["evidence_file"] = str(evidence_path)
    except Exception as e_w:
        # Nếu ghi file thất bại -> Bắt buộc chuyển status thành FAIL!
        report["status"] = "FAIL_EVIDENCE_SINK_ERROR"
        report["rejection_reason"] = f"EVIDENCE_WRITE_FAILED: {e_w}"
        report["evidence_file"] = f"WRITE_ERROR: {e_w}"


def main():
    parser = argparse.ArgumentParser(description="AGV Preflight Bounded No-TX Telemetry Collector")
    parser.add_argument("--port", type=str, default=DEFAULT_PORT, help="Serial port")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Baudrate")
    parser.add_argument("--mock", action="store_true", help="Run with MockSerial")
    parser.add_argument("--wall-timeout", type=float, default=WALL_TIMEOUT_S, help="Wall timeout (s)")
    parser.add_argument("--min-obs", type=float, default=MIN_OBSERVATION_S, help="Min observation (s)")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES, help="Min samples")
    parser.add_argument("--max-samples", type=int, default=MAX_SAMPLES, help="Max samples")
    parser.add_argument("--output-dir", type=str, default=None, help="Evidence dir")
    args = parser.parse_args()

    code, res = run_preflight_collector(
        port=args.port,
        baudrate=args.baud,
        mock=args.mock,
        wall_timeout_s=args.wall_timeout,
        min_observation_s=args.min_obs,
        min_samples=args.min_samples,
        max_samples=args.max_samples,
        output_dir=args.output_dir
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    sys.exit(code)


if __name__ == "__main__":
    main()
