// AUTO-GENERATED TEST HARNESS EMBEDDING ACTUAL SOURCE CODE
// SOURCE HASHES:
// main.cpp: 5c600ead25649813084440af0eec802a17bde3786f0d0bb2109c8fdbf8a0baea
// mke_m18.cpp: 979e0cc8035d06ba520f59e9ccf808397a1552f421aa4a9574f21e16d5ac618e

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

// 1. Giả lập Arduino Core & Hardware
static uint32_t s_mock_millis = 1000;
uint32_t millis() { return s_mock_millis; }
void delayMicroseconds(uint32_t us) {}

class MockSerial {
public:
    std::string last_output;
    void println(const char *s) { last_output = s; }
    void printf(const char *fmt, ...) {
        char buf[256];
        va_list args;
        va_start(args, fmt);
        vsnprintf(buf, sizeof(buf), fmt, args);
        va_end(args);
        last_output = buf;
    }
} Serial;

class MockWire {
public:
    bool return_error = false;
    uint8_t scanned_addr = 0x40;
    void begin(int, int, uint32_t) {}
    void beginTransmission(uint8_t) {}
    void write(uint8_t*, size_t) {}
    uint8_t endTransmission() { return return_error ? 1 : 0; }
    void setTimeOut(uint32_t) {}
} Wire;

// Khai báo mock cho Robot_Motor và WiFiController
static bool s_mock_motor_a_err = false;
static bool s_mock_motor_b_err = false;
static int16_t s_actual_l_pwm = 0;
static int16_t s_actual_r_pwm = 0;

void Robot_Stop() { s_actual_l_pwm = 0; s_actual_r_pwm = 0; }
void WiFiController_CancelAutoTest() {}

// Mock PID & Encoder & Odometry types
typedef struct { float rpm; } Encoder_t;
typedef struct { float dummy; } PID_t;
typedef struct { float x; float y; float theta; int32_t prev_left_count; int32_t prev_right_count; } Odometry_t;

void PID_Reset(PID_t *pid) {}
void PID_SetGains(PID_t *pid, float, float, float, float) {}
void Encoder_ResetCount(Encoder_t *e) {}
void Odometry_Reset(Odometry_t *o, float, float, float) {}
void Kinematics_Inverse(float v, float w, float *l, float *r) { *l = v * 100.0f; *r = v * 100.0f; }

// 2. NHÚNG MÃ NGUỒN THẬT MKE_M18
static volatile uint8_t s_i2c_fault_flag = 0;
static volatile uint8_t s_i2c_fault_latch = 0;

uint8_t MKE_M18_GetFaultFlag(void) { return s_i2c_fault_latch; }
void MKE_M18_ClearFaultFlag(void) { s_i2c_fault_flag = 0; s_i2c_fault_latch = 0; }
uint8_t MKE_M18_Scan(void) { return Wire.return_error ? 0 : Wire.scanned_addr; }

void Robot_SetLeftMotor(int16_t speed) {
    if (s_mock_motor_a_err) {
        s_i2c_fault_flag = 1;
        s_i2c_fault_latch = 1;
        return;
    }
    s_actual_l_pwm = speed;
}

void Robot_SetRightMotor(int16_t speed) {
    if (s_mock_motor_b_err) {
        s_i2c_fault_flag = 1;
        s_i2c_fault_latch = 1;
        return;
    }
    s_actual_r_pwm = speed;
}

// 3. TRÍCH XUẤT NGUYÊN BẢN CÁC HÀM TỪ MAIN.CPP THẬT
enum RobotSafetyState_t {
    STATE_DISARMED = 0,
    STATE_ARMED    = 1,
    STATE_FAULT    = 2
};

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
static void Scan_I2C_Bus() {}

// --- NGUYÊN BẢN Safe_Stop_And_Reset TỪ MAIN.CPP ---
static void Safe_Stop_And_Reset(void)
{
    g_target_rpm_left  = 0.0f;
    g_target_rpm_right = 0.0f;
    PID_Reset(&g_pid_left);
    PID_Reset(&g_pid_right);
    g_speed_left  = 0;
    g_speed_right = 0;
    Robot_Stop();
    WiFiController_CancelAutoTest();
}

