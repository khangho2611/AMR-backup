#ifndef ROBOT_MOTOR_H_
#define ROBOT_MOTOR_H_

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Bánh Trái (Motor A): quay thuận (1)
 * Bánh Phải (Motor B): đảo chiều (-1) để cùng tiến tới
 */
#define LEFT_MOTOR_DIRECTION    ( 1)
#define RIGHT_MOTOR_DIRECTION   (-1)

bool Robot_Motor_Init(int sda_pin, int scl_pin, uint32_t frequency);
void Robot_SetLeftMotor(int16_t speed);
void Robot_SetRightMotor(int16_t speed);
void Robot_SetMotorDirections(int8_t left_dir, int8_t right_dir);
int8_t Robot_GetLeftMotorDirection(void);
int8_t Robot_GetRightMotorDirection(void);
void Robot_Stop(void);

#ifdef __cplusplus
}
#endif

#endif /* ROBOT_MOTOR_H_ */
