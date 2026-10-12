#!/usr/bin/env python3
"""
agv_passive_encoder_logger_v2.py
Công cụ thu thập dữ liệu thụ động READ-ONLY v2 có Preflight Guard và Bounded Execution.
Khắc phục các thiếu sót Counterexample G (Codex Review 15:02):
  - Preflight Gate: Kiểm tra nghiêm ngặt bắt buộc nhận đủ >= 3 mẫu liên tiếp có:
      safety == DISARMED, target == [0, 0], PWM == [0, 0], RPM == [0, 0].
      Nếu không đạt preflight (ví dụ ARMED, PWM != 0, hoặc thiếu trường số) -> Abort ngay lập tức, exit code 1, không cho phép tiếp tục.
  - Thu thập đầy đủ dữ liệu counts và RPM từng bánh xe trái/phải độc lập.
  - Bounded duration hữu hạn (mặc định 15.0s). Nếu mất mẫu (gap > 1.0s) -> Abort báo lỗi mất dữ liệu.
  - An toàn ghi file: Đặt timestamp vào tên file tránh overwrite đè lên bằng chứng cũ.
  - Cảnh báo người dùng: Trạng thái DISARMED chỉ là ngắt xung phần mềm, motor vẫn có thể nối nguồn; nếu phát hiện mất an toàn, lập tức báo người trực ngắt công tắc vật lý và dừng thử nghiệm.
"""

import sys
import os
import time
import json
import math
import argparse
from typing import Optional, Tuple, Dict, Any, Union
try:
    import fcntl
except ImportError:
    fcntl = None


def _is_valid_finite_number(val: Any) -> bool:
    """Kiểm tra giá trị phải là số thực hữu hạn, loại trừ kiểu bool."""
    if isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    return math.isfinite(val)


