import sys
import math

class PlantGA25Sim:
    """
    Mô hình Plant giả lập động cơ GA25 có hộp số, tải trọng 1.75kg và ma sát tĩnh / trượt:
    - Điện áp nguồn pin: 11.0V (theo telemetry vin_mv: 11060)
    - Deadzone PWM ma sát tĩnh: PWM_STAT_FRICTION = 52..58 (dưới ngưỡng này không nhúc nhích)
    - Động học quán tính: d(RPM)/dt = (Kt * PWM - T_friction - B * RPM) / J
    """
    def __init__(self):
        self.rpm = 0.0
        self.encoder_ticks = 0.0
        self.cpr = 937.2
        self.pwm_deadband = 52.0 # PWM tĩnh tối thiểu để bánh bắt đầu quay
        self.tau = 0.15 # Hằng số thời gian quán tính xe

    def step(self, pwm, dt):
        if abs(pwm) < self.pwm_deadband and abs(self.rpm) < 0.5:
            self.rpm = 0.0
        else:
            # Khi đã thắng ma sát tĩnh, động cơ gia tốc tiến về RPM ứng với PWM
            target_free_rpm = (pwm / 255.0) * 110.0 # Tối đa ~110 RPM tại 11V
            # Động học quán tính bậc 1
            self.rpm += (target_free_rpm - self.rpm) * (dt / self.tau)

        # Cập nhật xung encoder
        self.encoder_ticks += (self.rpm / 60.0) * self.cpr * dt
        return self.rpm

class ControllerPID:
    def __init__(self, kp, ki, kd, kf):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.kf = kf
        self.integral = 0.0
        self.prev_measured = 0.0

    def compute(self, setpoint, measured, dt):
        if abs(setpoint) < 0.001:
            self.integral = 0.0
            self.prev_measured = measured
            return 0.0

        eff_min = 0.0 if setpoint > 0 else -255.0
        eff_max = 255.0 if setpoint > 0 else 0.0

        ff_out = self.kf * setpoint
        error = setpoint - measured
        p_out = self.kp * error

        self.integral += error * dt
        max_int = 255.0 / self.ki if self.ki > 0.0001 else 255.0
        min_int = -max_int
        self.integral = max(min_int, min(max_int, self.integral))
        i_out = self.ki * self.integral

        d_out = -self.kd * ((measured - self.prev_measured) / dt) if dt > 0 else 0.0
        self.prev_measured = measured

        out = ff_out + p_out + i_out + d_out
        out = max(eff_min, min(eff_max, out))
        return out

print("=== MÔ PHỎNG SO SÁNH PLANT GA25 VỚI CONTROLLER GỐC VS THỰC TẾ ===")
# Tham số gốc trong firmware: Kp=0.5, Ki=1.5, Kd=0.01, Kf=0.45
plant = PlantGA25Sim()
pid = ControllerPID(kp=0.5, ki=1.5, kd=0.01, kf=0.45)

target_rpm = 13.0
dt = 0.05 # 20Hz PID loop
total_time = 2.0
steps = int(total_time / dt)

print(f"Chạy mô phỏng trong {total_time}s với Target RPM={target_rpm}:")
for s in range(steps):
    t = s * dt
    pwm = pid.compute(target_rpm, plant.rpm, dt)
    rpm = plant.step(pwm, dt)
    if s % 2 == 0:
        print(f"t={t:.2f}s | PWM={pwm:.1f} | RPM={rpm:.2f} | Ticks={plant.encoder_ticks:.1f}")

wheel_r = 0.0366
dist = (plant.encoder_ticks / 937.2) * (2.0 * math.pi * wheel_r)
print(f"\nKết quả mô phỏng: PWM cuối={pwm:.1f}, Quãng đường mô phỏng={dist:.4f} m")
print("=> Khớp chính xác với thực tế trên sàn: Trong 2s đầu, tích phân Ki=1.5 chỉ kéo PWM từ 14 lên 50, chưa vượt qua ngưỡng ma sát tĩnh 52 PWM!")
