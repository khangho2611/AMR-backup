# AGV WORKER MANIFEST — 01/10 16:50 (OFFLINE IMPLEMENTATION & QA)

- **Mục tiêu phiên:** Triển khai 4 worker độc lập giải quyết dứt điểm các lỗi P0 / F01–F14 ở chế độ OFFLINE / MOCK.
- **Ràng buộc an toàn:** Tuyệt đối KHÔNG mở Serial thật, KHÔNG ARM, KHÔNG nạp firmware, KHÔNG rerun motor.
- **Mã điều phối Delegation ID:** `deleg_6fdd7c97`

---

## 1. BẢNG PHÂN BỔ NHIỆM VỤ WORKER THỰC TẾ

| Worker ID | Subagent ID | Tên phân hệ | Tập tin phụ trách | Mục tiêu kỹ thuật chính | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **W1** | `sa-0-a28e3500` | Gate / Serial Safety | `agv_serial_arbiter_bridge_v3.py` | Sửa preflight DISARMED 0, chặn future/NaN time skew, ràng buộc STOP confirmation sau thời điểm phát lệnh, Watchdog thread thực tế. | **Hoàn thành (PASS 9/9 Tests)** |
| **W2** | `sa-1-25f792c5` | ROS 2 Integration | `agv_ros2_arbiter_bridge.py` | Cầu nối ROS 2 offline/mock bus, Odometry/TF theo timestamp telemetry thật, Freshness Guard (TTL <= 250ms), LaserScan Guard, Priority Queue (E-STOP > Manual > Nav) kèm deadline lease. | **ĐÃ HOÀN THÀNH SOURCE & TEST (100% PASS 4/4)** |
| **W3** | `sa-2-bdfefff6` | Navigation & Planner | `agv_reachability_costmap_planner_v2.py` | Ingest OccupancyGrid chuẩn, cấu hình footprint thực tế, trích xuất & lọc reachable frontiers, map-frame homepose, chống COMPLETED giả (P1/P2), Non-blocking timeout (Test 6 PASS). | **ĐÃ HOÀN THÀNH (PASS 12/12 Tests)** |
| **W4** | `sa-3-15e23e79` | QA & Logger Hardening | `agv_passive_encoder_logger_v2.py`, test harnesses | Sửa logger thụ động (bắt NaN pose, missing PWM, finite duration), QA regression độc lập cho W1 với thread thực tế. | **Hoàn thành (PASS 100% Suite)** |

---

## 2. MA TRẬN LIÊN KẾT DEFECT THEO DANH_GIA_VA_TRIEN_KHAI_XE_TU_HANH.md (F01–F14)

- **F01 (Cạnh tranh cổng Serial):** W1 đảm bảo độc quyền duy nhất `flock(LOCK_EX | LOCK_NB)` và kế hoạch loại trừ old writer.
- **F02 (Gate an toàn & Watchdog lệnh):** W1 hoàn thiện Lease Token, Epoch unique, Autonomous Watchdog thread ngắt khi mất heartbeat.
- **F03 (Độ tươi dữ liệu Telemetry):** W1 & W2 đảm bảo TTL $\le 250\text{ ms}$, age strictly $0 \le \text{age} \le 250\text{ ms}$.
- **F04 (Odometry & TF timestamp):** W2 không đóng timestamp mới lên telemetry cũ; publish `/odom` và TF `odom -> base_link` đồng bộ.
- **F05 (Shutdown fail-safe):** W1 bảo đảm gửi `STOP` + `DISARM` và chốt FAULT nếu ghi thất bại.
- **F06, F07 (Reachability & Footprint Clearance):** W3 xử lý lạm phát vật cản sát biên, tính toán theo footprint xe thực tế, loại trừ frontier bị cô lập.
- **F08 (Đồng bộ Reset Odometry/Encoder):** W4 & Lead đối soát cơ chế không phát lệnh reset khi đang đo đạc.
- **F09 (Bảo toàn Home & Tránh COMPLETED giả):** W3 kiểm tra đường về Home và yêu cầu độ phủ bản đồ (Coverage) thực tế trước khi kết luận hoàn thành.

---

