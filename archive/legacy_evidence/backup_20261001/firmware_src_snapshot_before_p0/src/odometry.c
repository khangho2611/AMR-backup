/**
 * @file odometry.c
 * @brief Hiện thực thuật toán Động học và Tích phân Odometry Runge-Kutta bậc 2
 */

#include "odometry.h"
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

/* Chuẩn hóa góc về khoảng [-PI, +PI] */
static float Normalize_Angle(float angle)
{
    while (angle > (float)M_PI)  angle -= 2.0f * (float)M_PI;
    while (angle < -(float)M_PI) angle += 2.0f * (float)M_PI;
    return angle;
}

void Odometry_Init(Odometry_t *odom, float init_x, float init_y, float init_theta)
{
    if (!odom) return;
    odom->x = init_x;
    odom->y = init_y;
    odom->theta = Normalize_Angle(init_theta);
    odom->v_linear = 0.0f;
    odom->omega_angular = 0.0f;
    odom->prev_left_count = 0;
    odom->prev_right_count = 0;
    odom->wheel_radius = ROBOT_WHEEL_RADIUS;
    odom->wheel_base = ROBOT_WHEEL_BASE;
    odom->meters_per_count = ROBOT_METERS_PER_COUNT;
}

void Odometry_Reset(Odometry_t *odom, float x, float y, float theta)
{
    if (!odom) return;
    odom->x = x;
    odom->y = y;
    odom->theta = Normalize_Angle(theta);
    odom->v_linear = 0.0f;
    odom->omega_angular = 0.0f;
}

void Odometry_Update(Odometry_t *odom, int32_t left_total_count, int32_t right_total_count, float dt)
{
    if (!odom || dt <= 0.0001f) return;

    /* 1. Tính delta số xung giữa 2 chu kỳ */
    int32_t delta_l = left_total_count - odom->prev_left_count;
    int32_t delta_r = right_total_count - odom->prev_right_count;

    odom->prev_left_count = left_total_count;
    odom->prev_right_count = right_total_count;

    /* 2. Quy đổi ra quãng đường dịch chuyển của từng bánh (mét) */
    float d_l = (float)delta_l * odom->meters_per_count;
    float d_r = (float)delta_r * odom->meters_per_count;

    /* 3. Động học thuận: Quãng đường tịnh tiến ds và góc xoay d_theta */
    float ds = (d_r + d_l) / 2.0f;
    float d_theta = (d_r - d_l) / odom->wheel_base;

    /* 4. Vận tốc tức thời thân xe */
    odom->v_linear = ds / dt;
    odom->omega_angular = d_theta / dt;

    /* 5. Tích phân quỹ đạo Runge-Kutta bậc 2 (chính xác hơn xấp xỉ Euler thuần) */
    float mid_theta = odom->theta + (d_theta / 2.0f);
    odom->x += ds * cosf(mid_theta);
    odom->y += ds * sinf(mid_theta);
    odom->theta = Normalize_Angle(odom->theta + d_theta);
}

void Kinematics_Inverse(float v_linear, float omega_angular, float *out_rpm_left, float *out_rpm_right)
{
    if (!out_rpm_left || !out_rpm_right) return;

    /* Vận tốc dài yêu cầu tại mỗi bánh xe: v = v_robot +- omega * (L / 2) */
    float v_l = v_linear - (omega_angular * ROBOT_WHEEL_BASE / 2.0f);
    float v_r = v_linear + (omega_angular * ROBOT_WHEEL_BASE / 2.0f);

    /* Vận tốc góc bánh xe: omega_wheel = v / R (rad/s) */
    /* RPM = (omega_wheel * 60) / (2 * PI) = (v / R) * (30 / PI) */
    const float rad_to_rpm = 60.0f / (2.0f * (float)M_PI);
    *out_rpm_left  = (v_l / ROBOT_WHEEL_RADIUS) * rad_to_rpm;
    *out_rpm_right = (v_r / ROBOT_WHEEL_RADIUS) * rad_to_rpm;
}

void Kinematics_Forward(float rpm_left, float rpm_right, float *out_v, float *out_omega)
{
    if (!out_v || !out_omega) return;

    /* RPM -> rad/s: omega_wheel = RPM * (2 * PI / 60) */
    const float rpm_to_rad = (2.0f * (float)M_PI) / 60.0f;
    float w_l = rpm_left * rpm_to_rad;
    float w_r = rpm_right * rpm_to_rad;

    /* v = R * (w_R + w_L) / 2 */
    *out_v = ROBOT_WHEEL_RADIUS * (w_r + w_l) / 2.0f;
    /* omega = R * (w_R - w_L) / L */
    *out_omega = ROBOT_WHEEL_RADIUS * (w_r - w_l) / ROBOT_WHEEL_BASE;
}
