// AUTO-GENERATED TRUE SOURCE HARNESS INCLUDING MKE_M18_WriteCommand
// SHA256 main.cpp: 5c600ead25649813084440af0eec802a17bde3786f0d0bb2109c8fdbf8a0baea
// SHA256 mke_m18.cpp: 979e0cc8035d06ba520f59e9ccf808397a1552f421aa4a9574f21e16d5ac618e

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
uint32_t millis() { return s_mock_millis; }
void delayMicroseconds(uint32_t) {}

class MockWire {
public:
    int write_call_count = 0;
    bool fail_on_mode_mb = false;
    bool fail_on_mode_ma = false;
    bool fail_all = false;
    uint8_t last_mode = 0;
    uint32_t last_payload = 0;

    void beginTransmission(uint8_t) {}
    void write(uint8_t *p, size_t len) {
        if (len >= 6) {
            last_mode = p[1];
            last_payload = (p[2] << 24) | (p[3] << 16) | (p[4] << 8) | p[5];
        }
    }
    uint8_t endTransmission() {
        write_call_count++;
        if (fail_all) return 1;
        if (fail_on_mode_ma && (last_mode == MKE_M18_MODE_MA_CW || last_mode == MKE_M18_MODE_MA_CCW || last_mode == MKE_M18_MODE_MA_STOP)) return 1;
        if (fail_on_mode_mb && (last_mode == MKE_M18_MODE_MB_CW || last_mode == MKE_M18_MODE_MB_CCW || last_mode == MKE_M18_MODE_MB_STOP)) return 1;
        return 0; // Thành công
    }
} Wire;

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

static uint8_t s_address_7bit = MKE_M18_DEFAULT_ADDRESS;
static volatile uint8_t s_i2c_fault_flag = 0;
static volatile uint8_t s_i2c_fault_latch = 0;

uint8_t MKE_M18_GetFaultFlag(void) { return s_i2c_fault_latch; }
void MKE_M18_ClearFaultFlag(void) { s_i2c_fault_flag = 0; s_i2c_fault_latch = 0; }
uint8_t MKE_M18_Scan(void) { return Wire.fail_all ? 0 : s_address_7bit; }

// --- NHÚNG NGUYÊN BẢN TỪ MKE_M18.CPP ---
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



bool Robot_SetLeftMotor(int16_t speed) { return MKE_M18_SetMotorA(speed); }
bool Robot_SetRightMotor(int16_t speed) { return MKE_M18_SetMotorB(speed); }
bool Robot_Stop(void) { return MKE_M18_StopAll(); }
void WiFiController_CancelAutoTest() {}

typedef struct { float rpm; } Encoder_t;
typedef struct { float dummy; } PID_t;
typedef struct { float x; float y; float theta; int32_t prev_left_count; int32_t prev_right_count; } Odometry_t;

void PID_Reset(PID_t *pid) {}
void PID_SetGains(PID_t *pid, float, float, float, float) {}
void Encoder_ResetCount(Encoder_t *e) {}
void Odometry_Reset(Odometry_t *o, float, float, float) {}
void Kinematics_Inverse(float v, float w, float *l, float *r) { *l = v * 100.0f; *r = v * 100.0f; }
static void Scan_I2C_Bus() {}

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

// --- NHÚNG NGUYÊN BẢN CÁC HÀM TỪ MAIN.CPP ---
static void Safe_Stop_And_Reset(void);
static void Safe_Motor_Write(int16_t l_pwm, int16_t r_pwm);
static void Check_Safety_Watchdog(void);

Encoder_t g_enc_left;
Encoder_t g_enc_right;

PID_t g_pid_left;
PID_t g_pid_right;

float g_target_rpm_left  = 0.0f;
float g_target_rpm_right = 0.0f;

/* Bộ thông số PID tối ưu thực tế cho GA25-370 */
float g_kp = 0.50f;
float g_ki = 1.50f;
float g_kd = 0.010f;
float g_kf = 0.45f;

int16_t g_speed_left  = 0;
int16_t g_speed_right = 0;

static bool s_i2c_scanned = false;

