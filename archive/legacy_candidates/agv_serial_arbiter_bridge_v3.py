#!/usr/bin/env python3
"""
agv_serial_arbiter_bridge_v3.py
Trọng tài Serial duy nhất & Safety Gate Bridge (Phiên bản v3 Strict Formal Hardening).
Khắc phục triệt để 5 Counterexamples trong evidence/v2_review_1505.json (Codex Review 15:06):

1. Phân quyền bắt buộc: Dù telemetry có ARMED, nhưng nếu chưa arm_control_session hoặc token/deadline là None/không hợp lệ -> Lệnh V BẮT BUỘC BỊ TỪ CHỐI (REJECT_NO_ACTIVE_SESSION).
2. Kiểm tra kiểu số & hữu hạn toàn diện: now_mono, command_deadline, v, w đều bắt buộc là kiểu số thực (int, float), KHÔNG PHẢI BOOL (isinstance(x, bool) -> False), và math.isfinite() == True.
3. Quy trình ARM 3 bước nghiêm ngặt:
   - Chỉ cho phép yêu cầu ARM khi đã có telemetry DISARMED tươi (target=0, pwm=0).
   - arm_control_session() phát lệnh ARM nhưng KHÔNG mở gate ngay.
   - Gate CHỈ ĐƯỢC MỞ khi nhận đủ: (a) ARM_ACK từ Serial, và (b) Telemetry ARMED tươi có timestamp monotonic LỚN HƠN thời điểm gửi ARM (loại bỏ hoàn toàn old ARMED).
4. Khóa Epoch & Lease Token duy nhất:
   - Mỗi phiên ARM sinh một epoch duy nhất và lease token bắt buộc phải mới (không dùng lại token cũ).
   - Lệnh V bắt buộc truyền đúng epoch và token.
   - Khi STOP được gọi, epoch và token lập tức bị hủy vĩnh viễn (invalidated).
5. Autonomous Watchdog chạy Thread độc lập:
   - Chạy background thread tự động tick mỗi 20ms kiểm tra đồng thời: Telemetry Freshness (< 250ms), Command Lease Timeout (< 200ms).
   - Nếu Serial.write gặp lỗi I/O hoặc ghi thiếu byte -> Chốt cứng STATE_FAULT, dừng mọi lệnh, không xác nhận dừng ảo.
   - Lệnh STOP/DISARM chỉ được coi là CONFIRMED khi nhận đủ telemetry DISARMED 0 tươi sau lệnh.
"""

import sys
import os
import time
import math
import threading
from typing import Optional, Tuple, Dict, Any, Set

def _is_valid_finite_number(val: Any) -> bool:
    """Kiểm tra giá trị phải là số thực hữu hạn, loại trừ kiểu bool."""
    if isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    return math.isfinite(val)

