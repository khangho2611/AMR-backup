# BÁO CÁO KỸ THUẬT: BÀN GIAO MÃ NGUỒN PREFLIGHT TĨNH, SỬA ĐỔI STOP COMPLETION VÀ KẾ HOẠCH ĐO MOTION THỰC

**Thời gian:** 01/10/2026 — 21:05  
**Dự án:** AGV Autonomous Navigation System  
**Hardware Owner duy nhất:** Khang AI Assistant (Broker)  
**Tình trạng phần cứng:** Tĩnh trên sàn, `DISARMED`, `NO hardware/Serial thật/startROS trên Pi/flash/ARM/run2/logger/gain`.

---

## 1. MINH BẠCH VAI TRÒ THỰC HIỆN (MODEL_PROPOSED / BROKER_APPLIED / BROKER_EXECUTED)

- **Coder Agent (`gemini-3.8-flash-high`)**: `MODEL_PROPOSED` mã nguồn module thu thập telemetry thụ động `agv_preflight_static_collector.py` (cơ chế ReadOnlySerialWrapper cấm phát xung TX, timeout 15s, min 30 mẫu, kiểm tra nghiêm ngặt `safety == 'DISARMED'`).
- **Broker (Khang AI Assistant)**: `BROKER_APPLIED` hoàn thiện mã nguồn `agv_preflight_static_collector.py` (SHA256: `4069daef...`) và sửa lỗi STOP completion trong `agv_ros2_runtime_adapter.py` và `agv_serial_arbiter_bridge_v3.py`.
- **QA Tester (`gemini-3.8-flash-high`)**: `MODEL_PROPOSED` danh mục 8 ca kiểm thử biên độc lập cho Preflight Collector (positive flow, zero-tx guard, armed safety reject, non-zero pwm, non-zero rpm, non-finite values, timeout insufficient samples, settling garbage lines).
- **Broker (Khang AI Assistant)**: `BROKER_EXECUTED` viết harness `test_preflight_collector_independent.py` và chạy kiểm thử độc lập (8/8 tests PASS trong 2.1s).
- **Lead Coordinator (`claude-opus-4-6-thinking`)**: `MODEL_PROPOSED` kế hoạch đo lường Motion Ground Truth & Phân tích nguyên nhân ma sát / encoder bài 13:57.

---

## 2. BÀN GIAO MÃ NGUỒN PREFLIGHT TĨNH (`agv_preflight_static_collector.py`)

Module thu thập telemetry thụ động được thiết kế bảo vệ an toàn cao nhất:
1. **Zero-TX Guard (Cấm phát xung):** Lớp `ReadOnlySerialWrapper` ghi đè các hàm `write()`, `writelines()`, `flush()` bằng ngoại lệ `PureReadOnlyViolationError`.
2. **Cấu hình phần cứng an toàn:** Thiết lập `rts=False, dtr=False` trước khi open port để giảm thiểu rủi ro toggle chân nạp gây reset ESP32. Đồng thời tài liệu hóa rõ ràng cảnh báo: *Trên một số mạch USB-UART (CH340/CP2102), driver vẫn có thể tạo sườn toggle vật lý, do đó cần theo dõi gói D0 fresh sau settling*.
3. **Ràng buộc thời gian & số lượng:** `wall_timeout_s = 15.0s`, `min_samples = 30`, `max_samples = 150` (cap), `max_line_bytes = 256`.
4. **Kiểm duyệt mẫu Fail-Closed:**
   - Bắt buộc `safety == 'DISARMED'`.
   - Bắt buộc `l_tgt == 0.0, r_tgt == 0.0, l_pwm == 0, r_pwm == 0`.
   - Bắt buộc `l_rpm == 0.0, r_rpm == 0.0` (dung sai nhiễu vi mô $< 10^{-3}$).
   - Tất cả giá trị số phải hữu hạn (`is_valid_finite`).
   - Bỏ qua các dòng rác ban đầu trong quá trình settling của vi điều khiển.
5. **Mã băm SHA-256:** `4069daef1abffcae49730d29cddb415b256d28f96c976466367605956277dcd5`
6. **Lệnh chạy thử nghiệm Offline:**
   ```bash
   python "D:/HoMinhKhang/PROJECT/GITHUB_PROJECT/CODE XE TU HANH/agv_preflight_static_collector.py" --mock
   ```
   *Kết quả:* Exit code 0, thu thập 50 mẫu DISARMED an toàn trong 15s.

---

## 3. KẾT QUẢ KIỂM THỬ ĐỘC LẬP QA HARNESS (`test_preflight_collector_independent.py`)

Harness độc lập kiểm tra toàn diện 8 ca biên cho module Preflight Collector:
- **Test 1 (Positive Flow):** 40 mẫu DISARMED chuẩn $\rightarrow$ **PASS (exit 0)**.
- **Test 2 (Zero-TX Enforcement):** Cố tình gọi `write()` hoặc `flush()` $\rightarrow$ Ném lỗi `PureReadOnlyViolationError` $\rightarrow$ **PASS**.
- **Test 3 (Reject ARMED Safety):** Nhận gói `safety='ARMED'` $\rightarrow$ Báo lỗi `INVALID_SAFETY_STATE` $\rightarrow$ **PASS (exit 1)**.
- **Test 4 (Reject Non-zero PWM/Target):** Nhận `l_pwm = 15` $\rightarrow$ Báo lỗi `NON_ZERO_PWM` $\rightarrow$ **PASS (exit 1)**.
- **Test 5 (Reject Non-zero RPM):** Nhận `l_rpm = 1.5` $\rightarrow$ Báo lỗi `NON_ZERO_RPM` $\rightarrow$ **PASS (exit 1)**.
- **Test 6 (Reject Non-finite NaN/Inf):** Nhận `v = 'NaN'` $\rightarrow$ Báo lỗi `NON_FINITE_OR_INVALID` $\rightarrow$ **PASS (exit 1)**.
- **Test 7 (Insufficient Samples Timeout):** Chỉ có 5 mẫu trong 15s $\rightarrow$ Báo lỗi `FAIL_INSUFFICIENT_SAMPLES` $\rightarrow$ **PASS (exit 1)**.
- **Test 8 (Settling Garbage Handled):** 3 dòng rác khởi động được bỏ qua an toàn $\rightarrow$ **PASS (exit 0)**.

