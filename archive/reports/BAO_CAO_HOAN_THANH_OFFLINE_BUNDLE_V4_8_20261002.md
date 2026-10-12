# BÁO CÁO TOÀN DIỆN VỀ BẢN BÀN GIAO OFFLINE INTEGRATION BUNDLE V4.8 (ĐỐI SOÁT CODEX QA 14:58)

> **Thời gian:** 02/10/2026 15:30 (Asia/Bangkok)  
> **Người thực hiện:** Khang AI Assistant (Hardware Owner duy nhất)  
> **Người giao việc/Review:** Codex QA  
> **Tài liệu đối soát trỏ tới:** `DOI_SOAT_BUNDLE_V4_7_AGV_20261002_1458.md`  
> **Artifact Snapshot V4.8:** `candidate_agv_unified_brain_v4_8.py`  
> **Artifact Harness V4.8:** `test_bundle_v4_8_production.py`  
> **Artifact UI HTML:** `index_cyberpunk.html`

---

## 1. THẨM ĐỊNH SHA-256 ARTIFACTS
- `candidate_agv_unified_brain_v4_8.py`: `6034babff1c72211c20b01624cbe7b433686f3993f2eff554759ceb560b1bd9e`
- `test_bundle_v4_8_production.py`: `dce8f45af7d05a6b1d16414415e0c5b2210938f648ac959a9fdbfc5bfd74dd95`
- `index_cyberpunk.html`: `35ab348006b16f2ede16fc2289b49cbeb4a2a3ea4e16038b249927353c8a10e9`

---

## 2. GIẢI QUYẾT TRIỆT ĐỂ BA RESIDUAL CỐT LÕI (A, B, C) TỪ CODEX 14:58

### RESIDUAL A: Khởi động tuần tự nghiêm ngặt (Audited Startup FSM)
- **Tiến trình 4 giai đoạn tuần tự bắt buộc:**
  - `Giai đoạn 0`: Chờ nhận diện chuỗi boot banner chính xác: `{"info":"ESP32 Robot Ready - BENCH SERIAL ONLY (WiFi DISABLED)"}`.
  - `Giai đoạn 1`: Chờ nhận diện chuỗi quét bus I2C: `{"info":"Scanning I2C bus..."}`.
  - `Giai đoạn 2`: Chờ tìm thấy thiết bị I2C hợp lệ (`"i2c_found"` hoặc `"vin_mv"`). Nếu nhận được `{"error": ...}` $\implies$ Lập tức báo lỗi phần cứng và reset về 0.
  - `Giai đoạn 3`: Pha ổn định tín hiệu $\rightarrow$ **Chỉ bắt đầu tích lũy bộ đếm Preflight (10.0s / 80 mẫu DISARMED zero) SAU KHI đã hoàn tất giai đoạn 2**.
- Tuyệt đối loại bỏ nguy cơ nhận diện ngược thứ tự hoặc chấp nhận các mẫu tin telemetry gửi trước khi quét I2C hoàn tất.

### RESIDUAL B: Khóa hàng đợi ghi đơn chủ & Ưu tiên phát STOP lập tức
- Khi luồng đọc UART phát hiện gói tin lỗi phần cứng (`error` hoặc `fault`), hệ thống **chiếm ngay khóa `tx_lock`**, lập tức phát chùm 3 lệnh `STOP\r\n` vật lý ra cổng Serial, chuyển FSM sang `FAULT_STOP`, hạ `is_moving = False` và chốt chặn `latched_stop = True`.
- Mọi lệnh điều khiển di chuyển ($V$) đang chờ hoặc đến sau đều bị chặn đứng và từ chối ngay lập tức tại chốt khóa ghi (`REJECTED_LATCHED_STOP`).

### RESIDUAL C: Tách biệt rạch ròi ZERO_OBSERVED vs STOP_CONFIRMED & Quản lý ID tác vụ
- **Quản lý theo ID tác vụ (`stop_op_id`):** Chỉ những lệnh dừng chủ động được người dùng hoặc hệ thống phát ra kèm ID tác vụ hợp lệ mới có quyền chuyển trạng thái sang `STOP_CONFIRMED`.
- **Phân biệt `ZERO_OBSERVED`:** Khi xe bị chốt dừng do lỗi phần cứng hoặc dừng tự nhiên, việc quan sát thấy gói D0 zero chỉ được ghi nhận là `ZERO_OBSERVED`, tuyệt đối không tự nhận là `STOP_CONFIRMED` khi chưa có tác vụ dừng được phát ra.
- **Bảo toàn lỗi ghi (`WRITE_FAULT`):** Nếu việc phát lệnh `STOP` bị lỗi ghi hoặc ghi thiếu byte, hệ thống giữ nguyên cờ lỗi `stop_write_fault = True`, ngăn chặn việc gói tin D0 zero vô tình xóa mất lỗi phần cứng.

---

## 3. BẰNG CHỨNG KIỂM THỬ TỰ ĐỘNG HARNESS V4.8
Lệnh thực thi: `python test_bundle_v4_8_production.py`  
Kết quả (Exit Code 0):
```text
=== STARTING PRODUCTION INTEGRATED HARNESS V4.8 ===

[SUITE 1] Residual A - Sequential Startup FSM Validation...
-> PASS: Residual A satisfied - Sequential Startup FSM cleanly enforced.

[SUITE 2] Residual B - Priority STOP bursts under tx_lock on Hardware Error...
-> PASS: Residual B satisfied - Priority STOP bursts delivered under lock and in-flight drive rejected.

[SUITE 3] Residual C - Operation Tracking: ZERO_OBSERVED vs STOP_CONFIRMED...
-> PASS: Unrequested zero D0 records ZERO_OBSERVED without falsely marking STOP_CONFIRMED.
-> PASS: Persistent write failure preserves WRITE_FAULT and prevents false confirmation.

[SUITE 4] Typed Scan/Map/TF & Map Origin NaN Validation...
-> PASS: NaN map origin cleanly caught and held safely at V 0.00 0.00.

[SUITE 5] Bounded Cleanup...
-> PASS: All threads cleanly terminated.

========================================================
ALL 5 CRITICAL PRODUCTION INTEGRATION SUITES PASSED (100% OK)
========================================================
```

---

## 4. BẢO TỒN NGUYÊN TRẠNG HIỆN TRƯỜNG PHẦN CỨNG
- Raspberry Pi 4 (`100.90.252.15`) sau lần reboot (`boot ID 1a219e09-b897-49c1-b0e3-a1649833aaf7`) được giữ nguyên trạng thái tĩnh hoàn toàn.
- Cổng `/dev/ttyUSB0` chưa mở, động cơ xe đặt an toàn trên sàn phòng Lab.
- Không có bất kỳ lệnh cấp điện, ARM hay ghi flash nào được phát ra khi chưa có lệnh phê duyệt chạy thực địa.
