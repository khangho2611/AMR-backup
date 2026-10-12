# Initial deployment and live observation, 02/10/2026

Human requested deployment/web test and confirmed current clear area and person
at the power switch in this turn. Codex owns this operation directly; no bot.

Action: `bash /home/khangho/agv_codex_20261002_1915/start_observe.sh` exactly once.
Brain args: `python3 -B -u agv_unified_brain.py --observe-only`, USB0/115200,
exclusive OPEN + shared collector flock, RTS/DTR low configured before OPEN,
bounded read/write, same-owner reader and continuous 20ms Pi watchdog.
HTTP binds before hardware OPEN. No ARM/M/V/PID/AUTO START routes permitted;
STOP remains available. No flash, gain/PWM changes, auto retry/reset/reARM.

Before start: both UART ports and HTTP8080 unowned, source hashes match the
tested bundle, real Pi ROS imports succeed without constructing/opening UART.
Frozen firmware/supervisor are not modified. Source hash is not binary proof.

CAD opened read-only via SolidWorks COM: Assem3 bbox X[-.16,.10],
Y[-.1035,.1035]; wheel axle midpoint and LiDAR XY both zero.
Human confirmed the current frame/LiDAR match this layout, and beam0 faces the
front. Word measured circumference .23m and track .1875m take priority over
CAD65mm wheels/180mm track. Maximum CAD corner radius from axle is .19057m;
round up to .20m for the confirmed frame. This is a conservative configuration
derived from human-confirmed geometry, not a new physical measurement.
TF base_footprint->laser X/Y/yaw0: human-confirmed planar mounting. Z0 is a
coplanar 2D scan representation, not a claim of physical LiDAR height.
SLAM base_frame=base_footprint; map_update_interval1s; no fake static odom.

Review: APPROVED_FOR_INITIAL_OBSERVE_ONLY_START under this turn's explicit
request/current conditions; NOT_APPROVED_FOR_MOTION. 38 Python tests + prior
JS suite cover source paths, not full ROS/physical stopping/coverage acceptance.
After start inspect actual HTTP telemetry/map, logs, process owners, startup
FSM, fresh DISARMED target/PWM/RPM/vw zero and STOP outcome. Missing boot/diag
must stay latched; no fallback accepting historical D0 or automatic retries.
If any unexpected motion or unconfirmed STOP: human cuts power.

Rollback: old Pi main and HTML preserved in backup_previous. This isolated
bundle does not overwrite the old launcher or flash. Stop only this bundle's
recorded processes after confirmed STOP; no blanket pkill/kill -9.
