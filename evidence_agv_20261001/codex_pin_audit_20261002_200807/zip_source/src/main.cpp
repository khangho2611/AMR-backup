#include <Arduino.h>
#include <stdio.h>
#include <string.h>
#include "encoder.h"
#include "mke_m18.h"
#include "pid.h"
#include "robot_motor.h"
#include "wifi_controller.h"
#include "mpu6050.h"

/* Cấu hình Pinout ESP32-32D DevKitC */
#define PIN_I2C_SDA         21      /* I2C1 (Wire) cho Driver MKE-M18 */
#define PIN_I2C_SCL         22

#define PIN_MPU_SDA_P       16      /* I2C2 (Wire1) riêng cho Cảm biến MPU6050 */
#define PIN_MPU_SCL_P       17

#define PIN_ENC_LEFT_A      18      /* Encoder Bánh Trái */
#define PIN_ENC_LEFT_B      19

#define PIN_ENC_RIGHT_A     25      /* Encoder Bánh Phải */
#define PIN_ENC_RIGHT_B     26

#define TELEMETRY_INTERVAL_MS   100     /* Gửi JSON qua Serial mỗi 100ms (10Hz) */

/* Định nghĩa chế độ điều khiển */
#define MODE_OPEN_LOOP      0
#define MODE_PID            1

uint8_t g_control_mode = MODE_PID;

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
    Serial.println("{\"info\":\"Scanning I2C bus (Wire)...\"}");
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
        Serial.println("{\"error\":\"No I2C device found on Wire\"}");
    }
}

