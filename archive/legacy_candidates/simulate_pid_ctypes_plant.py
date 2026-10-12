import sys
import ctypes
import os

# Tải thư viện chia sẻ libpid.so đã biên dịch từ pid.c thật
so_path = "/tmp/libpid.so"
if not os.path.exists(so_path):
    print(f"Lỗi: Không tìm thấy {so_path}")
    sys.exit(1)

c_lib = ctypes.CDLL(so_path)

class PID_t(ctypes.Structure):
    _fields_ = [
        ("kp", ctypes.c_float),
        ("ki", ctypes.c_float),
        ("kd", ctypes.c_float),
        ("kf", ctypes.c_float),
        ("integral", ctypes.c_float),
        ("prev_measured", ctypes.c_float),
        ("out_min", ctypes.c_float),
        ("out_max", ctypes.c_float),
    ]

c_lib.PID_Init.argtypes = [ctypes.POINTER(PID_t), ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
c_lib.PID_Init.restype = None

c_lib.PID_Compute.argtypes = [ctypes.POINTER(PID_t), ctypes.c_float, ctypes.c_float, ctypes.c_float]
c_lib.PID_Compute.restype = ctypes.c_float

print("=== MÔ PHỎNG KHẢO SÁT PLANT GIẢ ĐỊNH VỚI CONTROLLER LINK pid.c THẬT ===")
print("LƯU Ý: Đây là khảo sát toán học giả thuyết (HYPOTHESIS), các thông số deadzone và gain của Plant chỉ là giả định chưa đo đạc trực tiếp trên động cơ tháo rời.\n")

deadband_candidates = [25.0, 35.0, 45.0, 52.0]
target_rpm = 13.0
dt = 0.05
steps = 40 # 2.0 giây

for db in deadband_candidates:
    pid = PID_t()
    c_lib.PID_Init(ctypes.byref(pid), 0.5, 1.5, 0.01, 0.45, -255.0, 255.0)

    cur_rpm = 0.0
    displacement_m = 0.0
    cpr = 937.2
    wheel_r = 0.0366

    print(f"--- Giả định Deadband ma sát tĩnh = {db:.1f} PWM ---")
    for s in range(steps):
        pwm = c_lib.PID_Compute(ctypes.byref(pid), target_rpm, cur_rpm, dt)

        # Plant dynamics giả định
        if pwm < db:
            cur_rpm = 0.0
        else:
            # Khi vượt ngưỡng ma sát
            target_free = (pwm / 255.0) * 110.0
            cur_rpm += (target_free - cur_rpm) * (dt / 0.15)

        ticks = (cur_rpm / 60.0) * cpr * dt
        displacement_m += (ticks / cpr) * (2.0 * 3.14159265 * wheel_r)

    print(f"  Kết quả sau 2.0s: PWM cuối = {pwm:.1f}, RPM cuối = {cur_rpm:.2f}, Quãng đường = {displacement_m*1000.0:.2f} mm")
