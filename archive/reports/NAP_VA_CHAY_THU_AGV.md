# QUY TRÌNH NẠP VÀ CHẠY THỬ AGV (BENCH TEST CÓ KIỂM SOÁT)

- **Mục tiêu:** Thực hiện nạp bản build bench an toàn và chạy thử ngắn có kiểm soát (thẳng $\le 0.10\text{ m}$, $v \le 0.05\text{ m/s}$ trong tối đa 2.0s).
- **Trạng thái an toàn bắt buộc:**
  - Có người trực tại chỗ sẵn sàng ngắt nguồn pin khẩn cấp nếu có bất thường.
  - Khu vực sàn thử nghiệm đã được dọn sạch chướng ngại vật.
  - Nguồn Wi-Fi/Web Controller bị ngắt hoàn toàn (`BENCH_SERIAL_ONLY = 1`). Chỉ duy nhất một tiến trình supervisor qua cổng Serial `/dev/ttyUSB0` được phép phát lệnh.

---

## 1. THÔNG SỐ VÀ MÃ BĂM BẢN BUILD NẠP

| Thành phần | Đường dẫn | Mã băm SHA-256 |
| :--- | :--- | :--- |
| **Source main.cpp** | `robot_stm32_f103/src/main.cpp` | `5c600ead25649813084440af0eec802a17bde3786f0d0bb2109c8fdbf8a0baea` |
| **Source mke_m18.cpp** | `robot_stm32_f103/src/mke_m18.cpp` | `adc5ac877c81ece09c69539fb3b53ce28ebe2471a0aaf42f9ffa2376bf17e985` |
| **Firmware Binary (BENCH)** | `robot_stm32_f103/.pio/build/esp32dev/firmware.bin` | `7743a41d7ca27fbb98a82790e04f9f3689bdde14610c239e4f4322164edee42a` |
| **Cấu hình Flash Offset** | `0x1000: bootloader.bin`, `0x8000: partitions.bin`, `0x10000: firmware.bin` | Tốc độ nạp khuyến nghị: 460800 baud |

---

## 2. KẾT QUẢ KIỂM THỬ TRỰC TIẾP TRÊN MÃ NGUỒN THẬT (TRUE SOURCE HARNESS)

- **Tệp harness chạy thật:** `test_extracted_source_harness.cpp` (nhúng trực tiếp hàm nguồn thật từ `main.cpp` và `mke_m18.cpp`).
- **Lệnh thực thi:** `g++ -O2 /tmp/test_extracted_source_harness.cpp -o /tmp/run_harness && /tmp/run_harness`
- **Exit code:** `0`
- **Output ghi nhận thực tế:**
  ```text
  === RUNNING TRUE SOURCE HARNESS (SOURCE HASH: 5c600ead25649813...) ===
  [PASS 1/8] Boot DISARMED strictly rejects V command
  [PASS 2/8] Strict token matching accepts ARM, blocks ARMxxx
  [PASS 3/8] Heartbeat timeout correctly triggers DISARM after 350ms
  [PASS 4/8] Millis() rollover handled accurately without false trigger
  [PASS 5/8] Motor write gated to 0 in DISARMED state
  [PASS 6/8] I2C Latch fault halts Motor B, prevents re-ARM, verifies bus before clear
  [PASS 7/8] Tuning parameter validation strictly blocks out-of-range & NaN
  [PASS 8/8] Blocking SCAN and Odometry RESET rejected in ARMED state
  === ALL 8/8 TESTS ON ACTUAL EMBEDDED LOGIC PASSED! ===
  ```

---

## 3. CÁC BIỆN PHÁP AN TOÀN TRONG KỊCH BẢN GIÁM SÁT STRICT V3
- **Tập tin giám sát duy nhất được duyệt:** `/home/khangho/agv_motor_bench_supervisor_strict_v3.py`
  - **Mã băm SHA-256:** `1bd402dda54d20609239d72cb980af79d985870253af33383dd26876c1636bfd`
  - **Cấu hình Firmware nạp tương thích:** `firmware_f5bf.bin` (SHA-256: `f5bf29a16ea297d746e7a18f14f66cd6bb2dab4d47b8a474a9e11aa956505050`).
- **Quy tắc kiểm soát nghiêm ngặt:**
  1. Boot an toàn: Bắt buộc $\ge 3$ mẫu liên tiếp `safety = DISARMED`, `target = [0.0, 0.0]`, `PWM = [0, 0]`, `RPM = [0.0, 0.0]` sau mốc $elapsed \ge 3.0\text{ s}$.
  2. Baseline Reset an toàn: Lấy mốc tọa độ $(x_0, y_0, \theta_0)$ ngay trước lệnh ARM đầu tiên.
  3. Giới hạn vận tốc mềm: $v \le 0.05\text{ m/s}$ (thẳng), thời gian tối đa $2.0\text{ s}$.
  4. Giới hạn quãng đường cứng (Max Displacement): Tối đa $\le 0.10\text{ m}$ (10 cm). Nếu vượt ngưỡng lập tức ngắt khẩn cấp và đánh dấu FAIL.
  5. Watchdog kiểm tra độ tươi dữ liệu (Telemetry Freshness): Nếu không nhận được telemetry mới trong 250 ms $\rightarrow$ Tự động ngắt STOP và DISARM.
  6. Khối `finally` bảo đảm phát `STOP` và `DISARM`, giải phóng khóa độc quyền cổng Serial.

