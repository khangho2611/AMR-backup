#include "robot_motor.h"

void Robot_Motor_Init(I2C_HandleTypeDef *hi2c)
{
    MKE_M18_Init(hi2c);
}

void Robot_SetLeftMotor(int16_t speed)
{
    /* Bánh Trái (Encoder TIM2 PA0/PA1) nối với ngõ ra Motor B của MKE-M18 */
    int16_t actual_speed = (int16_t)(speed * LEFT_MOTOR_DIRECTION);
    MKE_M18_SetMotorB(actual_speed);
}

void Robot_SetRightMotor(int16_t speed)
{
    /* Bánh Phải (Encoder TIM3 PA6/PA7) nối với ngõ ra Motor A của MKE-M18 */
    int16_t actual_speed = (int16_t)(speed * RIGHT_MOTOR_DIRECTION);
    MKE_M18_SetMotorA(actual_speed);
}

void Robot_Stop(void)
{
    MKE_M18_StopAll();
}
