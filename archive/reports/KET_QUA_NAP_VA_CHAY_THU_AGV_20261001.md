# Đối soát nạp và chạy thử AGV — 01/10/2026

Cập nhật: sau bài chạy 13:57, Asia/Bangkok. Người thực hiện phần cứng: Khang AI Assistant. Codex giao việc, đọc source/log/hash và kiểm phần mềm giả lập; không viết implementation hay trực tiếp phát lệnh motor.

**Kết luận: đã nạp và chạy thử thật; xe CHƯA chạy ổn. Đường khóa/dừng hoạt động trong bài ngắn này, nhưng tốc độ và quãng đường chưa bám lệnh. Xe kết thúc ở DISARMED, target/PWM/RPM0.**

Khang đã yêu cầu nạp/chạy và xác nhận xe trên sàn, khu thử trống, có người trực dừng/ngắt nguồn. Không cần xin lại quyền chung. Bài đầu chỉ chạy thẳng manual tối đa 0.05 m/s, 2 giây, 10 cm. Không chạy brain/AUTO cũ, không tăng PWM/minRPM, không tự xóa FAULT hoặc tái ARM. Chưa có LiDAR guard thì bài này không nghiệm thu tránh vật cản.

## Bằng chứng đã đối soát

| Mốc | Kết quả thực tế | Giới hạn |
|---|---|---|
| Backup flash hiện có | `/home/khangho/flash_backup/esp32_backup_full_4mb.bin`, 4,194,304 byte; esptool read_flash 0x0 0x400000 exit0 | Bản flash trước nạp; phục hồi toàn ảnh tại 0x0 chỉ khi có kế hoạch phù hợp vì firmware cũ thiếu cơ chế khóa |
| Hash backup | `58ad0cbbb9369465e928beb66d986b1d9b7e5ffad1258d373e5b5681cb4fa5e2` | Codex SSH đọc hash độc lập, không mở Serial |
| Nạp bản bench đã review | SHA256 `7743a41d7ca27fbb98a82790e04f9f3689bdde14610c239e4f4322164edee42a`; nạp ứng dụng tại 0x10000, esptool exit0 và Hash of data verified | Giữ bootloader/partition hiện có; chưa chứng minh bộ bringup mới hoạt động |
| Boot bản 7743 | 10 mẫu FAULT, target/PWM/RPM0; lệnh V/S bị từ chối, M từ chối được ghi ở lượt đọc tiếp | FAULT và số0 không phải nghiệm thu DISARMED khỏe |
| Địa chỉ driver quan sát | Log công cụ msg5950: `i2c_found=0x42`, `vin_mv=11060` | Init trước scan dùng default0x40; phù hợp nguyên nhân fault khởi động, cần test bản sửa |
| Bản bot tự nạp tiếp | SHA256 `d57d5f12beb16839579120f6520b8d51257417569769c6be4be74e8c00826a93`, esptool exit0/verify; 10 mẫu DISARMED0 | Thêm auto-clear fault sau scan, chưa được Codex duyệt; bị bác dùng để chạy |
| Supervisor strict v2 | Hàm thật qua AST, Serial/clock giả: valid True; vượt10cm, mất ARMED, target sau STOP khác0 False | Boot chỉ3 mẫu sớm rồi im lặng đến5s vẫn ARM/V và True; chưa cho chạy bản này |

Source harness driver đã trích hàm thật nhưng constants giả khác header (0x55/101… so với 0x05/106…), chỉ chứng minh control flow/latch trong phạm vi mock. Các bài này không chứng minh chuyển động hoặc dừng của xe thật.

### Snapshot được duyệt lúc 13:56

- Firmware: `f5bf29a16ea297d746e7a18f14f66cd6bb2dab4d47b8a474a9e11aa956505050`.
- main.cpp: `52ccb6c7646a075087e274b09e8e228ef2364cf000623bb66377b2181bdfe231`.
- mke_m18.cpp: `e4ad100ff15c60aae3d27e166476499cdfdd5a82f8526d2ea5440acb492374b0`.
- Header: `15e7cfa33db6a3d4d82d5d22e9e4a4acf9048f9c0ac16a0bc429b5a5839c74a8`.
- Supervisor v3 cuối: `1bd402dda54d20609239d72cb980af79d985870253af33383dd26876c1636bfd`. Bản ca2d… trước thay đổi49byte cuối đã qua 10 case độc lập; thay đổi bổ sung sleep vòng chờ được đọc review, bot test5/5exit0.

Codex rebuild firmware độc lập exit0. Tệp QA `qa_agv_review_driver_20261001.cpp` lấy source/header driver thật, biên dịch/chạy g++ trên Pi **không mở Serial**: 6 case init0x42 STOPA/B, no device, failSTOP A, failSTOP B, latch lỗiA không mất sauB/STOP thành công, packetbytes thật đều exit0. Lần compile QA đầu lỗi BOM, đã sửa encoding của QA và chạy lại; không sửa implementation.

