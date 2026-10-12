# 140 RPM — candidate offline, NOT DEPLOYED

User explicitly requested normal/faster operation up to 140 RPM on 03/10/2026.
This directory is an isolated proposed bundle. Neither the live Pi controller
nor the physical MCU was modified or flashed while preparing it.

## Why the existing stack cannot command 140 RPM

- Original firmware source SHA256
  `52ccb6c7646a075087e274b09e8e228ef2364cf000623bb66377b2181bdfe231`
  clips V to .15 m/s, S/V wheel targets to 65 RPM, M to 120 PWM.
- Original host clips V to .20 m/s and the dashboard sends M140 for forward.
  M140 is NOT a 140-RPM target. Source identity is not current flash proof.
- The current live AUTO is separately in HOLD with reachable frontiers but no
  selected goal. Raising a target limit alone cannot remove that condition.

## Candidate changes

- MCU target ceiling140 RPM for both S and inverse-kinematics V; saturation
  scales both wheel targets by the same ratio, preserving curvature.
- MCU V ceiling derives from its existing .0366-m wheel radius. No pin, encoder,
  PID gain, PWM ceiling, ARM/STOP or300ms watchdog changes.
- Host V ceiling .536m/s (rounding down to three protocol decimals); reduces
  linear velocity while turning to keep the outer wheel at or below140RPM.
- Dashboard forward/back use V±.536, not M±140. Existing turning buttons are
  unchanged; manual remains manually controlled, without AUTO geometry gates.
- AUTO straight-path lookahead .60m; swept geometry horizon1s above.20m/s,
  retaining body+.15m clearance and all map/scan checks. This is NOT measured
  braking distance, and does not prove a stopping envelope at140RPM.
- Existing firmware effective track.1925m is retained for consistent limiting.
  Word physical track.1875m remains the accepted physical measurement; the
  provenance of the effective calibration must be resolved before acceptance.

## Checks completed

- Native C++ executes the actual shared MCU wheel-limit header: straight,
  reversing and asymmetric saturation, zero and velocity conversion.
- Five Python candidate tests: velocity conversion/wheel bounds, invalid
  numbers, extended occupied-cell sweep, actual session gates and STOP, actual
  navigation follow command. Session/ROS fixtures are offline, not hardware.
- Full100 Python regression cases pass/18.758s. The two old cruise expectations
  were deliberately updated for the new requested speed (.536/.537 boundary).
-14 JavaScript groups pass, including actual W/S key handlers issuing V±.536.
- PlatformIO ESP32 build succeeds/10.74s. Firmware binary SHA256:
  `36969447c8f43d3816277b9e5d98fddc99d5e61561cd01ab4248b50a644b32c1`.
- Logs, retained initial test failure, source hashes and diffs in `tests/`.
  An initial fixture failure had MAN ownership explicitly disabling AUTO; the
  component fixture now explicitly grants AUTO ownership before its assertion.

## Still required before commissioning this faster profile

1. Resolve the actual live HOLD cause using rejected-command/geometry evidence;
   do not remove collision checks or declare the map complete to make it move.
2. Review PID tracking/overshoot and establish a bounded acceleration/stopping
   envelope. A new ceiling, a longer scan horizon and passing mocks are not
   proof that140RPM is controllable or stops inside the available free space.
3. Prepare an exact DISARMED controller-retirement/MCU backup+flash/rollback
   plan, with one serial owner. Verify boot, startup schema and target readback
   of the new image before motion. Do not install just the web/host half.
4. Use an observed incremental speed/tracking/STOP check with the operator at
   power, rather than jumping the running vehicle directly to140RPM. Record
   actual RPM, ground displacement and stopping distance; no blind PID/PWM or
   telemetry-timeout changes. User already authorized the requested speed; do
   not ask again for generic permission. Current field conditions still matter.
5. Full-room exploration/map/home position AND heading remain unaccepted.

The live system remains `/home/khangho/agv_codex_reader_20261003_0652`,
PID1541 on boot`9c3a6c5d-3059-4f78-b482-fc4ec64f7612` at the last observation.
Read fresh status before any interaction; these are not permanent identifiers.

Observed live HOLD rejection: V0.200/0.203 -> ARC_NOT_VALIDATED with fresh D0/scan; see tests/live_hold_reasons.json. Geometry vs epoch/budget cause is not yet isolated.
