#!/usr/bin/env bash
set -eo pipefail
cd /home/khangho/agv_codex_document_20261003_174108
test "$(cat /proc/sys/kernel/random/boot_id)" = 4269f3dd-12c6-4330-9753-7cafc283ba5d
test -f mapper_retired.json
test ! -e runtime/slam.pid
if pgrep -f '^/opt/ros/jazzy/lib/slam_toolbox/async_slam_toolbox_node ' >/dev/null; then echo SLAM_ALREADY_RUNNING; exit 1; fi
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
nohup ros2 launch slam_toolbox online_async_launch.py slam_params_file:=/home/khangho/agv_codex_document_20261003_174108/slam_scan_fix.yaml use_sim_time:=false >runtime/slam.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/slam.pid
cat runtime/slam.pid
