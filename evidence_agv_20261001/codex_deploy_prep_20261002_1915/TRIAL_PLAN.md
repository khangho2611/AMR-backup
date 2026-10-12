# Single operator AUTO test, 02/10/2026 Asia/Bangkok

Human requested deployment and web testing; confirmed clear area/person at
power switch, confirmed current frame/LiDAR match the CAD layout, and replied
"rồi" after Codex confirmed the controller stopped and asked for placement
at least 50cm from nearby obstacles. No Telegram delegation.

Action: run start_trial.sh once in isolated /home/khangho/agv_codex_20261002_1915.
Arguments: AGV_BODY_RADIUS_M=.20 python3 -B -u agv_unified_brain.py
--motion-window-s 15; USB0/115200, shared flock + exclusive port, read .05s,
write .2s; no auto ARM, no firmware flash/PID/gain/PWM edits.

Checks: exact tested source SHA manifest, boot305c4d73-736c-4871-968d-a84b997be21e,
USB0 free and HTTP8080 unbound. Existing healthy LiDAR/static planar TF remain;
new SLAM process starts a fresh map after physical repositioning. Known-free
body radius .20 plus margin .15; no shrink or unsafe straight fallback.

Review APPROVED_FOR_SINGLE_OPERATOR_TRIAL_START under the explicit deployment
and test request/current replies. Codex launches DISARMED and checks live
ordered boot/scan/found/postdiag10s80, exact-zero fresh D0, map/TF/scan and
planner origin clearance. Operator clicks ARM, then AUTO; ARM needs full-byte
write plus explicit matching MCU ACK and fresh ARMED D0. Window starts at ARM
confirmation and cannot be extended. V<=.04m/s, angular limit .35rad/s,
RPM guard35; MAN and PID disabled; first full ARM consumes the one trial.

Continuous 20ms Pi watchdog checks caller/sensor freshness and hard window.
STOP/FAULT never silently reARMs; timeout and write failures remain visible.
Emergency STOP is available even before ARM. If unexpected motion or STOP
unconfirmed while moving, operator cuts power. 45 Python tests and eight JS
groups pass offline; this is not physical stopping/encoder/whole-room proof.

Evidence verification_20261002_194443 includes stable source hashes and exits.
Original files are preserved in backup_previous; isolated bundle does not
replace the old launcher. No automatically repeated trial after any failure.
Rollback requires confirmed STOP and retirement of this recorded controller;
do not start the original unsafe launcher as a fallback.

## Preparation replaced before any ARM, 19:54

The first test preparation had trial_used=false, fresh DISARMED exact-zero
telemetry, and no ARM. It was retired after a real confirmed STOP; SIGTERM now
closes the new controller and releases USB0 normally. Old SLAM was retired.
New action start_scan_fix_preparation.sh replaces preparation, not a motion
retry. Original invocation markers/logs remain immutable. New logs go to
runtime_scan_fix; actual first ARM still consumes one 15s trial.

The latest tested source manifest scan_fix_sources.sha256 matches evidence
verification_20261002_195206. Raw /scan stays unchanged for safety. Fresh valid
scans publish /scan_slam with only explicit positive infinity encoded below
sensor max16m but above SLAM threshold12m (15.99m). Karto ignores infinity;
finite censored rays trace free space without adding occupied endpoints.
NaN, negative infinity, invalid rays and actual obstacle distances are not
made free. New SLAM config consumes /scan_slam, threshold12m unchanged.
Source: https://raw.githubusercontent.com/SteveMacenski/slam_toolbox/jazzy/lib/karto_sdk/include/karto_sdk/Karto.h
OccupancyGrid::AddScan skips >=maxRange/NaN and sets no-hit endpoints invalid
above rangeThreshold. This explains near-origin UNKNOWN wedges despite raw
range coverage; do not shrink footprint/margin or clear unknown map pixels.
Review APPROVED_FOR_REPLACEMENT_PREPARATION before first ARM under the active
human deploy/test request, not permission for additional motion or reARM.
