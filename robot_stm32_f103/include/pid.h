#ifndef INC_PID_H_
#define INC_PID_H_

#include <stdint.h>

#define PID_MIN_PWM_FLOOR           25.0f

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    float kp;               /* Hệ số tỉ lệ (Proportional) */
    float ki;               /* Hệ số tích phân (Integral) */
    float kd;               /* Hệ số vi phân (Derivative) */
    float kf;               /* Hệ số feedforward tốc độ */

    float integral;         /* Tích phân sai số tích lũy */
    float prev_measured;    /* Giá trị đo chu kỳ trước (cho derivative-on-measurement) */

    float out_min;          /* Giới hạn xuất nhỏ nhất (vd: -255.0f) */
    float out_max;          /* Giới hạn xuất lớn nhất (vd: +255.0f) */
} PID_t;

/**
 * @brief  Khởi tạo bộ điều khiển PID
 * @param  pid: Con trỏ tới cấu trúc PID_t
 * @param  kp, ki, kd, kf: Các hệ số điều khiển
 * @param  out_min, out_max: Giới hạn đầu ra PWM (-255..+255)
 */
void PID_Init(PID_t *pid, float kp, float ki, float kd, float kf, float out_min, float out_max);

/**
 * @brief  Cập nhật hệ số PID khi đang chạy (Tuning on-the-fly)
 */
void PID_SetGains(PID_t *pid, float kp, float ki, float kd, float kf);

/**
 * @brief  Tính toán ngõ ra PID cho 1 chu kỳ lấy mẫu
 * @param  pid: Con trỏ tới PID_t
 * @param  setpoint: Giá trị mong muốn (Target RPM)
 * @param  measured: Giá trị đo thực tế (Actual RPM)
 * @param  dt: Chu kỳ lấy mẫu (giây, ví dụ 0.05f)
 * @retval Giá trị điều khiển PWM (-255..+255)
 */
float PID_Compute(PID_t *pid, float setpoint, float measured, float dt);

/**
 * @brief  Reset bộ tích phân và trạng thái PID về 0
 */
void PID_Reset(PID_t *pid);

#ifdef __cplusplus
}
#endif

#endif /* INC_PID_H_ */