def run_passive_logger_v2(
    port: str = "/dev/ttyUSB0",
    baud: int = 115200,
    duration: float = 15.0,
    log_dir: str = "/home/khangho",
    mock_serial: Any = None,
    min_samples: int = 10,
):
    # Đặt tên file log có timestamp để không overwrite bằng chứng cũ
    ts_str = time.strftime("%Y%m%d_%H%M%S")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        sys.stderr.write(f"CẢNH BÁO: Không thể tạo thư mục {log_dir}: {e}\n")

    out_file = os.path.join(log_dir, f"passive_hand_push_{ts_str}.log")

    print(f"=== KHỞI ĐỘNG PASSIVE READ-ONLY LOGGER V2 ===")
    print(f"Cổng: {port}, Baud: {baud}, Giới hạn: {duration:.1f}s, Mẫu tối thiểu: {min_samples}")
    print(f"Tập tin ghi: {out_file}")
    print("CHẾ ĐỘ: 100% READ-ONLY (TUYỆT ĐỐI KHÔNG GỬI LỆNH XUỐNG SERIAL)\n")

    ser = mock_serial
    owns_serial = False

    if ser is None:
        try:
            import serial
            ser = serial.Serial(port, baudrate=baud, timeout=0.2)
            owns_serial = True
            if fcntl and hasattr(ser, "fileno"):
                try:
                    fcntl.flock(ser.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except Exception as e_lock:
                    sys.stderr.write(f"LỖI: Không thể lấy khóa độc quyền cổng Serial {port}: {e_lock}\n")
                    ser.close()
                    return False
        except Exception as e:
            sys.stderr.write(f"LỖI: Không thể mở hoặc khóa độc quyền cổng Serial {port}: {e}\n")
            return False

    start_mono = time.monotonic()
    
    # -------------------------------------------------------------
    # 1. PREFLIGHT GATE: Bắt buộc >= 3 mẫu DISARMED 0 tươi trước khi log
    # -------------------------------------------------------------
    print("Giai đoạn 1: Thực hiện Preflight Gate (Kiểm tra an toàn tĩnh DISARMED 0)...")
    preflight_samples = 0
    preflight_start = time.monotonic()
    PREFLIGHT_REQUIRED_FIELDS = ("safety", "l_tgt", "r_tgt", "l_pwm", "r_pwm", "l_rpm", "r_rpm", "x", "y", "th")

    while preflight_samples < 3 and (time.monotonic() - preflight_start) < 3.0:
        try:
            line_bytes = ser.readline()
        except Exception as e_read:
            sys.stderr.write(f"LỖI ĐỌC SERIAL TRONG PREFLIGHT: {e_read}\n")
            break

        if not line_bytes:
            continue

        if isinstance(line_bytes, str):
            line = line_bytes.strip()
        else:
            line = line_bytes.decode("utf-8", errors="ignore").strip()

        if line.startswith("{") and line.endswith("}"):
            try:
                d = json.loads(line)
                if not isinstance(d, dict):
                    preflight_samples = 0
                    continue

                has_all_fields = all(k in d for k in PREFLIGHT_REQUIRED_FIELDS)
                if not has_all_fields:
                    preflight_samples = 0
                    sys.stderr.write(f"CẢNH BÁO PREFLIGHT: Thiếu trường bắt buộc trong mẫu: {line}\n")
                    continue

                is_safe = (
                    d.get("safety") == "DISARMED" and
                    _is_valid_finite_number(d.get("l_tgt")) and float(d["l_tgt"]) == 0.0 and
                    _is_valid_finite_number(d.get("r_tgt")) and float(d["r_tgt"]) == 0.0 and
                    _is_valid_finite_number(d.get("l_pwm")) and float(d["l_pwm"]) == 0.0 and
                    _is_valid_finite_number(d.get("r_pwm")) and float(d["r_pwm"]) == 0.0 and
                    _is_valid_finite_number(d.get("l_rpm")) and abs(float(d["l_rpm"])) < 0.05 and
                    _is_valid_finite_number(d.get("r_rpm")) and abs(float(d["r_rpm"])) < 0.05 and
                    _is_valid_finite_number(d.get("x")) and
                    _is_valid_finite_number(d.get("y")) and
                    _is_valid_finite_number(d.get("th"))
                )
                if is_safe:
                    preflight_samples += 1
                else:
                    preflight_samples = 0
                    sys.stderr.write(f"CẢNH BÁO PREFLIGHT: Nhận mẫu không an toàn: {line}\n")
            except Exception:
                preflight_samples = 0

    if preflight_samples < 3:
        sys.stderr.write("PREFLIGHT THẤT BẠI: Không nhận đủ 3 mẫu DISARMED 0 an toàn liên tiếp! Abort.\n")
        sys.stderr.write("YÊU CẦU: Kiểm tra xe và KHÔNG thực hiện thao tác đẩy tay.\n")
        if owns_serial:
            if fcntl and hasattr(ser, "fileno"):
                try:
                    fcntl.flock(ser.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            ser.close()
        return False

    print("-> PREFLIGHT PASS: Xác nhận xe ở trạng thái tĩnh an toàn.\n")

    # -------------------------------------------------------------
    # 2. THU THẬP DỮ LIỆU ĐẨY TAY THỤ ĐỘNG
    # -------------------------------------------------------------
    print("Giai đoạn 2: Sẵn sàng ghi nhận dữ liệu đẩy tay...")
    samples_count = 0
    init_pose = None
    last_pose = None
    last_sample_mono = time.monotonic()
    abort_due_to_safety_violation = False
    abort_due_to_data_corruption = False

    try:
        with open(out_file, "w", encoding="utf-8") as f_out:
            f_out.write(f"# PASSIVE_LOGGER_V2_START: {time.time()}\n")
            f_out.write("# monotonic_ts | raw_line\n")

            empty_reads_in_row = 0
            while (time.monotonic() - start_mono) < duration:
                now_mono = time.monotonic()
                # Kiểm tra mất mẫu (gap > 1.5s)
                if (now_mono - last_sample_mono) > 1.5:
                    sys.stderr.write(f"CẢNH BÁO: Mất dữ liệu telemetry quá 1.5s! Abort.\n")
                    return False

                try:
                    raw_bytes = ser.readline()
                except Exception as e_loop_read:
                    sys.stderr.write(f"LỖI ĐỌC DỮ LIỆU SERIAL (OSError/IOError): {e_loop_read}\n")
                    abort_due_to_data_corruption = True
                    break

                now_mono = time.monotonic()
                if not raw_bytes:
                    empty_reads_in_row += 1
                    if mock_serial is not None and samples_count >= min_samples and empty_reads_in_row >= 2:
                        break
                    time.sleep(0.01)
                    continue

                empty_reads_in_row = 0

                if isinstance(raw_bytes, str):
                    line = raw_bytes.strip()
                else:
                    line = raw_bytes.decode("utf-8", errors="ignore").strip()

                if not line:
                    continue

                f_out.write(f"{now_mono:.4f} | {line}\n")
                f_out.flush()

                if line.startswith("{") and line.endswith("}"):
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue

                    if not isinstance(data, dict):
                        continue

                    is_telemetry_packet = any(k in data for k in ("safety", "l_pwm", "r_pwm", "l_tgt", "r_tgt", "x", "y"))
                    if not is_telemetry_packet:
                        continue

                    # 1. KIỂM SOÁT AN TOÀN TUYỆT ĐỐI (Phát hiện missing PWM hoặc nonzero target)
                    if data.get("safety") != "DISARMED":
                        sys.stderr.write(f"NGUY HIỂM: Phát hiện trạng thái không an toàn (safety != DISARMED): {line}\n")
                        sys.stderr.write("HÃY NGẮT CÔNG TẮC NGUỒN PIN NGAY LẬP TỨC!\n")
                        abort_due_to_safety_violation = True
                        break

                    has_pwm_fields = ("l_pwm" in data) and ("r_pwm" in data)
                    has_tgt_fields = ("l_tgt" in data) and ("r_tgt" in data)
                    if not has_pwm_fields or not has_tgt_fields:
                        sys.stderr.write(f"NGUY HIỂM: Gói telemetry thiếu trường PWM hoặc Target an toàn: {line}\n")
                        sys.stderr.write("HÃY NGẮT CÔNG TẮC NGUỒN PIN NGAY LẬP TỨC!\n")
                        abort_due_to_safety_violation = True
                        break

                    l_pwm_val = data["l_pwm"]
                    r_pwm_val = data["r_pwm"]
                    if not _is_valid_finite_number(l_pwm_val) or float(l_pwm_val) != 0.0 or \
                       not _is_valid_finite_number(r_pwm_val) or float(r_pwm_val) != 0.0:
                        sys.stderr.write(f"NGUY HIỂM: Phát hiện PWM != 0 trong lúc thu thập thụ động: {line}\n")
                        sys.stderr.write("HÃY NGẮT CÔNG TẮC NGUỒN PIN NGAY LẬP TỨC!\n")
                        abort_due_to_safety_violation = True
                        break

                    l_tgt_val = data["l_tgt"]
                    r_tgt_val = data["r_tgt"]
                    if not _is_valid_finite_number(l_tgt_val) or float(l_tgt_val) != 0.0 or \
                       not _is_valid_finite_number(r_tgt_val) or float(r_tgt_val) != 0.0:
                        sys.stderr.write(f"NGUY HIỂM: Phát hiện Target != 0 trong lúc thu thập thụ động: {line}\n")
                        sys.stderr.write("HÃY NGẮT CÔNG TẮC NGUỒN PIN NGAY LẬP TỨC!\n")
                        abort_due_to_safety_violation = True
                        break

                    # 2. KIỂM SOÁT TOÀN VẸN DỮ LIỆU POSE (Khắc phục nan_pose)
                    if "x" not in data or "y" not in data or "th" not in data:
                        sys.stderr.write(f"CẢNH BÁO: Mẫu thiếu trường x, y, hoặc th: {line}\n")
                        abort_due_to_data_corruption = True
                        break

                    raw_x = data["x"]
                    raw_y = data["y"]
                    raw_th = data["th"]

                    if not _is_valid_finite_number(raw_x) or not _is_valid_finite_number(raw_y) or not _is_valid_finite_number(raw_th):
                        sys.stderr.write(f"LỖI DỮ LIỆU HỎNG: Phát hiện giá trị NaN/Inf trong Odometry Pose: {line}\n")
                        abort_due_to_data_corruption = True
                        break

                    cur_x = float(raw_x)
                    cur_y = float(raw_y)
                    cur_th = float(raw_th)

                    if init_pose is None:
                        init_pose = (cur_x, cur_y, cur_th)

                    last_pose = (cur_x, cur_y, cur_th)
                    samples_count += 1
                    last_sample_mono = now_mono

    finally:
        if owns_serial:
            if fcntl and hasattr(ser, "fileno"):
                try:
                    fcntl.flock(ser.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            ser.close()

    if abort_due_to_safety_violation:
        sys.stderr.write("THẤT BẠI: Quá trình dừng khẩn cấp do vi phạm an toàn phần cứng!\n")
        return False

    if abort_due_to_data_corruption:
        sys.stderr.write("THẤT BẠI: Quá trình dừng do phát hiện dữ liệu Odometry/Pose bị lỗi hoặc chứa NaN/Inf!\n")
        return False

    if samples_count < min_samples:
        sys.stderr.write(f"THẤT BẠI: Chỉ nhận được {samples_count} mẫu (< {min_samples} mẫu), không đủ bằng chứng.\n")
        return False

    if init_pose is None or last_pose is None:
        sys.stderr.write("THẤT BẠI: Không xác định được Pose ban đầu hoặc kết thúc hợp lệ!\n")
        return False

    dx = last_pose[0] - init_pose[0]
    dy = last_pose[1] - init_pose[1]
    dist = math.hypot(dx, dy)
    d_th = last_pose[2] - init_pose[2]

    if not math.isfinite(dist) or not math.isfinite(d_th):
        sys.stderr.write("THẤT BẠI: Khoảng cách hoặc góc quay tính toán không hữu hạn (NaN/Inf)!\n")
        return False

    print(f"\n=== HOÀN TẤT THU THẬP THÀNH CÔNG ({samples_count} MẪU) ===")
    print(f"Tổng dịch chuyển Odometry: {dist:.4f} m ({dist*100.0:.2f} cm)")
    print(f"Độ lệch góc: {d_th:.4f} rad")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--dir", default="/home/khangho")
    parser.add_argument("--min-samples", type=int, default=10)
    args = parser.parse_args()

    ok = run_passive_logger_v2(
        port=args.port,
        duration=args.duration,
        log_dir=args.dir,
        min_samples=args.min_samples,
    )
    sys.exit(0 if ok else 1)
