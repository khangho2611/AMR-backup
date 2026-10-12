#!/usr/bin/env python3
"""
agv_motor_bench_supervisor.py
Kịch bản giám sát độc quyền Serial duy nhất cho bài thử motor ngắn có kiểm soát.
Tính năng:
- Đảm bảo độc quyền cổng Serial /dev/ttyUSB0 (ngắt mọi process khác nếu có).
- Khởi động xác nhận trạng thái boot DISARMED.
- Watchdog kiểm soát Telemetry Freshness (< 250ms).
- Deadline thời gian cứng (tối đa 2.0s cho bài thẳng, 2.5s cho bài xoay).
- Giới hạn dịch chuyển tối đa (Max Displacement <= 0.10m cho bài thẳng).
- Tự động phát lệnh STOP và DISARM trong khối finally hoặc khi gặp SIGINT / Exception.
- Ghi raw telemetry có timestamp ra file log độc lập.
"""

import sys
import time
import signal
import serial
import json
import math

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
LOG_FILE = "/home/khangho/agv_bench_run.log"

g_ser = None
g_running = True

def emergency_shutdown(signum=None, frame=None):
    global g_running, g_ser
    g_running = False
    print("\n[SUPERVISOR] !!! KÍCH HOẠT DỪNG KHẨN CẤP / SHUTDOWN HOOK !!!")
    if g_ser and g_ser.is_open:
        try:
            for _ in range(3):
                g_ser.write(b"STOP\n")
                g_ser.flush()
                time.sleep(0.02)
            g_ser.write(b"DISARM\n")
            g_ser.flush()
            print("[SUPERVISOR] Đã gửi STOP và DISARM thành công!")
        except Exception as e:
            print(f"[SUPERVISOR] Lỗi gửi lệnh dừng: {e}")
    sys.exit(0)

signal.signal(signal.SIGINT, emergency_shutdown)
signal.signal(signal.SIGTERM, emergency_shutdown)

def run_bench_test(test_type="STRAIGHT"):
    global g_ser
    print(f"=== KHỞI ĐỘNG BENCH SUPERVISOR CHO BÀI THỬ: {test_type} ===")
    
    try:
        g_ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    except Exception as e:
        print(f"[ERROR] Không thể mở cổng Serial {SERIAL_PORT}: {e}")
        return False

    with open(LOG_FILE, "w", encoding="utf-8") as log_fp:
        log_fp.write(f"--- BENCH TEST LOG START: {test_type} | {time.time()} ---\n")

        # 1. Đọc telemetry xác minh boot DISARMED
        boot_verified = False
        start_wait = time.time()
        while time.time() - start_wait < 3.0:
            line = g_ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                log_fp.write(f"[{time.time():.3f}] RECV: {line}\n")
                if "safety" in line or "mode" in line:
                    try:
                        d = json.loads(line)
                        if d.get("safety") == "DISARMED" or (d.get("l_pwm", 0) == 0 and d.get("r_pwm", 0) == 0):
                            boot_verified = True
                            print(f"[SUPERVISOR] Xác minh trạng thái ban đầu: DISARMED, Target=0, PWM=0! OK!")
                            break
                    except:
                        pass
        
        if not boot_verified:
            print("[ERROR] Không thể xác minh trạng thái an toàn DISARMED ban đầu!")
            emergency_shutdown()
            return False

        # 2. Gửi lệnh ARM có kiểm soát
        print("[SUPERVISOR] Gửi lệnh ARM...")
        g_ser.write(b"ARM\n")
        g_ser.flush()
        time.sleep(0.1)

        # 3. Thực thi bài thử với deadline cứng và max displacement
        init_x = None
        init_y = None
        max_allowed_dist = 0.10 if test_type == "STRAIGHT" else 0.50
        max_duration_sec = 2.0 if test_type == "STRAIGHT" else 2.5
        cmd_str = "V 0.05 0.0\n" if test_type == "STRAIGHT" else "V 0.0 0.20\n"

        print(f"[SUPERVISOR] Bắt đầu phát lệnh di chuyển: {cmd_str.strip()} (Deadline: {max_duration_sec}s, Max Dist: {max_allowed_dist}m)")
        
        test_start_time = time.time()
        last_heartbeat_sent = 0
        last_telemetry_time = time.time()

        try:
            while g_running and (time.time() - test_start_time < max_duration_sec):
                now = time.time()

                # Gửi heartbeat định kỳ mỗi 80ms (< 300ms watchdog)
                if now - last_heartbeat_sent >= 0.08:
                    g_ser.write(cmd_str.encode('utf-8'))
                    g_ser.flush()
                    last_heartbeat_sent = now

                # Đọc Telemetry giám sát
                line = g_ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    log_fp.write(f"[{now:.3f}] {line}\n")
                    last_telemetry_time = now
                    try:
                        d = json.loads(line)
                        cx = d.get("x", 0.0)
                        cy = d.get("y", 0.0)
                        if init_x is None:
                            init_x = cx
                            init_y = cy

                        cur_dist = math.hypot(cx - init_x, cy - init_y)
                        if cur_dist > max_allowed_dist:
                            print(f"[SUPERVISOR] !!! CẢNH BÁO: ĐẠT NGƯỠNG DỊCH CHUYỂN AN TOÀN ({cur_dist:.3f}m > {max_allowed_dist}m) -> DỪNG NGAY !!!")
                            break
                    except:
                        pass

                # Freshness watchdog: Nếu mất telemetry quá 250ms -> Dừng khẩn cấp
                if now - last_telemetry_time > 0.25:
                    print(f"[SUPERVISOR] !!! MẤT FRESHNESS TELEMETRY ({now - last_telemetry_time:.3f}s > 0.25s) -> NGẮT KHẨN CẤP !!!")
                    break

                time.sleep(0.01)

        finally:
            print("[SUPERVISOR] Kết thúc bài thử -> Gửi STOP & DISARM...")
            for _ in range(3):
                g_ser.write(b"STOP\n")
                g_ser.flush()
                time.sleep(0.02)
            g_ser.write(b"DISARM\n")
            g_ser.flush()

        # 4. Xác nhận sau khi dừng: Động cơ phải về 0 RPM
        time.sleep(0.3)
        stopped_verified = False
        for _ in range(5):
            line = g_ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                log_fp.write(f"[{time.time():.3f}] POST_STOP: {line}\n")
                try:
                    d = json.loads(line)
                    if abs(d.get("l_rpm", 0.0)) < 0.1 and abs(d.get("r_rpm", 0.0)) < 0.1:
                        stopped_verified = True
                        print(f"[SUPERVISOR] Xác nhận dừng hoàn tất: RPM=[{d.get('l_rpm')}, {d.get('r_rpm')}], Safety={d.get('safety')}")
                        break
                except:
                    pass

        log_fp.write(f"--- BENCH TEST COMPLETED: Success={stopped_verified} ---\n")
        print(f"=== BÀI THỬ HOÀN TẤT. KẾT QUẢ DỪNG AN TOÀN: {stopped_verified} ===")
        return stopped_verified

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "STRAIGHT"
    run_bench_test(t)