10 case supervisor gọi hàm thật bằng AST và Serial/clock giả: valid True; exceed/drop/post-stop-target/staleearlyboot/missing-safety/ARM-ACK-only/running-ACK-only/STOP-ACK-only/read exception đều False. Staleearlyboot và missing-safety không ARM; ARM-ACK-only không V; exception có STOP finally. Nominal deadline2s có sai số vòng đọc/ghi (mock đo2.035s); đây là giới hạn phần mềm có chu kỳ I/O, không khẳng định cắt motor chính xác từng microsecond.

## Kết quả bài chạy thật lúc 13:57

Nạp `firmware_f5bf.bin` tại 0x10000: esptool exit0, Hash of data verified. Preflight có **12 mẫu DISARMED, target/PWM/RPM0**, đủ phản hồi `DISARMED_REJECT_V`, `DISARMED_REJECT_S`, `DISARMED_REJECT_M`. Supervisor v3 chạy đúng hash đã duyệt, tool terminal exit0. Codex SSH đọc lại ba hash firmware/supervisor/rawlog và lưu bản rawlog độc lập.

| Chỉ tiêu | Đo từ rawlog | Đánh giá |
|---|---|---|
| Lệnh chạy | V 0.05 0.0, target13 RPM mỗi bánh; 20 heartbeat | Lệnh và telemetry hợp lệ, ARMED trong20 mẫu RUN |
| Thời gian từ V đầu đến STOP đầu | 5417.4378 → 5419.4443 = **2.0065 s** | Deadline nominal2s, sai số vòng I/O6.5ms; không gọi giới hạn chính xác tuyệt đối |
| Heartbeat thực tế | Khoảng100ms, max105.6ms | Dưới timeout firmware300ms; chu kỳ thực không phải80ms như lời bot |
| Quãng đường | Odometry **0.002 m (2 mm)**; lệnh tương ứng khoảng100mm nếu bám tốc độ | **MOTION_TRACKING FAIL**; chỉ ~2% tham chiếu nominal, chưa có đo quãng đường ngoài encoder |
| RPM đo | Trái peak5.12, phải peak2.56; target13 | **18/20 mẫu cả hai RPM0**; không có cơ sở nói tăng tốc mượt hoặc bám tốc độ |
| PWM | Trái14…49, phải14…51 | Lệnh tăng dần trong khi encoder hầu hết0; chưa kết luận do ma sát, deadzone hay sai encoder |
| Góc cuối | -0.013 rad ≈ -0.745° | Xe gần như đứng yên nên chưa chứng minh giữ thẳng khi chạy |
| Dừng | STOP5419.4443; mẫu DISARMED/target/PWM/RPM0 đầu5419.5387 | **Dừng quan sát được trong94.4ms**, thời điểm thật nằm giữa các mẫu, không suy chính xác hơn10Hz |
| Xác nhận sau dừng | 3 mẫu0 ở5419.5387,5419.6385,5419.7386 | Hoàn tất3 mẫu sau294.3ms; STOP_OBSERVED PASS giới hạn bài này |

`Motion=True` trong supervisor chỉ là cờ có một chút RPM/pose thay đổi; `exit0` chứng minh đạt điều kiện kết thúc của chương trình. **Hai giá trị này không phải nghiệm thu xe chạy tốt.** Bot đã được yêu cầu đính chính kết luận “100%”, “an toàn tuyệt đối”, “tăng tốc mượt” vì không phù hợp dữ liệu.

![Telemetry bài thẳng: RPM/PWM/quãng đường](<D:/HoMinhKhang/PROJECT/GITHUB_PROJECT/CODE XE TU HANH/evidence_agv_20261001/straight_1357_telemetry.png>)

Bằng chứng lưu trong thư mục `evidence_agv_20261001`:

- `straight_1357_raw.log`, SHA256 `0b4d82d5c6ab2867cb295828340eca2acc732294110e4e7543f70628baabec1a`; hash khớp file trên Pi.
- `straight_1357_summary.json`, số liệu tổng hợp của Codex.
- `straight_1357_telemetry.png`, đồ thị số liệu thật; tham chiếu100mm là quãng đường nominal từ lệnh, không phải bắt buộc xe đạt100mm ngay trong2s với gia tốc bất kỳ.
- `execution_1356_1357.json`, trích riêng10 mục command/result công cụ lượt nạp, preflight, đồng bộ hash và chạy thật; không trộn lịch sử chat khác.

Chưa kiểm mất heartbeat thật, mất scan thật, chướng ngại vật, quay, tải thay đổi, độ bền lặp lại, map/planner/home. Bài này không đủ khẳng định hệ thống fail-safe cho mọi tình huống.

## Việc đã giao tiếp sau bài chạy

1. Giữ DISARMED, không tự chạy lần2/tăng tốc/minPWM/minRPM/CLEAR_FAULT. Firmware f5bf giữ nguyên khi phân tích.
2. Sửa báo cáo của bot theo kết quả nạp/boot/dừng PASS giới hạn, motion tracking FAIL.
3. Phân tích offline PID/feedforward/ma sát/deadzone, source encoder/CPR/hướng, driver và điện áp. Phân biệt giả thuyết với nguyên nhân đã xác minh; đang chờ quan sát thực tế từ Khang để đối chiếu đo encoder.
4. QA dùng controller nguồn thật và plant giả có ma sát/độ trễ. Đề xuất hiệu chỉnh có giới hạn trước review bài thật tiếp; không dùng tăng PWM mù để chữa.
5. Tiếp tục P0, ROS freshness/arbiter/TF và planner/costmap/frontier reachable/map-home của mục tiêu toàn phòng. Chưa chạy AUTO cũ.

