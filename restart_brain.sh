#!/usr/bin/env bash
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
cd /home/khangho/agv_codex_reader_20261003_0652
pkill -f agv_unified_brain.py || true
sleep 1
AGV_WALL_MARGIN_M=0.00 AGV_AUTO_SPEED_RPM=40.0 AGV_BODY_RADIUS_M=0.20 AGV_BODY_BOUNDS_M=-0.16,-0.12,0.10,0.12 AGV_PROGRESS_TIMEOUT_S=3.5 AGV_AUTO_TURN_RPM=35.0 nohup python3 -B -u agv_unified_brain.py --operator-control > runtime/brain.log 2>&1 < /dev/null &
echo $! > runtime/brain.pid
sleep 2
ps aux | grep agv_unified_brain | grep -v grep
