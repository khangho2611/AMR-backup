#!/usr/bin/env bash
# ==============================================================================
# run_slam_tuned.sh - CHẠY THỬ NGHIỆM SLAM CẤU HÌNH TỐI ƯU CÁCH LY
# Không làm ảnh hưởng đến Unified Brain, Serial STM32 hay Web UI Dashboard.
# Hỗ trợ khôi phục (Rollback) về cấu hình cũ chỉ bằng 1 câu lệnh!
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_DIR="/home/khangho/agv_codex_reader_20261003_0652"
TUNED_YAML="${SCRIPT_DIR}/slam_tuned.yaml"
ORIGINAL_YAML="${MAIN_DIR}/slam_scan_fix.yaml"
LOG_FILE="${SCRIPT_DIR}/slam_tuned.log"

source /opt/ros/jazzy/setup.bash
source /home/khangho/rplidar_c1_ws/install/setup.bash

action="${1:---start}"

show_help() {
    echo "Sử dụng:"
    echo "  ./run_slam_tuned.sh --start     : Kích hoạt SLAM cấu hình tối ưu mới"
    echo "  ./run_slam_tuned.sh --rollback  : Quay trở lại cấu hình cũ nguyên bản"
    echo "  ./run_slam_tuned.sh --status    : Kiểm tra trạng thái SLAM hiện tại"
}

case "$action" in
    --start)
        echo "=========================================================="
        echo ">> [1/3] DỪNG NODE SLAM TOOLBOX CŨ..."
        echo "   (Các node khác: LiDAR, Brain, Web UI vẫn hoạt động bình thường)"
        pkill -9 -f slam_toolbox || true
        sleep 1

        echo ">> [2/3] KHỞI ĐỘNG SLAM TOOLBOX VỚI CẤU HÌNH TỐI ƯU..."
        echo "   File cấu hình: ${TUNED_YAML}"
        nohup ros2 launch slam_toolbox online_async_launch.py \
            slam_params_file:="${TUNED_YAML}" \
            use_sim_time:=false > "${LOG_FILE}" 2>&1 < /dev/null &
        echo $! > "${SCRIPT_DIR}/slam_tuned.pid"
        sleep 2

        echo ">> [3/3] KIỂM TRA TRẠNG THÁI:"
        if pgrep -f async_slam_toolbox_node >/dev/null; then
            echo "   [THÀNH CÔNG] SLAM Toolbox đã khởi chạy với cấu hình mới!"
            echo "   Bây giờ bạn có thể mở Web UI (port 8080) và quay xe để kiểm tra bản đồ."
            echo "   Log theo dõi tại: ${LOG_FILE}"
        else
            echo "   [CẢNH BÁO] Chưa thấy node khởi chạy, kiểm tra log: tail -n 20 ${LOG_FILE}"
        fi
        echo "=========================================================="
        ;;

    --rollback)
        echo "=========================================================="
        echo ">> ĐANG ROLLBACK VỀ CẤU HÌNH GỐC NGUYÊN BẢN..."
        pkill -9 -f slam_toolbox || true
        sleep 1

        echo ">> Khởi động lại SLAM Toolbox với: ${ORIGINAL_YAML}"
        cd "${MAIN_DIR}"
        nohup ros2 launch slam_toolbox online_async_launch.py \
            slam_params_file:="${ORIGINAL_YAML}" \
            use_sim_time:=false > "${MAIN_DIR}/runtime/slam.log" 2>&1 < /dev/null &
        sleep 2
        echo ">> [HOÀN TẤT] Đã phục hồi về hệ thống ban đầu 100%!"
        echo "=========================================================="
        ;;

    --status)
        echo "=== TRẠNG THÁI SLAM HIỆN TẠI ==="
        ps aux | grep -E 'slam_toolbox' | grep -v grep || echo "Không có node SLAM nào đang chạy."
        echo ""
        echo "=== TOPIC KIỂM TRA ==="
        ros2 topic info /map || true
        ;;

    *)
        show_help
        ;;
esac