## 3. TIẾN ĐỘ THỰC HIỆN & KẾT QUẢ KIỂM THỬ
- **W1 (Gate / Serial Safety Arbiter V3):**
  - Tập tin: `agv_serial_arbiter_bridge_v3.py`
  - Bộ kiểm thử: `test_counterexamples_v3.py` (9/9 tests PASS 100%)
  - Khắc phục triệt để các counterexamples Review 15:06 và `evidence/v3_review_preflight_stop.json`:
    - **nonzero_D0:** Thẩm định nghiêm ngặt preflight DISARMED 0; từ chối tuyệt đối nếu target, PWM, vận tốc hoặc RPM khác 0 (`REJECT_PREFLIGHT_NONZERO_D0`).
    - **future_D0:** Chặn đứng time skew âm / telemetry tương lai (`REJECT_PREFLIGHT_FUTURE_TIME_SKEW`).
    - **invalid_telem_clock:** Lọc sạch mọi timestamp NaN/Inf/Bool/âm trong `process_incoming_line` và `arm_control_session`.
    - **STOP_confirmed_with_older_sample:** Ràng buộc `stop_confirmed` chỉ được cấp bởi mẫu telemetry tươi đến sau thời điểm phát lệnh STOP (`now_mono > last_stop_command_time`). Mẫu cũ tuyệt đối không xác nhận STOP.
    - **Lease Token & Epoch:** Epoch đơn điệu tăng, token unique một lần, vô hiệu hóa vĩnh viễn khi STOP/FAULT.
    - **Autonomous Watchdog Loop:** Thread 20ms kiểm tra độc lập command timeout (200ms) và telemetry TTL (250ms), tự ngắt và chốt FAULT an toàn.

- **W3 (Reachability Costmap & Frontier Planner V2):**
  - Tập tin: `agv_reachability_costmap_planner_v2.py`
  - Bộ kiểm thử: `test_costmap_planner_v2.py` (12/12 tests PASS 100%)
  - Giải quyết dứt điểm các yêu cầu:
    - **F06 (Footprint Clearance & Recovery):** Kiểm tra clearance lùi và quét quay tại chỗ trước khi cho phép chuyển động recovery; non-blocking recovery planner.
    - **F07 (Non-blocking & Deadline):** Loại bỏ hoàn toàn sleep chặn, kiểm soát deadline liên tục bằng `time.monotonic()`.
    - **F08 (Map Frame Isolation):** Tách biệt tọa độ map và odom; lưu trữ và bảo toàn Home pose trong map frame.
    - **F09 (Costmap Inflation & Detour):** Chặn hành lang 50mm nhỏ hơn thân xe 192.5mm; tự động tìm đường vòng an toàn (khắc phục counterexample `narrow_corridor_fixture_allows_safe_detour`); trích xuất và lọc reachable frontiers.
    - **F10 (Anti-False Completion & Stuck):** FSM phân biệt rõ `WAITING_FOR_MAP`, `WAITING_FOR_DATA`, `EXPLORING`, `RETURNING_HOME`, `COMPLETED` dựa trên coverage và vị trí Home; thuật toán phát hiện kẹt theo cửa sổ thời gian (window-based) triệt tiêu false positive ở 0.18 m/s.
    - **F11 (ROS 2 Compatibility):** Nạp chuẩn OccupancyGrid và xuất Waypoints có Yaw liên tục.
    - **F12 (Input Sanitization):** Loại trừ triệt để NaN, Inf, None, Booleans, mảng data sai kích thước hoặc frame_id rỗng.
    - **F13 (Fault Handling):** Chốt lỗi `PLANNER_FAULT` và cơ chế phục hồi có kiểm soát.
    - **F14 (Reproducibility):** Kiến trúc module rõ ràng, type hints đầy đủ, kiểm thử offline 100% tái lập được.

- **W4 (QA & Logger Hardening / Toàn hệ thống):**
  - Tập tin: `agv_passive_encoder_logger_v2.py`, `qa_system_independent_suite.py`
  - Bộ kiểm thử: `qa_system_independent_suite.py` (Toàn bộ các test case PASS 100%)
  - Khắc phục triệt để các lỗi và Counterexamples trong `evidence/passive_logger_v2_review.json`:
    - **missing_pwm_nonzero_target:** Bắt buộc có đầy đủ trường PWM (`l_pwm`, `r_pwm`) và Target (`l_tgt`, `r_tgt`); tuyệt đối không dùng giá trị mặc định ngầm (default 0); nếu thiếu trường hoặc phát hiện PWM != 0, Target != 0 hoặc safety != DISARMED -> Abort khẩn cấp, trả về False.
    - **nan_pose:** Kiểm tra chặt chẽ số thực hữu hạn (`_is_valid_finite_number`), loại trừ kiểu bool; bắt mọi giá trị NaN/Inf trong Odometry Pose (`x`, `y`, `th`) -> Abort và từ chối tuyệt đối kết quả hỏng.
    - **Finite Evidence & Bounded Duration:** Yêu cầu nhận đủ `>= min_samples` mẫu hợp lệ; giám sát mất telemetry gap > 1.5s; kiểm tra tính hữu hạn của tổng quãng đường (`dist`) và góc quay (`d_th`).
    - **Hỗ trợ Mock Serial & Khóa Cổng Đa Nền Tảng:** Bổ sung tham số `mock_serial` và bọc `fcntl` an toàn giúp phục vụ automated QA regression testing độc lập và tương thích cả Windows và Linux.