Review phân tích offline của bot lúc14:04: đã có đính chính motion tracking trong hai báo cáo. `simulate_motor_plant.py` vẫn viết lại PID bằng Python thay vì gọi `pid.c`; mô hình deadzone52/58PWM chưa được đo, chưa chứng minh nguyên nhân. Bánh phải có mẫu2.56RPM ởPWM28, bánh trái5.12RPM ởPWM48, không khớp lời “chỉ cuối bài/PWM>=50 mới quay”. Codex yêu cầu ghi HYPOTHESIS và dùng controller nguồn thật; **chưa duyệt Kf2.0 hoặc nạp/chạy bản tiếp**. Chưa có cơ sở suy hệ số feedforward mới chỉ từ VIN11V.

Cập nhật14:27: nhà cung cấp bot trả HTTP429 `RESOURCE_EXHAUSTED` ở14:08 và tiếp tục lỗi sau `/retry`14:17, phản hồi lỗi14:18:35. Gateway vẫn chạy nhưng lượt offline chưa xử lý; firmware f5bf và file phân tích không đổi. Codex không tự đổi model/gateway hoặc retry định kỳ. Chờ quota hiện tại được khôi phục hoặc chỉ thị cụ thể của Khang để tiếp tục qua bot; chưa có bài chạy tiếp.

## Cập nhật offline 14:54 — bot xử lý lại, chưa chạy lần hai

Bot đã có tool call AGV thật từ14:40, quota blocker trước đó không còn chặn lượt này. Codex kiểm độc lập bằng gcc trên Pi, chỉ CPU/tmp, không Serial: PID nguồn thật SHA256 `45013c9db32bc532b734eb73a84cb0192b524a59c794f6e0b2e609a8556a6e13`, header `75af288ed2742ccee976886b9d897ae108ed0f7c36653e734c4d130281fbe601` khớp local. QA v2 SHA256 thực `2466c96ebb874d96121ba143ccf4b122055226db1a59d08fe8f9fede489cbc0d` khớp Pi; hash1d303 trong phản hồi bot sai.

Bản thật compile/run exit0. Case target0 với tích phân150 reset output/integral0; stall20s +/-13.04RPM đạt clamp +/-170, quan sát output +/-255, rồi target0 reset0. Hai bản mutation độc lập compile0/run1: bỏ reset và bỏ clamp được assert bắt. Mutation bỏ reset hiện đổi cả Init/Reset, cần thu hẹp; output saturation đang in ra, chưa có assert riêng. Lệnh xác minh chạy `gcc -O2 -Wall -Wextra -I/tmp /tmp/test_real_pid_c_qa_v2.c -lm -o /tmp/codex_pid_v2_verify` rồi `timeout 10 /tmp/codex_pid_v2_verify`; các mutation được build/run bằng subprocess với exitcode thật (1), không lấy exit0 của lệnh echo cuối làm kết luận.

Đây chỉ là kiểm cơ chế số học theo case. Replay20 mẫu10Hz đã tách L/R đúng mẫu9R/mẫu20L nhưng firmware PID20Hz; thiếu mẫu50ms nên không gọi replay chính xác execution thật. Bot còn nói stall10s chạm clamp trong file phân tích, đã yêu cầu sửa thành20s và bỏ suy luận “encoder khỏe/thiếu lực đã chứng minh/triệt tiêu mọi kick”. Plant ctypes dùng controller thật, ma sát/gain/tau vẫn là giả định. Nguồn production và firmware hiện có giữ nguyên; không chứng minh xe chạy ổn.

Review14:54 giao bot tiếp tục implementation **offline** serial arbiter, telemetry/scan freshness, Odometry/TF và planner/costmap/frontier reachable/home trong map, kèm source-linked QA. Passive push10cm mới là đề xuất: cần logger hữu hạn, một Serial lead, không lệnh điều khiển/reset, delta pose/counts và điều kiện người dùng thao tác trước khi chấp nhận. Chưa có thử motor thứ2, chưa duyệt nạp/ARM/gain/PWM mới. Trạng thái DISARMED được xác minh cuối bài13:57, không gọi số đo cũ là trạng thái live hiện tại.

## Kết luận nghiệm thu hiện tại

Nạp và preflight bản cuối: **đạt**. Dừng trong bài ngắn: **đã quan sát đạt**, giới hạn như bảng. Chạy bám tốc độ/quãng đường: **chưa đạt**. Khám phá toàn phòng, map và quay đúng vị trí/hướng gốc: **chưa thử/chưa đạt**. Codex tiếp tục giám sát bot sửa; không đánh dấu mục tiêu hoàn tất.
