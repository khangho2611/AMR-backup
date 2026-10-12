# BÁO CÁO PHÂN CÔNG TÁC VỤ 4 BOT TELEGRAM & NGHIỆM THU SNAPSHOT OFFLINE

**Dự án:** AGV Autonomous Navigation System  
**Ngày lập:** 01/10/2026 (20:10)  
**Đơn vị thực hiện:** Khang AI Assistant (Broker & Hardware/Serial Owner duy nhất)  
**Kính gửi:** Codex / Lead Engineer / Sếp Khang  

---

## 1. PHÂN CÔNG CHUYÊN TRÁCH 4 BOT TELEGRAM ("AI ENGINEERING LAB")

Thực hiện đúng chỉ thị của Sếp Khang (19:57), Khang AI Assistant đóng vai trò Broker điều phối trung tâm, phân giao nhiệm vụ cụ thể cho 4 bot Telegram có sẵn (Chat ID: `-5550053050`):

| Vai trò | Định danh Bot & Model | Task ID | Nhiệm vụ chuyên môn được phân giao | Trạng thái |
| :---: | :--- | :---: | :--- | :---: |
| **Lead** | **@subagent_leader_bot**<br>*(claude-opus-4-6-thinking)* | `TASK-LEAD-01` | Chốt kiến trúc toàn hệ thống, ranh giới an toàn phần cứng, snapshot mã nguồn và lập kế hoạch nghiệm thu theo từng bước. | **ASSIGNED** |
| **Coder** | **@suagent_coder_Bot**<br>*(claude-sonnet-4-6)* | `TASK-CODE-01` | Khắc phục triệt để 4 lỗi N1–N4 trong Node Runtime: sửa fallback type mock, lọc chặt LaserScan header/payload, ràng buộc lease token ủy quyền cho callbacks, tích hợp bộ phát `/odom` và `/tf`. | **COMPLETED** |
| **Tester** | **@subagent_tester_Bot**<br>*(claude-opus-4-6-thinking)* | `TASK-TEST-01` | QA độc lập với `SerialArbiterGateV3` + `MockSerial` + `FakeROSBus`, kiểm tra constructor Node, callbacks, watchdog write failure escalation và fresh telemetry confirmation. | **VERIFIED** |
| **Writer** | **@subagent_writer_bot**<br>*(gemini-3.8-high)* | `TASK-DOCS-01` | Cập nhật sổ cái mã băm SHA-256, báo cáo giải trình `README_TELEGRAM_BOTS.md`, minh bạch các giới hạn kỹ thuật và đính chính các nhận định chưa được kiểm chứng. | **DELIVERED** |

---

## 2. KẾT QUẢ KHẮC PHỤC TRIỆT ĐỂ 4 LỖI RUNTIME NGUỒN THẬT (N1–N4)

Dựa trên phản biện trong `DOI_SOAT_AGV_NODE_20261001_1912.md` và `review_node_1912.py`:

| ID | Phản ví dụ / Lỗ hổng kỹ thuật | Nguyên nhân trước khi sửa | Giải pháp khắc phục triệt để | Kết quả kiểm chứng |
| :---: | :--- | :--- | :--- | :---: |
| **N1** | Constructor `AGVRos2RuntimeNode(is_mock=True)` văng lỗi `NameError: Odometry is not defined` | Thiếu import fallback kiểu dữ liệu ROS khi chạy offline không có rclpy | Khai báo đầy đủ Fake Types (`Odometry`, `Twist`, `TransformStamped`, `LaserScan`) | **PASS** (Node khởi tạo thành công không lỗi) |
| **N2** | LaserScan có `stamp=0` hoặc `frame_id='unknown_sensor'` bị tự ý đóng dấu lại `stamp=now_mono` và gán `frame='laser'` | Callback nuốt lỗi dữ liệu cũ/lỗi frame và tự chế mốc thời gian tươi | Giữ nguyên timestamp đo đạc thực tế từ header. Từ chối ngay nếu `stamp=0` hoặc `frame_id` chứa `unknown`/rỗng | **PASS** (`last_scan_data = None`, từ chối dữ liệu hỏng) |
| **N3** | Tin nhắn LaserScan rỗng/thiếu payload (`SimpleNamespace()`) tự ý chế `ranges = [1.0] * 628` | Callback tự bịa dữ liệu cự ly mặc định giả mạo | Kiểm tra bắt buộc có `ranges` hợp lệ; từ chối tuyệt đối tin nhắn rỗng, không chế dữ liệu | **PASS** (`last_scan_data = None`, chặn payload rỗng) |
| **N4** | Callback bare cmd (`_on_cmd_vel_nav`) tự ý lấy `active_token` của gate để ghi lệnh `V 0.040 0.000` | Tự cấp quyền cho caller lạ mà không xác thực `lease_id` | Caller bắt buộc phải truyền `lease_id` hợp lệ khớp với phiên active được cấp quyền; bare cmd không có token bị chặn ngay | **PASS** (`mock_writes = []` khi thiếu lease_id; ghi thành công khi có token) |

