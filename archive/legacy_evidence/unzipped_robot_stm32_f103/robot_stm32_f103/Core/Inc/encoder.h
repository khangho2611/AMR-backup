#ifndef INC_ENCODER_H_
#define INC_ENCODER_H_

#include "main.h"

/*
 * ==============================================================================
 * CẤU HÌNH THÔNG SỐ ENCODER GA25-370
 * ==============================================================================
 * Chu kỳ lấy mẫu tốc độ: 100ms (0.1s)
 */
#define ENCODER_SAMPLE_MS           50
#define ENCODER_SAMPLE_DT_SEC       (ENCODER_SAMPLE_MS / 1000.0f)   /* 0.05f */

/*
 * Cấu hình hướng quay dương quy ước của từng Encoder:
 * Đặt 1 hoặc -1 để khi robot tiến tới, cả 2 encoder đều cho ra DELTA và RPM DƯƠNG.
 */
#define LEFT_ENCODER_DIRECTION      ( 1)
#define RIGHT_ENCODER_DIRECTION     ( 1)

/*
 * THÔNG SỐ XUNG / VÒNG ĐẦU RA (LÝ THUYẾT):
 * - Đĩa từ Hall: 11 xung/vòng motor (PPR = 11)
 * - Tỉ số truyền hộp số: 21.3:1
 * - Chế độ Timer Encoder TI1 and TI2: nhân 4 (x4 Quadrature)
 * -> COUNTS_PER_OUTPUT_REV = 11 * 21.3 * 4 = 937.2f
 *
 * LƯU Ý QUAN TRỌNG:
 * Giá trị này PHẢI ĐƯỢC HIỆU CHUẨN THỰC TẾ:
 *   1. Dán băng dính làm dấu trên bánh xe.
 *   2. Dùng tay quay đúng 10 vòng bánh xe (360 độ x 10).
 *   3. Lấy (tổng xung đếm được) / 10 -> điền vào giá trị này.
 */
#define COUNTS_PER_OUTPUT_REV       937.2f

typedef struct
{
    TIM_HandleTypeDef *htim;
    uint16_t previous_count;
    int16_t delta;
    int32_t total_count;
    float rpm;
    int8_t direction_factor;    /* +1 hoặc -1 */
} Encoder_t;

/* Khởi tạo encoder */
void Encoder_Init(Encoder_t *enc, TIM_HandleTypeDef *htim, int8_t direction_factor);

/* Khởi động phần cứng Timer Encoder */
void Encoder_Start(Encoder_t *enc);

/* Cập nhật số xung delta (xử lý tràn 16-bit) và tính RPM */
int16_t Encoder_Update(Encoder_t *enc);
float Encoder_CalculateRPM(Encoder_t *enc, float dt_seconds, float counts_per_output_rev);

/* Lấy tổng số xung tích lũy */
int32_t Encoder_GetTotalCount(Encoder_t *enc);

/* Reset toàn bộ biến đếm xung */
void Encoder_ResetCount(Encoder_t *enc);

#endif /* INC_ENCODER_H_ */
