#include <iostream>
#include <cstdint>
#include <cassert>
#include <cmath>
#include <cstring>
#include <string>

// Giả lập môi trường phần cứng Arduino / Wire / Motor
static uint32_t s_mock_millis = 1000;
static uint32_t millis() { return s_mock_millis; }

enum RobotSafetyState_t {
    STATE_DISARMED = 0,
    STATE_ARMED    = 1,
    STATE_FAULT    = 2
};

static volatile RobotSafetyState_t g_safety_state = STATE_DISARMED;
static volatile uint32_t g_last_valid_cmd_ms = 0;
static const uint32_t CMD_TIMEOUT_MS = 300;

static volatile uint8_t s_i2c_fault_flag = 0;
static volatile uint8_t s_i2c_fault_latch = 0;

static uint8_t MKE_M18_GetFaultFlag(void) { return s_i2c_fault_latch; }
static void MKE_M18_ClearFaultFlag(void) { s_i2c_fault_flag = 0; s_i2c_fault_latch = 0; }

// Giả lập lỗi I2C có chủ đích
static bool s_inject_i2c_error_a = false;
static bool s_inject_i2c_error_b = false;

static int16_t s_last_motor_a_pwm = 0;
static int16_t s_last_motor_b_pwm = 0;

static bool Robot_SetLeftMotor(int16_t speed) {
    if (s_inject_i2c_error_a) {
        s_i2c_fault_flag = 1;
        s_i2c_fault_latch = 1;
        return false;
    }
    s_last_motor_a_pwm = speed;
    return true;
}

static bool Robot_SetRightMotor(int16_t speed) {
    if (s_inject_i2c_error_b) {
        s_i2c_fault_flag = 1;
        s_i2c_fault_latch = 1;
        return false;
    }
    s_last_motor_b_pwm = speed;
    return true;
}

static void Robot_Stop(void) {
    s_last_motor_a_pwm = 0;
    s_last_motor_b_pwm = 0;
}

static float g_target_rpm_left = 0.0f;
static float g_target_rpm_right = 0.0f;

static void Safe_Stop_And_Reset(void) {
    g_target_rpm_left = 0.0f;
    g_target_rpm_right = 0.0f;
    Robot_Stop();
}

static void Safe_Motor_Write(int16_t l_pwm, int16_t r_pwm) {
    if (g_safety_state != STATE_ARMED || MKE_M18_GetFaultFlag() != 0) {
        Safe_Stop_And_Reset();
        return;
    }

    Robot_SetLeftMotor(l_pwm);
    if (MKE_M18_GetFaultFlag() != 0) {
        g_safety_state = STATE_FAULT;
        Safe_Stop_And_Reset();
        return;
    }

    Robot_SetRightMotor(r_pwm);
    if (MKE_M18_GetFaultFlag() != 0) {
        g_safety_state = STATE_FAULT;
        Safe_Stop_And_Reset();
    }
}

static void Check_Safety_Watchdog(void) {
    uint32_t now_ms = millis();
    if (g_safety_state == STATE_ARMED) {
        if ((uint32_t)(now_ms - g_last_valid_cmd_ms) > CMD_TIMEOUT_MS) {
            g_safety_state = STATE_DISARMED;
            Safe_Stop_And_Reset();
        }
    }
    if (MKE_M18_GetFaultFlag() != 0) {
        g_safety_state = STATE_FAULT;
        Safe_Stop_And_Reset();
    }
}

static std::string Execute_Robot_Command(const char *cmd) {
    const char *p = cmd;
    while (*p == ' ' || *p == '\t') p++;

    if (strcasecmp(p, "STOP") == 0) {
        g_safety_state = STATE_DISARMED;
        Safe_Stop_And_Reset();
        return "ACK_STOP_DISARMED";
    }
    else if (strcasecmp(p, "ARM") == 0) {
        if (MKE_M18_GetFaultFlag() != 0) {
            return "ERROR_FAULT_ACTIVE_CANNOT_ARM";
        }
        g_safety_state = STATE_ARMED;
        g_last_valid_cmd_ms = millis();
        return "ACK_ARM";
    }
    else if (strcasecmp(p, "DISARM") == 0) {
        g_safety_state = STATE_DISARMED;
        Safe_Stop_And_Reset();
        return "ACK_DISARM";
    }
    else if (strcasecmp(p, "CLEAR_FAULT") == 0) {
        MKE_M18_ClearFaultFlag();
        if (MKE_M18_GetFaultFlag() == 0 && g_safety_state == STATE_FAULT) {
            g_safety_state = STATE_DISARMED;
        }
        return "ACK_CLEAR_FAULT";
    }
    else if ((*p == 'V' || *p == 'v') && (*(p + 1) == ' ' || *(p + 1) == '\t')) {
        if (g_safety_state != STATE_ARMED) {
            return "ERROR_DISARMED_REJECT_V";
        }
        float v = 0.0f, w = 0.0f;
        if (sscanf(p + 1, "%f %f", &v, &w) == 2) {
            if (!std::isfinite(v) || !std::isfinite(w)) return "ERROR_INVALID_FINITE_V";
            g_last_valid_cmd_ms = millis();
            return "ACK_V";
        }
    }
    return "UNKNOWN_CMD";
}

