#!/usr/bin/env bash
# Starts only the SLLiDAR serial driver, samples AI1 predictions, and cleans up.
# This script never launches the AGV brain or opens the motor UART.
set -eo pipefail

ROOT=/home/khangho/agv_codex_reader_20261003_0652
STAGE=/home/khangho/agv_ai_shadow_stage_20261020

source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash
set -u
export PYTHONPATH="$STAGE:$ROOT:${PYTHONPATH:-}"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

mkdir -p "$STAGE/evidence"
if fuser /dev/ttyUSB1 >/dev/null 2>&1; then
  echo 'LiDAR serial port already owned; refusing to disrupt its owner' >&2
  exit 2
fi

driver_pgid=''
cleanup() {
  if [[ -n "$driver_pgid" ]]; then
    kill -TERM -- "-$driver_pgid" 2>/dev/null || true
    wait "$driver_pgid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

setsid bash -c 'source /opt/ros/jazzy/setup.bash; source /home/khangho/rplidar_c1_ws/install/setup.bash; exec ros2 launch sllidar_ros2 sllidar_c1_launch.py serial_port:=/dev/ttyUSB1 serial_baudrate:=460800 frame_id:=laser inverted:=false angle_compensate:=true' \
  > "$STAGE/evidence/lidar_only.log" 2>&1 < /dev/null &
driver_pgid=$!

sleep 5
if ! kill -0 "$driver_pgid" 2>/dev/null; then
  echo 'LiDAR driver exited before read-only sampling' >&2
  cat "$STAGE/evidence/lidar_only.log"
  exit 3
fi

python3 -B -u "$STAGE/tests/pi_ai_shadow_live.py" --model-root "$ROOT" \
  --duration 20 --output "$STAGE/evidence/scan_shadow.jsonl"
