#include "mpu6050.h"
#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#define REG_SMPLRT_DIV      0x19
#define REG_CONFIG          0x1A
#define REG_GYRO_CONFIG     0x1B
#define REG_ACCEL_CONFIG    0x1C
#define REG_ACCEL_XOUT_H    0x3B
#define REG_PWR_MGMT_1      0x6B
#define REG_WHO_AM_I        0x75

#define ACCEL_SCALE_4G      8192.0f     /* LSB / g */
#define GYRO_SCALE_500      65.5f       /* LSB / (deg/s) */

static uint8_t s_mpu_addr = MPU6050_ADDR_DEFAULT;
static MPU6050_Data_t s_mpu_data = {};

static float s_offset_gx = 0.0f;
static float s_offset_gy = 0.0f;
static float s_offset_gz = 0.0f;

static bool writeReg(uint8_t reg, uint8_t data)
{
    Wire1.beginTransmission(s_mpu_addr);
    Wire1.write(reg);
    Wire1.write(data);
    return (Wire1.endTransmission() == 0);
}

static bool readBytes(uint8_t reg, uint8_t *buf, uint8_t len)
{
    Wire1.beginTransmission(s_mpu_addr);
    Wire1.write(reg);
    if (Wire1.endTransmission(false) != 0) return false;

    uint8_t count = Wire1.requestFrom((uint8_t)s_mpu_addr, len);
    if (count != len) return false;

    for (uint8_t i = 0; i < len; i++) {
        buf[i] = Wire1.read();
    }
    return true;
}

bool MPU6050_Init(int sda_pin, int scl_pin)
{
    s_mpu_data.is_ready = false;

    /* Khởi tạo Bus I2C thứ 2 riêng biệt trên GPIO 16 (SDA) và GPIO 17 (SCL) */
    Wire1.begin(sda_pin, scl_pin, 400000); // 400kHz Fast I2C
    delay(50);

    /* Thử tìm địa chỉ 0x68 trước, nếu không thấy thử 0x69 */
    Wire1.beginTransmission(0x68);
    if (Wire1.endTransmission() == 0) {
        s_mpu_addr = 0x68;
    } else {
        Wire1.beginTransmission(0x69);
        if (Wire1.endTransmission() == 0) {
            s_mpu_addr = 0x69;
        } else {
            Serial.println("{\"warn\":\"MPU6050 not found on Wire1 (GPIO 16, 17)\"}");
            return false;
        }
    }

    /* Đánh thức MPU6050 (thoát Sleep mode, chọn Clock PLL Gyro X) */
    if (!writeReg(REG_PWR_MGMT_1, 0x01)) return false;
    delay(10);

    /* Bộ lọc số chống rung động cơ DLPF = 42Hz */
    writeReg(REG_CONFIG, 0x03);

    /* Cấu hình Gyro ±500 deg/s */
    writeReg(REG_GYRO_CONFIG, 0x08);

    /* Cấu hình Gia tốc ±4g */
    writeReg(REG_ACCEL_CONFIG, 0x08);

    /* Lấy mẫu nhanh 100 lần khi khởi động để triệt tiêu trôi dạt góc (Gyro Zero-Drift Calibration) */
    float sum_gx = 0.0f, sum_gy = 0.0f, sum_gz = 0.0f;
    uint8_t raw[14];
    int valid_samples = 0;

    for (int i = 0; i < 100; i++) {
        if (readBytes(REG_ACCEL_XOUT_H, raw, 14)) {
            int16_t rgx = (int16_t)((raw[8]  << 8) | raw[9]);
            int16_t rgy = (int16_t)((raw[10] << 8) | raw[11]);
            int16_t rgz = (int16_t)((raw[12] << 8) | raw[13]);

            sum_gx += rgx;
            sum_gy += rgy;
            sum_gz += rgz;
            valid_samples++;
        }
        delay(4);
    }

    if (valid_samples > 50) {
        s_offset_gx = sum_gx / valid_samples;
        s_offset_gy = sum_gy / valid_samples;
        s_offset_gz = sum_gz / valid_samples;
    }

    s_mpu_data.yaw = 0.0f;
    s_mpu_data.pitch = 0.0f;
    s_mpu_data.roll = 0.0f;
    s_mpu_data.is_ready = true;

    Serial.printf("{\"info\":\"MPU6050 Ready on Wire1(SDA:%d, SCL:%d) Addr:0x%02X\"}\r\n", sda_pin, scl_pin, s_mpu_addr);
    return true;
}

void MPU6050_Update(float dt_sec)
{
    if (!s_mpu_data.is_ready || dt_sec <= 0.0001f) return;

    uint8_t raw[14];
    if (!readBytes(REG_ACCEL_XOUT_H, raw, 14)) return;

    int16_t raw_ax = (int16_t)((raw[0] << 8) | raw[1]);
    int16_t raw_ay = (int16_t)((raw[2] << 8) | raw[3]);
    int16_t raw_az = (int16_t)((raw[4] << 8) | raw[5]);

    int16_t raw_gx = (int16_t)((raw[8]  << 8) | raw[9]);
    int16_t raw_gy = (int16_t)((raw[10] << 8) | raw[11]);
    int16_t raw_gz = (int16_t)((raw[12] << 8) | raw[13]);

    s_mpu_data.ax = (float)raw_ax / ACCEL_SCALE_4G;
    s_mpu_data.ay = (float)raw_ay / ACCEL_SCALE_4G;
    s_mpu_data.az = (float)raw_az / ACCEL_SCALE_4G;

    s_mpu_data.gx = ((float)raw_gx - s_offset_gx) / GYRO_SCALE_500;
    s_mpu_data.gy = ((float)raw_gy - s_offset_gy) / GYRO_SCALE_500;
    s_mpu_data.gz = ((float)raw_gz - s_offset_gz) / GYRO_SCALE_500;

    /* Vùng chết triệt tiêu trôi dạt góc tĩnh khi xe đứng yên */
    if (fabsf(s_mpu_data.gz) < 0.25f) s_mpu_data.gz = 0.0f;

    /* Tích lũy góc xoay hướng xe Yaw (độ) */
    s_mpu_data.yaw += s_mpu_data.gz * dt_sec;

    /* Bộ lọc bù (Complementary Filter) tính góc nghiêng Pitch & Roll */
    float pitch_acc = atan2f(-s_mpu_data.ax, sqrtf(s_mpu_data.ay * s_mpu_data.ay + s_mpu_data.az * s_mpu_data.az)) * 57.2957795f;
    float roll_acc  = atan2f(s_mpu_data.ay, s_mpu_data.az) * 57.2957795f;

    s_mpu_data.pitch = 0.96f * (s_mpu_data.pitch + s_mpu_data.gy * dt_sec) + 0.04f * pitch_acc;
    s_mpu_data.roll  = 0.96f * (s_mpu_data.roll  + s_mpu_data.gx * dt_sec) + 0.04f * roll_acc;
}

float MPU6050_GetYaw(void)    { return s_mpu_data.yaw; }
float MPU6050_GetPitch(void)  { return s_mpu_data.pitch; }
float MPU6050_GetRoll(void)   { return s_mpu_data.roll; }
float MPU6050_GetGyroZ(void)  { return s_mpu_data.gz; }

void MPU6050_ResetYaw(void)   { s_mpu_data.yaw = 0.0f; }
bool MPU6050_IsReady(void)    { return s_mpu_data.is_ready; }

const MPU6050_Data_t* MPU6050_GetData(void)
{
    return &s_mpu_data;
}
