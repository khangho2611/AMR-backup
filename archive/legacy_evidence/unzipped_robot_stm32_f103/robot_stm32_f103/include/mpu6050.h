#ifndef MPU6050_H_
#define MPU6050_H_

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Chốt cứng chân GPIO 16 (SDA) và GPIO 17 (SCL) trên Wire1 */
#define PIN_MPU_SDA     16
#define PIN_MPU_SCL     17

#define MPU6050_ADDR_DEFAULT  0x68

typedef struct {
    float ax, ay, az;       /* Gia tốc (g) */
    float gx, gy, gz;       /* Vận tốc góc Gyro (deg/s) */
    float pitch, roll, yaw; /* Góc tư thế (độ) */
    bool is_ready;
} MPU6050_Data_t;

bool MPU6050_Init(int sda_pin, int scl_pin);
void MPU6050_Update(float dt_sec);

float MPU6050_GetYaw(void);
float MPU6050_GetPitch(void);
float MPU6050_GetRoll(void);
float MPU6050_GetGyroZ(void);
void MPU6050_ResetYaw(void);
bool MPU6050_IsReady(void);

const MPU6050_Data_t* MPU6050_GetData(void);

#ifdef __cplusplus
}
#endif

#endif /* MPU6050_H_ */
