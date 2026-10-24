"""Requested 65 RPM cruise / 40 RPM crawl, checked at the UART boundary."""
import math
import time

import pytest
from agv_command_session import CommandSession
from agv_navigation import twist_centres
from agv_speed_profile import twist_to_wheels, running_wheels, wheels_to_twist


class UART:
    is_open=True
    def __init__(self): self.writes=[]
    def write(self, data): self.writes.append(data); return len(data)


def ready():
    uart=UART()
    s=CommandSession(uart, strict_preflight=False)
    s.operator_rpm_profile=True
    s.armed=True; s.autonomy_allowed=True
    s.last_d0=s.scan_time=s.clock()
    s.latest={'safety':'ARMED'}
    s.scan_clear=s.rotation_clear=True
    s.arc_validator=lambda v,w:True
    s.escape_validator=lambda v,w:True
    return s,uart


def targets(uart):
    parts=uart.writes[-1].decode().split()
    assert parts[0]=='S', 'Use firmware RPM mode, bypassing old V turn clamp'
    return tuple(map(float,parts[1:]))


def test_normal_forward_reverse_and_turn_reach_65rpm():
    for cmd in ['V 0.249 0','V -0.249 0','V 0 2.595','M 200 200','S 65 65']:
        s,uart=ready()
        assert s.drive(cmd)[0]
        assert all(abs(r)==65 for r in targets(uart))


def test_old_low_speed_commands_and_cautious_mode_use_40rpm():
    for cmd in ['V 0.040 0','V 0 0.350','S 40 40']:
        s,uart=ready(); assert s.drive(cmd,autonomous=True)[0]
        assert all(abs(r)==40 for r in targets(uart))
    s,uart=ready();s.slow_speed_requested=lambda:True
    assert s.drive('V 0.249 0',autonomous=True)[0]
    assert targets(uart)==(40,40)


def test_turning_wheels_are_bounded_without_dead_rpm_zone():
    s,uart=ready()
    assert s.drive('V 0.200 0.700',autonomous=True)[0]
    left,right=targets(uart)
    assert 40 <= left < right <= 65


def test_geometry_checks_the_actual_boosted_twist_before_any_write():
    s,uart=ready();checked=[]
    s.arc_validator=lambda v,w:checked.append((v,w)) or False
    assert not s.drive('V 0.040 0',autonomous=True)[0]
    assert uart.writes==[]
    assert checked[0][0]==pytest.approx(40*2*math.pi*.0366/60)


def test_escape_checks_actual_40rpm_and_preserves_zero_and_stop_latch():
    s,uart=ready();checked=[]
    s.escape_validator=lambda v,w:checked.append((v,w)) or True
    assert s.drive('V -0.060 0',autonomous=True,escape=True)[0]
    assert targets(uart)==(-40,-40)
    assert checked[0][0]==pytest.approx(-40*2*math.pi*.0366/60)
    assert s.drive('V 0.000 0.000',autonomous=True)[0]
    assert targets(uart)==(0,0)
    s.latched=True
    before=list(uart.writes)
    assert not s.drive('V 0.249 0',autonomous=True)[0]
    assert uart.writes==before


def test_rpm_mode_cannot_bypass_limits_or_stale_scan():
    s,uart=ready()
    for cmd in ['S 66 65','S nan 65','S inf 0']:
        assert not s.drive(cmd,autonomous=True)[0]
    s.scan_time=s.clock()-1
    assert not s.drive('S 65 65',autonomous=True)[0]
    assert uart.writes==[]


def test_sampler_covers_actual_65rpm_spin():
    assert twist_centres(0.,65*2*math.pi*.0366/(60*.096)) is not None
    assert twist_centres(0.,2.7) is None


@pytest.mark.parametrize('v,w',[(.05,.8),(.05,-.8),(-.06,.9),(-.06,-.9)])
def test_crawl_arc_must_not_turn_into_a_stationary_spin(v,w):
    wheels=running_wheels(*twist_to_wheels(v,w),slow=True)
    actual_v,actual_w=wheels_to_twist(*wheels)
    assert actual_v*v > 0, 'Preserve requested forward/reverse motion'
    assert actual_w*w > 0, 'Preserve requested steering direction'
    assert all(r==0 or abs(r)==40 for r in wheels)


def test_cautious_same_direction_arc_preserves_steering():
    wheels=running_wheels(*twist_to_wheels(.12,.4),slow=True)
    v,w=wheels_to_twist(*wheels)
    assert v>0 and w>0


@pytest.mark.parametrize('w', [0.14, 0.24, 0.47, 0.66, -0.14, -0.24, -0.47, -0.66])
def test_slow_forward_steering_keeps_both_wheels_turning(w):
    v = 0.153
    left, right = running_wheels(*twist_to_wheels(v, w), slow=True)
    assert left != 0 and right != 0
    assert (left > 0 if v > 0 else left < 0)
    assert (right > 0 if v > 0 else right < 0)
    outer = right if w > 0 else left
    inner = left if w > 0 else right
    assert abs(outer) == 40.0
    assert 20.0 <= abs(inner) <= 40.0
    actual_v, actual_w = wheels_to_twist(left, right)
    assert actual_w * w > 0
    assert actual_v > 0


@pytest.mark.parametrize('v', [0.153, 0.249])
@pytest.mark.parametrize('slow', [False, True])
def test_straight_drive_never_zeroes_a_wheel(v, slow):
    left, right = running_wheels(*twist_to_wheels(v, 0.0), slow=slow)
    assert left != 0 and right != 0
    assert left == right


def test_no_alternating_single_wheel_pivot_during_forward_corrections():
    for tick in range(60):
        w = 0.2 if tick % 2 == 0 else -0.2
        left, right = running_wheels(*twist_to_wheels(0.153, w), slow=True)
        assert left != 0, f'tick {tick} left wheel was 0'
        assert right != 0, f'tick {tick} right wheel was 0'
