#ifndef AGV_SPEED_LIMITS_H
#define AGV_SPEED_LIMITS_H
#include <math.h>
#include "odometry.h"

/* Candidate only. These are target limits, not measured stopping capability. */
#define AGV_MAX_WHEEL_RPM 140.0f
#define AGV_MAX_LINEAR_MPS (AGV_MAX_WHEEL_RPM * 2.0f * 3.14159265f * ROBOT_WHEEL_RADIUS / 60.0f)

/* Scale both wheels together so saturation preserves curvature. */
static inline void AGV_LimitWheelRPM(float *left, float *right) {
    float peak = fmaxf(fabsf(*left), fabsf(*right));
    if (peak > AGV_MAX_WHEEL_RPM) {
        float scale = AGV_MAX_WHEEL_RPM / peak;
        *left *= scale;
        *right *= scale;
    }
}
#endif
