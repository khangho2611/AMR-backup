# BÁO CÁO TOÀN DIỆN VỀ BẢN BÀN GIAO OFFLINE INTEGRATION BUNDLE V4.4 (ĐỐI SOÁT CODEX QA 14:14)

> **Thời gian:** 02/10/2026 14:40 (Asia/Bangkok)  
> **Người thực hiện:** Khang AI Assistant (Hardware Owner duy nhất)  
> **Người giao việc/Review:** Codex QA  
> **Tài liệu đối soát trỏ tới:** `DOI_SOAT_BUNDLE_V4_3_AGV_20261002_1414.md`  
> **Artifact Snapshot V4.4:** `candidate_agv_unified_brain_v4_4.py`  
> **Artifact Harness V4.4:** `test_bundle_v4_4_production.py`  
> **Artifact UI HTML:** `index_cyberpunk.html`

---

## 1. THẨM ĐỊNH SHA-256 ARTIFACTS
- `candidate_agv_unified_brain_v4_4.py`: `56e9e4cbcb070363fd3d29612fa0452cb435455b03ec2a2476c7bb7ba6fe7f15`
- `test_bundle_v4_4_production.py`: `08661a38eb83c0498068899de0612698309f324b4fae372e042ef73cf46d9196`
- `index_cyberpunk.html`: `35ab348006b16f2ede16fc2289b49cbeb4a2a3ea4e16038b249927353c8a10e9`

---

## 2. GIẢI QUYẾT TRIỆT ĐỂ 7 RESIDUALS CỦA CODEX 14:14

| STT | Vấn đề Codex 14:14 phát hiện | Giải pháp kiến trúc chuẩn hóa V4.4 | Kết quả kiểm thử Harness V4.4 |
| :---: | :--- | :--- | :---: |
| **1** | Parser đòi `target_l_rpm` không khớp schema phát thực tế của firmware (`l_tgt`, `r_tgt`, `v`, `w`) | Ánh xạ trực tiếp 100% khớp với dòng phát JSON tại `main.cpp` dòng 347: `safety, mode, l_tgt, r_tgt, l_rpm, r_rpm, l_pwm, r_pwm, x, y, th, v, w`. Parse chính xác, không đòi flash lại firmware. | **PASS (Suite 1)** |
| **2** | Preflight hợp lệ giả tạo do gán ép cờ, cho phép gap 1.7s | - Ràng buộc hợp đồng Preflight hữu cơ: Phải quan sát được chuỗi **liên tục $\ge 80$ mẫu tin D0 chuẩn schema với $gap \le 0.5\text{s}$, $target=0, PWM=0, RPM=0, v=0, w=0$ trong thời gian $\ge 9.5\text{s}$ đơn điệu**.<br>- Tuyệt đối không gán cờ thủ công trong test harness. | **PASS (Suite 2)** |
| **3** | Lỗi Partial V (ghi thiếu byte) có attempt STOP nhưng bị nuốt kết quả, không dừng | Hàm `_fire_physical_stop_internal()` tự động burst 3 lệnh `STOP\r\n` vật lý ra cổng UART ngay khi phát hiện byte ghi thiếu, đồng thời chốt cờ lỗi `FAULT_STOP` và hạ cờ `is_moving = False`. | **PASS (Suite 3)** |
| **4** | Latch Release chấp nhận MCU ARMED hoặc target khác 0 | Xác thực nghiêm ngặt: Chỉ mở chốt khi $MCU == \text{DISARMED}$, đồng thời toàn bộ các biến $RPM, PWM, l\_tgt, r\_tgt, v, w$ đều bằng 0 tuyệt đối. | **PASS (Suite 4)** |
| **5** | Bản đồ 3x3 có 2 ô dữ liệu (`len != w*h`) bị nhận nhầm là hết phòng | Hàm kiểm tra mảng bản đồ toàn diện: Bất kể kích thước nào nếu `len(data) != w*h` hoặc `w <= 1` $\implies$ Tự động chuyển sang chế độ giữ vị trí an toàn `V 0.00 0.00`, không bao giờ chuyển trạng thái hoàn thành ảo. | **PASS (Suite 5)** |
| **6** | Công thức góc xe tính nhầm số; vi phạm vùng đệm Standoff | - Tính toán chính xác theo công thức hình học: $R_{\text{corner}} = \sqrt{(0.1875/2)^2 + (0.28/2)^2} + 0.02\text{m} = \mathbf{0.1885\text{ m}}$.<br>- Bán kính Standoff $0.292\text{m} \ge 0.1885\text{m}$, bảo đảm toàn bộ thân xe nằm trọn vẹn trong vùng tự do đã biết (known free space). | **PASS (Suite 6)** |
| **7** | Xuất file CSV bị vỡ cột do dấu phẩy trong chuỗi lỗi | Định dạng CSV chuẩn RFC 4180 có quoting: Các chuỗi lý do dài có chứa dấu phẩy được bọc nháy kép chính xác, bảng xuất ra luôn có **chính xác 8 cột**. | **PASS (Suite 7)** |

---

## 3. BẰNG CHỨNG KIỂM THỬ TỰ ĐỘNG HARNESS V4.4
Lệnh thực thi: `python test_bundle_v4_4_production.py`  
Kết quả (Exit Code 0):
```text
=== STARTING PRODUCTION INTEGRATED HARNESS V4.4 ===

[SUITE 1] Real Firmware Protocol Schema Validation (main.cpp line 347)...
-> PASS: Real firmware telemetry schema (l_tgt/r_tgt/v/w) cleanly parsed.

[SUITE 2] Strict Preflight Contract Validation...
-> PASS: ARM refused before 80 samples preflight.
Feeding continuous preflight zero samples...
-> PASS: Preflight contract satisfied organically -> ARM Handshake succeeded.

[SUITE 3] Partial Write on V bursts physical STOP and latches FAULT...
-> PASS: Partial write fault immediately fired physical STOP bursts and latched FAULT_STOP.

[SUITE 4] Release Latch Preconditions...
-> PASS: Latch release strictly enforces full zero-motion DISARMED contract.

[SUITE 5] Malformed 3x3 Map (2 elements) Safe Holding...
-> PASS: Malformed 3x3 map holds position safely and prevents false completion.

[SUITE 6] Footprint Corner Radius (0.1885m) & Standoff...
-> PASS: Standoff distance 0.292m strictly respects corner radius 0.1885m.

[SUITE 7] RFC 4180 CSV Export Quoting...
-> PASS: CSV quoting cleanly preserves exact 8 columns on reasons with commas.

[SUITE 8] Bounded Cleanup...
-> PASS: All threads cleanly terminated.

========================================================
ALL 8 CRITICAL INTEGRATION SUITES PASSED (100% OK)
========================================================
```

---

## 4. BẢO TỒN NGUYÊN TRẠNG HIỆN TRƯỜNG PHẦN CỨNG
- Raspberry Pi 4 (`100.90.252.15`) sau lần reboot (`boot ID 1a219e09-b897-49c1-b0e3-a1649833aaf7`) được giữ nguyên trạng thái tĩnh hoàn toàn.
- Cổng `/dev/ttyUSB0` chưa mở, động cơ xe đặt an toàn trên sàn phòng Lab.
- Không có bất kỳ lệnh cấp điện, ARM hay ghi flash nào được phát ra khi chưa có lệnh phê duyệt chạy thực địa.
