#include <Arduino.h>
#include <stdio.h>
#include <string.h>
#include "encoder.h"
#include "mke_m18.h"
#include "pid.h"
#include "robot_motor.h"
#include "wifi_controller.h"
#include "odometry.h"
#include "agv_speed_limits.h"

/* Biến toàn cục Odometry */
Odometry_t g_odometry;

/* Cấu hình Pinout ESP32-32D DevKitC */
#define PIN_I2C_SDA         21
#define PIN_I2C_SCL         22

#define PIN_ENC_LEFT_A      18
#define PIN_ENC_LEFT_B      19

#define PIN_ENC_RIGHT_A     25
#define PIN_ENC_RIGHT_B     26

#define TELEMETRY_INTERVAL_MS   100     /* Gửi JSON qua Serial mỗi 100ms (10Hz) */
#define BENCH_SERIAL_ONLY   1     /* 1: Chế độ Bench test Serial duy nhất, khóa hoàn toàn Wi-Fi Controller */
#define CMD_TIMEOUT_MS      300     /* Mất lệnh quá 300ms tự động ngắt động cơ */

/* Trạng thái an toàn hệ thống */
enum RobotSafetyState_t {
    STATE_DISARMED = 0,
    STATE_ARMED    = 1,
    STATE_FAULT    = 2
};

volatile RobotSafetyState_t g_safety_state = STATE_DISARMED;
static volatile uint32_t g_last_valid_cmd_ms = 0;

/* Định nghĩa chế độ điều khiển */
#define MODE_OPEN_LOOP      0
#define MODE_PID            1

uint8_t g_control_mode = MODE_PID;

/* Khai báo nguyên mẫu hàm an toàn */
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

            /* Giới hạn trần an toàn phần cứng: candidate 140 RPM, w <= 0.60 rad/s */
            if (v_req > AGV_MAX_LINEAR_MPS) v_req = AGV_MAX_LINEAR_MPS;
            if (v_req < -AGV_MAX_LINEAR_MPS) v_req = -AGV_MAX_LINEAR_MPS;
            if (w_req > 0.60f) w_req = 0.60f;
            if (w_req < -0.60f) w_req = -0.60f;

            float target_l_rpm = 0.0f, target_r_rpm = 0.0f;
            Kinematics_Inverse(v_req, w_req, &target_l_rpm, &target_r_rpm);

            /* Preserve curvature when either wheel reaches the candidate limit. */
            AGV_LimitWheelRPM(&target_l_rpm, &target_r_rpm);

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

            AGV_LimitWheelRPM(&l_rpm, &r_rpm);

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
    if (!Robot_Motor_Init(PIN_I2C_SDA, PIN_I2C_SCL, 100000))
    {
        g_safety_state = STATE_FAULT;
        Serial.println("{\"error\":\"MKE_M18_INIT_FAILED\"}");
    }
    else
    {
        g_safety_state = STATE_DISARMED;
    }

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

void loop(void)
{
    static uint32_t last_sample_ms = 0;
    static uint32_t last_telemetry_ms = 0;

    /* 1. Kiểm tra an toàn ngay đầu vòng lặp */
    Check_Safety_Watchdog();

    /* Tác vụ 0: Xử lý lệnh từ Serial USB của ESP32 */
    Process_Serial_Commands();

    /* Kiểm tra an toàn sau khi nhận lệnh Serial */
    Check_Safety_Watchdog();

    /* Tác vụ Wi-Fi: Xử lý Web Server điều khiển từ điện thoại (Chỉ khi không ở chế độ BENCH) */
#if !BENCH_SERIAL_ONLY
    WiFiController_Update();
#endif

    /* Quét I2C một lần sau khi khởi động 1.5s (Chỉ quét khi DISARMED) */
    uint32_t current_ms = millis();
    if (!s_i2c_scanned && current_ms >= 1500)
    {
        s_i2c_scanned = true;
        if (g_safety_state != STATE_ARMED)
        {
            Scan_I2C_Bus();
        }
    }

    /* Kiểm tra an toàn trước khi vào vòng lặp PID cấp xung motor */
    Check_Safety_Watchdog();

    /* ----------------------------------------------------------------------
     * Tác vụ 1: Lấy mẫu Encoder & Tính toán PID mỗi 50ms (20Hz)
     * ---------------------------------------------------------------------- */
    if ((current_ms - last_sample_ms) >= ENCODER_SAMPLE_MS)
    {
        uint32_t dt_ms = current_ms - last_sample_ms;
        last_sample_ms = current_ms;
        float dt_sec = (float)dt_ms / 1000.0f;
        if (dt_sec <= 0.001f || dt_sec > 0.5f) dt_sec = ENCODER_SAMPLE_DT_SEC;

        /* Đọc delta xung và tính RPM cho cả 2 bánh xe */
        Encoder_Update(&g_enc_left);
        Encoder_Update(&g_enc_right);

        Encoder_CalculateRPM(&g_enc_left, dt_sec, COUNTS_PER_OUTPUT_REV);
        Encoder_CalculateRPM(&g_enc_right, dt_sec, COUNTS_PER_OUTPUT_REV);

        /* Cập nhật tọa độ Odometry Runge-Kutta bậc 2 từ tổng xung Encoder theo dt thực tế */
        Odometry_Update(&g_odometry, Encoder_GetTotalCount(&g_enc_left), Encoder_GetTotalCount(&g_enc_right), dt_sec);

        /* Điều khiển vòng kín PID nếu đang ở MODE_PID */
        if (g_control_mode == MODE_PID)
        {
            float out_l = PID_Compute(&g_pid_left, g_target_rpm_left, g_enc_left.rpm, dt_sec);
            float out_r = PID_Compute(&g_pid_right, g_target_rpm_right, g_enc_right.rpm, dt_sec);

            g_speed_left  = (int16_t)out_l;
            g_speed_right = (int16_t)out_r;

            /* Xuất lệnh qua cổng ghi an toàn có chốt khóa ARM */
            Safe_Motor_Write(g_speed_left, g_speed_right);
        }
    }

    /* ----------------------------------------------------------------------
     * Tác vụ 2: Xuất Telemetry JSON qua Serial mỗi 100ms (10Hz)
     * ---------------------------------------------------------------------- */
    if ((current_ms - last_telemetry_ms) >= TELEMETRY_INTERVAL_MS)
    {
        last_telemetry_ms += TELEMETRY_INTERVAL_MS;
        Print_Telemetry_JSON();
    }
}
