"""Regression for read-only raw LiDAR angle normalisation and missing data."""

import math

from pi_ai_shadow_live import rasterize_scan, summarize


def test_scan_angle_clockwise_and_duplicate_choose_nearest():
    scan, covered, valid = rasterize_scan([3., 1.2, 2.],
                                           math.radians(1), -math.radians(1),
                                           .1, 16.)
    assert covered == valid == 3
    assert scan[1] == 3.
    assert scan[0] == 1.2
    assert scan[359] == 2.
    assert scan[180] == .12  # unknown must never be treated as clear


def test_invalid_rays_default_to_blocked_and_positive_inf_means_no_hit():
    scan, covered, valid = rasterize_scan([math.nan, -math.inf, math.inf, -.1],
                                           0., math.radians(1), .1, 16.)
    assert (covered, valid) == (1, 1)
    assert scan[0] == .12
    assert scan[2] == 12.


def test_360_uniform_complete_scan_and_summary():
    scan, covered, valid = rasterize_scan([2.] * 360,
                                           0., math.radians(1), .1, 16.)
    assert covered == valid == 360
    assert min(scan) == 2.
    summary = summarize([dict(event='scan', min_obstacle_m=2.0,
                              observed_bins=covered, ai1_latency_ms=2.5,
                              ai1_filtered=[0., 0.], pose_source='synthetic_stationary_goal_2m')])
    assert summary['ai1_p99_ms'] == 2.5
    assert summary['ai1_zero_commands'] == 1


def test_invalid_scan_geometry_rejected():
    try:
        rasterize_scan([2.], float('nan'), .01, .1, 16.)
    except ValueError:
        pass
    else:
        raise AssertionError('Nonfinite scan geometry was accepted')