---

## 4. KỊCH BẢN THỰC THI VÀ NGUYÊN TẮC KHÔNG RERUN KHI THẤT BẠI

* **Bước 1: Nạp Firmware Bench được duyệt (`firmware_f5bf.bin`):**
  Chuyển `firmware_f5bf.bin` sang Pi và flash qua `esptool.py` vào cổng `/dev/ttyUSB0` tại offset `0x10000`.
* **Bước 2: Xác minh sau Boot (Preflight):**
  Đọc $\ge 10$ gói tin Serial thô, xác nhận:
  - `safety`: `DISARMED`
  - `l_tgt`: `0.0`, `r_tgt`: `0.0`, `l_pwm`: `0`, `r_pwm`: `0`
  - Gửi thử `V 0.05 0.0`, `S 50 50`, `M 100 100` $\rightarrow$ Xác nhận chip từ chối với `DISARMED_REJECT_*`.
* **Bước 3: Chạy bài thử thẳng ngắn:**
  Chạy `python3 /home/khangho/agv_motor_bench_supervisor_strict_v3.py` (vận tốc $0.05\text{ m/s}$ trong tối đa 2.0s, quãng đường tối đa 10 cm).
* **Bước 4: Kiểm tra dừng và báo cáo raw log:**
  Trích xuất file log `/home/khangho/agv_bench_run.log` kiểm tra RPM sau khi dừng đã về 0.0.
* **QUY TẮC KHÓA AN TOÀN (NO RERUN RULE):**
  Nếu kết quả bài chạy bị đánh giá **FAIL** (như trường hợp `MOTION_TRACKING FAIL` tại bài chạy 13:57), **TUYỆT ĐỐI KHÔNG CHẠY LẠI (KHÔNG RERUN)**, không tự ý nạp đè firmware hoặc phát lệnh ARM. Xe phải được giữ nguyên ở trạng thái `DISARMED` (phần mềm ngừng phát xung điều khiển) để phục vụ phân tích nguyên nhân offline. Mọi lần chạy tiếp theo đều phải được lập kế hoạch và có sự phê duyệt độc lập từ Codex.

---

## 5. KẾT QUẢ ĐỐI SOÁT BÀI CHẠY THỰC TẾ (BENCH RUN 13:57)

- **Trạng thái nạp & Preflight:** PASS (Binary SHA256: `f5bf29a16ea297d746e7a18f14f66cd6bb2dab4d47b8a474a9e11aa956505050`).
- **An toàn dừng (Stop & Disarm):** `STOP_OBSERVED` PASS GIỚI HẠN (Lệnh STOP đầu lúc 5419.4443s -> mẫu DISARMED 0 RPM đầu lúc 5419.5387s = 94.4ms; mẫu 3 đạt lúc 5419.7386s = 294.3ms).
- **Chức năng bám vết chuyển động:** `MOTION_TRACKING` **FAIL / CHƯA ĐẠT**.
  - **Kỳ vọng lý thuyết:** Lệnh `V 0.05 0.0` trong 2.0065s dự kiến di chuyển xấp xỉ ~0.10 m (10 cm).
  - **Thực tế đo được trên Odometry:** Chỉ đạt $0.0020\text{ m}$ (2 mm, tức ~2% so với mục tiêu).
  - **Phân tích Telemetry:** Trong 20 mẫu chu kỳ RUN, có đến 18/20 mẫu cả hai bánh đều 0.00 RPM dù Target đặt 13.0 RPM.
  - **Đỉnh RPM & PWM:** Đỉnh bên trái chỉ đạt 5.12 RPM, bên phải 2.56 RPM; PWM tăng dần từ 14 lên 49 (Trái) và 51 (Phải). Chu kỳ heartbeat thực tế ~100ms.
- **Kết luận:** Hệ thống dừng và giải giáp an toàn được chứng minh trong phạm vi thử nghiệm, nhưng **chức năng chạy và điều khiển chuyển động CHƯA ĐẠT** do lực kéo PWM < 50 chưa thắng được ma sát tĩnh/hộp số hoặc cấu hình PID/Feedforward chưa tối ưu. Cần phân tích và cân chỉnh offline. Tuyệt đối không tự ý tăng xung/vọt tốc.
