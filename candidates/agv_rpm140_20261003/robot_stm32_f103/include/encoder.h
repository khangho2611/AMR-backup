#ifndef ENCODER_H_
#define ENCODER_H_

#include <stdint.h>
#include <driver/pcnt.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ENCODER_SAMPLE_MS           50
#define ENCODER_SAMPLE_DT_SEC       (ENCODER_SAMPLE_MS / 1000.0f)   /* 0.05f */

/*
 * Cả 2 encoder đều đặt (-1) để khi 2 bánh quay tiến tới,
 * cả 2 xung đều đếm DƯƠNG (+) và bám chuẩn xác Target RPM (không bị rồ ga lên 280)
 */
#define LEFT_ENCODER_DIRECTION      (-1)
#define RIGHT_ENCODER_DIRECTION     (-1)

/* 11 PPR * 4 (x4 Quadrature) * 21.3 (Gear Ratio) = 937.2 xung / vòng bánh xe */
#define COUNTS_PER_OUTPUT_REV       937.2f

typedef struct
{
    pcnt_unit_t unit;
    int pin_a;
    int pin_b;
    volatile int64_t accum_count;
    int64_t prev_total_raw;
    int32_t delta;
    int32_t total_count;
    float rpm;
    int8_t direction_factor;
} Encoder_t;

void Encoder_Init(Encoder_t *enc, pcnt_unit_t unit, int pin_a, int pin_b, int8_t direction_factor);
void Encoder_Start(Encoder_t *enc);
int32_t Encoder_Update(Encoder_t *enc);
float Encoder_CalculateRPM(Encoder_t *enc, float dt_seconds, float counts_per_output_rev);
int32_t Encoder_GetTotalCount(Encoder_t *enc);
void Encoder_ResetCount(Encoder_t *enc);

#ifdef __cplusplus
}
#endif

#endif /* ENCODER_H_ */
