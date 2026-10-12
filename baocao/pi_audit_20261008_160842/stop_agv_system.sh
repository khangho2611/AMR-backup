#!/usr/bin/env bash
cd /home/khangho/agv_codex_reader_20261003_0652
echo "Dừng các tiến trình AGV đang chạy nếu có..."

if [ -d runtime ]; then
  for pidfile in runtime/*.pid; do
    if [ -f "$pidfile" ]; then
      pid=$(cat "$pidfile" 2>/dev/null || true)
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "Killing PID $pid ($pidfile)..."
        kill -SIGINT "$pid" 2>/dev/null || true
        sleep 0.5
        kill -9 "$pid" 2>/dev/null || true
      fi
      rm -f "$pidfile"
    fi
  done
fi

pkill -f 'agv_unified_brain.py' || true
pkill -f 'sllidar_node' || true
pkill -f 'async_slam_toolbox_node' || true
pkill -f 'static_transform_publisher.*laser' || true

sleep 1
echo "Đã dừng toàn bộ tiến trình AGV."
