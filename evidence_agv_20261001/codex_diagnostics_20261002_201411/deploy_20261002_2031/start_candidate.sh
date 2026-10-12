#!/usr/bin/env bash
set -eo pipefail
cd /home/khangho/agv_codex_diag_20261002_201411
source /opt/ros/jazzy/setup.bash
python3 -B -c 'import agv_unified_brain, serial, rclpy, tf2_ros'
test ! -e runtime_diagnostic/brain.pid
AGV_BODY_RADIUS_M=0.20 nohup python3 -B -u agv_unified_brain.py --motion-window-s 15 > runtime_diagnostic/brain.log 2>&1 < /dev/null &
pid=$!
printf '%s\n' "$pid" > runtime_diagnostic/brain.pid
printf '%s\n' "$pid"