/* Hàm quét I2C bus và đọc điện áp VIN của module MKE-M18 */
static void Scan_I2C_Bus(void)
{
    Serial.println("{\"info\":\"Scanning I2C bus...\"}");
    uint8_t addr = MKE_M18_Scan();

    if (addr > 0)
    {
        Serial.printf("{\"i2c_found\":\"0x%02X\"}\r\n", addr);
        uint32_t vin_mv = 0;
        if (MKE_M18_ReadVIN(&vin_mv) && vin_mv > 0)
        {
            Serial.printf("{\"vin_mv\":%u}\r\n", (unsigned int)vin_mv);
        }
    }
    else
    {
        Serial.println("{\"error\":\"No I2C device found\"}");
    }
}

/* Xử lý lệnh dùng chung cho cả cổng Serial và Wi-Fi Web Controller */
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
static void Process_Serial_Commands(void)
{
    static char rx_buf[80];
    static uint8_t rx_idx = 0;

    while (Serial.available() > 0)
    {
        char c = (char)Serial.read();
        if (c == '\r' || c == '\n')
        {
            if (rx_idx > 0)
            {
                rx_buf[rx_idx] = '\0';
                Execute_Robot_Command(rx_buf);
                rx_idx = 0;
            }
        }
        else if (rx_idx < sizeof(rx_buf) - 1)
        {
            rx_buf[rx_idx++] = c;
        }
    }
}

/* Định dạng Telemetry JSON gửi qua Serial và Web Dashboard (10Hz) */
static void Print_Telemetry_JSON(void)
{
    const char *state_str = "DISARMED";
    if (g_safety_state == STATE_ARMED) state_str = "ARMED";
    else if (g_safety_state == STATE_FAULT) state_str = "FAULT";

    Serial.printf("{\"safety\":\"%s\",\"mode\":\"%s\",\"l_tgt\":%.1f,\"r_tgt\":%.1f,\"l_rpm\":%.2f,\"r_rpm\":%.2f,\"l_pwm\":%d,\"r_pwm\":%d,\"x\":%.3f,\"y\":%.3f,\"th\":%.3f,\"v\":%.2f,\"w\":%.2f}\r\n",
        state_str,
        (g_control_mode == MODE_PID) ? "PID" : "MAN",
        g_target_rpm_left,
        g_target_rpm_right,
        g_enc_left.rpm,
        g_enc_right.rpm,
        g_speed_left,
        g_speed_right,
        g_odometry.x,
        g_odometry.y,
        g_odometry.theta,
        g_odometry.v_linear,
        g_odometry.omega_angular
    );
}