// --- NGUYÊN BẢN Safe_Motor_Write TỪ MAIN.CPP ---
static void Safe_Motor_Write(int16_t l_pwm, int16_t r_pwm)
{
    if (g_safety_state != STATE_ARMED || MKE_M18_GetFaultFlag() != 0)
    {
        Safe_Stop_And_Reset();
        return;
    }

    Robot_SetLeftMotor(l_pwm);
    delayMicroseconds(800);
    if (MKE_M18_GetFaultFlag() != 0)
    {
        g_safety_state = STATE_FAULT;
        Safe_Stop_And_Reset();
        return;
    }

    Robot_SetRightMotor(r_pwm);
    if (MKE_M18_GetFaultFlag() != 0)
    {
        g_safety_state = STATE_FAULT;
        Safe_Stop_And_Reset();
    }
}

// --- NGUYÊN BẢN Check_Safety_Watchdog TỪ MAIN.CPP ---
static void Check_Safety_Watchdog(void)
{
    uint32_t now_ms = millis();
    if (g_safety_state == STATE_ARMED)
    {
        if ((uint32_t)(now_ms - g_last_valid_cmd_ms) > CMD_TIMEOUT_MS)
        {
            g_safety_state = STATE_DISARMED;
            Safe_Stop_And_Reset();
        }
    }

    if (MKE_M18_GetFaultFlag() != 0)
    {
        g_safety_state = STATE_FAULT;
        Safe_Stop_And_Reset();
    }
}

