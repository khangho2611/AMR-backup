"""Offline 140-RPM candidate; geometry matches the accompanying firmware.

The .1925 effective track is retained from that firmware, not a new measurement
or a replacement for the Word's .1875 physical track. Calibration remains open.
"""
import math

MAX_WHEEL_RPM = 140.
WHEEL_RADIUS_M = .0366
FIRMWARE_EFFECTIVE_TRACK_M = .1925
# Round down for the three-decimal V protocol so the target stays below 140.
MAX_LINEAR_MPS = .536
MAX_ANGULAR_RAD_S = .35

def limited_twist(v, w):
    if not all(type(x) in (int,float) and math.isfinite(x) for x in (v,w)):
        raise ValueError('Finite twist required')
    w=max(-MAX_ANGULAR_RAD_S,min(MAX_ANGULAR_RAD_S,w))
    wheel_mps=MAX_WHEEL_RPM*2*math.pi*WHEEL_RADIUS_M/60
    linear_cap=min(MAX_LINEAR_MPS,wheel_mps-abs(w)*FIRMWARE_EFFECTIVE_TRACK_M/2)
    # Floor the magnitude to the command precision; rounding up can overshoot.
    linear_cap=math.floor(linear_cap*1000)/1000
    return max(-linear_cap,min(linear_cap,v)),w
