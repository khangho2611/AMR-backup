#!/usr/bin/env bash
set -eo pipefail
cd /home/khangho/agv_codex_reader_20261003_0652

echo "DỌN SẠCH CÁC TIẾN TRÌNH ROS 2 CŨ..."
pkill -9 -f "slam_toolbox" || true
pkill -9 -f "static_transform_publisher" || true
pkill -9 -f "sllidar" || true
pkill -9 -f "agv_unified_brain" || true
sleep 1

if fuser /dev/ttyUSB0 /dev/ttyUSB1 >/dev/null 2>&1; then 
    fuser -k /dev/ttyUSB0 /dev/ttyUSB1 || true
    sleep 1
fi
if ss -H -ltn "sport = :8080" | grep -q .; then 
    fuser -k 8080/tcp || true
    sleep 1
fi

rm -rf runtime
mkdir -p runtime logs

source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash

# 1. Chạy đúng 1 tiến trình static TF
nohup ros2 run tf2_ros static_transform_publisher --x 0 --y 0 --z 0 \
    --yaw 0 --pitch 0 --roll 0 --frame-id base_footprint --child-frame-id laser \
    >runtime/static_tf.log 2>&1 < /dev/null &
echo $! > runtime/static_tf.pid

# 2. Chạy đúng 1 tiến trình RPLIDAR C1
nohup ros2 launch sllidar_ros2 sllidar_c1_launch.py serial_port:=/dev/ttyUSB1 \
    serial_baudrate:=460800 frame_id:=laser inverted:=false angle_compensate:=true \
    >runtime/lidar.log 2>&1 < /dev/null &
echo $! > runtime/lidar.pid
sleep 2

# 3. Chạy đúng 1 tiến trình SLAM Toolbox
nohup ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:=/home/khangho/agv_codex_reader_20261003_0652/slam_scan_fix.yaml \
    use_sim_time:=false >runtime/slam.log 2>&1 < /dev/null &
echo $! > runtime/slam.pid
sleep 2

# 4. Chạy agv_unified_brain với Footprint chuẩn theo CAD: đuôi -16cm, mũi +10cm, rộng +-11cm
AGV_BODY_RADIUS_M=0.20 AGV_BODY_BOUNDS_M=-0.16,-0.11,0.10,0.11 nohup python3 -B -u agv_unified_brain.py --operator-control \
    >runtime/brain.log 2>&1 < /dev/null &
echo $! > runtime/brain.pid

echo "ALL_SERVICES_STARTED_CLEANLY"
