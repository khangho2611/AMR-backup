#ifndef INC_MKE_M18_H_
#define INC_MKE_M18_H_

#include "main.h"

/*
 * MKE-M18 BD62130 I2C Dual Motor Driver Module
 * Repository chính thức: https://github.com/makereduvn/MKE-M18-BD62130-I2C-MOTOR-DRIVER-MODULE
 *
 * Giao thức I2C Chuẩn (Raw Protocol):
 * Gói Write 6 bytes: [0x05 (Region)] [ModeID] [Payload MSB] [Payload Byte 2] [Payload Byte 1] [Payload LSB]
 * Thứ tự byte: Big-Endian
 */
#define MKE_M18_DEFAULT_ADDRESS  0x40

/* Header byte raw protocol */
#define MKE_M18_FRAME_HEADER     0x05

/* Các Mode ID chính thức từ MakerEdu */
#define MKE_M18_MODE_SET_FREQ    104
#define MKE_M18_MODE_MA_CW       106
#define MKE_M18_MODE_MA_CCW      107
#define MKE_M18_MODE_MB_CW       108
#define MKE_M18_MODE_MB_CCW      109
#define MKE_M18_MODE_MA_STOP     110
#define MKE_M18_MODE_MB_STOP     111
#define MKE_M18_MODE_GET_VIN     112

/* Giới hạn tốc độ */
#define MKE_M18_MAX_SPEED        255
#define MKE_M18_MIN_SPEED       -255
#define MKE_M18_I2C_TIMEOUT      30      /* ms */

/* Quản lý địa chỉ động (hỗ trợ I2C Scanner tự động nhận diện) */
void MKE_M18_SetAddress(uint8_t address_7bit);
uint8_t MKE_M18_GetAddress(void);

/* Khởi tạo module driver */
HAL_StatusTypeDef MKE_M18_Init(I2C_HandleTypeDef *hi2c);

/* Điều khiển Motor A và Motor B (-255 .. +255) */
HAL_StatusTypeDef MKE_M18_SetMotorA(int16_t speed);
HAL_StatusTypeDef MKE_M18_SetMotorB(int16_t speed);

/* Dừng từng động cơ hoặc toàn bộ */
HAL_StatusTypeDef MKE_M18_StopMotorA(void);
HAL_StatusTypeDef MKE_M18_StopMotorB(void);
HAL_StatusTypeDef MKE_M18_StopAll(void);

/* Đọc điện áp nguồn cấp động cơ Vin (mV) */
HAL_StatusTypeDef MKE_M18_ReadVIN(uint32_t *vin_mv);

/* Quản lý cờ lỗi I2C */
uint8_t MKE_M18_GetFaultFlag(void);
void MKE_M18_ClearFaultFlag(void);

#endif /* INC_MKE_M18_H_ */

