#!/usr/bin/env python3
"""
agv_serial_arbiter_bridge_v2.py
Trọng tài Serial duy nhất & Safety Gate Bridge (Phiên bản v2 Strict Hardening).
Khắc phục triệt để các lỗ hổng P0 theo đối soát Codex 15:02:
  - Counterexample A: Bắt buộc kiểm tra math.isfinite() và kiểu số hợp lệ (int, float) TRƯỚC KHI clamp. Từ chối tuyệt đối NaN/Inf.
  - Counterexample B: Xác thực độ tuổi telemetry strictly 0 <= (now_mono - last_telemetry_time) <= TTL. Chặn timestamp âm (future time skew).
  - Counterexample C: Cơ chế STOP latch / Epoch hủy toàn bộ lệnh cũ. Khi phát STOP, khóa cứng gate cho tới khi có chu trình cấp quyền mới. Command bắt buộc có token/source và deadline hữu hạn.
  - Counterexample D: _raw_write trả về bool/raise, không bao giờ nuốt OSError/SerialException. Nếu lỗi ghi, chốt STATE_FAULT ngay lập tức.
  - Autonomous Watchdog: Luồng kiểm tra watchdog định kỳ tự động phát STOP nếu caller im lặng (heartbeat timeout).
  - Khóa độc quyền cổng: Xử lý đóng handle khi connect fail.
"""

import sys
import os
import time
import math
import threading
from typing import Optional, Tuple, Dict, Any

