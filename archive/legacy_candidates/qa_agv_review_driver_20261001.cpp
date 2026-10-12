// QA snapshot SHA256 e4ad100ff15c60aae3d27e166476499cdfdd5a82f8526d2ea5440acb492374b0
#ifndef MKE_M18_H_
#define MKE_M18_H_

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MKE_M18_DEFAULT_ADDRESS  0x42
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

#include <cassert>
#include <vector>
#include <iostream>
struct Packet{int addr;std::vector<uint8_t> data;};
struct WireFake {
 int address=0;bool present=true,fail_a=false,fail_b=false;std::vector<uint8_t> data;std::vector<Packet> packets;
 void begin(int,int,uint32_t){} void setTimeOut(int){}
 void beginTransmission(uint8_t a){address=a;data.clear();}
 void write(uint8_t*p,size_t n){data.assign(p,p+n);}
 int endTransmission(){if(data.empty())return present&&address==0x42?0:2;packets.push_back({address,data});if(!present||address!=0x42)return 2;int m=data[1];return (fail_a&&(m==106||m==107||m==110))||(fail_b&&(m==108||m==109||m==111))?2:0;}
 uint8_t requestFrom(uint8_t,size_t){return 0;}int read(){return 0;}
 void reset(){present=true;fail_a=fail_b=false;packets.clear();}
}Wire;
void delayMicroseconds(uint32_t){}

static uint8_t s_address_7bit = MKE_M18_DEFAULT_ADDRESS;
static volatile uint8_t s_i2c_fault_flag = 0;
static volatile uint8_t s_i2c_fault_latch = 0; /* Latch lỗi cứng, chỉ xóa bằng lệnh tường minh */

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
            /* KHÔNG xóa s_i2c_fault_latch tại đây để tránh lỗi A bị ghi B thành công xóa mất */
            return true;
        }
        delayMicroseconds(300);
    }

    s_i2c_fault_flag = 1;
    s_i2c_fault_latch = 1; /* Latch lỗi cứng */
    return false;
}

bool MKE_M18_Init(int sda_pin, int scl_pin, uint32_t frequency)
{
    Wire.begin(sda_pin, scl_pin, frequency);
    Wire.setTimeOut(50);
    s_i2c_fault_flag = 0;
    s_i2c_fault_latch = 0;

    /* Quét tìm địa chỉ driver thực tế trước khi Stop */
    uint8_t found = MKE_M18_Scan();
    if (found == 0)
    {
        s_i2c_fault_flag = 1;
        s_i2c_fault_latch = 1;
        return false;
    }

    /* Đảm bảo dừng an toàn cả 2 motor sau khi đã có địa chỉ chính xác */
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
    Wire.setTimeOut(50); // Timeout 50ms tránh treo I2C
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
    return s_i2c_fault_latch;
}

void MKE_M18_ClearFaultFlag(void)
{
    s_i2c_fault_flag = 0;
    s_i2c_fault_latch = 0;
}
int main(){
 Wire.reset();assert(MKE_M18_Init(21,22,100000));assert(MKE_M18_GetAddress()==0x42);assert(MKE_M18_GetFaultFlag()==0);assert(Wire.packets.size()==2);assert(Wire.packets[0].data[1]==110&&Wire.packets[1].data[1]==111);for(auto&p:Wire.packets){assert(p.addr==0x42);assert(p.data[0]==0x05);}std::cout<<"PASS init actual0x42 STOP A/B\n";
 Wire.reset();Wire.present=false;assert(!MKE_M18_Init(21,22,100000));assert(MKE_M18_GetFaultFlag()==1);std::cout<<"PASS no device init fails/latches\n";
 Wire.reset();Wire.fail_a=true;assert(!MKE_M18_Init(21,22,100000));assert(MKE_M18_GetFaultFlag()==1);std::cout<<"PASS init STOP A fails/latches\n";
 Wire.reset();Wire.fail_b=true;assert(!MKE_M18_Init(21,22,100000));assert(MKE_M18_GetFaultFlag()==1);std::cout<<"PASS init STOP B fails/latches\n";
 Wire.reset();assert(MKE_M18_Init(21,22,100000));Wire.fail_a=true;assert(!MKE_M18_SetMotorA(20));assert(MKE_M18_SetMotorB(20));assert(MKE_M18_GetFaultFlag()==1);Wire.fail_a=false;assert(MKE_M18_StopAll());assert(MKE_M18_GetFaultFlag()==1);std::cout<<"PASS A failure survives B success and STOP success\n";
 Wire.reset();assert(MKE_M18_Init(21,22,100000));assert(MKE_M18_SetMotorA(20));assert(MKE_M18_SetMotorB(-20));auto a=Wire.packets[2].data;auto b=Wire.packets[3].data;assert(a==std::vector<uint8_t>({5,106,0,0,0,20}));assert(b==std::vector<uint8_t>({5,109,0,0,0,20}));std::cout<<"PASS actual header/mode/payload bytes\n";
}