#include <cassert>
#include <cmath>
#include "agv_speed_limits.h"

int main() {
    float l=140, r=140;
    AGV_LimitWheelRPM(&l,&r);
    assert(l==140 && r==140);
    l=140; r=175;
    AGV_LimitWheelRPM(&l,&r);
    assert(fabs(l-112)<.001 && fabs(r-140)<.001);
    l=-175; r=175;
    AGV_LimitWheelRPM(&l,&r);
    assert(l==-140 && r==140);
    l=0; r=0; AGV_LimitWheelRPM(&l,&r);
    assert(l==0 && r==0);
    assert(AGV_MAX_LINEAR_MPS>.536 && AGV_MAX_LINEAR_MPS<.537);
    return 0;
}
