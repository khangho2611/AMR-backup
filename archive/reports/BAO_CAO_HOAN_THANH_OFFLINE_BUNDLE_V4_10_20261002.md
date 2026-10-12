# BÁO CÁO TOÀN DIỆN VỀ BẢN BÀN GIAO OFFLINE INTEGRATION BUNDLE V4.10 (ĐỐI SOÁT CODEX QA 15:25)

> **Thời gian:** 02/10/2026 15:55 (Asia/Bangkok)  
> **Người thực hiện:** Khang AI Assistant (Hardware Owner duy nhất)  
> **Người giao việc/Review:** Codex QA  
> **Tài liệu đối soát trỏ tới:** `DOI_SOAT_BUNDLE_V4_9_AGV_20261002_1525.md`  
> **Artifact Snapshot V4.10:** `candidate_agv_unified_brain_v4_10.py`  
> **Artifact Harness V4.10:** `test_bundle_v4_10_production.py`  
> **Artifact UI HTML:** `index_cyberpunk.html`

---

## 1. THẨM ĐỊNH SHA-256 ARTIFACTS
- `candidate_agv_unified_brain_v4_10.py`: `13073462c149ee83aa3faf94529f24f12c4f3addeda9051c6644e4b249c4fb66`
- `test_bundle_v4_10_production.py`: `2940e91c9cc6040b7fc1e8c320d665a095b79d656e16a476dc3583dff94ac329`
- `index_cyberpunk.html`: `35ab348006b16f2ede16fc2289b49cbeb4a2a3ea4e16038b249927353c8a10e9`

---

## 2. GIẢI QUYẾT TRIỆT ĐỂ BA BLOCKER CỐT LÕI (A, B, C) TỪ CODEX 15:25

### BLOCKER A: Tách biệt Rạch ròi Hạn mức Khởi động (3.5s) vs Cửa sổ Preflight 10.0s
- **Pha 1 (Khởi động Chẩn đoán - Giai đoạn 0, 1, 2):**
  - Bắt buộc nhận diện chuỗi boot banner, chuỗi quét bus I2C, và xác nhận địa chỉ I2C hợp lệ (`0x01..0x7F`) trong vòng `STARTUP_DEADLINE_S = 3.5s` kể từ khi bắt đầu.
- **Pha 2 (Tích lũy Preflight - Giai đoạn 3):**
  - **Hủy bỏ hoàn toàn hạn mức 3.5s** một khi đã bước vào Giai đoạn 3 (Post-Diagnostic Settling).
  - Cửa sổ Preflight thu thập chuỗi **liên tục 10.0s / 80 mẫu tin D0 DISARMED zero** ($PWM=0, RPM=0, targets=0, v=0, w=0, gap \le 0.5\text{s}$) mà không bao giờ bị ngắt lỗi oan bởi hạn mức 3.5s chẩn đoán!

### BLOCKER B: Khóa chặt Mốc Thời gian Ghi cho Từng Tác vụ STOP (Second-Op Fix)
- Mỗi tác vụ STOP mới (`request_stop`) cấp phát một `stop_op_id` tăng đơn điệu và **reset ngay lập tức `stop_write_complete_mono = 0.0`**.
- Cửa sổ xác nhận dừng yêu cầu: `state.stop_op_id == op_id` VÀ `now >= state.stop_write_complete_mono > 0.0`.
- Triệt tiêu hoàn toàn lỗ hổng ở tác vụ dừng thứ hai: Nếu tác vụ dừng mới bị lỗi ghi hoặc chưa ghi xong, hệ thống tuyệt đối không bao giờ lấy mốc thời gian ghi của tác vụ dừng cũ để xác nhận dừng ảo!

### BLOCKER C: Công bố Ngay Lập tức Lỗi Công khai khi Ghi STOP Thất bại / Thiếu Byte
- Khi phát hiện việc ghi lệnh STOP bị thiếu byte (Partial Write) hoặc lỗi cổng UART $\implies$ Hệ thống lập tức thiết lập:
  - `state.stop_write_fault = True`
  - `state.fault_code = err_msg` (ví dụ `PARTIAL_STOP_WRITE: 1/6`)
  - `state.first_fault_reason = err_msg`
  - Chuyển trạng thái sang `FAULT_STOP`.
- Phản hồi HTTP 500 trung thực và cập nhật ngay vào `/api/telemetry`, không bao giờ để `fault_code: null` khi đã có lỗi ghi thực tế.

---

## 3. BẰNG CHỨNG KIỂM THỬ TỰ ĐỘNG HARNESS V4.10
Lệnh thực thi: `python test_bundle_v4_10_production.py`  
Kết quả (Exit Code 0):
```text
=== STARTING PRODUCTION INTEGRATED HARNESS V4.10 ===

[SUITE 1] Blocker A - Diagnostics Deadline (3.5s) vs Post-Diagnostic Preflight...
-> PASS: Blocker A resolved - Diagnostics deadline and 10s preflight cleanly separated.

[SUITE 2] Blocker B - Operation-bound write completion (Second-op fix)...
-> PASS: Blocker B resolved - Second operation resets completion timestamp and prevents false confirmation.

[SUITE 3] Blocker C - Immediate Public Fault Commit on Partial/Failed STOP...
-> PASS: Blocker C resolved - Partial write immediately committed public FAULT and first_fault_reason.

[SUITE 4] Dedicated Tuning Error Rejection...
-> PASS: INVALID_TUNING_RANGE cleanly mapped to REJECTED without FAULT_STOP.

[SUITE 5] Typed Scan/Map/TF & Map Origin NaN Validation...
-> PASS: NaN map origin cleanly caught and held safely at V 0.00 0.00.

[SUITE 6] Bounded Cleanup...
-> PASS: All threads cleanly terminated.

========================================================
ALL 6 CRITICAL PRODUCTION INTEGRATION SUITES PASSED (100% OK)
========================================================
```

---

## 4. BẢO TỒN NGUYÊN TRẠNG HIỆN TRƯỜNG PHẦN CỨNG
- Raspberry Pi 4 (`100.90.252.15`) sau lần reboot (`boot ID 1a219e09-b897-49c1-b0e3-a1649833aaf7`) được giữ nguyên trạng thái tĩnh hoàn toàn.
- Cổng `/dev/ttyUSB0` chưa mở, động cơ xe đặt an toàn trên sàn phòng Lab.
- Không có bất kỳ lệnh cấp điện, ARM hay ghi flash nào được phát ra khi chưa có lệnh phê duyệt chạy thực địa.
