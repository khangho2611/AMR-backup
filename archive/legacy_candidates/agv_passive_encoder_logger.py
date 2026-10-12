#!/usr/bin/env python3
"""
agv_passive_encoder_logger.py
Công cụ đọc thụ động (READ-ONLY) dữ liệu Telemetry Serial phục vụ thử nghiệm đẩy tay (Hand-Push).
Tuân thủ nghiêm ngặt chỉ đạo an toàn Codex 14:54:
  - 100% READ-ONLY: Tuyệt đối KHÔNG ghi bất kỳ byte nào xuống Serial (Không ARM, không V, không S, không M, không ClearFault).
  - Không gửi lệnh reset odom.
  - Có giới hạn thời gian (Timeout định trước).
  - Ghi raw timestamp, đếm số mẫu, theo dõi delta pose (x, y, theta) và raw counts / RPM.
"""

import sys
import os
import time
import json
import argparse
import fcntl

def run_passive_logger(port="/dev/ttyUSB0", baud=115200, duration=15.0, output_log="/home/khangho/passive_hand_push.log"):
    print(f"=== KHỞI ĐỘNG PASSIVE READ-ONLY LOGGER ({duration}s) ===")
    print(f"Cổng: {port}, Baud: {baud}")
    print(f"File log: {output_log}")
    print("CHẾ ĐỘ: 100% READ-ONLY (KHÔNG PHÁT LỆNH SERIAL)\n")

    import serial
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.2)
    except Exception as e:
        print(f"LỖI: Không thể mở cổng Serial {port}: {e}")
        return False

    # Khóa độc quyền cổng
    try:
        fcntl.flock(ser.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception as e:
        print(f"LỖI: Cổng Serial đang bị chiếm dụng bởi tiến trình khác: {e}")
        ser.close()
        return False

    start_time = time.monotonic()
    samples_count = 0
    init_pose = None
    last_pose = None

    try:
        with open(output_log, "w", encoding="utf-8") as f_out:
            f_out.write(f"# PASSIVE READ-ONLY LOG START: {time.time()}\n")
            f_out.write("# monotonic_ts | raw_line\n")

            while time.monotonic() - start_time < duration:
                raw_bytes = ser.readline()
                if not raw_bytes:
                    continue

                now_mono = time.monotonic()
                line = raw_bytes.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                f_out.write(f"{now_mono:.4f} | {line}\n")
                f_out.flush()

                if line.startswith("{") and line.endswith("}"):
                    try:
                        data = json.loads(line)
                        if "safety" in data and "x" in data and "y" in data:
                            samples_count += 1
                            cur_x = float(data.get("x", 0.0))
                            cur_y = float(data.get("y", 0.0))
                            cur_th = float(data.get("th", 0.0))
                            safety = data.get("safety", "UNKNOWN")

                            if init_pose is None:
                                init_pose = (cur_x, cur_y, cur_th)
                                print(f"-> Mốc Pose ban đầu (Sample 1): x={cur_x:.4f}, y={cur_y:.4f}, th={cur_th:.4f}, Safety={safety}")

                            last_pose = (cur_x, cur_y, cur_th)

                            if samples_count % 10 == 0:
                                dx = cur_x - init_pose[0]
                                dy = cur_y - init_pose[1]
                                dist = (dx*dx + dy*dy)**0.5
                                print(f"Sample {samples_count:3d} (t={now_mono - start_time:4.1f}s) | Dist={dist*100.0:5.2f} cm | RPM=[{data.get('l_rpm')},{data.get('r_rpm')}] | Safety={safety}")
                    except Exception:
                        pass
    finally:
        try:
            fcntl.flock(ser.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        ser.close()

    print(f"\n=== HOÀN TẤT THU THẬP ({samples_count} MẪU) ===")
    if init_pose and last_pose:
        dx = last_pose[0] - init_pose[0]
        dy = last_pose[1] - init_pose[1]
        total_dist = (dx*dx + dy*dy)**0.5
        d_th = last_pose[2] - init_pose[2]
        print(f"Tổng quãng đường dịch chuyển đo được trên Odometry: {total_dist:.4f} m ({total_dist*100.0:.2f} cm)")
        print(f"Độ lệch góc: {d_th:.4f} rad")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Passive Serial Logger")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--duration", type=float, default=15.0, help="Duration in seconds")
    parser.add_argument("--out", default="/home/khangho/passive_hand_push.log", help="Output file")
    args = parser.parse_args()

    run_passive_logger(port=args.port, duration=args.duration, output_log=args.out)
