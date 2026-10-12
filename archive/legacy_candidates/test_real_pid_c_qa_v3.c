#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#include "pid.h"
#include "pid.c"

int main()
{
    printf("=== KIỂM THỬ KHẢO SÁT PID THỰC TẾ V3 (ASSERT OUTPUT SATURATION & SEPARATE CALLS) ===\n");

    /* -------------------------------------------------------------
     * TEST 1: Kiểm tra Setpoint = 0.0 lập tức RESET integral và Output = 0
     * ------------------------------------------------------------- */
    printf("\n[KIỂM TRA 1] Setpoint = 0.0 sau khi tích lũy integral lớn -> bắt buộc output=0 và integral=0\n");
    PID_t pid1;
    PID_Init(&pid1, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);
    pid1.integral = 150.0f;
    float out_zero = PID_Compute(&pid1, 0.0f, 10.0f, 0.05f);

    printf("  Output = %.4f, Integral sau lệnh = %.4f\n", out_zero, pid1.integral);
    if (out_zero != 0.0f || pid1.integral != 0.0f)
    {
        fprintf(stderr, "ASSERTION FAILED: Setpoint=0.0 không reset integral/output về 0!\n");
        return EXIT_FAILURE;
    }
    printf("  -> TEST 1 PASS: Reset sạch sẽ không kick giật.\n");

    /* -------------------------------------------------------------
     * TEST 2: Tách biệt độc lập PID Trái & PID Phải theo Telemetry thật 10Hz
     * ------------------------------------------------------------- */
    printf("\n[KIỂM TRA 2] Mô phỏng 2 kênh PID độc lập Trái & Phải theo đúng mẫu thô 10Hz (dt = 0.10s, 20 mẫu)\n");
    PID_t pid_left, pid_right;
    PID_Init(&pid_left, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);
    PID_Init(&pid_right, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);

    float target_rpm = 13.04f;
    float dt_sample = 0.10f; /* 10Hz giữa các mẫu telemetry */

    for (int step = 1; step <= 20; step++)
    {
        float meas_right = (step == 9) ? 2.56f : 0.0f;
        float meas_left  = (step == 20) ? 5.12f : 0.0f;

        float out_l = PID_Compute(&pid_left, target_rpm, meas_left, dt_sample);
        float out_r = PID_Compute(&pid_right, target_rpm, meas_right, dt_sample);

        if (step == 1 || step == 9 || step == 10 || step == 19 || step == 20)
        {
            printf("  Mẫu %2d (t=%.2fs): [Trái] Meas=%4.2f RPM, PWM=%5.1f, Int=%5.2f | [Phải] Meas=%4.2f RPM, PWM=%5.1f, Int=%5.2f\n",
                   step, step * dt_sample, meas_left, out_l, pid_left.integral, meas_right, out_r, pid_right.integral);
        }
    }

    if (pid_left.integral <= 0.0f || pid_right.integral <= 0.0f)
    {
        fprintf(stderr, "ASSERTION FAILED: Tích phân không tăng theo thời gian chạy!\n");
        return EXIT_FAILURE;
    }
    printf("  -> TEST 2 PASS: Tách biệt độc lập 2 kênh L/R khớp tiến trình tích phân.\n");

    /* -------------------------------------------------------------
     * TEST 3: Stall kéo dài >= 20 giây (400 chu kỳ dt=0.05s) với cả ±13.0 RPM
     * Kiểm tra assert cả:
     *   1) Integral clamp: +170.0f và -170.0f
     *   2) Output PWM saturation: bắt buộc chạm +255.0f và -255.0f (không vượt quá)
     *   3) Tách lệnh PID_Compute ra biến riêng, không gọi lặp trong printf
     * ------------------------------------------------------------- */
    printf("\n[KIỂM TRA 3] Khảo sát Stall kéo dài 20s (400 chu kỳ dt=0.05s) cho cả +13 RPM và -13 RPM\n");
    PID_t pid_stall_pos, pid_stall_neg;
    PID_Init(&pid_stall_pos, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);
    PID_Init(&pid_stall_neg, 0.5f, 1.5f, 0.01f, 0.45f, -255.0f, 255.0f);

    float expected_clamp = 255.0f / 1.5f; /* 170.0f */

    /* Chạy 400 chu kỳ stall */
    for (int i = 0; i < 400; i++)
    {
        PID_Compute(&pid_stall_pos, 13.04f, 0.0f, 0.05f);
        PID_Compute(&pid_stall_neg, -13.04f, 0.0f, 0.05f);
    }

    /* Đọc giá trị sau 400 chu kỳ bằng 1 lần gọi xác định */
    float out_pwm_pos = PID_Compute(&pid_stall_pos, 13.04f, 0.0f, 0.05f);
    float out_pwm_neg = PID_Compute(&pid_stall_neg, -13.04f, 0.0f, 0.05f);

    printf("  Sau 20s Stall dương (+13 RPM): Integral = %6.2f (Clamp = %6.2f), PWM = %6.2f (Bão hòa = +255.00)\n",
           pid_stall_pos.integral, expected_clamp, out_pwm_pos);
    printf("  Sau 20s Stall âm   (-13 RPM): Integral = %6.2f (Clamp = %6.2f), PWM = %6.2f (Bão hòa = -255.00)\n",
           pid_stall_neg.integral, -expected_clamp, out_pwm_neg);

    /* Assert Integral Clamp */
    if (fabsf(pid_stall_pos.integral - expected_clamp) > 0.001f)
    {
        fprintf(stderr, "ASSERTION FAILED: Stall dương không kẹp cứng ở +170.0! (Thực tế: %.4f)\n", pid_stall_pos.integral);
        return EXIT_FAILURE;
    }
    if (fabsf(pid_stall_neg.integral - (-expected_clamp)) > 0.001f)
    {
        fprintf(stderr, "ASSERTION FAILED: Stall âm không kẹp cứng ở -170.0! (Thực tế: %.4f)\n", pid_stall_neg.integral);
        return EXIT_FAILURE;
    }

    /* Assert Output PWM Saturation */
    if (fabsf(out_pwm_pos - 255.0f) > 0.001f)
    {
        fprintf(stderr, "ASSERTION FAILED: Output PWM dương không chạm bão hòa +255.0! (Thực tế: %.4f)\n", out_pwm_pos);
        return EXIT_FAILURE;
    }
    if (fabsf(out_pwm_neg - (-255.0f)) > 0.001f)
    {
        fprintf(stderr, "ASSERTION FAILED: Output PWM âm không chạm bão hòa -255.0! (Thực tế: %.4f)\n", out_pwm_neg);
        return EXIT_FAILURE;
    }

    /* Thử lệnh STOP target 0 ngay sau khi stall chạm đỉnh */
    float out_stop_pos = PID_Compute(&pid_stall_pos, 0.0f, 0.0f, 0.05f);
    float out_stop_neg = PID_Compute(&pid_stall_neg, 0.0f, 0.0f, 0.05f);
    printf("  Ngay sau đó gửi Target=0.0: Pos Out=%.2f (Int=%.2f), Neg Out=%.2f (Int=%.2f)\n",
           out_stop_pos, pid_stall_pos.integral, out_stop_neg, pid_stall_neg.integral);

    if (out_stop_pos != 0.0f || pid_stall_pos.integral != 0.0f ||
        out_stop_neg != 0.0f || pid_stall_neg.integral != 0.0f)
    {
        fprintf(stderr, "ASSERTION FAILED: STOP sau stall không reset integral/output về 0!\n");
        return EXIT_FAILURE;
    }
    printf("  -> TEST 3 PASS: Clamp bão hòa integral, Output saturation +255/-255 và STOP reset đều đạt.\n");

    printf("\n=== TOÀN BỘ 3/3 BÀI KIỂM TRA PID STRICT QA V3 ĐỀU PASS ĐẠT CHUẨN ===\n");
    return EXIT_SUCCESS;
}
