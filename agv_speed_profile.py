"""Wheel RPM policy shared by navigation and the final UART writer."""
import math

NORMAL_RPM = 65.0
SLOW_RPM = 40.0
ARC_INNER_MIN_RPM = 20.0
WHEEL_RADIUS_M = .0366
HALF_TRACK_M = .096
MPS_PER_RPM = 2 * math.pi * WHEEL_RADIUS_M / 60


def rpm_to_speed(rpm):
    return rpm * MPS_PER_RPM


def rpm_to_turn(rpm):
    return rpm_to_speed(rpm) / HALF_TRACK_M


def twist_to_wheels(v, w):
    return ((v - w * HALF_TRACK_M) / MPS_PER_RPM,
            (v + w * HALF_TRACK_M) / MPS_PER_RPM)


def wheels_to_twist(left, right):
    return ((left + right) * MPS_PER_RPM / 2,
            (right - left) * MPS_PER_RPM / (2 * HALF_TRACK_M))


def running_wheels(left, right, normal_rpm=NORMAL_RPM, slow=False):
    """Keep direction and differential steering, with no weak nonzero target.

    Zero remains zero. Straight cruise reaches 65; crawl/recovery reaches 40.
    Turning can use unequal wheel targets within [40, 65]. The resulting
    twist must be checked against geometry *after* this conversion.
    """
    if not all(math.isfinite(x) for x in (left, right, normal_rpm)):
        raise ValueError('Nonfinite wheel target')
    if not (10.0 <= normal_rpm <= 100.0):
        raise ValueError('Choose between 10 and 100 RPM')
    peak=max(abs(left),abs(right))
    if peak < 1e-8:
        return 0.,0.
    if normal_rpm < SLOW_RPM:
        ceiling = normal_rpm
    else:
        ceiling=SLOW_RPM if slow or peak <= SLOW_RPM + 1e-6 else normal_rpm
    # Flooring two unequal, opposite wheel speeds to +/-40 used to erase
    # translation entirely. A requested forward/reverse arc must remain an
    # arc: pivot about the inner wheel rather than turning both wheels in
    # opposite directions. The same pivot preserves steering at crawl speed.
    translating = abs(left + right) > 1e-8
    if not translating:
        return round(math.copysign(ceiling, left), 3), round(math.copysign(ceiling, right), 3)
    if translating and left * right < 0:
        if abs(left) > abs(right):
            return math.copysign(ceiling, left), 0.
        return 0., math.copysign(ceiling, right)
    if min(abs(left), abs(right)) < 1e-8:
        if abs(left) > abs(right):
            return math.copysign(ceiling, left), 0.
        return 0., math.copysign(ceiling, right)
    if translating and ceiling < SLOW_RPM:
        if abs(left - right) < 0.5:
            return round(math.copysign(ceiling, left), 3), round(math.copysign(ceiling, right), 3)
        min_inner = max(10.0, ceiling * 0.5)
        def low_wheel(value):
            scaled = abs(value) * ceiling / peak
            mag = max(min_inner, min(ceiling, scaled))
            return round(math.copysign(mag, value), 3)
        return low_wheel(left), low_wheel(right)
    if translating and ceiling == SLOW_RPM:
        if abs(left - right) < 0.5:
            return round(math.copysign(ceiling, left), 3), round(math.copysign(ceiling, right), 3)
        def arc_wheel(value):
            scaled = abs(value) * ceiling / peak
            mag = max(ARC_INNER_MIN_RPM, min(ceiling, scaled))
            return round(math.copysign(mag, value), 3)
        return arc_wheel(left), arc_wheel(right)
    if translating and ceiling >= NORMAL_RPM and abs(left - right) < 0.5:
        return round(math.copysign(ceiling, left), 3), round(math.copysign(ceiling, right), 3)
    def wheel(value):
        if abs(value) < 1e-8:
            return 0.
        return round(math.copysign(max(SLOW_RPM, min(ceiling, abs(value) * ceiling / peak)), value), 3)
    return wheel(left), wheel(right)
