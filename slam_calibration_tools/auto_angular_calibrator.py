#!/usr/bin/env python3
# ==============================================================================
# auto_angular_calibrator.py - CÔNG CỤ TỰ ĐỘNG ĐO & HIỆU CHUẨN GÓC QUAY AGV
# ==============================================================================
# Nguyên lý:
#   1. Đo góc quay thực tế ngoài không gian bằng LiDAR (Scan-to-Scan Circular Correlation).
#      LiDAR quét tia vào tường phòng nên góc đo được KHÔNG BAO GIỜ BỊ TRƯỢT.
#   2. Đọc đồng thời góc quay do bánh xe/Encoder báo về qua TF (odom -> base_footprint).
#   3. So sánh 2 góc này trong suốt quá trình xe xoay tại chỗ 360 độ (1 vòng) hoặc 720 độ (2 vòng).
#   4. Tự động tính toán:
#      - Hệ số sai lệch góc (Scale Factor K)
#      - Khoảng cách cơ sở bánh xe hiệu dụng thực tế (Effective Wheelbase L_actual)
#      - Tạo file báo cáo calibration_report.json và hướng dẫn áp dụng.
# ==============================================================================

import sys
import os
import time
import math
import json
import argparse
import numpy as np

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import LaserScan
    from tf2_ros import Buffer, TransformListener
except ImportError:
    print("[LỖI] Cần môi trường ROS 2. Hãy chạy: source /opt/ros/jazzy/setup.bash")
    sys.exit(1)


def quaternion_to_yaw(z, w):
    """Tính góc yaw (-pi .. +pi) từ quaternion 2D (z, w)"""
    return math.atan2(2.0 * w * z, 1.0 - 2.0 * (z * z))


def unwrap_angle(current_angle, last_unwrapped):
    """Chuyển đổi góc modulo 2*pi thành góc liên tục không giới hạn."""
    if last_unwrapped is None:
        return current_angle
    diff = current_angle - (last_unwrapped % (2 * math.pi))
    if diff > math.pi:
        diff -= 2 * math.pi
    elif diff < -math.pi:
        diff += 2 * math.pi
    return last_unwrapped + diff


def compute_scan_relative_yaw(prev_ranges, curr_ranges, angle_increment, max_search_rad=0.35):
    """
    Tính góc xoay tương đối giữa 2 scan kế tiếp bằng tương quan vòng (Circular Cross-Correlation).
    Cực kỳ chính xác và ổn định khi xe quay chậm (< 30 deg/s).
    """
    n = len(curr_ranges)
    if n == 0 or len(prev_ranges) != n:
        return 0.0

    # Lọc bỏ giá trị inf/nan
    valid_prev = np.where(np.isfinite(prev_ranges), prev_ranges, 0.0)
    valid_curr = np.where(np.isfinite(curr_ranges), curr_ranges, 0.0)

    # Giới hạn số bước dịch chuyển tìm kiếm tương ứng max_search_rad
    max_shift = int(max_search_rad / angle_increment) + 1
    shifts = range(-max_shift, max_shift + 1)

    best_shift = 0
    best_corr = -1.0

    # Tính tương quan cho từng độ lệch
    for s in shifts:
        rolled = np.roll(valid_curr, -s)
        # Tích vô hướng giữa 2 mảng khoảng cách có cùng vùng quét hợp lệ
        mask = (valid_prev > 0.1) & (rolled > 0.1)
        if np.count_nonzero(mask) < (n * 0.25):
            continue
        corr = np.dot(valid_prev[mask], rolled[mask])
        if corr > best_corr:
            best_corr = corr
            best_shift = s

    return float(best_shift * angle_increment)