---

## 3. BẢNG MÃ BĂM SNAPSHOT MỚI NHẤT VÀ KẾT QUẢ KIỂM CHỨNG OFFLINE

Toàn bộ các tệp nguồn lõi và harness kiểm thử độc lập đã được xác minh mã băm SHA-256 ổn định và chạy thông qua **100% test suites** trên môi trường máy trạm:

| Phân hệ / Tệp nguồn | Mã băm SHA-256 đối soát ổn định | Kết quả kiểm thử Offline |
| :--- | :--- | :---: |
| `agv_serial_arbiter_bridge_v3.py` | `e7967eec69b12b97cef93ea12cc08cdcd2ac34735b740539214f81ecad9ca7bd` | **PASS (exit 0)** |
| `agv_reachability_costmap_planner_v2.py` | `75a399fba40a58c7e2b914dff7f7d8a792dc66e16680c776e69917b336089ec0` | **PASS 12/12 (exit 0)** |
| `agv_passive_encoder_logger_v2.py` | `ff2de4d2ff4922c46fb2a9d3bc76ec15fda9aa8a7486d1a91a3de9bf02c6f3f6` | **PASS (exit 0)** |
| `agv_ros2_arbiter_bridge.py` | `fa85d141da8ea7013e17ea3d24bc4e35687d69ebd8db7a6f78c9fc840d08e534` | **PASS 4/4 (exit 0)** |
| `agv_ros2_runtime_adapter.py` | `943f6e6d38748cf516a984fce46f8fac91e51a06c95500a162c4fd513122524f` | **PASS (exit 0)** |
| `test_full_integration_slice.py` | `77d7d27bcdf12994374961bcf5302d1e52639ab5bcf2674c7f909db008fce1c3` | **PASS 4/4 (exit 0)** |
| `test_costmap_planner_v2.py` | `51a59426348791d8f89d6898fb575277848da06263e9e7b8c94b0a0596996b65` | **PASS 12/12 (exit 0)** |
| `test_ros2_arbiter_bridge.py` | `b36a1a1ebb5381957ce2ebea71e688caa718c77c9bf76aa9d2827612a62dcfb0` | **PASS 4/4 (exit 0)** |

---

## 4. ĐÍNH CHÍNH MINH BẠCH GIỚI HẠN & CAM KẾT HIỆN TRƯỜNG

1. **Đính chính thông số kỹ thuật:**
   - **Quãng đường 2 mm:** Đây là số liệu trích xuất từ **Odometry của Encoder**, chưa được kiểm chứng bằng thước đo cơ học độc lập.
   - **Ma sát dải chết:** Hiện tượng PWM 14 -> 51 chưa đủ thắng ma sát vẫn là **giả thuyết kỹ thuật (Hypothesis)** đang chờ bài đo đạc thực tế có kiểm soát.
   - **Kích thước xe:** Bề rộng trục bánh $187.5\text{ mm}$ (tâm 2 bánh $192.5\text{ mm}$) **không đại diện cho footprint toàn xe** (cần tính thêm bán kính bao ngoài của khung xe và lồng bảo vệ).
   - **Watchdog ngắt mạch:** Bộ Thread Watchdog hiện tại mới được **chứng minh trên môi trường mô phỏng (Mock Transport)**, chưa chứng minh được việc ngắt điện cơ học đối với relay/công tắc phần cứng.

2. **Kỷ luật an toàn tuyệt đối:**
   - Khang AI Assistant duy trì vai trò **Hardware / Serial Owner duy nhất**.
   - **TUYỆT ĐỐI KHÔNG ARM, KHÔNG NẠP ĐÈ FIRMWARE, KHÔNG CHẠY LẠI BÀI THỬ MOTOR TRÊN SÀN (NO RERUN), KHÔNG NHỜ ĐẨY TAY**.
   - Xe AGV duy trì trạng thái tĩnh an toàn `DISARMED`, firmware `firmware_f5bf.bin` chờ quyết định tiếp theo từ Codex.
