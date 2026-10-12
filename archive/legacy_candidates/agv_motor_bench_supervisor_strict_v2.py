#!/usr/bin/env python3
"""
agv_motor_bench_supervisor_strict.py
Kịch bản giám sát độc quyền Serial duy nhất cho bài thử motor ngắn có kiểm soát.
Phiên bản Strict Compliance hoàn chỉnh (Review 13:42):
- Đảm bảo mở log_fp thành công mới được tiếp tục, tuyệt đối không nuốt lỗi mở log.
- Boot Check: Chờ >= 3.0s sau khi mở Serial, bắt buộc nhận liên tiếp >= 3 mẫu telemetry DISARMED tươi với target=0, pwm=0.
- TX Logging: Ghi nhận từng lệnh TX gửi đi kèm timestamp monotonic chính xác.
- ARM Check: Phải nhận cả ACK ARM và ít nhất 1 telemetry xác nhận safety == "ARMED" mới được phát lệnh V.
- Trong RUN: Nếu safety != "ARMED" -> Kích hoạt dừng khẩn cấp và đánh dấu FAIL.
- Bất kỳ early_stop_reason nào (kể cả vượt quá 10cm) đều được xử lý dừng an toàn và đánh dấu FAIL.
- POST_STOP: Bắt buộc >= 3 mẫu telemetry DISARMED liên tiếp với PWM == 0, RPM < 0.1 VÀ l_tgt == 0.0, r_tgt == 0.0.
- Thoát lỗi: Bất kỳ vi phạm nào đều trả về exit code khác 0.
"""

import sys
import time
import signal
import serial
import json
import math
import os
try:
    import fcntl
except ImportError:
    fcntl = None

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
LOG_FILE = "/home/khangho/agv_bench_run.log"

g_ser = None
g_running = True

def parse_valid_telemetry(line):
    if not line or not line.startswith("{") or not line.endswith("}"):
        return None
    try:
        d = json.loads(line)
        if "safety" not in d:
            return None
        safety = d["safety"]
        if safety not in ("DISARMED", "ARMED", "FAULT"):
            return None

        numeric_fields = ["l_tgt", "r_tgt", "l_rpm", "r_rpm", "l_pwm", "r_pwm", "x", "y", "th", "v", "w"]
        for field in numeric_fields:
            if field not in d:
                return None
            val = float(d[field])
            if not math.isfinite(val):
                return None
            d[field] = val

        return d
    except Exception:
        return None

def emergency_shutdown(signum=None, frame=None):
    global g_running, g_ser
    g_running = False
    sys.stderr.write("\n[SUPERVISOR] !!! KÍCH HOẠT SHUTDOWN HOOK KHẨN CẤP !!!\n")
    if g_ser and g_ser.is_open:
        try:
            for _ in range(3):
                g_ser.write(b"STOP\n")
                g_ser.flush()
                time.sleep(0.02)
            g_ser.write(b"DISARM\n")
            g_ser.flush()
        except Exception:
            pass
    sys.exit(2)

signal.signal(signal.SIGINT, emergency_shutdown)
signal.signal(signal.SIGTERM, emergency_shutdown)