class AngularCalibratorNode(Node):
    def __init__(self, current_wheel_base=0.1925):
        super().__init__('auto_angular_calibrator')
        self.current_wheel_base = current_wheel_base

        # TF Listener
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # LaserScan Subscription
        qos_scan = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5
        )
        self.sub_scan = self.create_subscription(
            LaserScan, '/scan', self.scan_callback, qos_scan
        )

        # State tracking
        self.last_scan_ranges = None
        self.last_scan_time = None
        self.angle_increment = None

        self.start_odom_yaw = None
        self.last_unwrapped_odom_yaw = None
        self.accumulated_lidar_yaw = 0.0

        self.last_reported_odom_yaw = 0.0
        self.is_collecting = False
        self.start_time = None

        self.samples = []
        self.get_logger().info("Đã sẵn sàng. Đang chờ dữ liệu /scan và TF odom...")

    def scan_callback(self, msg: LaserScan):
        ranges = np.array(msg.ranges, dtype=np.float32)
        # Giới hạn tầm quét 0.15m - 8.0m
        ranges[(ranges < 0.15) | (ranges > 8.0)] = 0.0

        self.angle_increment = msg.angle_increment
        now_sec = self.get_clock().now().nanoseconds * 1e-9

        # 1. Đọc góc Odometry hiện tại từ TF
        odom_yaw = None
        try:
            if self.tf_buffer.can_transform('odom', 'base_footprint', rclpy.time.Time(), timeout=rclpy.duration.Duration(seconds=0.05)):
                t = self.tf_buffer.lookup_transform('odom', 'base_footprint', rclpy.time.Time())
                odom_yaw = quaternion_to_yaw(t.transform.rotation.z, t.transform.rotation.w)
        except Exception:
            pass

        if odom_yaw is None:
            return

        # 2. Xử lý bước đầu tiên (Initialize)
        if not self.is_collecting:
            self.last_scan_ranges = ranges
            self.last_scan_time = now_sec
            self.start_odom_yaw = odom_yaw
            self.last_unwrapped_odom_yaw = odom_yaw
            self.is_collecting = True
            self.start_time = now_sec
            print("\n" + "=" * 65)
            print(" BẮT ĐẦU GHI NHẬN DỮ LIỆU HIỆU CHUẨN GÓC QUAY")
            print(f" Wheelbase hiện tại: {self.current_wheel_base * 1000.0:.1f} mm")
            print(" Hãy điều khiển xe quay 1 vòng (360 độ) tại chỗ...")
            print("=" * 65 + "\n")
            return

        # 3. Tính góc quay thực tế bằng LiDAR (Scan Matching)
        d_lidar = compute_scan_relative_yaw(
            self.last_scan_ranges, ranges, self.angle_increment
        )
        self.accumulated_lidar_yaw += d_lidar
        self.last_scan_ranges = ranges
        self.last_scan_time = now_sec

        # 4. Tính góc quay Odometry tích lũy
        unwrapped_odom = unwrap_angle(odom_yaw, self.last_unwrapped_odom_yaw)
        self.last_unwrapped_odom_yaw = unwrapped_odom
        total_odom_delta = unwrapped_odom - self.start_odom_yaw

        odom_deg = math.degrees(total_odom_delta)
        lidar_deg = math.degrees(self.accumulated_lidar_yaw)

        # Lưu mẫu dữ liệu
        self.samples.append({
            "t": now_sec - self.start_time,
            "odom_deg": odom_deg,
            "lidar_deg": lidar_deg
        })

        # In tiến độ dạng thanh tiến trình động
        ratio_str = f"{(lidar_deg / odom_deg):.4f}" if abs(odom_deg) > 10.0 else "Đang đo..."
        sys.stdout.write(
            f"\r[QUAY XE] Odom: {odom_deg:+6.1f}° | LiDAR: {lidar_deg:+6.1f}° | Tỉ lệ tức thời K: {ratio_str}   "
        )
        sys.stdout.flush()

    def generate_final_report(self):
        print("\n\n" + "=" * 65)
        print("          KẾT QUẢ PHÂN TÍCH HIỆU CHUẨN GÓC QUAY")
        print("=" * 65)

        if len(self.samples) < 20:
            print("[CẢNH BÁO] Số lượng mẫu đo quá ít! Xe chưa di chuyển đủ lâu.")
            return

        final_sample = self.samples[-1]
        odom_total = final_sample["odom_deg"]
        lidar_total = final_sample["lidar_deg"]

        if abs(odom_total) < 45.0 or abs(lidar_total) < 45.0:
            print(f"[CẢNH BÁO] Tổng góc quay còn quá nhỏ ({odom_total:.1f}°). Hãy quay xe ít nhất 180° đến 360°!")
            return

        # Tính hệ số tỷ lệ
        # Nếu Odom báo 340 độ nhưng LiDAR báo 360 độ -> Odom đang quay ít hơn thực tế -> K = 360 / 340 > 1.0
        k_ratio = lidar_total / odom_total
        error_percent = abs(k_ratio - 1.0) * 100.0

        # Công thức hiệu chuẩn Wheel Base cho Differential Drive:
        # d_theta = (d_r - d_l) / L
        # Để theta mới = theta cũ * k_ratio => L_mới = L_cũ / k_ratio
        calibrated_wheel_base = self.current_wheel_base / k_ratio

        print(f"1. Tổng góc Encoder (Odom) đếm được : {odom_total:+7.2f} độ")
        print(f"2. Tổng góc LiDAR (Thực tế không trượt): {lidar_total:+7.2f} độ")
        print(f"3. Sai lệch phần trăm                : {error_percent:6.2f} %")
        print(f"4. Hệ số bù góc (Scale Factor K)     : {k_ratio:7.4f}")
        print("-" * 65)
        print(f"[*] Chiều rộng 2 bánh (Wheel Base) hiện tại  : {self.current_wheel_base * 1000.0:.2f} mm")
        print(f"[>] Chiều rộng 2 bánh HIỆU CHUẨN ĐỀ XUẤT     : {calibrated_wheel_base * 1000.0:.2f} mm")
        print("=" * 65)

        # Xuất file kết quả JSON
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "current_wheel_base_m": self.current_wheel_base,
            "calibrated_wheel_base_m": round(calibrated_wheel_base, 5),
            "calibrated_wheel_base_mm": round(calibrated_wheel_base * 1000.0, 2),
            "scale_factor_k": round(k_ratio, 5),
            "odom_deg_total": round(odom_total, 2),
            "lidar_deg_total": round(lidar_total, 2),
            "error_percent": round(error_percent, 2),
            "sample_count": len(self.samples)
        }

        output_path = os.path.join(os.path.dirname(__file__), "calibration_report.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[OK] Đã lưu báo cáo tại: {output_path}")
        print("\nCÁCH ÁP DỤNG:")
        print(f" - Cách 1 (Phần cứng): Sửa ROBOT_WHEEL_BASE trong file robot_stm32_f103/include/odometry.h")
        print(f"   #define ROBOT_WHEEL_BASE {calibrated_wheel_base:.4f}f")
        print(f" - Cách 2 (Phần mềm): Sử dụng cấu hình SLAM tối ưu slam_tuned.yaml để LiDAR")
        print(f"   tự động khóa góc tường mà không cần nạp lại chip STM32.")
        print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Tự động đo & hiệu chuẩn góc quay AGV bằng LiDAR")
    parser.add_argument("--wheelbase", type=float, default=0.1925, help="Khoảng cách 2 bánh hiện tại (mét), mặc định 0.1925m")
    args = parser.parse_args()

    rclpy.init()
    node = AngularCalibratorNode(current_wheel_base=args.wheelbase)

    try:
        rclpy.spin(node)
    except Exception:
        pass
    finally:
        node.generate_final_report()
        node.destroy_node()
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    main()
