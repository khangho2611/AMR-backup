#!/usr/bin/env bash
set -eo pipefail
cd /home/khangho/agv_codex_reader_20261003_0652
MCU_PORT="/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
LIDAR_PORT="/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_76815f48566eef11bd64dec2c169b110-if00-port0"

echo "=== KHOI DONG HE THONG AGV CODEX ==="

# 1. Dung cac tien trinh cu neu con
bash ./stop_agv_system.sh

# 2. Kiem tra thiet bi phan cung
if [ ! -e "$MCU_PORT" ]; then
  echo "LOI: Khong tim thay ESP32 CH340 ($MCU_PORT)"
  exit 1
fi
if [ ! -e "$LIDAR_PORT" ]; then
  echo "LOI: Khong tim thay RPLiDAR C1 CP2102N ($LIDAR_PORT)"
  exit 1
fi

if fuser "$MCU_PORT" "$LIDAR_PORT" >/dev/null 2>&1; then
  echo "Canh bao: Cong serial dang bi chiem, tien hanh giai phong..."
  fuser -k "$MCU_PORT" "$LIDAR_PORT" || true
  sleep 1
fi

if ss -H -ltn 'sport = :8080' | grep -q .; then
  echo "Canh bao: Cong 8080 dang bi chiem, tien hanh giai phong..."
  fuser -k 8080/tcp || true
  sleep 1
fi

# 3. Nap moi truong ROS 2
source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash

mkdir -p runtime logs

# 4. Chay Static Transform (base_footprint -> laser)
echo "[1/4] Khoi dong Static TF Publisher (base_footprint -> laser)..."
ros2 run tf2_ros static_transform_publisher --x 0 --y 0 --z 0 \
    --yaw 0 --pitch 0 --roll 0 --frame-id base_footprint --child-frame-id laser \
    >runtime/static_tf.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/static_tf.pid

# 5. Chay RPLiDAR C1 Driver
echo "[2/4] Khoi dong RPLiDAR C1 Driver ($LIDAR_PORT)..."
ros2 launch sllidar_ros2 sllidar_c1_launch.py serial_port:="$LIDAR_PORT" \
    serial_baudrate:=460800 frame_id:=laser inverted:=false angle_compensate:=true \
    >runtime/lidar.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/lidar.pid

sleep 2

# 6. Chay SLAM Toolbox Online Async
echo "[3/4] Khoi dong SLAM Toolbox..."
SLAM_PARAMS="/home/khangho/agv_codex_reader_20261003_0652/slam_scan_fix.yaml"
if [ -f "/home/khangho/slam_calibration_tools/slam_tuned.yaml" ]; then
  SLAM_PARAMS="/home/khangho/slam_calibration_tools/slam_tuned.yaml"
  echo "    (Kich hoat cau hinh SLAM toi uu: ${SLAM_PARAMS})"
fi
nohup ros2 launch slam_toolbox online_async_launch.py \
    slam_params_file:="${SLAM_PARAMS}" \
    use_sim_time:=false >runtime/slam.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/slam.pid

sleep 2

# 7. Chay AGV Unified Brain
echo "[4/4] Khoi dong AGV Unified Brain Node & Cyberpunk Web UI (Port 8080)..."
AGV_WALL_MARGIN_M=0.00 AGV_AUTO_SPEED_RPM=40.0 AGV_BODY_RADIUS_M=0.20 AGV_BODY_BOUNDS_M=-0.16,-0.12,0.10,0.12 AGV_PROGRESS_TIMEOUT_S=3.5 AGV_AUTO_TURN_RPM=35.0 python3 -B -u agv_unified_brain.py --operator-control \
    >runtime/brain.log 2>&1 < /dev/null &
printf '%s\n' "$!" >runtime/brain.pid

sleep 2

echo "=== TRANG THAI KHOI DONG ==="
ps aux | grep -E 'brain|sllidar|slam|static_transform' | grep -v grep

echo "Kiem tra cong Web UI:"
ss -tlpn | grep 8080 || true

echo "=== KHOI DONG HOAN TAT ==="