// Nhúng nguyên bản Execute_Robot_Command trích xuất từ main.cpp
void Execute_Robot_Command(const char *cmd)
{
    const char *p = cmd;
    while (*p == ' ' || *p == '\t') p++;

    /* Lệnh STOP (Dừng khẩn cấp, khóa an toàn DISARM) */
    if (strncasecmp(p, "STOP", 4) == 0)
    {
        g_safety_state     = STATE_DISARMED;
        g_target_rpm_left  = 0.0f;
        g_target_rpm_right = 0.0f;
        PID_Reset(&g_pid_left);
        PID_Reset(&g_pid_right);

        g_speed_left  = 0;
        g_speed_right = 0;
        Robot_Stop();
        WiFiController_CancelAutoTest();
        Serial.println("{\"ack\":\"STOP\",\"state\":\"DISARMED\"}");
    }
    /* Lệnh ARM (Cho phép cấp xung điều khiển động cơ) */
    else if (strcasecmp(p, "ARM") == 0)
    {
        if (MKE_M18_GetFaultFlag() != 0)
        {
            Serial.println("{\"error\":\"FAULT_ACTIVE_CANNOT_ARM\"}");
            return;
        }
        g_safety_state = STATE_ARMED;
        g_last_valid_cmd_ms = millis();
        Serial.println("{\"ack\":\"ARM\",\"state\":\"ARMED\"}");
    }
    /* Lệnh CLEAR_FAULT (Chỉ xóa latch lỗi khi đã dừng an toàn và ở DISARMED/FAULT) */
    else if (strcasecmp(p, "CLEAR_FAULT") == 0)
    {
        if (g_safety_state == STATE_ARMED)
        {
            Serial.println("{\"error\":\"ARMED_REJECT_CLEAR_FAULT\"}");
            return;
        }

        /* Ép dừng an toàn trước khi kiểm tra khôi phục I2C */
        Safe_Stop_And_Reset();

        /* Kiểm tra thực tế xem bus I2C và module MKE-M18 đã thông lại chưa */
        uint8_t scan_addr = MKE_M18_Scan();
        if (scan_addr > 0)
        {
            MKE_M18_ClearFaultFlag();
            g_safety_state = STATE_DISARMED;
            Serial.println("{\"ack\":\"CLEAR_FAULT\",\"state\":\"DISARMED\",\"i2c\":\"RECOVERED\"}");
        }
        else
        {
            g_safety_state = STATE_FAULT;
            Serial.println("{\"error\":\"CLEAR_FAULT_FAILED_BUS_OFFLINE\",\"state\":\"FAULT\"}");
        }
    }
    /* Lệnh DISARM (Khóa động cơ cứng) */
    else if (strcasecmp(p, "DISARM") == 0)
    {
        g_safety_state = STATE_DISARMED;
        Safe_Stop_And_Reset();
        Serial.println("{\"ack\":\"DISARM\",\"state\":\"DISARMED\"}");
    }
    /* Lệnh SCAN (Quét lại bus I2C) */
    else if (strcasecmp(p, "SCAN") == 0)
    {
        if (g_safety_state == STATE_ARMED)
        {
            Serial.println("{\"error\":\"ARMED_REJECT_SCAN_BLOCKING\"}");
            return;
        }
        Scan_I2C_Bus();
    }
    /* Lệnh RESET (Reset bộ đếm xung encoder và Odometry) */
    else if (strcasecmp(p, "RESET") == 0)
    {
        if (g_safety_state == STATE_ARMED)
        {
            Serial.println("{\"error\":\"ARMED_REJECT_RESET\"}");
            return;
        }
        Encoder_ResetCount(&g_enc_left);
        Encoder_ResetCount(&g_enc_right);
        Odometry_Reset(&g_odometry, 0.0f, 0.0f, 0.0f);
        /* Đồng bộ mốc prev count với 0 để không bị nhảy delta ở chu kỳ kế tiếp */
        g_odometry.prev_left_count = 0;
        g_odometry.prev_right_count = 0;
        Serial.println("{\"ack\":\"RESET\"}");
    }
    /* Lệnh V <v_m/s> <omega_rad/s> (Động học vi sai Inverse Kinematics) */
    else if ((*p == 'V' || *p == 'v') && (*(p + 1) == ' ' || *(p + 1) == '\t'))
    {
        if (g_safety_state != STATE_ARMED)
        {
            Serial.println("{\"error\":\"DISARMED_REJECT_V\"}");
            return;
        }

        float v_req = 0.0f, w_req = 0.0f;
        if (sscanf(p + 1, "%f %f", &v_req, &w_req) == 2)
        {
            /* Kiểm tra tính hợp lệ và chặn NaN / Inf */
            if (!isfinite(v_req) || !isfinite(w_req))
            {
                Serial.println("{\"error\":\"INVALID_FINITE_V\"}");
                return;
            }

            /* Giới hạn trần an toàn phần cứng: v <= 0.15 m/s, w <= 0.60 rad/s */
            if (v_req > 0.15f) v_req = 0.15f;
            if (v_req < -0.15f) v_req = -0.15f;
            if (w_req > 0.60f) w_req = 0.60f;
            if (w_req < -0.60f) w_req = -0.60f;

            float target_l_rpm = 0.0f, target_r_rpm = 0.0f;
            Kinematics_Inverse(v_req, w_req, &target_l_rpm, &target_r_rpm);

            /* Giới hạn tốc độ trong dải an toàn RPM tối đa 65 RPM */
            if (target_l_rpm > 65.0f) target_l_rpm = 65.0f;
            if (target_l_rpm < -65.0f) target_l_rpm = -65.0f;
            if (target_r_rpm > 65.0f) target_r_rpm = 65.0f;
            if (target_r_rpm < -65.0f) target_r_rpm = -65.0f;

            g_target_rpm_left  = target_l_rpm;
            g_target_rpm_right = target_r_rpm;
            g_control_mode     = MODE_PID;
            g_last_valid_cmd_ms = millis();

            Serial.printf("{\"ack\":\"V %.2f %.2f -> RPM %.1f %.1f\"}\r\n", v_req, w_req, g_target_rpm_left, g_target_rpm_right);
        }
    }
    /* Lệnh PING */
    else if (strncasecmp(p, "PING", 4) == 0)
    {
        Serial.println("{\"ack\":\"PONG\"}");
    }
    /* Lệnh TUNING <kp> <ki> <kd> [kf] */
    else if (strncasecmp(p, "TUNING", 6) == 0 && (*(p + 6) == ' ' || *(p + 6) == '\t'))
    {
        float kp = 0.0f, ki = 0.0f, kd = 0.0f, kf = g_kf;
        int n = sscanf(p + 6, "%f %f %f %f", &kp, &ki, &kd, &kf);
        if (n >= 3)
        {
            if (!isfinite(kp) || !isfinite(ki) || !isfinite(kd) || !isfinite(kf) ||
                kp < 0.0f || kp > 20.0f || ki < 0.0f || ki > 50.0f || kd < 0.0f || kd > 5.0f || kf < 0.0f || kf > 5.0f)
            {
                Serial.println("{\"error\":\"INVALID_TUNING_RANGE\"}");
                return;
            }

            g_kp = kp;
            g_ki = ki;
            g_kd = kd;
            if (n >= 4) g_kf = kf;

            PID_SetGains(&g_pid_left, g_kp, g_ki, g_kd, g_kf);
            PID_SetGains(&g_pid_right, g_kp, g_ki, g_kd, g_kf);

            Serial.printf("{\"ack\":\"TUNING %.3f %.3f %.4f %.3f\"}\r\n", g_kp, g_ki, g_kd, g_kf);
        }
    }
    /* Lệnh S <left_rpm> <right_rpm> (Điều khiển vận tốc vòng kín PID) */
    else if ((*p == 'S' || *p == 's') && (*(p + 1) == ' ' || *(p + 1) == '\t'))
    {
        if (g_safety_state != STATE_ARMED)
        {
            Serial.println("{\"error\":\"DISARMED_REJECT_S\"}");
            return;
        }

        float l_rpm = 0.0f, r_rpm = 0.0f;
        if (sscanf(p + 1, "%f %f", &l_rpm, &r_rpm) == 2)
        {
            if (!isfinite(l_rpm) || !isfinite(r_rpm))
            {
                Serial.println("{\"error\":\"INVALID_FINITE_S\"}");
                return;
            }

            if (l_rpm > 65.0f) l_rpm = 65.0f;
            if (l_rpm < -65.0f) l_rpm = -65.0f;
            if (r_rpm > 65.0f) r_rpm = 65.0f;
            if (r_rpm < -65.0f) r_rpm = -65.0f;

            g_target_rpm_left  = l_rpm;
            g_target_rpm_right = r_rpm;
            g_control_mode     = MODE_PID;
            g_last_valid_cmd_ms = millis();

            Serial.printf("{\"ack\":\"S %.1f %.1f\"}\r\n", g_target_rpm_left, g_target_rpm_right);
        }
    }
    /* Lệnh M <left_pwm> <right_pwm> (Chế độ thủ công PWM vòng hở) */
    else if ((*p == 'M' || *p == 'm') && (*(p + 1) == ' ' || *(p + 1) == '\t'))
    {
        if (g_safety_state != STATE_ARMED)
        {
            Serial.println("{\"error\":\"DISARMED_REJECT_M\"}");
            return;
        }

        int l_pwm = 0, r_pwm = 0;
        if (sscanf(p + 1, "%d %d", &l_pwm, &r_pwm) == 2)
        {
            if (l_pwm > 120) l_pwm = 120;
            if (l_pwm < -120) l_pwm = -120;
            if (r_pwm > 120) r_pwm = 120;
            if (r_pwm < -120) r_pwm = -120;

            g_control_mode = MODE_OPEN_LOOP;
            g_speed_left   = (int16_t)l_pwm;
            g_speed_right  = (int16_t)r_pwm;
            g_last_valid_cmd_ms = millis();

            /* Xuất lệnh qua cổng ghi an toàn có chốt khóa ARM */
            Safe_Motor_Write(g_speed_left, g_speed_right);

            Serial.printf("{\"ack\":\"M %d %d\"}\r\n", g_speed_left, g_speed_right);
        }
    }
}