int main() {
    std::cout << "=== BẮT ĐẦU CHẠY C++ HARNESS KIỂM THỬ THỰC TẾ ===" << std::endl;

    // Test 1: Khởi động boot DISARMED, từ chối lệnh V
    assert(g_safety_state == STATE_DISARMED);
    assert(Execute_Robot_Command("V 0.10 0.00") == "ERROR_DISARMED_REJECT_V");
    std::cout << "[PASS 1/7] Boot DISARMED blocks V command" << std::endl;

    // Test 2: Chặn lệnh ARM sai cú pháp (ARMxxx, ARM_TEST, v.v.)
    assert(Execute_Robot_Command("ARMxxx") == "UNKNOWN_CMD");
    assert(Execute_Robot_Command("ARM") == "ACK_ARM");
    assert(g_safety_state == STATE_ARMED);
    std::cout << "[PASS 2/7] Token-strict parser blocks ARMxxx" << std::endl;

    // Test 3: Watchdog Timeout khi mất heartbeat (>300ms)
    s_mock_millis = 1000;
    g_last_valid_cmd_ms = 1000;
    s_mock_millis = 1350; // Quá 350ms
    Check_Safety_Watchdog();
    assert(g_safety_state == STATE_DISARMED);
    std::cout << "[PASS 3/7] Watchdog triggers DISARM after 350ms" << std::endl;

    // Test 4: Rollover millis() hoạt động chính xác không kích nhầm và vẫn bắt được timeout
    Execute_Robot_Command("ARM");
    assert(g_safety_state == STATE_ARMED);
    s_mock_millis = 4294967200U; // Gần ngưỡng tràn 32-bit
    g_last_valid_cmd_ms = s_mock_millis;
    s_mock_millis = 50U; // Đã rollover qua 0 (hiệu = 146ms <= 300ms)
    Check_Safety_Watchdog();
    assert(g_safety_state == STATE_ARMED); // Không được kích nhầm!
    s_mock_millis = 350U; // Hiệu = 446ms > 300ms
    Check_Safety_Watchdog();
    assert(g_safety_state == STATE_DISARMED); // Bắt đúng timeout sau rollover!
    std::cout << "[PASS 4/7] Watchdog uint32 subtraction handles millis() rollover perfectly" << std::endl;

    // Test 5: Safe_Motor_Write chặn motor khi DISARMED
    Safe_Motor_Write(50, 50);
    assert(s_last_motor_a_pwm == 0 && s_last_motor_b_pwm == 0);
    std::cout << "[PASS 5/7] Safe_Motor_Write enforces zero PWM in DISARMED state" << std::endl;

    // Test 6: Latch lỗi I2C Motor A -> Không cho ghi Motor B, Latch không bị xóa
    s_mock_millis = 2000;
    Execute_Robot_Command("ARM");
    assert(g_safety_state == STATE_ARMED);
    s_inject_i2c_error_a = true; // Gây lỗi tại Motor A
    Safe_Motor_Write(60, 60);
    assert(g_safety_state == STATE_FAULT);
    assert(MKE_M18_GetFaultFlag() == 1);
    assert(s_last_motor_b_pwm == 0); // Motor B bị chặn ngay, không được ghi!
    s_inject_i2c_error_a = false;
    // Thử ghi tiếp khi đang FAULT
    Safe_Motor_Write(60, 60);
    assert(s_last_motor_a_pwm == 0 && s_last_motor_b_pwm == 0);
    assert(MKE_M18_GetFaultFlag() == 1); // Cờ lỗi latch vẫn giữ nguyên!
    // ARM bị từ chối khi đang FAULT
    assert(Execute_Robot_Command("ARM") == "ERROR_FAULT_ACTIVE_CANNOT_ARM");
    // Xóa lỗi bằng lệnh tường minh
    assert(Execute_Robot_Command("CLEAR_FAULT") == "ACK_CLEAR_FAULT");
    assert(g_safety_state == STATE_DISARMED);
    std::cout << "[PASS 6/7] I2C Latching Fault: Motor A fail halts write to Motor B and prevents re-arming" << std::endl;

    // Test 7: Lệnh V với NaN/Inf bị từ chối
    Execute_Robot_Command("ARM");
    assert(g_safety_state == STATE_ARMED);
    assert(Execute_Robot_Command("V nan 0.0") == "ERROR_INVALID_FINITE_V");
    assert(Execute_Robot_Command("V 0.10 inf") == "ERROR_INVALID_FINITE_V");
    std::cout << "[PASS 7/7] Non-finite NaN/Inf velocities rejected strictly" << std::endl;

    std::cout << "=== HOÀN TẤT: 7/7 TEST HARNESS CHẠY THẬT ĐÃ PASS 100% ===" << std::endl;
    return 0;
}
