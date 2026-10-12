#!/usr/bin/env bash
# ==============================================================================
# launch_full_system.sh - KHỞI ĐỘNG ĐẦY ĐỦ HỆ THỐNG AGV TRÊN RASPBERRY PI
# 1. Driver RPLIDAR C1 (10Hz, 670 tia)
# 2. SLAM Toolbox (Ceres solver, tạo topic /map)
# 3. AGV Unified Brain Server (Cổng 8080, quản lý Serial ESP32)
# ==============================================================================

source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash

echo "[1/3] Khởi động Driver RPLIDAR C1..."
nohup ros2 launch sllidar_ros2 sllidar_c1_launch.py serial_port:=/dev/ttyUSB1 > /home/khangho/rplidar_c1_test/logs/lidar.log 2>&1 &
sleep 3

echo "[2/3] Khởi động SLAM Toolbox..."
nohup ros2 launch slam_toolbox online_async_launch.py > /home/khangho/rplidar_c1_test/logs/slam.log 2>&1 &
sleep 3

echo "[3/3] Khởi động AGV Unified Brain & Web Dashboard..."
pkill -9 -f agv_unified_brain 2>/dev/null
nohup python3 /home/khangho/rplidar_c1_test/bridge/agv_unified_brain.py > /home/khangho/rplidar_c1_test/logs/unified.log 2>&1 &
sleep 2

echo "KIỂM TRA CỔNG 8080:"
lsof -i :8080 || netstat -tuln | grep 8080
