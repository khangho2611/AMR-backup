# Đối soát ZIP, khai báo chân và phiên test không chuyển động

02/10/2026 20:08 Asia/Bangkok. Codex trực tiếp, không giao bot. Người dùng báo không thấy xe di chuyển và yêu cầu đọc `C:/Users/Khang/Downloads/robot_stm32_f103.zip`.

## Khai báo thực trong ZIP

ZIP SHA256 `4078ffb4f166833366187a2ae3fe4b6f0e49dc4fdfb7a8973e4aafc6a419341c`. Mã chọn mặc định bởi `platformio.ini` là `esp32dev`, Arduino/espressif32, thư mục `src`; tên ZIP không chứng minh đây là firmware STM32 đang chạy.

| Chức năng | ESP32 `src` | STM32 HAL `Core` |
|---|---|---|
| Driver MKE-M18 SDA / SCL | GPIO21 / GPIO22 | PB7 / PB6 |
| Encoder trái A / B | GPIO18 / GPIO19, PCNT0 | PA0 / PA1, TIM2 |
| Encoder phải A / B | GPIO25 / GPIO26, PCNT1 | PA6 / PA7, TIM3 |
| Ngõ driver cho bánh trái | Motor A | Motor B |
| Ngõ driver cho bánh phải | Motor B | Motor A |
| MPU6050 SDA / SCL | GPIO16 / GPIO17, Wire1 | Không suy từ nhánh ESP32 |

`src/robot_motor.cpp` và `Core/Src/robot_motor.c` thực sự gọi ngõ motor ngược nhau. Điều này cần đối chiếu dây vật lý khi chẩn đoán trái/phải; chưa phải bằng chứng dây xe sai. Motor được điều khiển qua I2C MKE-M18, không phải các GPIO PWM riêng từ ESP32.

Sáu GPIO driver/encoder của ZIP khớp nguồn local hiện tại. ZIP có MPU6050; nguồn firmware BENCH hiện tại không khai báo/khởi tạo MPU ở GPIO16/17. Đây không phải đường lệnh motor. `main.cpp` ZIP SHA `ad0e263076bdc8738fe8c4e4a107d20a8855ebe9dbe56cf130db19eb341d2db4`, khác nguồn BENCH local SHA `52ccb6c7646a075087e274b09e8e228ef2364cf000623bb66377b2181bdfe231`. ZIP không thay thế nguyên trạng: giao thức, watchdog và ARM của các phiên bản khác nhau.

Local `.pio/build/esp32dev/firmware.bin` vẫn SHA `f5bf29a16ea297d746e7a18f14f66cd6bb2dab4d47b8a474a9e11aa956505050`, khớp artifact được nạp trong báo cáo 01/10. Đối soát này không đọc lại binary MCU, không chứng minh flash hiện tại bằng source hash.

Chứng cứ source trích nguyên byte, manifest và phép kiểm sáu GPIO: `evidence_agv_20261001/codex_pin_audit_20261002_200807/`. Không chạy mã trong ZIP, không flash hay sửa GPIO.

## Trạng thái thật sau test

HTTP đọc 20:04:54: `trial_used=true`, `armed=false`, `latched=true`, `fault=TELEMETRY_TIMEOUT`, `auto=false`, `stop_op=17`, `stop_write_ok=true`, `stop_confirmed=true`. Fresh D0 DISARMED/PID, cả target/PWM/RPM/v/w bằng 0, x/y/th bằng 0. Người dùng trực tiếp xác nhận không thấy xe chuyển động. Phiên ARM đã tiêu thụ; checkpoint 19:58 `trial_used=false` đã hết hiệu lực.

50 HTTP mẫu chỉ đọc đến 20:06:49: mọi D0 DISARMED exact zero, mọi mẫu STOP confirmed; max D0 age 98.18ms. Đây là cửa sổ sau lỗi, không tái hiện đoạn gián đoạn khi ARMED. `TELEMETRY_TIMEOUT` trong source là watchdog Pi thấy D0 quá 250ms hoặc tuổi âm; không phải tự động chứng minh mạng web mất kết nối hay encoder/driver hỏng.

Snapshot radar: 360 bins, không bin0, min dương .55925m, không bin dưới .35m; phép kiểm khoảng trống xoay của snapshot đạt. Điều này không chứng minh scan liên tục trong phiên đã chạy.

Pi chỉ đọc: boot `305c4d73-736c-4871-968d-a84b997be21e`, controller 14214 vẫn là owner USB0, sáu file manifest triển khai đều OK. Brain log chỉ có startup, không có RX/TX timeline hoặc timestamp first fault. Không thể kết luận V đã tới MCU, PWM có tăng trong phiên, hay độ dài gián đoạn đã gây lỗi từ log này. Trạng thái sau STOP không thay chứng cứ trong chuyển động.

Chứng cứ: `codex_deploy_prep_20261002_1915/operator_status_20261002_200454.json`, `idle_http_readonly_20261002_200649.json`. Không gửi STOP trùng khi trạng thái đã xác nhận dừng, không Serial OPEN cạnh tranh, không ARM/retry/CLEAR_FAULT/deploy/flash/gain/PWM/PID.

## Bước sửa tiếp theo

Ưu tiên thêm chẩn đoán offline vào owner hiện có: timestamp RX D0, full-byte TX, quyết định V/reason bị từ chối, tuổi D0/scan/caller ngay first fault và bounded event history. Cần kiểm thử history giữ first cause và không thay timeout/ARM/STOP semantics. Review nguồn/kế hoạch rồi mới thay phiên live và đo bounded khi điều kiện hiện trường hiện tại được xác nhận. Không tăng timeout hoặc PWM để che lỗi chưa rõ nguyên nhân.

Action ARM/reARM/rerun/CLEAR_FAULT/flash ZIP/chỉnh GPIO/gain/PWM: NOT_APPROVED_FOR_NEW_TRIAL. Args USB0/115200, bundle đang chạy 778e+22c4+91b1+ba24. Reason phiên một lần đã dùng, telemetry timeout chưa có timeline nguyên nhân. Đây là QA gate, không automatic approval rejection. Khám phá toàn phòng/map/home position+heading chưa đạt.
