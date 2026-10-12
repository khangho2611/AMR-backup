#!/usr/bin/env bash
set -eo pipefail
cd /home/khangho/agv_codex_20261002_1915
test ! -e trial_started_once
test ! -e runtime_trial
test "$(cat /proc/sys/kernel/random/boot_id)" = 305c4d73-736c-4871-968d-a84b997be21e
kill -0 2429
kill -0 2456
if fuser /dev/ttyUSB0 >/dev/null 2>&1; then echo PORT_BUSY_NO_START; exit 1; fi
if ss -H -ltn 'sport = :8080' | grep -q .; then echo HTTP_BUSY_NO_START; exit 1; fi
sha256sum -c trial_sources.sha256
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
python3 -B -c 'import agv_unified_brain,serial,rclpy,tf2_ros'
date -Is > trial_started_once
mkdir runtime_trial
nohup ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:=/home/khangho/agv_codex_20261002_1915/slam_observe.yaml \
    use_sim_time:=false > runtime_trial/slam.log 2>&1 < /dev/null &
echo $! > runtime_trial/slam.pid
sleep 1
AGV_BODY_RADIUS_M=0.20 nohup python3 -B -u agv_unified_brain.py --motion-window-s 15 \
    > runtime_trial/brain.log 2>&1 < /dev/null &
echo $! > runtime_trial/brain.pid
echo 'TRIAL_UI_STARTED_DISARMED; operator must explicitly ARM and start AUTO; no retry'
