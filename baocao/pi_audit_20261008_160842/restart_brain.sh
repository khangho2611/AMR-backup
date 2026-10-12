#!/usr/bin/env bash
cd /home/khangho/agv_codex_reader_20261003_0652
pkill -f "agv_unified_brain.py" 2>/dev/null || true
fuser -k 8080/tcp 2>/dev/null || true
fuser -k /dev/ttyUSB0 2>/dev/null || true
sleep 2

source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash

mkdir -p runtime
AGV_BODY_RADIUS_M=0.20 AGV_BODY_BOUNDS_M=-0.16,-0.12,0.10,0.12 AGV_SCAN_MAX_AGE_S=1.5 AGV_PROGRESS_TIMEOUT_S=3.5 nohup python3 -B -u agv_unified_brain.py --operator-control >runtime/brain.log 2>&1 < /dev/null &
echo $! > runtime/brain.pid
sleep 2
echo "Brain started with PID: $(cat runtime/brain.pid)"
ps aux | grep agv_unified_brain | grep -v grep
