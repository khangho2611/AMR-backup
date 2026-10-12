#!/usr/bin/env bash
set -eo pipefail
cd /home/khangho/agv_codex_document_20261003_174108
test ! -e started_once
test "$(cat /proc/sys/kernel/random/boot_id)" = 4269f3dd-12c6-4330-9753-7cafc283ba5d
if fuser /dev/ttyUSB0 >/dev/null 2>&1; then echo MCU_BUSY; exit 1; fi
if ss -H -ltn 'sport = :8080' | grep -q .; then echo HTTP_BUSY; exit 1; fi
sha256sum -c sources.sha256
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
python3 -B -c 'import agv_unified_brain, serial, rclpy, tf2_ros'
mkdir runtime
date -Is > started_once
AGV_BODY_RADIUS_M=0.20 AGV_BODY_BOUNDS_M=-0.16,-0.12,0.10,0.12 nohup python3 -B -u agv_unified_brain.py --operator-control >runtime/brain.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/brain.pid
printf 'DISARMED_START_PID=%s\n' "$(cat runtime/brain.pid)"
