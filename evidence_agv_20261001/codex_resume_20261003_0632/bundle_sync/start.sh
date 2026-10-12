#!/usr/bin/env bash
set -eo pipefail
cd /home/khangho/agv_codex_sync_20261003_0640
test ! -e started_once
test "$(cat /proc/sys/kernel/random/boot_id)" = b61a8008-2552-4fce-b5dc-2985b6d6177a
test "$(readlink -f /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0)" = /dev/ttyUSB0
if fuser /dev/ttyUSB0 >/dev/null 2>&1; then echo PORT_BUSY_NO_START; exit 1; fi
if ss -H -ltn 'sport = :8080' | grep -q .; then echo HTTP_BUSY_NO_START; exit 1; fi
test -d /proc/1692
test -d /proc/1714
sha256sum -c sources.sha256
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
python3 -B -c 'import agv_unified_brain,serial,rclpy,tf2_ros'
mkdir runtime
date -Is > started_once
AGV_BODY_RADIUS_M=0.20 AGV_BODY_BOUNDS_M=-0.16,-0.12,0.10,0.12 \
    nohup python3 -B -u agv_unified_brain.py --operator-control \
    >runtime/brain.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/brain.pid
printf 'MANUAL_TF_STARTED_DISARMED; PID=%s\n' "$(cat runtime/brain.pid)"
