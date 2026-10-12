# Một bài thử chuyển động ngắn — 02/10/2026, 10:28 Asia/Bangkok

Khang đã trực tiếp yêu cầu chạy và vừa xác nhận: **khu quanh xe trống ít nhất1,5m và đang có người trực công tắc nguồn**. Không xin lại quyền chạy chung.

## Phạm vi được chấp thuận

Khang AI Assistant là hardware/Serial owner duy nhất. Cho phép **đúng MỘT invocation** của production runner mới bên dưới, gồm OPEN→startup+10sD0fresh→ARMreq/ACK/freshARMED→motion ngắn→STOP/freshzero→cleanup. Nếu bất kỳ bước nào FAIL thì dừng bài, không retry, không reARM/CLEAR_FAULT.

Snapshot phải đúng:

- runner: `15cdfc6c6d86582df3ae219b8f301eb1dbb7bbdd0da742d43052242cda50f928`
- gate: `6f4a2106622e99fe60212199b621cdcbbd2a76b2e639519796b15d5a703e3d1d`
- Giữ firmware `f5bf29a16ea297d746e7a18f14f66cd6bb2dab4d47b8a474a9e11aa956505050` và supervisor cũ `1bd402dda54d20609239d72cb980af79d985870253af33383dd26876c1636bfd`, không flash hoặc ghi đè. Sourcehash không chứng minh flashedbinary; không phát biểu ngược.

Parent QA source15cdf stable: `review_runner_bundle_20261002_1024.json`, `review_runner_deadlines_20261002_1024.json`, `review_partial_stop_protocol_20261002_1024.json`, `review_runner_exact_profile_20261002_1026.json`. Actual productionpath/FakeUART clock thật: freshpostdiag10s80; thiếufound/late/unsafe noARM; profile .04/1/1.5 normalexit0/STOPconfirmed/reader+watchdogjoined/closed; partialSTOP+independentfreshzero exit1/FAULT/unconfirmed, không PASS. No-caller component xác nhậnSTOP độc lập. Đây là QA offline, không physicalmotion proof, không fullROS/SLAM/map/home proof. Helper `--mock` có đường callback khác production; không dùng output đó thay fullentry QA hoặc báo100%.

## Chuẩn bị và lệnh cụ thể

SCP đúng hai source được review vào thư mục MỚI `/home/khangho/agv_trial_20261002_1028/`, không ghi đè checkout/runner/firmware/supervisor đang có. Hash tại Pi trước/sau phải khớp. Lưu manifest Python/boot/uptime/tool IDs và backup/rollback là giữ nguyên bản hiện có. Không sửa config/gain/PWM/gate limit. QA import/`--mock` OFFLINE tại Pi3.12.3 được phép; kết quả này chỉ xác nhận môi trường/helper, không motorproof.

Ngay trước invocation: ghi visible AGV processes đầy đủ; không ROS/brain/bridge/launcher/logger khác. `fuser /dev/ttyUSB0` phải exit1/stdout+stderr trống; exit2 hoặc stdout/stderr lạ không được che bằng `||true`. Kiểm tra nguồn/mặt sàn/đánh dấu vị trí và thước đo ở ngoài đường bánh xe. Giữ người trực nguồn trong toàn bài. Không dùng D009:00 thay freshpreflight hiện tại; runner phải giữ cùng một owner/transport qua preflight→ARM.

Thư mục output MỚI `/home/khangho/evidence_motion_live_20261002_1028/`; stdout/stderr unique/noclobber, không dùng một log đã tồn tại. Invocation được duyệt:

```sh
/usr/bin/timeout --kill-after=2s 30s /usr/bin/python3 -X utf8 /home/khangho/agv_trial_20261002_1028/agv_motion_supervisor_runner.py --port /dev/ttyUSB0 --baud 115200 --target-v 0.04 --nominal-time 1.0 --hard-time-cap 1.5 --output-dir /home/khangho/evidence_motion_live_20261002_1028
```

Wrapper phải giữ exit thật và báo nonzero nguyên vẹn. Không nối lệnh chạy lần nữa khi FAIL. Vận tốc là **0,04m/s**, không phải140–150RPM. Gia tốc ramp làm tích phân lệnh khác40mmexact; ODOM không physicalhardcap. Đo quãng đường/hướng thật độc lập và đối chiếu rawRX/TX/ODOM/RPM/PWM; có đứng yên cũng báo thật, không nâng PWM chữa mù.

Continuous Pi reader/watchdog phải hiện diện trước ARM và trong motion. STOP confirmation mục tiêu<=200ms; source Pi telemetry-loss guard250ms, MCU source CMD_TIMEOUT_MS300ms, không ghi200msMCU. Nếu mất telemetry, chuyển động bất thường, STOPwrite lỗi/unconfirmed, process chết hoặc không xác nhận dừng: hardware owner STOP/DISARM nếu còn đường điều khiển và người trực ngắt nguồn ngay khi không xác nhận dừng. Không coi timeout kill là motorSTOP.

Sau bài: rawRX/TX, hash/filefinalstatus, request/write/freshconfirmedtimings, ARM/V/STOP counts, sample freshness, physicaldistance/heading, postcloseprocess/owner. PASS_MOTION_VERIFIED trong code chỉ phản ánh workflow/STOP của runner; mục tiêu tracking/phòng/map/home chưa nghiệm thu. Target140–150RPM còn trong lộ trình đo/STOPmargin riêng, không tự nâng tốc sau bài này.

Đây là chấp thuận mới MỘT bài cụ thể, không tái sử dụng quyền STATIC08:57. Khi bắt đầu invocation đánh dấu quyền USED; không có phần mở rộng tự động.
