with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'r') as f:
    code = f.read()

# NỚI LỎNG HEADER LIDAR TỪ 0.25s LÊN 2.0s:
# Tránh trường hợp LiDAR bị lệch vài mili-giây tem thời gian ROS 2 làm kích hoạt STALE_SCAN_STAMP!
code = code.replace("if not self._fresh_ros_header(msg.header,.25):", "if not self._fresh_ros_header(msg.header, 2.0):")

with open('/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py', 'w') as f:
    f.write(code)

print("SUCCESSFULLY RELAXED LIDAR STAMP AGE TO 2.0s")
