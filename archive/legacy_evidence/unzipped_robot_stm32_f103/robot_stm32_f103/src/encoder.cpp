#include "encoder.h"
#include <Arduino.h>
#include <driver/gpio.h>

void Encoder_Init(Encoder_t *enc, pcnt_unit_t unit, int pin_a, int pin_b, int8_t direction_factor)
{
    if (enc == nullptr) return;

    enc->unit = unit;
    enc->pin_a = pin_a;
    enc->pin_b = pin_b;
    enc->direction_factor = (direction_factor >= 0) ? 1 : -1;
    enc->accum_count = 0;
    enc->prev_total_raw = 0;
    enc->delta = 0;
    enc->total_count = 0;
    enc->rpm = 0.0f;
}

void Encoder_Start(Encoder_t *enc)
{
    if (enc == nullptr) return;

    /* Cấu hình Kênh 0: Đếm cả 2 sườn xung A dựa theo mức logic B */
    pcnt_config_t ch0_cfg = {};
    ch0_cfg.pulse_gpio_num = enc->pin_a;
    ch0_cfg.ctrl_gpio_num  = enc->pin_b;
    ch0_cfg.unit           = enc->unit;
    ch0_cfg.channel        = PCNT_CHANNEL_0;
    ch0_cfg.pos_mode       = PCNT_COUNT_DEC;
    ch0_cfg.neg_mode       = PCNT_COUNT_INC;
    ch0_cfg.lctrl_mode     = PCNT_MODE_REVERSE;
    ch0_cfg.hctrl_mode     = PCNT_MODE_KEEP;
    ch0_cfg.counter_h_lim  = 32767;
    ch0_cfg.counter_l_lim  = -32768;
    pcnt_unit_config(&ch0_cfg);

    /* Cấu hình Kênh 1: Đếm cả 2 sườn xung B dựa theo mức logic A (Đủ x4 Quadrature) */
    pcnt_config_t ch1_cfg = {};
    ch1_cfg.pulse_gpio_num = enc->pin_b;
    ch1_cfg.ctrl_gpio_num  = enc->pin_a;
    ch1_cfg.unit           = enc->unit;
    ch1_cfg.channel        = PCNT_CHANNEL_1;
    ch1_cfg.pos_mode       = PCNT_COUNT_INC;
    ch1_cfg.neg_mode       = PCNT_COUNT_DEC;
    ch1_cfg.lctrl_mode     = PCNT_MODE_REVERSE;
    ch1_cfg.hctrl_mode     = PCNT_MODE_KEEP;
    ch1_cfg.counter_h_lim  = 32767;
    ch1_cfg.counter_l_lim  = -32768;
    pcnt_unit_config(&ch1_cfg);

    /* Bật điện trở kéo lên nội bộ 3.3V cho cả 2 kênh A và B */
    pinMode(enc->pin_a, INPUT_PULLUP);
    pinMode(enc->pin_b, INPUT_PULLUP);
    gpio_set_pull_mode((gpio_num_t)enc->pin_a, GPIO_PULLUP_ONLY);
    gpio_set_pull_mode((gpio_num_t)enc->pin_b, GPIO_PULLUP_ONLY);

    /* Bộ lọc phần cứng chống nhiễu gai xung từ chổi than động cơ (100 APB clocks ~ 1.25us) */
    pcnt_set_filter_value(enc->unit, 100);
    pcnt_filter_enable(enc->unit);

    /* Tắt toàn bộ ngắt sự kiện để tránh nghẽn CPU / tràn số giả */
    pcnt_event_disable(enc->unit, PCNT_EVT_H_LIM);
    pcnt_event_disable(enc->unit, PCNT_EVT_L_LIM);

    pcnt_counter_pause(enc->unit);
    pcnt_counter_clear(enc->unit);
    pcnt_counter_resume(enc->unit);
}

int32_t Encoder_Update(Encoder_t *enc)
{
    if (enc == nullptr) return 0;

    int16_t hw_cnt = 0;
    pcnt_get_counter_value(enc->unit, &hw_cnt);
    pcnt_counter_clear(enc->unit);

    enc->delta = (int32_t)(hw_cnt * enc->direction_factor);
    enc->total_count += enc->delta;

    return enc->delta;
}

float Encoder_CalculateRPM(Encoder_t *enc, float dt_seconds, float counts_per_output_rev)
{
    if (enc == nullptr || dt_seconds <= 0.0001f || counts_per_output_rev <= 0.0f)
    {
        if (enc != nullptr) enc->rpm = 0.0f;
        return 0.0f;
    }

    enc->rpm = ((float)enc->delta / counts_per_output_rev) * (60.0f / dt_seconds);
    return enc->rpm;
}

int32_t Encoder_GetTotalCount(Encoder_t *enc)
{
    if (enc == nullptr) return 0;
    return enc->total_count;
}

void Encoder_ResetCount(Encoder_t *enc)
{
    if (enc == nullptr) return;

    pcnt_counter_pause(enc->unit);
    pcnt_counter_clear(enc->unit);
    enc->accum_count = 0;
    enc->prev_total_raw = 0;
    enc->delta = 0;
    enc->total_count = 0;
    enc->rpm = 0.0f;
    pcnt_counter_resume(enc->unit);
}
