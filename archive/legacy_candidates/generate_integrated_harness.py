import re, hashlib

main_cpp_path = r'D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH\robot_stm32_f103\src\main.cpp'
mke_cpp_path  = r'D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH\robot_stm32_f103\src\mke_m18.cpp'

with open(main_cpp_path, 'r', encoding='utf-8') as f:
    main_code = f.read()

with open(mke_cpp_path, 'r', encoding='utf-8') as f:
    mke_code = f.read()

main_hash = hashlib.sha256(main_code.encode('utf-8')).hexdigest()
mke_hash  = hashlib.sha256(mke_code.encode('utf-8')).hexdigest()

# 1. Trích xuất MKE_M18_WriteCommand, SetMotorA, SetMotorB, StopAll từ mke_m18.cpp
mke_write_cmd = mke_code[mke_code.find("static bool MKE_M18_WriteCommand"):mke_code.find("bool MKE_M18_Init")]
mke_set_a     = mke_code[mke_code.find("bool MKE_M18_SetMotorA"):mke_code.find("bool MKE_M18_SetMotorB")]
mke_set_b     = mke_code[mke_code.find("bool MKE_M18_SetMotorB"):mke_code.find("bool MKE_M18_StopMotorA")]
mke_stop_a    = mke_code[mke_code.find("bool MKE_M18_StopMotorA"):mke_code.find("bool MKE_M18_StopMotorB")]
mke_stop_b    = mke_code[mke_code.find("bool MKE_M18_StopMotorB"):mke_code.find("bool MKE_M18_StopAll")]
mke_stop_all  = mke_code[mke_code.find("bool MKE_M18_StopAll"):mke_code.find("bool MKE_M18_ReadVIN")]

# 2. Trích xuất Safe_Stop_And_Reset, Safe_Motor_Write, Check_Safety_Watchdog, Execute_Robot_Command từ main.cpp
safe_stop  = main_code[main_code.find("static void Safe_Stop_And_Reset(void)"):main_code.find("/* Cổng ghi an toàn motor")]
safe_write = main_code[main_code.find("static void Safe_Motor_Write(int16_t l_pwm"):main_code.find("/* Kiểm tra an toàn watchdog")]
safe_watch = main_code[main_code.find("static void Check_Safety_Watchdog(void)"):main_code.find("void loop(void)")]
exec_cmd   = main_code[main_code.find("void Execute_Robot_Command(const char *cmd)"):main_code.find("static void Process_Serial_Commands(void)")]

