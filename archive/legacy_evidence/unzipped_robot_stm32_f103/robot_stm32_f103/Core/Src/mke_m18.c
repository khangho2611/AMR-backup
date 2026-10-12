#include "mke_m18.h"

static I2C_HandleTypeDef *s_hi2c = NULL;
static uint8_t s_address_7bit = MKE_M18_DEFAULT_ADDRESS;
static volatile uint8_t s_i2c_fault_flag = 0;

void MKE_M18_SetAddress(uint8_t address_7bit)
{
    s_address_7bit = address_7bit;
}

uint8_t MKE_M18_GetAddress(void)
{
    return s_address_7bit;
}

/*
 * Giao thức chuẩn MKE-M18 BD62130 (makereduvn):
 * Gói Write 6 bytes:
 *   Byte 0: 0x05 (Region / Header)
 *   Byte 1: ModeID (106, 107, 108, 109, 110, 111, 112...)
 *   Byte 2: Payload MSB (Byte 3)
 *   Byte 3: Payload Byte 2
 *   Byte 4: Payload Byte 1
 *   Byte 5: Payload LSB (Byte 0) - Big Endian
 */
static HAL_StatusTypeDef MKE_M18_WriteCommand(uint8_t mode, uint32_t payload)
{
    if (s_hi2c == NULL) return HAL_ERROR;

    uint8_t packet[6];
    packet[0] = MKE_M18_FRAME_HEADER;
    packet[1] = mode;
    packet[2] = (uint8_t)((payload >> 24) & 0xFF);
    packet[3] = (uint8_t)((payload >> 16) & 0xFF);
    packet[4] = (uint8_t)((payload >> 8) & 0xFF);
    packet[5] = (uint8_t)(payload & 0xFF);

    uint16_t hal_addr = (uint16_t)(s_address_7bit << 1);
    HAL_StatusTypeDef status = HAL_I2C_Master_Transmit(s_hi2c, hal_addr, packet, sizeof(packet), MKE_M18_I2C_TIMEOUT);

    if (status == HAL_OK)
    {
        s_i2c_fault_flag = 0;
    }
    else
    {
        s_i2c_fault_flag = 1;
    }

    return status;
}

HAL_StatusTypeDef MKE_M18_Init(I2C_HandleTypeDef *hi2c)
{
    s_hi2c = hi2c;
    s_i2c_fault_flag = 0;

    return MKE_M18_StopAll();
}

HAL_StatusTypeDef MKE_M18_SetMotorA(int16_t speed)
{
    if (speed > MKE_M18_MAX_SPEED) speed = MKE_M18_MAX_SPEED;
    if (speed < MKE_M18_MIN_SPEED) speed = MKE_M18_MIN_SPEED;

    if (speed == 0)
    {
        return MKE_M18_WriteCommand(MKE_M18_MODE_MA_STOP, 0);
    }
    else if (speed > 0)
    {
        return MKE_M18_WriteCommand(MKE_M18_MODE_MA_CW, (uint32_t)speed);
    }
    else
    {
        return MKE_M18_WriteCommand(MKE_M18_MODE_MA_CCW, (uint32_t)(-speed));
    }
}

HAL_StatusTypeDef MKE_M18_SetMotorB(int16_t speed)
{
    if (speed > MKE_M18_MAX_SPEED) speed = MKE_M18_MAX_SPEED;
    if (speed < MKE_M18_MIN_SPEED) speed = MKE_M18_MIN_SPEED;

    if (speed == 0)
    {
        return MKE_M18_WriteCommand(MKE_M18_MODE_MB_STOP, 0);
    }
    else if (speed > 0)
    {
        return MKE_M18_WriteCommand(MKE_M18_MODE_MB_CW, (uint32_t)speed);
    }
    else
    {
        return MKE_M18_WriteCommand(MKE_M18_MODE_MB_CCW, (uint32_t)(-speed));
    }
}

HAL_StatusTypeDef MKE_M18_StopMotorA(void)
{
    return MKE_M18_WriteCommand(MKE_M18_MODE_MA_STOP, 0);
}

HAL_StatusTypeDef MKE_M18_StopMotorB(void)
{
    return MKE_M18_WriteCommand(MKE_M18_MODE_MB_STOP, 0);
}

HAL_StatusTypeDef MKE_M18_StopAll(void)
{
    HAL_StatusTypeDef s1 = MKE_M18_StopMotorA();
    HAL_StatusTypeDef s2 = MKE_M18_StopMotorB();
    return (s1 == HAL_OK && s2 == HAL_OK) ? HAL_OK : HAL_ERROR;
}

HAL_StatusTypeDef MKE_M18_ReadVIN(uint32_t *vin_mv)
{
    if (s_hi2c == NULL || vin_mv == NULL) return HAL_ERROR;

    /* Gửi gói Write 6 byte với ModeID 112 (payload = 0) */
    HAL_StatusTypeDef status = MKE_M18_WriteCommand(MKE_M18_MODE_GET_VIN, 0);
    if (status != HAL_OK) return status;

    /* Đợi tối thiểu 200us theo tài liệu MKE-M18 */
    for (volatile int i = 0; i < 500; i++) {}

    /* Đọc 4 bytes Big-Endian từ slave */
    uint8_t rx_buf[4] = {0};
    uint16_t hal_addr = (uint16_t)(s_address_7bit << 1);
    status = HAL_I2C_Master_Receive(s_hi2c, hal_addr, rx_buf, 4, MKE_M18_I2C_TIMEOUT);
    if (status == HAL_OK)
    {
        *vin_mv = ((uint32_t)rx_buf[0] << 24) |
                  ((uint32_t)rx_buf[1] << 16) |
                  ((uint32_t)rx_buf[2] << 8)  |
                  ((uint32_t)rx_buf[3]);
    }
    return status;
}

uint8_t MKE_M18_GetFaultFlag(void)
{
    return s_i2c_fault_flag;
}

void MKE_M18_ClearFaultFlag(void)
{
    s_i2c_fault_flag = 0;
}