---

## 4. KHẮC PHỤC TRIỆT ĐỂ LỖI RUNTIME STOP COMPLETION

**Hiện tượng trước đó:** Khi `destroy_node()` gửi `STOP` khẩn cấp (`write_ok = True`), gate ghi nhận `stop_confirmed = False`. Khi có gói D0 fresh tiếp theo xác nhận xe `DISARMED`, `gate.stop_confirmed` chuyển sang `True` nhưng `watchdog.last_stop_confirmed` vẫn bị kẹt ở `False` do chỉ snapshot cờ lúc gọi.

**Giải pháp:**
1. Trong `agv_ros2_runtime_adapter.py`: Khi `FirmwarePacketAdapter.parse_and_ingest()` tiếp nhận gói telemetry mới từ MCU, adapter kiểm tra nếu gate đã xác nhận `stop_confirmed == True` $\implies$ cập nhật ngay `watchdog.last_stop_confirmed = True`.
2. Trong `agv_serial_arbiter_bridge_v3.py`: Đảm bảo `self.safety_state` cập nhật chính xác theo gói telemetry DISARMED đến sau lệnh STOP, kích hoạt `stop_confirmed = True` tất định.
3. **Bằng chứng kiểm chứng thực tế:**
   ```text
   After destroy_node at 100.06:
     gate.stop_confirmed: False
     node.watchdog.last_stop_confirmed: False
   After fresh D0 packet at 100.08:
     gate.stop_confirmed: True
     node.watchdog.last_stop_confirmed: True
   ```

---

## 5. SỔ CÁI MÃ BĂM SHA-256 ĐỐI SOÁT ỔN ĐỊNH

| Tệp tin | Mã băm SHA-256 ổn định | Vai trò kỹ thuật |
| :--- | :--- | :---: |
| `agv_preflight_static_collector.py` | `4069daef1abffcae49730d29cddb415b256d28f96c976466367605956277dcd5` | Preflight tĩnh Bounded No-TX |
| `test_preflight_collector_independent.py` | `b08e5c550feb736caf4423c22690306f425c72f479dfd08c233fb798f2ac64ae` | Harness QA 8 ca biên độc lập |
| `agv_ros2_runtime_adapter.py` | `02ff0683f49e6f546606c4e7743fc4d978245f155ca0232dc34e88657025c6ec` | Runtime Node & Packet Adapter |
| `agv_serial_arbiter_bridge_v3.py` | `6f4a2106622e99fe60212199b621cdcbbd2a76b2e639519796b15d5a703e3d1d` | Serial Arbiter Gate v3 |
| `agv_ros2_arbiter_bridge.py` | `5a0542868f68349118df0ebb4957f5ed9cb65ef951d661d985f792106491b8ad` | ROS 2 Priority Arbiter Bridge |
| `test_full_integration_slice.py` | `77d7d27bcdf12994374961bcf5302d1e52639ab5bcf2674c7f909db008fce1c3` | Harness Full Integration Slice |

---

## 6. KẾ HOẠCH ĐO LƯỜNG MOTION GROUND TRUTH & PHÂN TÍCH MA SÁT BÀI 13:57 (TRÌNH CODEX REVIEW)

Để làm rõ nguyên nhân bài thử 13:57 bị `MOTION_TRACKING FAIL` (quãng đường thực tế chỉ 2mm dù đặt 10cm):
1. **Thiết lập:**
   - Cự ly tịnh tiến ngắn: $s = 100\text{ mm}$ (0.10 m), vận tốc đặt $v = 0.05\text{ m/s}$, thời gian tối đa $t_{\text{max}} = 2.0\text{ s}$.
   - Đo cự ly thực tế $s_{\text{real}}$ bằng thước kẹp cơ khí ($\pm 0.05\text{ mm}$) và vạch chuẩn laser.
2. **Đo lường đối sánh 3 kênh:**
   - $s_{\text{real}}$: Thước kẹp vật lý.
   - $s_{\text{odom}}$: Tính toán từ số xung Encoder (937.2 xung/vòng $\approx$ 0.245 mm/xung).
   - $s_{\text{lidar}}$: Dịch chuyển quét tương đối từ RPLIDAR C1 (LaserScan matching).
3. **Đo dải chết ma sát tĩnh (Deadband):**
   - **Kê kích hổng bánh:** Tăng dần PWM từ 0 để xác định $PWM_{\text{min\_free}}$ làm bánh xe bắt đầu quay không tải.
   - **Đặt trên sàn:** Lặp lại để xác định $PWM_{\text{min\_floor}}$ làm xe bắt đầu chuyển động.
   - Chênh lệch $\Delta PWM = PWM_{\text{min\_floor}} - PWM_{\text{min\_free}}$ sẽ lượng hóa chính xác lực cản ma sát tĩnh cần bù.
4. **Kỷ luật an toàn tuyệt đối:**
   - Thử nghiệm chức năng E-stop trước bài chạy.
   - Giữ nguyên firmware `firmware_f5bf.bin`, không tự ý tăng gain hay nạp đè firmware.
   - **Kế hoạch này đang ở trạng thái PENDING REVIEW, chưa được phép chạy thật khi chưa có văn bản duyệt từ Codex.**
