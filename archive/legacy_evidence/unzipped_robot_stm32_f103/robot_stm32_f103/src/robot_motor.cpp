#include "robot_motor.h"
#include "mke_m18.h"

static int8_t s_left_dir  = LEFT_MOTOR_DIRECTION;
static int8_t s_right_dir = RIGHT_MOTOR_DIRECTION;

bool Robot_Motor_Init(int sda_pin, int scl_pin, uint32_t frequency)
{
    return MKE_M18_Init(sda_pin, scl_pin, frequency);
}

void Robot_SetMotorDirections(int8_t left_dir, int8_t right_dir)
{
    s_left_dir  = (left_dir >= 0) ? 1 : -1;
    s_right_dir = (right_dir >= 0) ? 1 : -1;
}

int8_t Robot_GetLeftMotorDirection(void)
{
    return s_left_dir;
}

int8_t Robot_GetRightMotorDirection(void)
{
    return s_right_dir;
}

void Robot_SetLeftMotor(int16_t speed)
{
    /* Bánh Trái (Encoder GPIO 18/19) là MOTOR A trên MKE-M18 */
    int16_t actual_speed = (int16_t)(speed * s_left_dir);
    MKE_M18_SetMotorA(actual_speed);
}

void Robot_SetRightMotor(int16_t speed)
{
    /* Bánh Phải (Encoder GPIO 25/26) là MOTOR B trên MKE-M18 */
    int16_t actual_speed = (int16_t)(speed * s_right_dir);
    MKE_M18_SetMotorB(actual_speed);
}

void Robot_Stop(void)
{
    MKE_M18_StopAll();
}
