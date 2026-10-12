#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
#include <stdbool.h>

#include "pid.h"
#include "pid.c"

int main()
{
    printf("=== KIỂM THỬ KHẢO SÁT PID THỰC TẾ (LINK TRỰC TIẾP pid.c + pid.h THẬT) ===\n");

    /* 1. Kiểm tra trường hợp Setpoint = 0.0 (Dừng / Phanh an toàn) */
    PID_t pid_test;
    PID_Init(&pid_test, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);

    /* Giả lập bộ tích phân đang tích lũy lớn trước khi nhận lệnh dừng */
    pid_test.integral = 150.0f;
    float out_zero = PID_Compute(&pid_test, 0.0f, 10.0f, 0.05f);
    printf("[KIỂM TRA 1] Setpoint = 0.0 -> Output = %.4f, Integral sau lệnh = %.4f\n", out_zero, pid_test.integral);
    if (out_zero == 0.0f && pid_test.integral == 0.0f)
    {
        printf("-> KẾT QUẢ: PASS (Khi Setpoint = 0.0, bộ tích phân bị xóa triệt để và Output về 0, không kick giật)\n");
    }
    else
    {
        printf("-> KẾT QUẢ: FAIL\n");
    }

    /* 2. Khảo sát chuỗi đáp ứng toán học thực tế với Setpoint = 13.0 RPM (Bài test 13:57) */
    printf("\n[KIỂM TRA 2] Đáp ứng của PID thật với chuỗi phản hồi thực tế (Setpoint = 13.0 RPM, dt = 0.05s)\n");
    PID_Init(&pid_test, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);

    float measured_rpm = 0.0f;
    for (int step = 1; step <= 20; step++)
    {
        /* Mô phỏng theo telemetry raw log: Mẫu 7 bên phải nhích 2.56 RPM, mẫu 19-20 bên trái nhích 5.12 RPM */
        if (step == 7) measured_rpm = 2.56f;
        else if (step >= 19) measured_rpm = 5.12f;
        else measured_rpm = 0.0f;

        float out_pwm = PID_Compute(&pid_test, 13.0f, measured_rpm, 0.05f);
        if (step == 1 || step == 5 || step == 7 || step == 10 || step == 15 || step == 19 || step == 20)
        {
            printf("  Chu kỳ %2d (t=%.2fs): Measured=%5.2f RPM -> PWM ra = %5.1f (Tích phân=%5.2f)\n",
                   step, step * 0.05f, measured_rpm, out_pwm, pid_test.integral);
        }
    }

    /* 3. Kiểm tra cơ chế Anti-Windup và Saturation khi bánh xe bị kẹt cứng (Stall) */
    printf("\n[KIỂM TRA 3] Khảo sát Anti-Windup khi motor bị stall đứng yên liên tục 10 giây (200 chu kỳ)\n");
    PID_Init(&pid_test, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);
    for (int step = 1; step <= 200; step++)
    {
        PID_Compute(&pid_test, 13.0f, 0.0f, 0.05f);
    }
    float out_stall = PID_Compute(&pid_test, 13.0f, 0.0f, 0.05f);
    float expected_max_integral = 255.0f / 1.5f; /* 170.0f */
    printf("  Sau 10s stall: Integral = %.2f (Ngưỡng chặn max_integral = %.2f), Output PWM = %.2f\n",
           pid_test.integral, expected_max_integral, out_stall);
    if (pid_test.integral <= expected_max_integral + 0.001f && out_stall <= 255.0f)
    {
        printf("-> KẾT QUẢ: PASS (Anti-Windup kẹp cứng giá trị tích phân không vượt ngưỡng bão hòa out_max / Ki)\n");
    }
    else
    {
        printf("-> KẾT QUẢ: FAIL\n");
    }

    return 0;
}