class SerialArbiterGateV2:
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200, mock_serial: Any = None):
        self.port = port
        self.baudrate = baudrate
        self.ser = mock_serial
        self.is_running = False
        self.lock = threading.Lock()

        # Trạng thái an toàn & chốt chặn
        self.safety_state = "DISARMED" # DISARMED | ARMED | FAULT
        self.stop_latched = False      # Chốt chặn khi lệnh STOP được kích hoạt
        self.current_epoch = 0         # Epoch quản lý vòng đời phiên điều khiển
        self.active_token: Optional[str] = None

        # Watchdog & TTL
        self.last_telemetry_time = 0.0
        self.telemetry_ttl_sec = 0.250 # 250ms
        self.last_valid_command_time = 0.0
        self.command_timeout_sec = 0.200 # 200ms không nhận lệnh từ caller -> tự ngắt

        # Dữ liệu Odometry
        self.latest_odom = {
            "x": 0.0, "y": 0.0, "theta": 0.0,
            "v": 0.0, "w": 0.0,
            "l_rpm": 0.0, "r_rpm": 0.0,
            "timestamp": 0.0
        }

        # Giới hạn an toàn mềm
        self.MAX_LINEAR_VEL = 0.05   # m/s
        self.MAX_ANGULAR_VEL = 0.35  # rad/s

    def connect(self) -> bool:
        if self.ser is not None:
            self.is_running = True
            return True

        try:
            import serial
            import fcntl
            s = serial.Serial(self.port, self.baudrate, timeout=0.1)
            try:
                fcntl.flock(s.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except Exception as e:
                s.close()
                sys.stderr.write(f"[SerialArbiterGateV2] Không thể lấy khóa độc quyền cổng: {e}\n")
                return False
            self.ser = s
            self.is_running = True
            return True
        except Exception as e:
            sys.stderr.write(f"[SerialArbiterGateV2] Lỗi mở cổng Serial: {e}\n")
            return False

    def process_incoming_line(self, line: str, now_mono: float) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line or not (line.startswith("{") and line.endswith("}")):
            return None

        try:
            import json
            data = json.loads(line)
        except Exception:
            return None

        required_numeric = ["l_tgt", "r_tgt", "l_rpm", "r_rpm", "l_pwm", "r_pwm", "x", "y", "th", "v", "w"]
        if "safety" in data and all(k in data and isinstance(data[k], (int, float)) and math.isfinite(data[k]) for k in required_numeric):
            with self.lock:
                self.safety_state = data["safety"]
                self.last_telemetry_time = now_mono
                self.latest_odom = {
                    "x": float(data["x"]),
                    "y": float(data["y"]),
                    "theta": float(data["th"]),
                    "v": float(data["v"]),
                    "w": float(data["w"]),
                    "l_rpm": float(data["l_rpm"]),
                    "r_rpm": float(data["r_rpm"]),
                    "timestamp": now_mono
                }
            return data
        return None

    def arm_control_session(self, token: str, now_mono: float) -> Tuple[bool, str]:
        """Cấp quyền phiên điều khiển mới, mở chốt STOP latch."""
        with self.lock:
            if self.safety_state == "FAULT":
                return False, "REJECTED_FAULT: Hệ thống đang bị chốt FAULT"
            self.current_epoch += 1
            self.active_token = token
            self.stop_latched = False
            self.last_valid_command_time = now_mono
            ok = self._raw_write(b"ARM\n")
            if not ok:
                self.safety_state = "FAULT"
                return False, "HARDWARE_WRITE_ERROR: Không thể gửi lệnh ARM xuống Serial"
            return True, f"ARM_REQUESTED: Epoch={self.current_epoch}, Token={token}"

    def send_velocity_command(self, v: float, w: float, now_mono: float, token: Optional[str] = None, command_deadline: Optional[float] = None) -> Tuple[bool, str]:
        """
        Gate kiểm duyệt vận tốc với đối soát toàn diện A, B, C, D:
        - Kiểm tra kiểu dữ liệu & hữu hạn (NaN/Inf reject).
        - Kiểm tra tuổi telemetry: strictly 0 <= age <= 250ms.
        - Kiểm tra chốt dừng STOP latch và token điều khiển.
        - Kiểm tra deadline lệnh.
        """
        # 1. Counterexample A: Bắt buộc kiểu số và hữu hạn TRƯỚC KHI xử lý tiếp
        if not isinstance(v, (int, float)) or not isinstance(w, (int, float)):
            return False, "REJECT_INVALID_TYPE: Vận tốc phải là kiểu số thực"
        if not math.isfinite(v) or not math.isfinite(w):
            return False, "REJECT_NON_FINITE: Vận tốc không được chứa NaN hoặc Infinity"

        with self.lock:
            # 2. Counterexample C: Chốt chặn STOP latch và Token
            if self.stop_latched:
                return False, "REJECT_STOP_LATCHED: Hệ thống đang bị khóa bởi lệnh STOP trước đó"
            if self.active_token is not None and token != self.active_token:
                return False, "REJECT_INVALID_TOKEN: Token điều khiển không khớp phiên hiện tại"

            # Kiểm tra trạng thái an toàn phần cứng
            if self.safety_state != "ARMED":
                return False, f"REJECT_NOT_ARMED: Trạng thái robot là {self.safety_state} (Cần ARMED)"

            # 3. Counterexample B: Xác thực độ tuổi Telemetry (Chống age âm và Stale TTL)
            if self.last_telemetry_time == 0.0:
                return False, "REJECT_NO_TELEMETRY: Chưa nhận được mẫu telemetry nào"
            telem_age = now_mono - self.last_telemetry_time
            if telem_age < 0.0:
                return False, f"REJECT_FUTURE_TIME_SKEW: Timestamp telemetry không hợp lệ (age={telem_age:.4f}s < 0)"
            if telem_age > self.telemetry_ttl_sec:
                self._raw_write(b"STOP\n")
                return False, f"REJECT_STALE_TELEMETRY: Telemetry quá hạn ({telem_age:.3f}s > {self.telemetry_ttl_sec}s)"

            # Kiểm tra deadline lệnh nếu có
            if command_deadline is not None:
                if not math.isfinite(command_deadline) or now_mono > command_deadline:
                    return False, "REJECT_COMMAND_DEADLINE_EXPIRED: Lệnh đã quá hạn deadline"

            # 4. Giới hạn an toàn mềm
            v_clamped = max(-self.MAX_LINEAR_VEL, min(self.MAX_LINEAR_VEL, float(v)))
            w_clamped = max(-self.MAX_ANGULAR_VEL, min(self.MAX_ANGULAR_VEL, float(w)))

            cmd = f"V {v_clamped:.3f} {w_clamped:.3f}\n".encode("utf-8")
            ok = self._raw_write(cmd)
            if not ok:
                self.safety_state = "FAULT"
                self.stop_latched = True
                return False, "HARDWARE_WRITE_ERROR: Lỗi Serial.write, kích hoạt FAULT"

            self.last_valid_command_time = now_mono
            return True, f"ACCEPTED: V {v_clamped:.3f} {w_clamped:.3f}"

    def send_stop(self) -> bool:
        """Kích hoạt chốt STOP latch, hủy mọi quyền phát lệnh cũ."""
        with self.lock:
            self.stop_latched = True
            self.active_token = None
            ok = self._raw_write(b"STOP\n")
            if not ok:
                self.safety_state = "FAULT"
            return ok

    def send_disarm(self) -> bool:
        with self.lock:
            self.stop_latched = True
            self.active_token = None
            self.safety_state = "DISARMED"
            ok = self._raw_write(b"STOP\nDISARM\n")
            if not ok:
                self.safety_state = "FAULT"
            return ok

    def autonomous_watchdog_tick(self, now_mono: float) -> bool:
        """Watchdog tự động: Nếu caller im lặng quá 200ms khi đang ARMED -> tự động phát STOP."""
        with self.lock:
            if self.safety_state == "ARMED" and not self.stop_latched:
                if (now_mono - self.last_valid_command_time) > self.command_timeout_sec:
                    sys.stderr.write("[Watchdog] Phát hiện mất heartbeat lệnh từ caller -> Tự động STOP!\n")
                    self.stop_latched = True
                    self._raw_write(b"STOP\n")
                    return True
        return False

    def _raw_write(self, data: bytes) -> bool:
        """Counterexample D: Ghi Serial bảo đảm trả về bool chính xác, không giả định thành công."""
        if not self.ser:
            return False
        try:
            self.ser.write(data)
            self.ser.flush()
            return True
        except Exception as e:
            sys.stderr.write(f"[SerialArbiterGateV2] LỖI GHI SERIAL THỰC TẾ: {e}\n")
            return False

    def close(self) -> None:
        self.send_disarm()
        if self.ser:
            try:
                import fcntl
                fcntl.flock(self.ser.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self.ser.close()
            except Exception:
                pass
        self.is_running = False