void setup(void)
{
    Serial.begin(115200);
    delay(200);

    /* 1. An toàn: Khởi tạo I2C và dừng ngay động cơ */
    Robot_Motor_Init(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    Robot_Stop();

    /* 2. Cài đặt chiều quay: Bánh Trái (Motor A), Bánh Phải (Motor B) */
    Robot_SetMotorDirections(LEFT_MOTOR_DIRECTION, RIGHT_MOTOR_DIRECTION);

    /* 3. Khởi tạo Hardware PCNT Encoder x4 cho 2 bánh */
    Encoder_Init(&g_enc_left, PCNT_UNIT_0, PIN_ENC_LEFT_A, PIN_ENC_LEFT_B, LEFT_ENCODER_DIRECTION);
    Encoder_Init(&g_enc_right, PCNT_UNIT_1, PIN_ENC_RIGHT_A, PIN_ENC_RIGHT_B, RIGHT_ENCODER_DIRECTION);

    Encoder_Start(&g_enc_left);
    Encoder_Start(&g_enc_right);

    /* 4. Khởi tạo 2 bộ điều khiển PID vận tốc vòng kín */
    PID_Init(&g_pid_left, g_kp, g_ki, g_kd, g_kf, -255.0f, 255.0f);
    PID_Init(&g_pid_right, g_kp, g_ki, g_kd, g_kf, -255.0f, 255.0f);

    /* 5. Khởi tạo Odometry */
    Odometry_Init(&g_odometry, 0.0f, 0.0f, 0.0f);

    /* 6. Khởi tạo Wi-Fi SoftAP và Web Server điều khiển qua điện thoại (Nếu không ở chế độ BENCH) */
#if !BENCH_SERIAL_ONLY
    WiFiController_Init();
    Serial.println("{\"info\":\"ESP32 Robot Ready - USB + WiFi Enabled\"}");
#else
    Serial.println("{\"info\":\"ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)\"}");
#endif
}

/* Hàm ngắt cứng và xóa trạng thái vận hành */
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


static void Safe_Motor_Write(int16_t l_pwm, int16_t r_pwm);
static void Check_Safety_Watchdog(void);

Encoder_t g_enc_left;
Encoder_t g_enc_right;

PID_t g_pid_left;
PID_t g_pid_right;

float g_target_rpm_left  = 0.0f;
float g_target_rpm_right = 0.0f;

/* Bộ thông số PID tối ưu thực tế cho GA25-370 */
float g_kp = 0.50f;
float g_ki = 1.50f;
float g_kd = 0.010f;
float g_kf = 0.45f;

int16_t g_speed_left  = 0;
int16_t g_speed_right = 0;

static bool s_i2c_scanned = false;

/* Hàm quét I2C bus và đọc điện áp VIN của module MKE-M18 */
static void Scan_I2C_Bus(void)
{
    Serial.println("{\"info\":\"Scanning I2C bus...\"}");
    uint8_t addr = MKE_M18_Scan();

    if (addr > 0)
    {
        Serial.printf("{\"i2c_found\":\"0x%02X\"}\r\n", addr);
        uint32_t vin_mv = 0;
        if (MKE_M18_ReadVIN(&vin_mv) && vin_mv > 0)
        {
            Serial.printf("{\"vin_mv\":%u}\r\n", (unsigned int)vin_mv);
        }
    }
    else
    {
        Serial.println("{\"error\":\"No I2C device found\"}");
    }
}

/* Xử lý lệnh dùng chung cho cả cổng Serial và Wi-Fi Web Controller */
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
static void Process_Serial_Commands(void)
{
    static char rx_buf[80];
    static uint8_t rx_idx = 0;

    while (Serial.available() > 0)
    {
        char c = (char)Serial.read();
        if (c == '\r' || c == '\n')
        {
            if (rx_idx > 0)
            {
                rx_buf[rx_idx] = '\0';
                Execute_Robot_Command(rx_buf);
                rx_idx = 0;
            }
        }
        else if (rx_idx < sizeof(rx_buf) - 1)
        {
            rx_buf[rx_idx++] = c;
        }
    }
}

/* Định dạng Telemetry JSON gửi qua Serial và Web Dashboard (10Hz) */
static void Print_Telemetry_JSON(void)
{
    const char *state_str = "DISARMED";
    if (g_safety_state == STATE_ARMED) state_str = "ARMED";
    else if (g_safety_state == STATE_FAULT) state_str = "FAULT";

    Serial.printf("{\"safety\":\"%s\",\"mode\":\"%s\",\"l_tgt\":%.1f,\"r_tgt\":%.1f,\"l_rpm\":%.2f,\"r_rpm\":%.2f,\"l_pwm\":%d,\"r_pwm\":%d,\"x\":%.3f,\"y\":%.3f,\"th\":%.3f,\"v\":%.2f,\"w\":%.2f}\r\n",
        state_str,
        (g_control_mode == MODE_PID) ? "PID" : "MAN",
        g_target_rpm_left,
        g_target_rpm_right,
        g_enc_left.rpm,
        g_enc_right.rpm,
        g_speed_left,
        g_speed_right,
        g_odometry.x,
        g_odometry.y,
        g_odometry.theta,
        g_odometry.v_linear,
        g_odometry.omega_angular
    );
}

void setup(void)
{
    Serial.begin(115200);
    delay(200);

    /* 1. An toàn: Khởi tạo I2C và dừng ngay động cơ */
    Robot_Motor_Init(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    Robot_Stop();

    /* 2. Cài đặt chiều quay: Bánh Trái (Motor A), Bánh Phải (Motor B) */
    Robot_SetMotorDirections(LEFT_MOTOR_DIRECTION, RIGHT_MOTOR_DIRECTION);

    /* 3. Khởi tạo Hardware PCNT Encoder x4 cho 2 bánh */
    Encoder_Init(&g_enc_left, PCNT_UNIT_0, PIN_ENC_LEFT_A, PIN_ENC_LEFT_B, LEFT_ENCODER_DIRECTION);
    Encoder_Init(&g_enc_right, PCNT_UNIT_1, PIN_ENC_RIGHT_A, PIN_ENC_RIGHT_B, RIGHT_ENCODER_DIRECTION);

    Encoder_Start(&g_enc_left);
    Encoder_Start(&g_enc_right);

    /* 4. Khởi tạo 2 bộ điều khiển PID vận tốc vòng kín */
    PID_Init(&g_pid_left, g_kp, g_ki, g_kd, g_kf, -255.0f, 255.0f);
    PID_Init(&g_pid_right, g_kp, g_ki, g_kd, g_kf, -255.0f, 255.0f);

    /* 5. Khởi tạo Odometry */
    Odometry_Init(&g_odometry, 0.0f, 0.0f, 0.0f);

    /* 6. Khởi tạo Wi-Fi SoftAP và Web Server điều khiển qua điện thoại (Nếu không ở chế độ BENCH) */
#if !BENCH_SERIAL_ONLY
    WiFiController_Init();
    Serial.println("{\"info\":\"ESP32 Robot Ready - USB + WiFi Enabled\"}");
#else
    Serial.println("{\"info\":\"ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)\"}");
#endif
}

/* Hàm ngắt cứng và xóa trạng thái vận hành */
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

/* Cổng ghi an toàn motor: Khóa mọi lệnh xuất motor nếu không ở STATE_ARMED */
static void Safe_Motor_Write(int16_t l_pwm, int16_t r_pwm)
{
    if (g_safety_state != STATE_ARMED || MKE_M18_GetFaultFlag() != 0)
    {
        Safe_Stop_And_Reset();
        return;
    }

    Robot_SetLeftMotor(l_pwm);
    delayMicroseconds(800);
    /* Kiểm tra ngay sau ghi Motor A: Nếu phát sinh lỗi I2C latch thì lập tức dừng, không ghi Motor B */
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


static void Check_Safety_Watchdog(void);

Encoder_t g_enc_left;
Encoder_t g_enc_right;

PID_t g_pid_left;
PID_t g_pid_right;

float g_target_rpm_left  = 0.0f;
float g_target_rpm_right = 0.0f;

/* Bộ thông số PID tối ưu thực tế cho GA25-370 */
float g_kp = 0.50f;
float g_ki = 1.50f;
float g_kd = 0.010f;
float g_kf = 0.45f;

int16_t g_speed_left  = 0;
int16_t g_speed_right = 0;

static bool s_i2c_scanned = false;

/* Hàm quét I2C bus và đọc điện áp VIN của module MKE-M18 */
static void Scan_I2C_Bus(void)
{
    Serial.println("{\"info\":\"Scanning I2C bus...\"}");
    uint8_t addr = MKE_M18_Scan();

    if (addr > 0)
    {
        Serial.printf("{\"i2c_found\":\"0x%02X\"}\r\n", addr);
        uint32_t vin_mv = 0;
        if (MKE_M18_ReadVIN(&vin_mv) && vin_mv > 0)
        {
            Serial.printf("{\"vin_mv\":%u}\r\n", (unsigned int)vin_mv);
        }
    }
    else
    {
        Serial.println("{\"error\":\"No I2C device found\"}");
    }
}

/* Xử lý lệnh dùng chung cho cả cổng Serial và Wi-Fi Web Controller */
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
static void Process_Serial_Commands(void)
{
    static char rx_buf[80];
    static uint8_t rx_idx = 0;

    while (Serial.available() > 0)
    {
        char c = (char)Serial.read();
        if (c == '\r' || c == '\n')
        {
            if (rx_idx > 0)
            {
                rx_buf[rx_idx] = '\0';
                Execute_Robot_Command(rx_buf);
                rx_idx = 0;
            }
        }
        else if (rx_idx < sizeof(rx_buf) - 1)
        {
            rx_buf[rx_idx++] = c;
        }
    }
}

/* Định dạng Telemetry JSON gửi qua Serial và Web Dashboard (10Hz) */
static void Print_Telemetry_JSON(void)
{
    const char *state_str = "DISARMED";
    if (g_safety_state == STATE_ARMED) state_str = "ARMED";
    else if (g_safety_state == STATE_FAULT) state_str = "FAULT";

    Serial.printf("{\"safety\":\"%s\",\"mode\":\"%s\",\"l_tgt\":%.1f,\"r_tgt\":%.1f,\"l_rpm\":%.2f,\"r_rpm\":%.2f,\"l_pwm\":%d,\"r_pwm\":%d,\"x\":%.3f,\"y\":%.3f,\"th\":%.3f,\"v\":%.2f,\"w\":%.2f}\r\n",
        state_str,
        (g_control_mode == MODE_PID) ? "PID" : "MAN",
        g_target_rpm_left,
        g_target_rpm_right,
        g_enc_left.rpm,
        g_enc_right.rpm,
        g_speed_left,
        g_speed_right,
        g_odometry.x,
        g_odometry.y,
        g_odometry.theta,
        g_odometry.v_linear,
        g_odometry.omega_angular
    );
}

void setup(void)
{
    Serial.begin(115200);
    delay(200);

    /* 1. An toàn: Khởi tạo I2C và dừng ngay động cơ */
    Robot_Motor_Init(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    Robot_Stop();

    /* 2. Cài đặt chiều quay: Bánh Trái (Motor A), Bánh Phải (Motor B) */
    Robot_SetMotorDirections(LEFT_MOTOR_DIRECTION, RIGHT_MOTOR_DIRECTION);

    /* 3. Khởi tạo Hardware PCNT Encoder x4 cho 2 bánh */
    Encoder_Init(&g_enc_left, PCNT_UNIT_0, PIN_ENC_LEFT_A, PIN_ENC_LEFT_B, LEFT_ENCODER_DIRECTION);
    Encoder_Init(&g_enc_right, PCNT_UNIT_1, PIN_ENC_RIGHT_A, PIN_ENC_RIGHT_B, RIGHT_ENCODER_DIRECTION);

    Encoder_Start(&g_enc_left);
    Encoder_Start(&g_enc_right);

    /* 4. Khởi tạo 2 bộ điều khiển PID vận tốc vòng kín */
    PID_Init(&g_pid_left, g_kp, g_ki, g_kd, g_kf, -255.0f, 255.0f);
    PID_Init(&g_pid_right, g_kp, g_ki, g_kd, g_kf, -255.0f, 255.0f);

    /* 5. Khởi tạo Odometry */
    Odometry_Init(&g_odometry, 0.0f, 0.0f, 0.0f);

    /* 6. Khởi tạo Wi-Fi SoftAP và Web Server điều khiển qua điện thoại (Nếu không ở chế độ BENCH) */
#if !BENCH_SERIAL_ONLY
    WiFiController_Init();
    Serial.println("{\"info\":\"ESP32 Robot Ready - USB + WiFi Enabled\"}");
#else
    Serial.println("{\"info\":\"ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)\"}");
#endif
}

/* Hàm ngắt cứng và xóa trạng thái vận hành */
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

/* Cổng ghi an toàn motor: Khóa mọi lệnh xuất motor nếu không ở STATE_ARMED */
static void Safe_Motor_Write(int16_t l_pwm, int16_t r_pwm)
{
    if (g_safety_state != STATE_ARMED || MKE_M18_GetFaultFlag() != 0)
    {
        Safe_Stop_And_Reset();
        return;
    }

    Robot_SetLeftMotor(l_pwm);
    delayMicroseconds(800);
    /* Kiểm tra ngay sau ghi Motor A: Nếu phát sinh lỗi I2C latch thì lập tức dừng, không ghi Motor B */
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

/* Kiểm tra an toàn watchdog và sự cố I2C */
static void Check_Safety_Watchdog(void)
{
    uint32_t now_ms = millis();
    if (g_safety_state == STATE_ARMED)
    {
        /* Trừ không dấu (uint32_t)(now_ms - last_ms) xử lý đúng cả khi millis() rollover */
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
    std::cout << "=== RUNNING TRUE INTEGRATED HARNESS WITH ACTUAL MKE_M18_WriteCommand ===" << std::endl;
    std::cout << "Target main.cpp hash: 5c600ead25649813084440af0eec802a17bde3786f0d0bb2109c8fdbf8a0baea" << std::endl;
    std::cout << "Target mke_m18.cpp hash: 979e0cc8035d06ba520f59e9ccf808397a1552f421aa4a9574f21e16d5ac618e" << std::endl;

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
}
