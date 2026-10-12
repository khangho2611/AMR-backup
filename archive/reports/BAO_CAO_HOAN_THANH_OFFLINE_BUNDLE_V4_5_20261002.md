# BÁO CÁO TOÀN DIỆN VỀ BẢN BÀN GIAO OFFLINE INTEGRATION BUNDLE V4.5 (ĐỐI SOÁT CODEX QA 14:23)

> **Thời gian:** 02/10/2026 14:50 (Asia/Bangkok)  
> **Người thực hiện:** Khang AI Assistant (Hardware Owner duy nhất)  
> **Người giao việc/Review:** Codex QA  
> **Tài liệu đối soát trỏ tới:** `DOI_SOAT_BUNDLE_V4_4_AGV_20261002_1423.md`  
> **Artifact Snapshot V4.5:** `candidate_agv_unified_brain_v4_5.py`  
> **Artifact Harness V4.5:** `test_bundle_v4_5_production.py`  
> **Artifact UI HTML:** `index_cyberpunk.html`

---

## 1. THẨM ĐỊNH SHA-256 ARTIFACTS
- `candidate_agv_unified_brain_v4_5.py`: `d9c1a1b677d0380eb3ce53cf048a4fb88798f35704f7cf02f454296bed1e5c1a`
- `test_bundle_v4_5_production.py`: `661e4015f86afa68e055322e340f97382b5322d6d65bf2aa9c1e946d860110dc`
- `index_cyberpunk.html`: `35ab348006b16f2ede16fc2289b49cbeb4a2a3ea4e16038b249927353c8a10e9`

---

## 2. GIẢI QUYẾT TRIỆT ĐỂ BA SEAMS CỐT LÕI CỦA CODEX 14:23

### SEAM 1: Strict Collector 4b32 Validator & Startup FSM
- **Forbidden Mixed Keys**: Kiểm tra danh sách khóa cấm `["error", "fault", "info", "ack", "status_msg"]`. Bất kỳ gói tin telemetry nào mang lẫn khóa lỗi (ví dụ `error="I2C_FAULT"`) đều bị loại bỏ ngay lập tức, không tăng bộ đếm preflight và không mở chốt stop.
- **Hợp đồng Preflight 10.0s / 80 mẫu hữu cơ**: Bắt buộc ghi nhận liên tục $\ge 80$ gói tin D0 ở trạng thái `DISARMED`, khoảng cách các mẫu $gap \le 0.5\text{s}$, tuổi mẫu cuối $\le 0.5\text{s}$, và toàn bộ các trường $l\_tgt=0, r\_tgt=0, l\_pwm=0, r\_pwm=0, |l\_rpm|\le 10^{-3}, |r\_rpm|\le 10^{-3}, |v|\le 10^{-4}, |w|\le 10^{-4}$ trong thời gian $\ge 10.0\text{s}$ đơn điệu.
- **Tại thời điểm gửi lệnh ARM (At-write Lock)**: Kiểm tra lại toàn diện trạng thái preflight, nếu vi phạm sẽ từ chối ngay lập tức (`REFUSED_PREFLIGHT_NOT_MET`).

### SEAM 2: Shared STOP Engine & Phân biệt Observed vs Confirmed D0 Zero
- **Phát hiện lỗi Partial Write**: Nếu lệnh $V$ chỉ ghi được một phần byte $\implies$ Lập tức gọi `_fire_physical_stop_internal()` bắn chùm 3 lệnh `STOP\r\n` vật lý, khóa chốt `latched_stop = True`, chuyển FSM sang `FAULT_STOP` và hạ `is_moving = False`.
- **Giám sát Dừng khẩn cấp**: Lệnh STOP phân biệt rõ ràng giữa **OBSERVED** (nhìn thấy có gói tin sau lệnh) và **CONFIRMED** (gói tin D0 mới xác nhận $PWM=0, RPM=0$ và $safety == \text{DISARMED}$).
- **Watchdog độc lập cho MỌI chuyển động**: Luồng giám sát bất đồng bộ chạy chu kỳ $50\text{ms}$ tự động phanh dừng xe trong vòng $0.5\text{s}$ nếu mất dữ liệu LiDAR hoặc Telemetry D0, áp dụng cho cả chế độ lái tay (Manual) lẫn tự hành (Auto).

### SEAM 3: Typed Scan/Map/TF & An toàn Hình học Standoff
- **Bảo vệ Ma trận Bản đồ**: Kiểm tra chặt chẽ độ phân giải $res > 0.001$, kích thước $w > 1, h > 1$ và $len(grid) == w \times h$. Với bản đồ dị dạng hoặc độ phân giải $0$, hệ thống tự động giữ vị trí an toàn `V 0.00 0.00`, tuyệt đối không gây lỗi chia cho 0 (`ZeroDivisionError`) hay nhảy trạng thái hoàn thành ảo.
- **Bán kính góc ngoài thân xe ($0.1885\text{m}$) & Standoff an toàn**: Tính toán chính xác theo công thức hình học từ tài liệu Word của Khang:
  $$R_{\text{corner}} = \sqrt{(0.1875/2)^2 + (0.28/2)^2} + 0.02\text{m} = \mathbf{0.1885\text{ m}}$$
  Toàn bộ thân xe khi lập kế hoạch đường đi luôn nằm 100% trong vùng tự do đã biết (known free space).
- **Return To Home chuẩn xác**: Khóa tọa độ gốc $(x_0, y_0, \theta_0)$ trước chuyển động đầu tiên; trạng thái `COMPLETED` chỉ được công bố khi đạt cự ly $d < 12\text{cm}$, góc hướng $|\Delta\theta| < 0.15\text{ rad}$ VÀ đã xác nhận lệnh STOP dừng hẳn bánh xe.

---

## 3. BẰNG CHỨNG KIỂM THỬ TỰ ĐỘNG HARNESS V4.5
Lệnh thực thi: `python test_bundle_v4_5_production.py`  
Kết quả (Exit Code 0):
```text
=== STARTING PRODUCTION INTEGRATED HARNESS V4.5 ===

[SUITE 1] Collector 4b32 Pure Telemetry & Forbidden Keys...
-> PASS: Mixed payload with forbidden key ('error') strictly rejected.

[SUITE 2] Strict Preflight Contract Validation...
-> PASS: ARM refused before 80 samples and 10.0s preflight.
Feeding continuous preflight zero samples...
-> PASS: Preflight contract satisfied organically -> ARM Handshake succeeded.

[SUITE 3] Partial Write on V bursts physical STOP and latches FAULT...
-> PASS: Partial write fault immediately fired physical STOP bursts and latched FAULT_STOP.

[SUITE 4] Release Latch Preconditions...
-> PASS: Latch release strictly enforces full zero-motion DISARMED contract.

[SUITE 5] Map with Res 0 / Malformed Data Safe Holding...
-> PASS: Map with res 0 cleanly handled by holding safe position without ZeroDivisionError.

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