def run_bench_test(ser_instance=None):
    global g_ser, g_running
    print("=== BẮT ĐẦU BENCH TEST KIỂM SOÁT NGHIÊM NGẶT (STRAIGHT ONLY - MANUAL AREA) ===")

    # BẮT BUỘC MỞ ĐƯỢC LOG FILE, KHÔNG NUỐT LỖI
    log_fp = None
    try:
        log_fp = open(LOG_FILE, "w", encoding="utf-8")
    except Exception as e:
        sys.stderr.write(f"[FATAL ERROR] Không thể mở file log {LOG_FILE}: {e}\n")
        return False

    def log(msg, raw=None, is_tx=False):
        ts = time.monotonic()
        prefix = "TX >>>" if is_tx else "MSG   "
        text = f"[{ts:.4f}] {prefix} {msg}"
        if raw:
            text += f" | RAW: {raw}"
        text += "\n"
        sys.stdout.write(text)
        sys.stdout.flush()
        if log_fp:
            log_fp.write(text)
            log_fp.flush()

    own_serial = False
    if ser_instance is None:
        try:
            g_ser = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUD_RATE,
                timeout=0.05,
                write_timeout=0.1,
                exclusive=True
            )
            if fcntl:
                try:
                    fcntl.flock(g_ser.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except Exception as e:
                    log(f"[ERROR] Không thể lock độc quyền port {SERIAL_PORT}: {e}")
                    return False
            own_serial = True
        except Exception as e:
            log(f"[ERROR] Không thể mở cổng Serial {SERIAL_PORT}: {e}")
            return False
    else:
        g_ser = ser_instance

    try:
        # ----------------------------------------------------------------------
        # 1. BOOT SAFETY CHECK (Bắt buộc chờ >= 3.0s rồi nhận >= 3 mẫu DISARMED liên tiếp)
        # ----------------------------------------------------------------------
        log("Giai đoạn 1: Xác minh boot an toàn (Chờ >= 3.0s tránh autoscan, nhận >= 3 mẫu DISARMED liên tiếp)...")
        boot_start = time.monotonic()
        consecutive_disarmed = 0
        baseline_x = None
        baseline_y = None

        while time.monotonic() - boot_start < 5.0:
            raw_line = g_ser.readline().decode('utf-8', errors='ignore').strip()
            elapsed_boot = time.monotonic() - boot_start

            if raw_line:
                t_data = parse_valid_telemetry(raw_line)
                if t_data is not None:
                    log(f"BOOT_TELEMETRY (t={elapsed_boot:.2f}s): safety={t_data['safety']}, PWM=[{t_data['l_pwm']},{t_data['r_pwm']}], RPM=[{t_data['l_rpm']},{t_data['r_rpm']}]", raw_line)
                    # Ghi nhận trạng thái DISARMED hợp lệ
                    if (t_data['safety'] == "DISARMED" and 
                        t_data['l_pwm'] == 0 and t_data['r_pwm'] == 0 and
                        t_data['l_tgt'] == 0.0 and t_data['r_tgt'] == 0.0):
                        consecutive_disarmed += 1
                        baseline_x = t_data['x']
                        baseline_y = t_data['y']
                        # Bắt buộc thời gian mở serial đã qua 3.0s VÀ nhận >= 3 mẫu liên tiếp
                        if elapsed_boot >= 3.0 and consecutive_disarmed >= 3:
                            log(f"XÁC MINH BOOT AN TOÀN THÀNH CÔNG! Baseline: X={baseline_x:.3f}, Y={baseline_y:.3f}")
                            break
                    else:
                        consecutive_disarmed = 0
                else:
                    log("RECV_NON_TELEMETRY (Không tính freshness)", raw_line)
            else:
                time.sleep(0.02)

        if consecutive_disarmed < 3:
            log("LỖI KHỞI ĐỘNG: Không nhận đủ 3 mẫu Telemetry DISARMED hợp lệ sau mốc 3.0s!")
            return False

        # ----------------------------------------------------------------------
        # 2. GỬI LỆNH ARM VÀ XÁC MINH ARMED TELEMETRY
        # ----------------------------------------------------------------------
        log("Giai đoạn 2: Gửi lệnh ARM và chờ xác nhận ACK + Telemetry ARMED...")
        log("ARM\\n", is_tx=True)
        g_ser.write(b"ARM\n")
        g_ser.flush()

        arm_ack_received = False
        armed_telemetry_received = False
        arm_wait_start = time.monotonic()

        while time.monotonic() - arm_wait_start < 1.0:
            raw_line = g_ser.readline().decode('utf-8', errors='ignore').strip()
            if raw_line:
                if '{"ack":"ARM","state":"ARMED"}' in raw_line:
                    arm_ack_received = True
                    log("Đã nhận ACK ARM!", raw_line)
                t_data = parse_valid_telemetry(raw_line)
                if t_data is not None:
                    if t_data['safety'] == "ARMED":
                        armed_telemetry_received = True
                        log("Đã nhận Telemetry ARMED!", raw_line)
                        break
                    elif t_data['safety'] == "FAULT":
                        log("LỖI: Phát hiện FAULT khi đang ARM!")
                        return False

        if not (arm_ack_received and armed_telemetry_received):
            log(f"LỖI ARM: ACK={arm_ack_received}, Telemetry_ARMED={armed_telemetry_received}")
            g_ser.write(b"STOP\nDISARM\n")
            g_ser.flush()
            return False

        # ----------------------------------------------------------------------
        # 3. THỰC THI BÀI THỬ THẲNG NGẮN CÓ KIỂM SOÁT
        # ----------------------------------------------------------------------
        max_duration_sec = 2.0
        max_allowed_dist = 0.10 # Giới hạn cứng 10 cm
        cmd_str = b"V 0.05 0.0\n"

        log(f"Giai đoạn 3: Bắt đầu phát lệnh {cmd_str.strip().decode()} (Max duration: {max_duration_sec}s, Max dist: {max_allowed_dist}m)...")
        
        test_start = time.monotonic()
        last_heartbeat_sent = 0.0
        last_telemetry_monotonic = time.monotonic()
        early_stop_reason = None
        motion_observed = False

        while g_running and (time.monotonic() - test_start < max_duration_sec):
            now = time.monotonic()

            if now - last_heartbeat_sent >= 0.08:
                log(cmd_str.strip().decode(), is_tx=True)
                g_ser.write(cmd_str)
                g_ser.flush()
                last_heartbeat_sent = now

            raw_line = g_ser.readline().decode('utf-8', errors='ignore').strip()
            if raw_line:
                t_data = parse_valid_telemetry(raw_line)
                if t_data is not None:
                    last_telemetry_monotonic = now
                    cur_dist = math.hypot(t_data['x'] - baseline_x, t_data['y'] - baseline_y)
                    log(f"RUNNING: dist={cur_dist:.4f}m, RPM=[{t_data['l_rpm']},{t_data['r_rpm']}], safety={t_data['safety']}", raw_line)

                    # Ghi nhận có chuyển động thực tế
                    if abs(t_data['l_rpm']) > 0.5 or abs(t_data['r_rpm']) > 0.5 or cur_dist > 0.005:
                        motion_observed = True

                    # Trong RUN: bắt buộc safety == "ARMED"
                    if t_data['safety'] != "ARMED":
                        early_stop_reason = f"SAFETY_STATE_VIOLATION ({t_data['safety']})"
                        break

                    # Nếu vượt quá giới hạn khoảng cách cho phép -> Ngắt khẩn cấp và ĐÁNH DẤU LỖI
                    if cur_dist > max_allowed_dist:
                        early_stop_reason = f"EXCEEDED_MAX_DISPLACEMENT ({cur_dist:.3f}m > {max_allowed_dist}m)"
                        break
                else:
                    log("RECV_NON_TELEMETRY_DURING_RUN", raw_line)

            if now - last_telemetry_monotonic > 0.25:
                early_stop_reason = f"TELEMETRY_FRESHNESS_TIMEOUT ({now - last_telemetry_monotonic:.3f}s > 0.25s)"
                break

            time.sleep(0.005)

        # ----------------------------------------------------------------------
        # 4. GỬI LỆNH DỪNG VÀ XÁC NHẬN BẰNG NHIỀU MẪU DISARMED TƯƠI
        # ----------------------------------------------------------------------
        log(f"Giai đoạn 4: Dừng khẩn cấp và giải giáp (Lý do: {early_stop_reason or 'NORMAL_DEADLINE_REACHED'})...")
        for _ in range(3):
            log("STOP\\n", is_tx=True)
            g_ser.write(b"STOP\n")
            g_ser.flush()
            time.sleep(0.02)
        log("DISARM\\n", is_tx=True)
        g_ser.write(b"DISARM\n")
        g_ser.flush()

        log("Giai đoạn 5: Xác minh trạng thái sau dừng (yêu cầu >= 3 mẫu DISARMED, RPM < 0.1 và Target=0.0)...")
        stop_wait_start = time.monotonic()
        consecutive_stopped = 0

        while time.monotonic() - stop_wait_start < 2.0:
            raw_line = g_ser.readline().decode('utf-8', errors='ignore').strip()
            if raw_line:
                t_data = parse_valid_telemetry(raw_line)
                if t_data is not None:
                    log(f"POST_STOP_TELEMETRY: safety={t_data['safety']}, RPM=[{t_data['l_rpm']},{t_data['r_rpm']}], TGT=[{t_data['l_tgt']},{t_data['r_tgt']}]", raw_line)
                    if (t_data['safety'] == "DISARMED" and 
                        abs(t_data['l_rpm']) < 0.1 and abs(t_data['r_rpm']) < 0.1 and
                        t_data['l_pwm'] == 0 and t_data['r_pwm'] == 0 and
                        t_data['l_tgt'] == 0.0 and t_data['r_tgt'] == 0.0):
                        consecutive_stopped += 1
                        if consecutive_stopped >= 3:
                            log("XÁC NHẬN DỪNG AN TOÀN HOÀN TẤT VỚI BẰNG CHỨNG TELEMETRY VỮNG CHẮC!")
                            break
                    else:
                        consecutive_stopped = 0

        stop_verified = (consecutive_stopped >= 3)
        if not stop_verified:
            log("LỖI SAU DỪNG: Không thể xác minh đủ 3 mẫu dừng an toàn (RPM chưa về 0 hoặc safety chưa DISARMED hoặc target != 0)!")
            return False

        # BẤT KỲ EARLY_STOP_REASON NÀO CŨNG KHIẾN BÀI THỬ BỊ TÍNH LÀ THẤT BẠI
        if early_stop_reason is not None:
            log(f"BÀI THỬ THẤT BẠI VÌ CẢNH BÁO AN TOÀN: {early_stop_reason}")
            return False

        log(f"=== BÀI THỬ HOÀN TẤT ĐẠT CHUẨN: Motion={motion_observed}, StopVerified={stop_verified} ===")
        return True

    finally:
        try:
            if g_ser and g_ser.is_open:
                g_ser.write(b"STOP\nDISARM\n")
                g_ser.flush()
                if own_serial and fcntl:
                    try:
                        fcntl.flock(g_ser.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                    g_ser.close()
        except Exception:
            pass
        if log_fp:
            try:
                log_fp.close()
            except Exception:
                pass

if __name__ == "__main__":
    success = run_bench_test()
    sys.exit(0 if success else 1)
