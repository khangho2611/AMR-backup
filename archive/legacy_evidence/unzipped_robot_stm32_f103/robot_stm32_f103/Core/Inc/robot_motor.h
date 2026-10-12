#ifndef INC_ROBOT_MOTOR_H_
#define INC_ROBOT_MOTOR_H_

#include "mke_m18.h"

/*
 * CẤU HÌNH HƯỚNG QUAY ĐỘNG CƠ TRÁI / PHẢI:
 * Giá trị mặc định là 1.
 * Nếu động cơ bị quay ngược chiều tiến mong muốn, đổi thành -1.
 */
#define LEFT_MOTOR_DIRECTION    ( 1)
#define RIGHT_MOTOR_DIRECTION   ( 1)

void Robot_Motor_Init(I2C_HandleTypeDef *hi2c);
void Robot_SetLeftMotor(int16_t speed);
void Robot_SetRightMotor(int16_t speed);
void Robot_Stop(void);

#endif /* INC_ROBOT_MOTOR_H_ */
