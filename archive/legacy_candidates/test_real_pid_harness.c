#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
#include <stdbool.h>

/* Khai báo trực tiếp nguyên mẫu và struct từ pid.h thật */
typedef struct
{
    float kp;
    float ki;
    float kd;
    float kf;
    float integral;
    float prev_error;
    float prev_measured;
    float out_min;
    float out_max;
    float max_integral;
    float deadband;
} PID_t;

void PID_Init(PID_t *pid, float kp, float ki, float kd, float kf, float out_min, float out_max);
float PID_Compute(PID_t *pid, float setpoint, float measured, float dt);
void PID_Reset(PID_t *pid);

/* Nhúng trực tiếp file mã nguồn thật pid.c */
#include "pid.c"

int main()
{
    printf("=== KIỂM THỬ KHẢO SÁT PID THỰC TẾ (LINK pid.c THẬT) ===\n");

    /* 1. Kiểm tra trường hợp Setpoint = 0.0 (Dừng / Phanh) */
    PID_t pid_test;
    PID_Init(&pid_test, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);

    /* Giả lập bộ tích phân đang tích lũy lớn */
    pid_test.integral = 150.0f;
    float out_zero = PID_Compute(&pid_test, 0.0f, 10.0f, 0.05f);
    printf("[KIỂM TRA 1] Setpoint = 0.0 -> Output = %.4f, Integral sau lệnh = %.4f\n", out_zero, pid_test.integral);
    if (out_zero == 0.0f && pid_test.integral == 0.0f)
    {
        printf("-> KẾT QUẢ: PASS (Khi Setpoint = 0.0, bộ tích phân bị xóa sạch và Output lập tức về 0, không có hiện tượng kick giật khi phanh)\n");
    }
    else
    {
        printf("-> KẾT QUẢ: FAIL\n");
    }

    /* 2. Khảo sát chuỗi đáp ứng với Setpoint = 13.0 RPM (Bài test thực tế) */
    printf("\n[KIỂM TRA 2] Mô phỏng đáp ứng toán học của PID thật trong 20 chu kỳ (dt = 0.05s, Setpoint = 13.0 RPM)\n");
    PID_Init(&pid_test, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);

    float measured_rpm = 0.0f;
    for (int step = 1; step <= 20; step++)
    {
        /* Mẫu 7 phát hiện RPM nhích 2.56 như log thực nghiệm */
        if (step == 7) measured_rpm = 2.56f;
        else if (step >= 18) measured_rpm = 5.12f;
        else if (step > 7 && step < 18) measured_rpm = 0.0f;

        float out_pwm = PID_Compute(&pid_test, 13.0f, measured_rpm, 0.05f);
        if (step % 2 == 0 || step == 1 || step == 7 || step == 18 || step == 20)
        {
            printf("  Chu kỳ %2d (t=%.2fs): Measured=%.2f RPM -> Output PWM = %5.1f (Integral=%.2f)\n",
                   step, step * 0.05f, measured_rpm, out_pwm, pid_test.integral);
        }
    }

    /* 3. Kiểm tra cơ chế Anti-Windup và Saturation khi kẹt động cơ dài hạn */
    printf("\n[KIỂM TRA 3] Khảo sát Anti-Windup khi motor bị kẹt đứng yên liên tục 10 giây\n");
    PID_Init(&pid_test, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);
    for (int step = 1; step <= 200; step++)
    {
        PID_Compute(&pid_test, 13.0f, 0.0f, 0.05f);
    }
    printf("  Sau 10s kẹt cứng: Integral = %.2f (Ngưỡng max_integral = %.2f), Output = %.2f\n",
           pid_test.integral, pid_test.max_integral, PID_Compute(&pid_test, 13.0f, 0.0f, 0.05f));
    if (pid_test.integral <= pid_test.max_integral)
    {
        printf("-> KẾT QUẢ: PASS (Anti-Windup kẹp cứng giá trị tích phân trong ngưỡng an toàn out_max / Ki = %.1f)\n", 255.0f / 1.5f);
    }
    else
    {
        printf("-> KẾT QUẢ: FAIL (Bị tràn tích phân Windup)\n");
    }

    return 0;
}