class SerialArbiterGateV3:
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200, mock_serial: Any = None):
        self.port = port
        self.baudrate = baudrate
        self.ser = mock_serial
        self.is_running = False
        self.lock = threading.Lock()

        # Quản lý trạng thái an toàn
        self.safety_state = "DISARMED" # DISARMED | ARMED | FAULT
        self.local_fault = False       # Chốt lỗi nội bộ không cho phép ghi đè
        self.stop_latched = True       # Mặc định khóa gate khi khởi động
        self.stop_confirmed = True
        self.last_stop_command_time = 0.0

        # Quản lý phiên Session & Epoch
        self.current_epoch = 0
        self.active_token: Optional[str] = None
        self.session_arm_requested_time = 0.0
        self.session_arm_ack_received = False
        self.session_armed_telemetry_verified = False
        self.used_tokens: Set[str] = set()

        # Watchdog & TTL
        self.last_telemetry_time = 0.0
        self.telemetry_ttl_sec = 0.250     # 250ms
        self.last_valid_command_time = 0.0
        self.command_timeout_sec = 0.200   # 200ms
        self.watchdog_thread: Optional[threading.Thread] = None
        self.watchdog_stop_event = threading.Event()

        # Dữ liệu Odometry & Telemetry
        self.latest_odom = {
            "x": 0.0, "y": 0.0, "theta": 0.0,
            "v": 0.0, "w": 0.0,
            "l_rpm": 0.0, "r_rpm": 0.0,
            "timestamp": 0.0
        }
        self.latest_telemetry: Optional[Dict[str, Any]] = None

        # Giới hạn an toàn mềm
        self.MAX_LINEAR_VEL = 0.05   # m/s
        self.MAX_ANGULAR_VEL = 0.35  # rad/s

    def connect(self) -> bool:
        if self.ser is not None:
            self.is_running = True
            self._start_watchdog_thread()
            return True

        try:
            import serial
            import fcntl
            s = serial.Serial(self.port, self.baudrate, timeout=0.1, write_timeout=0.2)
            try:
                fcntl.flock(s.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except Exception as e:
                s.close()
                sys.stderr.write(f"[SerialArbiterGateV3] Không thể lấy khóa độc quyền cổng: {e}\n")
                return False
            self.ser = s
            self.is_running = True
            self._start_watchdog_thread()
            return True
        except Exception as e:
            sys.stderr.write(f"[SerialArbiterGateV3] Lỗi mở cổng Serial: {e}\n")
            return False

    def _start_watchdog_thread(self):
        self.watchdog_stop_event.clear()
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self.watchdog_thread.start()

    def _watchdog_loop(self):
        """Vòng lặp watchdog tự động kiểm tra mỗi 20ms."""
        while not self.watchdog_stop_event.is_set():
            time.sleep(0.020)
            now_mono = time.monotonic()
            self._autonomous_watchdog_tick(now_mono)

    def _autonomous_watchdog_tick(self, now_mono: float):
        if not _is_valid_finite_number(now_mono) or now_mono <= 0:
            return
        with self.lock:
            if self.safety_state == "ARMED" and not self.stop_latched:
                # Kiểm tra mất telemetry hoặc skew thời gian
                telem_age = now_mono - self.last_telemetry_time
                if telem_age > self.telemetry_ttl_sec or telem_age < 0.0:
                    sys.stderr.write(f"[Watchdog] Telemetry bất thường (age={telem_age:.3f}s) -> Phát STOP khẩn cấp!\n")
                    self._trigger_emergency_stop(now_mono=now_mono)
                    return

                # Kiểm tra mất heartbeat lệnh từ caller
                cmd_age = now_mono - self.last_valid_command_time
                if cmd_age > self.command_timeout_sec or cmd_age < 0.0:
                    sys.stderr.write(f"[Watchdog] Caller im lặng/skew (age={cmd_age:.3f}s) -> Phát STOP khẩn cấp!\n")
                    self._trigger_emergency_stop(now_mono=now_mono)
                    return

    def _trigger_emergency_stop(self, now_mono: Optional[float] = None):
        self.stop_latched = True
        self.active_token = None
        self.session_arm_ack_received = False
        self.session_armed_telemetry_verified = False
        self.stop_confirmed = False

        if now_mono is not None and _is_valid_finite_number(now_mono) and now_mono > 0:
            self.last_stop_command_time = float(now_mono)
        elif self.last_telemetry_time > 0:
            self.last_stop_command_time = max(self.last_telemetry_time, self.last_valid_command_time)
        else:
            self.last_stop_command_time = time.monotonic()

        ok = self._raw_write(b"STOP\n")
        if not ok:
            self.local_fault = True
            self.safety_state = "FAULT"

    def process_incoming_line(self, line: str, now_mono: float) -> Optional[Dict[str, Any]]:
        # Chặn đứng 'invalid_telem_clock': Loại bỏ triệt để now_mono không hợp lệ
        if not _is_valid_finite_number(now_mono) or now_mono <= 0:
            return None

        if not isinstance(line, str):
            return None
        line = line.strip()
        if not line or not (line.startswith("{") and line.endswith("}")):
            return None

        try:
            import json
            data = json.loads(line)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        with self.lock:
            # 1. Xử lý phản hồi ACK
            if "ack" in data:
                if data.get("ack") == "ARM" and data.get("state") == "ARMED":
                    if self.session_arm_requested_time > 0 and now_mono >= self.session_arm_requested_time:
                        self.session_arm_ack_received = True
                return data

            # 2. Xử lý gói tin Telemetry đầy đủ trường số
            required_numeric = ["l_tgt", "r_tgt", "l_rpm", "r_rpm", "l_pwm", "r_pwm", "x", "y", "th", "v", "w"]
            if "safety" in data and all(k in data and _is_valid_finite_number(data[k]) for k in required_numeric):
                reported_safety = str(data["safety"])
                # Khi đang chốt STOP latch hoặc đang yêu cầu dừng, cập nhật safety_state theo MCU reported
                self.safety_state = reported_safety

                # G2 Fix: PWM phải là số nguyên thuần túy (hoặc float bằng chính xác số nguyên)
                # Bắt buộc float(l_pwm) == 0.0 để không biến 0.5 thành 0
                l_pwm_val = data["l_pwm"]
                r_pwm_val = data["r_pwm"]

                self.last_telemetry_time = float(now_mono)
                self.latest_odom = {
                    "x": float(data["x"]),
                    "y": float(data["y"]),
                    "theta": float(data["th"]),
                    "v": float(data["v"]),
                    "w": float(data["w"]),
                    "l_rpm": float(data["l_rpm"]),
                    "r_rpm": float(data["r_rpm"]),
                    "timestamp": float(now_mono)
                }
                self.latest_telemetry = {
                    "safety": reported_safety,
                    "mode": data.get("mode"),
                    "l_tgt": float(data["l_tgt"]),
                    "r_tgt": float(data["r_tgt"]),
                    "l_rpm": float(data["l_rpm"]),
                    "r_rpm": float(data["r_rpm"]),
                    "l_pwm": l_pwm_val,
                    "r_pwm": r_pwm_val,
                    "v": float(data["v"]),
                    "w": float(data["w"]),
                    "x": float(data["x"]),
                    "y": float(data["y"]),
                    "th": float(data["th"]),
                    "timestamp": float(now_mono)
                }

                # Kiểm tra xác nhận ARM tươi sau thời điểm gửi ARM
                if self.safety_state == "ARMED" and self.session_arm_requested_time > 0 and now_mono > self.session_arm_requested_time:
                    self.session_armed_telemetry_verified = True
                    # Khi đã có cả ACK và Telemetry ARMED tươi -> Mở Stop-Latch
                    if self.session_arm_ack_received and self.active_token is not None:
                        self.stop_latched = False

                # Kiểm tra xác nhận STOP / DISARM thành công:
                # Chặn đứng 'STOP_confirmed_with_older_sample': Mẫu telemetry BẮT BUỘC phải đến sau STOP (now_mono > last_stop_command_time)
                # G2 Fix: float(l_pwm) == 0.0 và float(r_pwm) == 0.0 (chặn 0.5)
                is_actuators_zero = (
                    float(data["l_pwm"]) == 0.0 and float(data["r_pwm"]) == 0.0 and
                    float(data["l_tgt"]) == 0.0 and float(data["r_tgt"]) == 0.0 and
                    float(data["v"]) == 0.0 and float(data["w"]) == 0.0 and
                    float(data["l_rpm"]) == 0.0 and float(data["r_rpm"]) == 0.0
                )
                if self.safety_state == "DISARMED" and is_actuators_zero:
                    if self.last_stop_command_time > 0:
                        if now_mono > self.last_stop_command_time:
                            self.stop_confirmed = True
                    else:
                        self.stop_confirmed = True

                return data

        return None

    def arm_control_session(self, token: str, now_mono: float) -> Tuple[bool, str]:
        """
        Khởi tạo phiên điều khiển mới có kiểm tra preflight nghiêm ngặt:
        - Bắt buộc token hợp lệ và duy nhất.
        - Bắt buộc now_mono hợp lệ.
        - Bắt buộc có telemetry DISARMED 0 tươi (target=0, pwm=0, v=0, w=0, rpm=0).
        - Chặn tuyệt đối timestamp âm hoặc tương lai (future time skew).
        - Gửi lệnh ARM nhưng CHƯA mở gate ngay.
        """
        if not isinstance(token, str) or len(token.strip()) == 0:
            return False, "REJECT_INVALID_TOKEN: Token phải là chuỗi ký tự hợp lệ"
        if not _is_valid_finite_number(now_mono) or now_mono <= 0:
            return False, "REJECT_INVALID_CLOCK: now_mono không hợp lệ (NaN/Inf/Bool/Non-positive)"

        with self.lock:
            if self.local_fault or self.safety_state == "FAULT":
                return False, "REJECTED_FAULT: Hệ thống đang bị chốt FAULT"

            # 1. Kiểm tra telemetry preflight có tồn tại và clock hợp lệ không
            if self.last_telemetry_time <= 0.0 or not _is_valid_finite_number(self.last_telemetry_time) or self.latest_telemetry is None:
                return False, "REJECT_NO_FRESH_BOOT_TELEMETRY: Chưa có telemetry DISARMED tươi trước khi ARM"

            # 2. Chặn đứng 'future_D0': Độ tuổi telemetry âm (timestamp tương lai)
            telem_age = now_mono - self.last_telemetry_time
            if telem_age < 0.0:
                return False, f"REJECT_PREFLIGHT_FUTURE_TIME_SKEW: Timestamp telemetry tương lai ({telem_age:.4f}s < 0)"

            # 3. Kiểm tra TTL telemetry preflight
            if telem_age > self.telemetry_ttl_sec:
                return False, f"REJECT_NO_FRESH_BOOT_TELEMETRY: Telemetry DISARMED quá hạn ({telem_age:.3f}s > {self.telemetry_ttl_sec}s)"

            # 4. Kiểm tra trạng thái an toàn phải là DISARMED
            if self.safety_state != "DISARMED" or self.latest_telemetry.get("safety") != "DISARMED":
                return False, f"REJECT_PREFLIGHT_NOT_DISARMED: Trạng thái hiện tại là {self.safety_state} (Cần DISARMED)"

            # 5. Chặn đứng 'nonzero_D0': Preflight bắt buộc DISARMED tĩnh sạch 100% (target=0, pwm=0, v=0, w=0, rpm=0)
            # G2 Fix: Bắt buộc float(pwm) == 0.0 để chặn float fraction (+0.5/-0.5)
            telem = self.latest_telemetry
            is_clean_d0 = (
                float(telem["l_tgt"]) == 0.0 and float(telem["r_tgt"]) == 0.0 and
                float(telem["l_pwm"]) == 0.0 and float(telem["r_pwm"]) == 0.0 and
                float(telem["v"]) == 0.0 and float(telem["w"]) == 0.0 and
                float(telem["l_rpm"]) == 0.0 and float(telem["r_rpm"]) == 0.0
            )
            if not is_clean_d0:
                return False, (
                    f"REJECT_PREFLIGHT_NONZERO_D0: Telemetry DISARMED chứa cơ cấu chấp hành phi zero "
                    f"(l_tgt={telem['l_tgt']}, r_tgt={telem['r_tgt']}, l_pwm={telem['l_pwm']}, r_pwm={telem['r_pwm']}, "
                    f"v={telem['v']}, w={telem['w']}, l_rpm={telem['l_rpm']}, r_rpm={telem['r_rpm']})"
                )

            # 6. Kiểm tra token duy nhất
            if token in self.used_tokens:
                return False, f"REJECT_REUSED_TOKEN: Token '{token}' đã từng được sử dụng trước đó"

            self.used_tokens.add(token)
            self.current_epoch += 1
            self.active_token = token
            self.stop_latched = True # Vẫn khóa gate cho tới khi nhận ACK + Telemetry ARMED mới
            self.session_arm_requested_time = float(now_mono)
            self.session_arm_ack_received = False
            self.session_armed_telemetry_verified = False
            self.last_valid_command_time = float(now_mono)

            ok = self._raw_write(b"ARM\n")
            if not ok:
                self.local_fault = True
                self.safety_state = "FAULT"
                return False, "HARDWARE_WRITE_ERROR: Không thể gửi lệnh ARM xuống Serial"

            return True, f"ARM_REQUESTED: Epoch={self.current_epoch}, Token={token} (Chờ xác nhận ACK + Telemetry ARMED mới)"

    def send_velocity_command(self, v: float, w: float, now_mono: float, epoch: int, token: str, command_deadline: float) -> Tuple[bool, str]:
        """
        Gate kiểm duyệt vận tốc nghiêm ngặt chống 5 Counterexamples:
        - Kiểm tra tính hợp lệ của số & kiểu dữ liệu (NaN/Inf, bool, finite).
        - Kiểm tra token & epoch bắt buộc khớp phiên active.
        - Kiểm tra tuổi telemetry: strictly 0 <= age <= 250ms.
        - Kiểm tra deadline lệnh.
        """
        # 1. Counterexample 2: Validate tất cả tham số số thực hữu hạn (loại trừ bool)
        if not _is_valid_finite_number(v) or not _is_valid_finite_number(w):
            return False, "REJECT_NON_FINITE_VELOCITY: Vận tốc không hợp lệ (NaN/Inf/Bool/Non-numeric)"
        if not _is_valid_finite_number(now_mono) or now_mono <= 0:
            return False, "REJECT_INVALID_CLOCK: now_mono không hợp lệ (NaN/Inf/Bool/Non-numeric/Non-positive)"
        if not _is_valid_finite_number(command_deadline) or command_deadline <= 0:
            return False, "REJECT_INVALID_DEADLINE: command_deadline không hợp lệ (NaN/Inf/Bool/Non-numeric/Non-positive)"
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch <= 0:
            return False, "REJECT_INVALID_EPOCH: Epoch phải là số nguyên dương hợp lệ"
        if not isinstance(token, str) or len(token.strip()) == 0:
            return False, "REJECT_INVALID_TOKEN: Token không hợp lệ"

        with self.lock:
            # 2. Counterexample 1: Bắt buộc phải có active session được duyệt
            if self.active_token is None or self.stop_latched:
                return False, "REJECT_NO_ACTIVE_SESSION: Chưa có phiên điều khiển được cấp quyền hoặc đang bị khóa STOP"

            # 3. Counterexample 4: Kiểm tra epoch và token khớp phiên
            if epoch != self.current_epoch:
                return False, f"REJECT_EPOCH_MISMATCH: Epoch {epoch} không khớp epoch hiện tại {self.current_epoch}"
            if token != self.active_token:
                return False, "REJECT_TOKEN_MISMATCH: Token không khớp phiên active"

            # 4. Kiểm tra trạng thái an toàn phần cứng & xác nhận phiên
            if self.safety_state != "ARMED":
                return False, f"REJECT_NOT_ARMED: Trạng thái robot là {self.safety_state} (Cần ARMED)"
            if not (self.session_arm_ack_received and self.session_armed_telemetry_verified):
                return False, "REJECT_SESSION_NOT_CONFIRMED: Phiên ARM chưa được xác nhận đầy đủ bằng ACK và Telemetry ARMED mới"

            # 5. Kiểm tra deadline lệnh
            if now_mono > command_deadline:
                return False, f"REJECT_COMMAND_DEADLINE_EXPIRED: Lệnh đã quá hạn ({now_mono:.4f} > {command_deadline:.4f})"

            # 6. Kiểm tra độ tuổi Telemetry (Chống age âm và TTL quá hạn)
            telem_age = now_mono - self.last_telemetry_time
            if telem_age < 0.0:
                return False, f"REJECT_FUTURE_TIME_SKEW: Timestamp telemetry âm ({telem_age:.4f}s < 0)"
            if telem_age > self.telemetry_ttl_sec:
                self._trigger_emergency_stop(now_mono=now_mono)
                return False, f"REJECT_STALE_TELEMETRY: Telemetry quá hạn ({telem_age:.3f}s > {self.telemetry_ttl_sec}s)"

            # Kẹp an toàn mềm
            v_clamped = max(-self.MAX_LINEAR_VEL, min(self.MAX_LINEAR_VEL, float(v)))
            w_clamped = max(-self.MAX_ANGULAR_VEL, min(self.MAX_ANGULAR_VEL, float(w)))

            cmd = f"V {v_clamped:.3f} {w_clamped:.3f}\n".encode("utf-8")
            ok = self._raw_write(cmd)
            if not ok:
                self.local_fault = True
                self.safety_state = "FAULT"
                self.stop_latched = True
                self.active_token = None
                return False, "HARDWARE_WRITE_ERROR: Lỗi ghi lệnh V xuống Serial"

            self.last_valid_command_time = float(now_mono)
            return True, f"ACCEPTED: V {v_clamped:.3f} {w_clamped:.3f}"

    def send_stop(self, now_mono: Optional[float] = None) -> bool:
        """Kích hoạt chốt STOP latch, hủy vĩnh viễn epoch và token hiện tại."""
        with self.lock:
            self.stop_latched = True
            self.active_token = None
            self.session_arm_ack_received = False
            self.session_armed_telemetry_verified = False
            self.stop_confirmed = False

            if now_mono is not None and _is_valid_finite_number(now_mono) and now_mono > 0:
                self.last_stop_command_time = float(now_mono)
            else:
                self.last_stop_command_time = time.monotonic()

            ok = self._raw_write(b"STOP\n")
            if not ok:
                self.local_fault = True
                self.safety_state = "FAULT"
            return ok

    def send_disarm(self, now_mono: Optional[float] = None) -> bool:
        with self.lock:
            self.stop_latched = True
            self.active_token = None
            self.session_arm_ack_received = False
            self.session_armed_telemetry_verified = False
            self.safety_state = "DISARMED"
            self.stop_confirmed = False

            if now_mono is not None and _is_valid_finite_number(now_mono) and now_mono > 0:
                self.last_stop_command_time = float(now_mono)
            else:
                self.last_stop_command_time = time.monotonic()

            ok = self._raw_write(b"STOP\nDISARM\n")
            if not ok:
                self.local_fault = True
                self.safety_state = "FAULT"
            return ok

    def _raw_write(self, data: bytes) -> bool:
        """Ghi Serial bảo đảm kiểm tra partial write và bắt mọi ngoại lệ."""
        if not self.ser or not hasattr(self.ser, "write"):
            return False
        try:
            bytes_written = self.ser.write(data)
            if bytes_written is not None and bytes_written < len(data):
                sys.stderr.write(f"[SerialArbiterGateV3] Lỗi ghi thiếu byte ({bytes_written}/{len(data)})\n")
                return False
            self.ser.flush()
            return True
        except Exception as e:
            sys.stderr.write(f"[SerialArbiterGateV3] LỖI GHI SERIAL THỰC TẾ: {e}\n")
            return False

    def close(self) -> None:
        self.watchdog_stop_event.set()
        if self.watchdog_thread and self.watchdog_thread.is_alive():
            self.watchdog_thread.join(timeout=0.2)
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
