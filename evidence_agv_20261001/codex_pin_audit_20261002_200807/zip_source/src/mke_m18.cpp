#include "mke_m18.h"
#include <Arduino.h>
#include <Wire.h>

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

static bool MKE_M18_WriteCommand(uint8_t mode, uint32_t payload)
{
    uint8_t packet[6];
    packet[0] = MKE_M18_FRAME_HEADER;
    packet[1] = mode;
    packet[2] = (uint8_t)((payload >> 24) & 0xFF);
    packet[3] = (uint8_t)((payload >> 16) & 0xFF);
    packet[4] = (uint8_t)((payload >> 8) & 0xFF);
    packet[5] = (uint8_t)(payload & 0xFF);

    /* Thử truyền tối đa 3 lần nếu slave MKE-M18 đang bận */
    for (int retry = 0; retry < 3; retry++)
    {
        Wire.beginTransmission(s_address_7bit);
        Wire.write(packet, sizeof(packet));
        uint8_t err = Wire.endTransmission();

        if (err == 0)
        {
            s_i2c_fault_flag = 0;
            return true;
        }
        delayMicroseconds(300);
    }

    s_i2c_fault_flag = 1;
    return false;
}

bool MKE_M18_Init(int sda_pin, int scl_pin, uint32_t frequency)
{
    Wire.begin(sda_pin, scl_pin, frequency);
    s_i2c_fault_flag = 0;
    return MKE_M18_StopAll();
}

bool MKE_M18_SetMotorA(int16_t speed)
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

bool MKE_M18_SetMotorB(int16_t speed)
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

bool MKE_M18_StopMotorA(void)
{
    return MKE_M18_WriteCommand(MKE_M18_MODE_MA_STOP, 0);
}

bool MKE_M18_StopMotorB(void)
{
    return MKE_M18_WriteCommand(MKE_M18_MODE_MB_STOP, 0);
}

bool MKE_M18_StopAll(void)
{
    bool s1 = MKE_M18_StopMotorA();
    delayMicroseconds(500);
    bool s2 = MKE_M18_StopMotorB();
    return (s1 && s2);
}

bool MKE_M18_ReadVIN(uint32_t *vin_mv)
{
    if (vin_mv == nullptr) return false;

    if (!MKE_M18_WriteCommand(MKE_M18_MODE_GET_VIN, 0)) return false;

    delayMicroseconds(400);

    uint8_t count = Wire.requestFrom((uint8_t)s_address_7bit, (size_t)4);
    if (count == 4)
    {
        uint32_t b0 = Wire.read();
        uint32_t b1 = Wire.read();
        uint32_t b2 = Wire.read();
        uint32_t b3 = Wire.read();
        *vin_mv = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
        return true;
    }
    return false;
}

uint8_t MKE_M18_Scan(void)
{
    for (uint8_t addr = 1; addr < 128; addr++)
    {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0)
        {
            s_address_7bit = addr;
            return addr;
        }
    }
    return 0;
}

uint8_t MKE_M18_GetFaultFlag(void)
{
    return s_i2c_fault_flag;
}

void MKE_M18_ClearFaultFlag(void)
{
    s_i2c_fault_flag = 0;
}