harness_code = f"""// AUTO-GENERATED TRUE SOURCE HARNESS INCLUDING MKE_M18_WriteCommand
// SHA256 main.cpp: {main_hash}
// SHA256 mke_m18.cpp: {mke_hash}

#include <iostream>
#include <cstdint>
#include <cassert>
#include <cmath>
#include <cstdarg>
#include <cstring>
#include <string>
#include <vector>

using std::isfinite;
#define MODE_OPEN_LOOP 0
#define MODE_PID 1
#define MKE_M18_DEFAULT_ADDRESS 0x40
#define MKE_M18_FRAME_HEADER    0x55
#define MKE_M18_MODE_MA_CW      101
#define MKE_M18_MODE_MA_CCW     102
#define MKE_M18_MODE_MA_STOP    110
#define MKE_M18_MODE_MB_CW      103
#define MKE_M18_MODE_MB_CCW     104
#define MKE_M18_MODE_MB_STOP    111
#define MKE_M18_MAX_SPEED       255
#define MKE_M18_MIN_SPEED       -255

static uint32_t s_mock_millis = 1000;
uint32_t millis() {{ return s_mock_millis; }}
void delayMicroseconds(uint32_t) {{}}

class MockWire {{
public:
    int write_call_count = 0;
    bool fail_on_mode_mb = false;
    bool fail_on_mode_ma = false;
    bool fail_all = false;
    uint8_t last_mode = 0;
    uint32_t last_payload = 0;

    void beginTransmission(uint8_t) {{}}
    void write(uint8_t *p, size_t len) {{
        if (len >= 6) {{
            last_mode = p[1];
            last_payload = (p[2] << 24) | (p[3] << 16) | (p[4] << 8) | p[5];
        }}
    }}
    uint8_t endTransmission() {{
        write_call_count++;
        if (fail_all) return 1;
        if (fail_on_mode_ma && (last_mode == MKE_M18_MODE_MA_CW || last_mode == MKE_M18_MODE_MA_CCW || last_mode == MKE_M18_MODE_MA_STOP)) return 1;
        if (fail_on_mode_mb && (last_mode == MKE_M18_MODE_MB_CW || last_mode == MKE_M18_MODE_MB_CCW || last_mode == MKE_M18_MODE_MB_STOP)) return 1;
        return 0; // Thành công
    }}
}} Wire;

class MockSerial {{
public:
    std::string last_output;
    void println(const char *s) {{ last_output = s; }}
    void printf(const char *fmt, ...) {{
        char buf[256];
        va_list args;
        va_start(args, fmt);
        vsnprintf(buf, sizeof(buf), fmt, args);
        va_end(args);
        last_output = buf;
    }}
}} Serial;

static uint8_t s_address_7bit = MKE_M18_DEFAULT_ADDRESS;
static volatile uint8_t s_i2c_fault_flag = 0;
static volatile uint8_t s_i2c_fault_latch = 0;

uint8_t MKE_M18_GetFaultFlag(void) {{ return s_i2c_fault_latch; }}
void MKE_M18_ClearFaultFlag(void) {{ s_i2c_fault_flag = 0; s_i2c_fault_latch = 0; }}
uint8_t MKE_M18_Scan(void) {{ return Wire.fail_all ? 0 : s_address_7bit; }}

// --- NHÚNG NGUYÊN BẢN TỪ MKE_M18.CPP ---
{mke_write_cmd}
{mke_set_a}
{mke_set_b}
{mke_stop_a}
{mke_stop_b}
{mke_stop_all}

bool Robot_SetLeftMotor(int16_t speed) {{ return MKE_M18_SetMotorA(speed); }}
bool Robot_SetRightMotor(int16_t speed) {{ return MKE_M18_SetMotorB(speed); }}
bool Robot_Stop(void) {{ return MKE_M18_StopAll(); }}
void WiFiController_CancelAutoTest() {{}}

typedef struct {{ float rpm; }} Encoder_t;
typedef struct {{ float dummy; }} PID_t;
typedef struct {{ float x; float y; float theta; int32_t prev_left_count; int32_t prev_right_count; }} Odometry_t;

void PID_Reset(PID_t *pid) {{}}
void PID_SetGains(PID_t *pid, float, float, float, float) {{}}
void Encoder_ResetCount(Encoder_t *e) {{}}
void Odometry_Reset(Odometry_t *o, float, float, float) {{}}
void Kinematics_Inverse(float v, float w, float *l, float *r) {{ *l = v * 100.0f; *r = v * 100.0f; }}
static void Scan_I2C_Bus() {{}}

enum RobotSafetyState_t {{
    STATE_DISARMED = 0,
    STATE_ARMED    = 1,
    STATE_FAULT    = 2
}};

volatile RobotSafetyState_t g_safety_state = STATE_DISARMED;
static volatile uint32_t g_last_valid_cmd_ms = 0;
static const uint32_t CMD_TIMEOUT_MS = 300;

static float g_target_rpm_left = 0.0f;
static float g_target_rpm_right = 0.0f;
static int16_t g_speed_left = 0;
static int16_t g_speed_right = 0;
static PID_t g_pid_left, g_pid_right;
static Encoder_t g_enc_left, g_enc_right;
static Odometry_t g_odometry;
static uint8_t g_control_mode = 1;
static float g_kp = 0.5f, g_ki = 1.5f, g_kd = 0.01f, g_kf = 0.45f;

// --- NHÚNG NGUYÊN BẢN CÁC HÀM TỪ MAIN.CPP ---
{safe_stop}
{safe_write}
{safe_watch}
{exec_cmd}

int main() {{
    std::cout << "=== RUNNING TRUE INTEGRATED HARNESS WITH ACTUAL MKE_M18_WriteCommand ===" << std::endl;
    std::cout << "Target main.cpp hash: {main_hash}" << std::endl;
    std::cout << "Target mke_m18.cpp hash: {mke_hash}" << std::endl;

    // Test 1: MKE_M18_WriteCommand chạy qua MockWire thật
    Wire.fail_all = false;
    bool w_ok = MKE_M18_WriteCommand(MKE_M18_MODE_MA_CW, 100);
    assert(w_ok == true);
    assert(s_i2c_fault_flag == 0 && s_i2c_fault_latch == 0);
    std::cout << "[PASS 1/6] MKE_M18_WriteCommand successfully writes to Wire" << std::endl;

    // Test 2: Motor A thất bại, Motor B thành công -> LATCH PHẢI ĐƯỢC GIỮ NGUYÊN
    Wire.fail_on_mode_ma = true; // Làm cho Motor A thất bại
    bool a_ok = MKE_M18_SetMotorA(100);
    assert(a_ok == false);
    assert(s_i2c_fault_latch == 1);
    Wire.fail_on_mode_ma = false; // Motor B ghi thành công sau đó
    bool b_ok = MKE_M18_SetMotorB(100);
    assert(b_ok == true);
    assert(s_i2c_fault_latch == 1); // CỜ LATCH VẪN PHẢI BẰNG 1, KHÔNG BỊ XÓA!
    std::cout << "[PASS 2/6] Fail on Motor A + Success on Motor B PRESERVES I2C Latch" << std::endl;

    // Test 3: StopAll thất bại nếu có bất kỳ motor nào không phản hồi
    Wire.fail_on_mode_mb = true; // Làm cho Motor B thất bại khi Stop
    bool stop_ok = MKE_M18_StopAll();
    assert(stop_ok == false); // Dừng thất bại không được báo là thành công!
    Wire.fail_on_mode_mb = false;
    MKE_M18_ClearFaultFlag();
    std::cout << "[PASS 3/6] StopAll propagates failure correctly if Wire fails" << std::endl;

    // Test 4: Safe_Motor_Write dừng ngay khi Motor A lỗi I2C thật, không ghi Motor B
    g_safety_state = STATE_ARMED;
    Wire.write_call_count = 0;
    Wire.fail_on_mode_ma = true;
    Safe_Motor_Write(80, 80);
    assert(g_safety_state == STATE_FAULT);
    assert(MKE_M18_GetFaultFlag() == 1);
    // Wire.write_call_count chỉ là 3 lần retry của Motor A, không được có lệnh của Motor B
    assert(Wire.last_mode != MKE_M18_MODE_MB_CW);
    std::cout << "[PASS 4/6] Safe_Motor_Write halts before Motor B when Motor A fails I2C" << std::endl;

    // Test 5: Khi đang FAULT, từ chối lệnh ARM
    Execute_Robot_Command("ARM");
    assert(Serial.last_output.find("FAULT_ACTIVE_CANNOT_ARM") != std::string::npos);
    assert(g_safety_state == STATE_FAULT);
    std::cout << "[PASS 5/6] FAULT state strictly denies re-ARM" << std::endl;

    // Test 6: CLEAR_FAULT kiểm tra I2C Scan
    Wire.fail_all = true; // Bus vẫn hỏng
    Execute_Robot_Command("CLEAR_FAULT");
    assert(Serial.last_output.find("CLEAR_FAULT_FAILED_BUS_OFFLINE") != std::string::npos);
    assert(g_safety_state == STATE_FAULT);
    Wire.fail_all = false; // Bus đã hồi phục
    Execute_Robot_Command("CLEAR_FAULT");
    assert(Serial.last_output.find("RECOVERED") != std::string::npos);
    assert(g_safety_state == STATE_DISARMED);
    std::cout << "[PASS 6/6] CLEAR_FAULT verifies bus recovery before unlocking" << std::endl;

    std::cout << "=== ALL 6/6 ACTUAL INTEGRATED TESTS PASSED WITH 100% EVIDENCE ===" << std::endl;
    return 0;
}}
"""

out_harness = r'D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH\test_full_integrated_harness.cpp'
with open(out_harness, 'w', encoding='utf-8') as f:
    f.write(harness_code)

print("GENERATED FULL INTEGRATED HARNESS SUCCESSFULLY!")
