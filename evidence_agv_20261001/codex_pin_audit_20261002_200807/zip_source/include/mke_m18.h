#ifndef MKE_M18_H_
#define MKE_M18_H_

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MKE_M18_DEFAULT_ADDRESS  0x40
#define MKE_M18_FRAME_HEADER     0x05

/* Mode ID theo tài liệu MakerEdu */
#define MKE_M18_MODE_SET_FREQ    104
#define MKE_M18_MODE_MA_CW       106
#define MKE_M18_MODE_MA_CCW      107
#define MKE_M18_MODE_MB_CW       108
#define MKE_M18_MODE_MB_CCW      109
#define MKE_M18_MODE_MA_STOP     110
#define MKE_M18_MODE_MB_STOP     111
#define MKE_M18_MODE_GET_VIN     112

#define MKE_M18_MAX_SPEED        255
#define MKE_M18_MIN_SPEED       -255

void MKE_M18_SetAddress(uint8_t address_7bit);
uint8_t MKE_M18_GetAddress(void);

bool MKE_M18_Init(int sda_pin, int scl_pin, uint32_t frequency);
bool MKE_M18_SetMotorA(int16_t speed);
bool MKE_M18_SetMotorB(int16_t speed);
bool MKE_M18_StopMotorA(void);
bool MKE_M18_StopMotorB(void);
bool MKE_M18_StopAll(void);
bool MKE_M18_ReadVIN(uint32_t *vin_mv);

uint8_t MKE_M18_Scan(void);
uint8_t MKE_M18_GetFaultFlag(void);
void MKE_M18_ClearFaultFlag(void);

#ifdef __cplusplus
}
#endif

#endif /* MKE_M18_H_ */
