#include "pid.h"
#include <math.h>

void PID_Init(PID_t *pid, float kp, float ki, float kd, float kf, float out_min, float out_max)
{
    if (pid == 0) return;
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->kf = kf;
    pid->out_min = out_min;
    pid->out_max = out_max;
    pid->integral = 0.0f;
    pid->prev_measured = 0.0f;
}

void PID_SetGains(PID_t *pid, float kp, float ki, float kd, float kf)
{
    if (pid == 0) return;
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->kf = kf;
}

float PID_Compute(PID_t *pid, float setpoint, float measured, float dt)
{
    if (pid == 0 || dt <= 0.0001f) return 0.0f;

    /* Khi target = 0, ngắt hoàn toàn công suất và reset tích phân */
    if (fabsf(setpoint) < 0.001f)
    {
        pid->integral = 0.0f;
        pid->prev_measured = measured;
        return 0.0f;
    }

    /*
     * Giới hạn điều khiển theo hướng mong muốn (Unipolar / Quadrant Direction Clamping):
     * Khi xe đang tiến (setpoint > 0): Output PWM chạy trong khoảng [0 .. 255].
     * Khi xe đang lùi (setpoint < 0): Output PWM chạy trong khoảng [-255 .. 0].
     * Kỹ thuật này ngăn chặn hiện tượng H-bridge đảo cực ngược chiều đột ngột khi xảy ra overshoot.
     */
    float eff_min = pid->out_min;
    float eff_max = pid->out_max;

    if (setpoint > 0.0f)
    {
        eff_min = 0.0f;
        if (eff_max > 255.0f) eff_max = 255.0f;
    }
    else if (setpoint < 0.0f)
    {
        eff_max = 0.0f;
        if (eff_min < -255.0f) eff_min = -255.0f;
    }

    /* 1. Feedforward term: u_ff = kf * setpoint */
    float ff_out = pid->kf * setpoint;

    /* 2. Sai số Error */
    float error = setpoint - measured;

    /* 3. Proportional term: u_p = kp * error */
    float p_out = pid->kp * error;

    /* 4. Integral term with Anti-Windup Clamping (cho phép bù trừ feedforward) */
    pid->integral += error * dt;

    if (pid->ki > 0.0001f)
    {
        float max_int = 255.0f / pid->ki;
        float min_int = -255.0f / pid->ki;
        if (pid->integral > max_int) pid->integral = max_int;
        else if (pid->integral < min_int) pid->integral = min_int;
    }
    float i_out = pid->ki * pid->integral;

    /* 5. Derivative term on measurement (tránh derivative kick khi setpoint thay đổi) */
    float d_out = -pid->kd * ((measured - pid->prev_measured) / dt);
    pid->prev_measured = measured;

    /* 6. Tổng hợp tín hiệu điều khiển */
    float output = ff_out + p_out + i_out + d_out;

    /* 7. Giới hạn bão hòa (Output Saturation theo hướng di chuyển) */
    if (output > eff_max) output = eff_max;
    else if (output < eff_min) output = eff_min;

    return output;
}

void PID_Reset(PID_t *pid)
{
    if (pid == 0) return;
    pid->integral = 0.0f;
    pid->prev_measured = 0.0f;
}
