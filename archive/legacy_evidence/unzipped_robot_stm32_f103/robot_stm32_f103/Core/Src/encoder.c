#include "encoder.h"

void Encoder_Init(Encoder_t *enc, TIM_HandleTypeDef *htim, int8_t direction_factor)
{
    if (enc == NULL || htim == NULL) return;

    enc->htim = htim;
    enc->direction_factor = (direction_factor >= 0) ? 1 : -1;
    enc->previous_count = 0;
    enc->delta = 0;
    enc->total_count = 0;
    enc->rpm = 0.0f;
}

void Encoder_Start(Encoder_t *enc)
{
    if (enc == NULL || enc->htim == NULL) return;

    /* Khởi động cả 2 channel của Timer ở Encoder Interface Mode */
    HAL_TIM_Encoder_Start(enc->htim, TIM_CHANNEL_ALL);

    /* Đồng bộ giá trị đếm hiện tại làm mốc ban đầu */
    enc->previous_count = (uint16_t)__HAL_TIM_GET_COUNTER(enc->htim);
}

int16_t Encoder_Update(Encoder_t *enc)
{
    if (enc == NULL || enc->htim == NULL) return 0;

    uint16_t current_count = (uint16_t)__HAL_TIM_GET_COUNTER(enc->htim);

    /*
     * Kỹ thuật xử lý tràn/thiếu số 16-bit (Wrap-around):
     * Trong số học bù hai (Two's complement):
     * Phép trừ uint16_t rồi ép kiểu sang int16_t tự động cho ra độ dịch đúng (signed delta)
     * kể cả khi counter nhảy qua 0 (ví dụ từ 65530 -> 10 hay từ 5 -> 65531),
     * miễn là tốc độ lấy mẫu đủ nhanh để |delta| < 32767 xung / chu kỳ.
     */
    int16_t raw_delta = (int16_t)(current_count - enc->previous_count);

    /* Áp dụng chiều quay mong muốn */
    enc->delta = (int16_t)(raw_delta * enc->direction_factor);

    /* Cộng dồn vào biến 32-bit chống tràn */
    enc->total_count += enc->delta;

    /* Lưu lại giá trị đếm cho chu kỳ sau */
    enc->previous_count = current_count;

    return enc->delta;
}

float Encoder_CalculateRPM(Encoder_t *enc, float dt_seconds, float counts_per_output_rev)
{
    if (enc == NULL || dt_seconds <= 0.0001f || counts_per_output_rev <= 0.0f)
    {
        if (enc != NULL) enc->rpm = 0.0f;
        return 0.0f;
    }

    /* RPM = (số vòng quay được trong dt) * (60 giây / dt) */
    enc->rpm = ((float)enc->delta / counts_per_output_rev) * (60.0f / dt_seconds);
    return enc->rpm;
}

int32_t Encoder_GetTotalCount(Encoder_t *enc)
{
    if (enc == NULL) return 0;
    return enc->total_count;
}

void Encoder_ResetCount(Encoder_t *enc)
{
    if (enc == NULL || enc->htim == NULL) return;

    __HAL_TIM_SET_COUNTER(enc->htim, 0);
    enc->previous_count = 0;
    enc->delta = 0;
    enc->total_count = 0;
    enc->rpm = 0.0f;
}