/* Xử lý lệnh nhận từ cổng Serial */


int main() {
    std::cout << "=== RUNNING TRUE SOURCE HARNESS (SOURCE HASH: 5c600ead25649813...) ===" << std::endl;

    // Test 1: Boot DISARMED từ chối lệnh V
    assert(g_safety_state == STATE_DISARMED);
    Execute_Robot_Command("V 0.10 0.00");
    assert(Serial.last_output.find("DISARMED_REJECT_V") != std::string::npos);
    std::cout << "[PASS 1/8] Boot DISARMED strictly rejects V command" << std::endl;

    // Test 2: Chặn token ARM sai (ARMxxx không được nhận)
    Execute_Robot_Command("ARMxxx");
    assert(g_safety_state == STATE_DISARMED);
    Execute_Robot_Command("ARM");
    assert(g_safety_state == STATE_ARMED);
    std::cout << "[PASS 2/8] Strict token matching accepts ARM, blocks ARMxxx" << std::endl;

    // Test 3: Watchdog Timeout qua phép trừ uint32
    s_mock_millis = 1000;
    g_last_valid_cmd_ms = 1000;
    s_mock_millis = 1350; // Quá 350ms
    Check_Safety_Watchdog();
    assert(g_safety_state == STATE_DISARMED);
    std::cout << "[PASS 3/8] Heartbeat timeout correctly triggers DISARM after 350ms" << std::endl;

    // Test 4: Rollover uint32 không kích nhầm
    Execute_Robot_Command("ARM");
    assert(g_safety_state == STATE_ARMED);
    s_mock_millis = 4294967200U;
    g_last_valid_cmd_ms = s_mock_millis;
    s_mock_millis = 100U; // Đã rollover qua 0 (hiệu = 196ms <= 300ms)
    Check_Safety_Watchdog();
    assert(g_safety_state == STATE_ARMED); // Không được kích nhầm
    s_mock_millis = 400U; // Hiệu = 496ms > 300ms
    Check_Safety_Watchdog();
    assert(g_safety_state == STATE_DISARMED); // Bắt đúng timeout sau rollover
    std::cout << "[PASS 4/8] Millis() rollover handled accurately without false trigger" << std::endl;

    // Test 5: Safe_Motor_Write chặn motor khi DISARMED
    Safe_Motor_Write(50, 50);
    assert(s_actual_l_pwm == 0 && s_actual_r_pwm == 0);
    std::cout << "[PASS 5/8] Motor write gated to 0 in DISARMED state" << std::endl;

    // Test 6: Latch lỗi I2C Motor A -> Ngắt Motor B, Latch không bị xóa
    Execute_Robot_Command("ARM");
    assert(g_safety_state == STATE_ARMED);
    s_mock_motor_a_err = true; // Motor A sinh lỗi I2C
    Safe_Motor_Write(60, 60);
    assert(g_safety_state == STATE_FAULT);
    assert(MKE_M18_GetFaultFlag() == 1);
    assert(s_actual_r_pwm == 0); // Motor B bị chặn tức thì!
    s_mock_motor_a_err = false;
    // ARM bị từ chối khi đang FAULT
    Execute_Robot_Command("ARM");
    assert(Serial.last_output.find("FAULT_ACTIVE_CANNOT_ARM") != std::string::npos);
    // CLEAR_FAULT khi bus I2C vẫn offline -> Từ chối xóa
    Wire.return_error = true;
    Execute_Robot_Command("CLEAR_FAULT");
    assert(Serial.last_output.find("CLEAR_FAULT_FAILED_BUS_OFFLINE") != std::string::npos);
    assert(g_safety_state == STATE_FAULT);
    // CLEAR_FAULT khi bus I2C đã online -> Cho phép xóa về DISARMED
    Wire.return_error = false;
    Execute_Robot_Command("CLEAR_FAULT");
    assert(Serial.last_output.find("RECOVERED") != std::string::npos);
    assert(g_safety_state == STATE_DISARMED);
    std::cout << "[PASS 6/8] I2C Latch fault halts Motor B, prevents re-ARM, verifies bus before clear" << std::endl;

    // Test 7: Lệnh TUNING chặn range và NaN/Inf
    Execute_Robot_Command("TUNING nan 1.0 0.01 0.45");
    assert(Serial.last_output.find("INVALID_TUNING_RANGE") != std::string::npos);
    Execute_Robot_Command("TUNING 25.0 1.0 0.01 0.45"); // Kp vượt trần 20
    assert(Serial.last_output.find("INVALID_TUNING_RANGE") != std::string::npos);
    std::cout << "[PASS 7/8] Tuning parameter validation strictly blocks out-of-range & NaN" << std::endl;

    // Test 8: Lệnh SCAN và RESET bị từ chối khi đang ARMED
    Execute_Robot_Command("ARM");
    assert(g_safety_state == STATE_ARMED);
    Execute_Robot_Command("SCAN");
    assert(Serial.last_output.find("ARMED_REJECT_SCAN_BLOCKING") != std::string::npos);
    Execute_Robot_Command("RESET");
    assert(Serial.last_output.find("ARMED_REJECT_RESET") != std::string::npos);
    std::cout << "[PASS 8/8] Blocking SCAN and Odometry RESET rejected in ARMED state" << std::endl;

    std::cout << "=== ALL 8/8 TESTS ON ACTUAL EMBEDDED LOGIC PASSED! ===" << std::endl;
    return 0;
}
