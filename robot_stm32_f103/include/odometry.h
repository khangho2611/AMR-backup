/**
 * @file odometry.h
 * @brief Module Động học thuận, Động học nghịch và Định vị Odometry cho xe 2 bánh vi sai
 *        Thông số phần cứng:
 *          - Bán kính bánh xe R = 0.0366 m (Chu vi C = 23 cm)
 *          - Chiều rộng cơ sở L = 0.1875 m (Khoảng cách tim giữa 2 bánh)
 *          - Độ phân giải Encoder: 937.2 xung / vòng bánh xe
 */

#ifndef ODOMETRY_H_
#define ODOMETRY_H_

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Thông số hình học xe thực tế */
#define ROBOT_WHEEL_RADIUS          0.0366f     /* Bán kính bánh xe R = 36.6 mm = 0.0366 m */
#define ROBOT_WHEEL_BASE            0.1925f     /* Chiều rộng cơ sở hiệu dụng hiệu chuẩn L = 192.5 mm */
#define ROBOT_COUNTS_PER_REV        937.2f      /* 11 PPR * 4 * 21.3 ratio */
#define ROBOT_METERS_PER_COUNT      ((2.0f * 3.14159265f * ROBOT_WHEEL_RADIUS) / ROBOT_COUNTS_PER_REV)

typedef struct
{
    /* Tọa độ và hướng toàn cục (Oxy) */
    float x;                /* Tọa độ X (mét) */
    float y;                /* Tọa độ Y (mét) */
    float theta;            /* Hướng góc đầu xe (radian, -pi..+pi) */

    /* Vận tốc thực tế của thân xe */
    float v_linear;         /* Vận tốc dài tịnh tiến (m/s) */
    float omega_angular;    /* Vận tốc góc tự xoay (rad/s) */

    /* Lưu số đếm xung chu kỳ trước */
    int32_t prev_left_count;
    int32_t prev_right_count;

    /* Tham số hình học có thể hiệu chuẩn */
    float wheel_radius;
    float wheel_base;
    float meters_per_count;
} Odometry_t;

/**
 * @brief Khởi tạo hệ thống Odometry
 */
void Odometry_Init(Odometry_t *odom, float init_x, float init_y, float init_theta);

/**
 * @brief Reset vị trí Odometry về tọa độ mong muốn
 */
void Odometry_Reset(Odometry_t *odom, float x, float y, float theta);

/**
 * @brief Cập nhật tọa độ Odometry bằng tích phân Runge-Kutta bậc 2 mỗi chu kỳ dt
 * @param odom: Con trỏ cấu trúc Odometry_t
 * @param left_total_count: Tổng số xung tích lũy bánh trái
 * @param right_total_count: Tổng số xung tích lũy bánh phải
 * @param dt: Chu kỳ lấy mẫu (giây, vd: 0.05f)
 */
void Odometry_Update(Odometry_t *odom, int32_t left_total_count, int32_t right_total_count, float dt);

/**
 * @brief ĐỘNG HỌC NGHỊCH (Inverse Kinematics):
 *        Nhận vận tốc dài v (m/s) và vận tốc góc omega (rad/s) của thân xe,
 *        tính ra tốc độ vòng quay (Target RPM) cho 2 bánh xe.
 * @param v_linear: Vận tốc tịnh tiến mong muốn (m/s)
 * @param omega_angular: Vận tốc quay góc mong muốn (rad/s)
 * @param out_rpm_left: Con trỏ nhận giá trị RPM bánh trái
 * @param out_rpm_right: Con trỏ nhận giá trị RPM bánh phải
 */
void Kinematics_Inverse(float v_linear, float omega_angular, float *out_rpm_left, float *out_rpm_right);

/**
 * @brief ĐỘNG HỌC THUẬN (Forward Kinematics):
 *        Từ RPM thực tế của 2 bánh xe, tính ra vận tốc dài v (m/s) và vận tốc góc omega (rad/s)
 */
void Kinematics_Forward(float rpm_left, float rpm_right, float *out_v, float *out_omega);

#ifdef __cplusplus
}
#endif

#endif /* ODOMETRY_H_ */
