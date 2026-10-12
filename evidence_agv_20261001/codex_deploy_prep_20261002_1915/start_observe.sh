#!/usr/bin/env bash
# Initial live integration only. This invocation cannot ARM/drive/tune/start AUTO.
set -eo pipefail
cd /home/khangho/agv_codex_20261002_1915
test ! -e started_once
if fuser /dev/ttyUSB0 /dev/ttyUSB1 >/dev/null 2>&1; then
    echo 'PORT_BUSY_NO_START'; exit 1
fi
if ss -H -ltn 'sport = :8080' | grep -q .; then
    echo 'HTTP_PORT_BUSY_NO_START'; exit 1
fi
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
python3 -B -c 'import agv_unified_brain,serial,rclpy,tf2_ros'
date -Is > started_once
mkdir runtime
nohup ros2 run tf2_ros static_transform_publisher --x 0 --y 0 --z 0 \
    --yaw 0 --pitch 0 --roll 0 --frame-id base_footprint --child-frame-id laser \
    > runtime/static_tf.log 2>&1 < /dev/null &
echo $! > runtime/static_tf.pid
nohup ros2 launch sllidar_ros2 sllidar_c1_launch.py serial_port:=/dev/ttyUSB1 \
    serial_baudrate:=460800 frame_id:=laser inverted:=false angle_compensate:=true \
    > runtime/lidar.log 2>&1 < /dev/null &
echo $! > runtime/lidar.pid
sleep 2
nohup ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:=/home/khangho/agv_codex_20261002_1915/slam_observe.yaml \
    use_sim_time:=false > runtime/slam.log 2>&1 < /dev/null &
echo $! > runtime/slam.pid
sleep 1
AGV_BODY_RADIUS_M=0.20 nohup python3 -B -u agv_unified_brain.py --observe-only \
    > runtime/brain.log 2>&1 < /dev/null &
echo $! > runtime/brain.pid
echo 'OBSERVE_ONLY_STARTED; check HTTP health and live data, no motion approval'
