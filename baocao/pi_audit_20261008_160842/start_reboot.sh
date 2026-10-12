#!/usr/bin/env bash
set -eo pipefail
cd /home/khangho/agv_codex_reader_20261003_0652
test ! -e started_once
test "$(cat /proc/sys/kernel/random/boot_id)" = 9c3a6c5d-3059-4f78-b482-fc4ec64f7612
test "$(readlink -f /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0)" = /dev/ttyUSB0
test "$(readlink -f /dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_76815f48566eef11bd64dec2c169b110-if00-port0)" = /dev/ttyUSB1
if fuser /dev/ttyUSB0 /dev/ttyUSB1 >/dev/null 2>&1; then echo PORT_BUSY_NO_START; exit 1; fi
if ss -H -ltn 'sport = :8080' | grep -q .; then echo HTTP_BUSY_NO_START; exit 1; fi
sha256sum -c sources.sha256
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
python3 -B -c 'import agv_unified_brain, serial, rclpy, tf2_ros'
mkdir runtime
date -Is > started_once
nohup ros2 run tf2_ros static_transform_publisher --x 0 --y 0 --z 0 \
    --yaw 0 --pitch 0 --roll 0 --frame-id base_footprint --child-frame-id laser \
    >runtime/static_tf.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/static_tf.pid
nohup ros2 launch sllidar_ros2 sllidar_c1_launch.py serial_port:=/dev/ttyUSB1 \
    serial_baudrate:=460800 frame_id:=laser inverted:=false angle_compensate:=true \
    >runtime/lidar.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/lidar.pid
sleep 2
nohup ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:=/home/khangho/agv_codex_reader_20261003_0652/slam_scan_fix.yaml \
    use_sim_time:=false >runtime/slam.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/slam.pid
sleep 1
AGV_BODY_RADIUS_M=0.20 AGV_BODY_BOUNDS_M=-0.16,-0.12,0.10,0.12 nohup python3 -B -u agv_unified_brain.py --operator-control \
    >runtime/brain.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/brain.pid
printf 'OPERATOR_CONTROL_STARTED_DISARMED; PID=%s\n' "$(cat runtime/brain.pid)"