/* Xử lý lệnh dùng chung cho cả cổng Serial và Wi-Fi Web Controller */
void Execute_Robot_Command(const char *cmd)
{
    const char *p = cmd;
    while (*p == ' ' || *p == '\t') p++;

    /* Lệnh STOP (Dừng khẩn cấp, reset tích phân PID) */
    if (strncasecmp(p, "STOP", 4) == 0)
    {
        g_target_rpm_left  = 0.0f;
        g_target_rpm_right = 0.0f;
        PID_Reset(&g_pid_left);
        PID_Reset(&g_pid_right);

        g_speed_left  = 0;
        g_speed_right = 0;
        Robot_Stop();
        Serial.println("{\"ack\":\"STOP\"}");
    }
    /* Lệnh RESET_YAW (Đặt lại góc hướng xe về 0 độ) */
    else if (strncasecmp(p, "RESET_YAW", 9) == 0)
    {
        MPU6050_ResetYaw();
        Serial.println("{\"ack\":\"RESET_YAW\"}");
    }
    /* Lệnh SCAN (Quét lại bus I2C) */
    else if (strncasecmp(p, "SCAN", 4) == 0)
    {
        Scan_I2C_Bus();
    }
    /* Lệnh RESET (Reset bộ đếm xung encoder & góc yaw) */
    else if (strncasecmp(p, "RESET", 5) == 0)
    {
        Encoder_ResetCount(&g_enc_left);
        Encoder_ResetCount(&g_enc_right);
        MPU6050_ResetYaw();
        Serial.println("{\"ack\":\"RESET\"}");
    }
    /* Lệnh PING */
    else if (strncasecmp(p, "PING", 4) == 0)
    {
        Serial.println("{\"ack\":\"PONG\"}");
    }
    /* Lệnh TUNING <kp> <ki> <kd> [kf] */
    else if (strncasecmp(p, "TUNING", 6) == 0)
    {
        float kp = 0.0f, ki = 0.0f, kd = 0.0f, kf = g_kf;
        int n = sscanf(p + 6, "%f %f %f %f", &kp, &ki, &kd, &kf);
        if (n >= 3)
        {
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
        float l_rpm = 0.0f, r_rpm = 0.0f;
        if (sscanf(p + 1, "%f %f", &l_rpm, &r_rpm) == 2)
        {
            if (l_rpm > 280.0f) l_rpm = 280.0f;
            if (l_rpm < -280.0f) l_rpm = -280.0f;
            if (r_rpm > 280.0f) r_rpm = 280.0f;
            if (r_rpm < -280.0f) r_rpm = -280.0f;

            g_target_rpm_left  = l_rpm;
            g_target_rpm_right = r_rpm;
            g_control_mode     = MODE_PID;

            Serial.printf("{\"ack\":\"S %.1f %.1f\"}\r\n", g_target_rpm_left, g_target_rpm_right);
        }
    }
    /* Lệnh M <left_pwm> <right_pwm> (Chế độ thủ công PWM vòng hở) */
    else if ((*p == 'M' || *p == 'm') && (*(p + 1) == ' ' || *(p + 1) == '\t'))
    {
        int l_pwm = 0, r_pwm = 0;
        if (sscanf(p + 1, "%d %d", &l_pwm, &r_pwm) == 2)
        {
            if (l_pwm > 255) l_pwm = 255;
            if (l_pwm < -255) l_pwm = -255;
            if (r_pwm > 255) r_pwm = 255;
            if (r_pwm < -255) r_pwm = -255;

            g_control_mode = MODE_OPEN_LOOP;
            g_speed_left   = (int16_t)l_pwm;
            g_speed_right  = (int16_t)r_pwm;

            Robot_SetLeftMotor(g_speed_left);
            delayMicroseconds(800);
            Robot_SetRightMotor(g_speed_right);

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

/* Định dạng Telemetry JSON gửi lên Web Dashboard qua USB CDC (10Hz) kèm dữ liệu IMU */
static void Print_Telemetry_JSON(void)
{
    Serial.printf("{\"mode\":\"%s\",\"l_tgt\":%.1f,\"r_tgt\":%.1f,\"l_rpm\":%.2f,\"r_rpm\":%.2f,\"l_pwm\":%d,\"r_pwm\":%d,\"l_cnt\":%ld,\"r_cnt\":%ld,\"yaw\":%.2f,\"pitch\":%.2f,\"roll\":%.2f,\"gz\":%.2f}\r\n",
        (g_control_mode == MODE_PID) ? "PID" : "MAN",
        g_target_rpm_left,
        g_target_rpm_right,
        g_enc_left.rpm,
        g_enc_right.rpm,
        g_speed_left,
        g_speed_right,
        (long)Encoder_GetTotalCount(&g_enc_left),
        (long)Encoder_GetTotalCount(&g_enc_right),
        MPU6050_GetYaw(),
        MPU6050_GetPitch(),
        MPU6050_GetRoll(),
        MPU6050_GetGyroZ()
    );
}

void setup(void)
{
    Serial.begin(115200);
    delay(200);

    /* 1. An toàn: Khởi tạo I2C cho Driver MKE-M18 (Wire: GPIO 21, 22) và dừng động cơ */
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

    /* 5. Khởi tạo Cảm biến IMU GY-521 MPU6050 trên Wire1 (GPIO 16 SDA, GPIO 17 SCL) */
    MPU6050_Init(PIN_MPU_SDA_P, PIN_MPU_SCL_P);

    /* 6. Khởi tạo Wi-Fi SoftAP và Web Server điều khiển qua điện thoại */
    WiFiController_Init();

    Serial.println("{\"info\":\"ESP32 Robot Ready - Motors + Encoders + MPU6050(16,17) + WiFi\"}");
}

void loop(void)
{
    static uint32_t last_sample_ms = 0;
    static uint32_t last_telemetry_ms = 0;
    uint32_t current_ms = millis();

    /* Tác vụ 0: Xử lý lệnh từ Web Serial USB */
    Process_Serial_Commands();

    /* Tác vụ Wi-Fi: Xử lý Web Server điều khiển từ điện thoại */
    WiFiController_Update();

    /* Quét I2C MKE-M18 một lần sau khi khởi động 1.5s */
    if (!s_i2c_scanned && current_ms >= 1500)
    {
        s_i2c_scanned = true;
        Scan_I2C_Bus();
    }

    /* ----------------------------------------------------------------------
     * Tác vụ 1: Lấy mẫu Encoder, Đọc IMU & Tính toán PID mỗi 50ms (20Hz)
     * ---------------------------------------------------------------------- */
    if ((current_ms - last_sample_ms) >= ENCODER_SAMPLE_MS)
    {
        last_sample_ms += ENCODER_SAMPLE_MS;

        /* Cập nhật góc tư thế từ cảm biến MPU6050 */
        MPU6050_Update(ENCODER_SAMPLE_DT_SEC);

        /* Đọc delta xung và tính RPM cho cả 2 bánh xe */
        Encoder_Update(&g_enc_left);
        Encoder_Update(&g_enc_right);

        Encoder_CalculateRPM(&g_enc_left, ENCODER_SAMPLE_DT_SEC, COUNTS_PER_OUTPUT_REV);
        Encoder_CalculateRPM(&g_enc_right, ENCODER_SAMPLE_DT_SEC, COUNTS_PER_OUTPUT_REV);

        /* Điều khiển vòng kín PID nếu đang ở MODE_PID */
        if (g_control_mode == MODE_PID)
        {
            float out_l = PID_Compute(&g_pid_left, g_target_rpm_left, g_enc_left.rpm, ENCODER_SAMPLE_DT_SEC);
            float out_r = PID_Compute(&g_pid_right, g_target_rpm_right, g_enc_right.rpm, ENCODER_SAMPLE_DT_SEC);

            g_speed_left  = (int16_t)out_l;
            g_speed_right = (int16_t)out_r;

            Robot_SetLeftMotor(g_speed_left);
            delayMicroseconds(800);
            Robot_SetRightMotor(g_speed_right);
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
