#include "main.h"

void HAL_MspInit(void)
{
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_RCC_PWR_CLK_ENABLE();

    /* Vô hiệu hóa JTAG, giữ lại SWD trên PA13/PA14 cho ST-Link */
    __HAL_AFIO_REMAP_SWJ_NOJTAG();
}

void HAL_TIM_Encoder_MspInit(TIM_HandleTypeDef* htim_encoder)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    if (htim_encoder->Instance == TIM2)
    {
        __HAL_RCC_TIM2_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();

        /** TIM2 GPIO Configuration:
         * PA0 ------> TIM2_CH1 (Encoder Left A)
         * PA1 ------> TIM2_CH2 (Encoder Left B)
         */
        GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1;
        GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
        GPIO_InitStruct.Pull = GPIO_PULLUP;
        HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
    }
    else if (htim_encoder->Instance == TIM3)
    {
        __HAL_RCC_TIM3_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();

        /** TIM3 GPIO Configuration:
         * PA6 ------> TIM3_CH1 (Encoder Right A)
         * PA7 ------> TIM3_CH2 (Encoder Right B)
         */
        GPIO_InitStruct.Pin = GPIO_PIN_6 | GPIO_PIN_7;
        GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
        GPIO_InitStruct.Pull = GPIO_PULLUP;
        HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
    }
}

void HAL_I2C_MspInit(I2C_HandleTypeDef* hi2c)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    if (hi2c->Instance == I2C1)
    {
        /* 1. Bật clock GPIOB */
        __HAL_RCC_GPIOB_CLK_ENABLE();

        /* 2. MANUAL BUS RECOVERY (Khắc phục lỗi I2C_FLAG_BUSY bị kẹt trên STM32F1):
         * Cấu hình PB6/PB7 thành GPIO Output Open-Drain, phát 9 xung clock
         * trên chân SCL để giải phóng đường truyền nếu module slave bị treo */
        GPIO_InitStruct.Pin = GPIO_PIN_6 | GPIO_PIN_7;
        GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_OD;
        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
        HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6 | GPIO_PIN_7, GPIO_PIN_SET);

        for (int i = 0; i < 9; i++)
        {
            HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, GPIO_PIN_RESET);
            for (volatile int d = 0; d < 50; d++) {}
            HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, GPIO_PIN_SET);
            for (volatile int d = 0; d < 50; d++) {}
        }

        /* Phát điều kiện STOP bằng tay để giải phóng bus hoàn toàn */
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_7, GPIO_PIN_RESET);
        for (volatile int d = 0; d < 50; d++) {}
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, GPIO_PIN_SET);
        for (volatile int d = 0; d < 50; d++) {}
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_7, GPIO_PIN_SET);
        for (volatile int d = 0; d < 50; d++) {}

        /* 3. Chuyển chân PB6/PB7 sang chế độ Alternate Function Open-Drain cho I2C */
        GPIO_InitStruct.Pin = GPIO_PIN_6 | GPIO_PIN_7;
        GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;
        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
        HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

        /* 4. Bật clock và reset ngoại vi I2C1 SAU KHI chân GPIO đã ở mức cao ổn định */
        __HAL_RCC_I2C1_CLK_ENABLE();
        __HAL_RCC_I2C1_FORCE_RESET();
        for (volatile int d = 0; d < 100; d++) {}
        __HAL_RCC_I2C1_RELEASE_RESET();
    }
}

void HAL_UART_MspInit(UART_HandleTypeDef* huart)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    if (huart->Instance == USART2)
    {
        __HAL_RCC_USART2_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();

        /** USART2 GPIO Configuration:
         * PA2 ------> USART2_TX
         * PA3 ------> USART2_RX
         */
        GPIO_InitStruct.Pin = GPIO_PIN_2;
        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
        HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

        GPIO_InitStruct.Pin = GPIO_PIN_3;
        GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
        GPIO_InitStruct.Pull = GPIO_NOPULL;
        HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
    }
}
