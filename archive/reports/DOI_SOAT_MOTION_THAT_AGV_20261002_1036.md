# Đối soát bài thật 02/10/2026, 10:36 Asia/Bangkok

Quyền đúng một invocation10:28 đã **USED**: private lệnh đã Sent10:33, broker tool9541 thực thi real runner, tool9542 outerexit0/start1790912186.660470434/end1790912198.387708872 (11.727s). Không --mock trong invocation. Source runner15cdf/gate6f4a giữ đúng snapshot; Pi3.12.3/bootb9714a2d…41eb. Tool9532/hash,9534/import,9536/mock là bước offline riêng, không motorproof.

Parent **SSH readonly** đọc độc lập rawPi `/home/khangho/evidence_motion_live_20261002_1028/motion_evidence_1790912198344_19050.json`; SHA256 `c5c4a6d54fd7662e6b82556b9405efdce27b4c0d5f022fd526f62dea85827715`. Lưu `evidence_agv_20261001/parent_motion_live_raw_20261002_1036.json` và `parent_motion_live_review_20261002_1036.json`. Không Serial OPEN/TX bởi Codex. Hash hai source tạiPi khớp approval, ps19050exit1 và fuserUSB0exit1/stdoutstderrtrống.

## Kết quả được xác minh

- 137raw RX/115D0; 1ARM,20V,1STOP, TX expected==written/successTrue trong log.
- V ramp .007→.04, firstV9043.173079680→STOP9044.180233333: **1.007153653s**. Không gọi khoảng giữa firstV và lastV0.957s là thời gian đếnSTOP.
- STOPACK9044.190070768, freshDISARMEDtarget/PWM/RPM/v/w0 tại9044.257699492: **77.466159ms sau timestamp attempt STOP**. Hai D0zero hậuSTOP. Gate/runnerconfirmed trong file và exit0: workflow/STOPconfirmation đạt cho bài này, không physicalfullSTOP100%/killsafe proof. TimestampTX là trướcwrite, không có writecompletion stamp riêng.
- Trong khoảng firstV→STOP có10D0: **10/10 cả RPM0, ODOM x/y/th0, peakRPM0**, l/rPWM1..23, target cuối10.4RPM. **Motion tracking chưa đạt**. Chưa thể kết luận bánh xe quay/xe đi, encoder/CPR tốt, deadband/ma sát là nguyên nhân duy nhất.
- Người dùng hiện chỉ xác nhận khu thử trống/người trực nguồn; câu hỏi quan sát bánh xe/dịch chuyển đang chờ trả lời. Report9559 tự nêu tiếng rít/nhích/đo0–2mm chưa có provenance người trực hoặc rawmeasurement: **UNVERIFIED**, không lấy làm groundtruth.

## Phạm vi tiếp theo

Không tự retry/ARM/reARM/CLEAR_FAULT/flash/gain/ROS/logger. Quyền một bài đã hết. Chỉnh claims100%software/fullPASS và physical0–2mm thành scope kiểm chứng ở trên. Physical distance/heading cần người trực xác nhận nguồn đo.

Tiếp tục điều tra SOURCE-linked offline vì RPM/ODOM0; không tăngPWM chữa mù. Chuẩn bị profile/lộ trình target140–150RPM vẫn theo yêu cầu Khang: xác địnhwheel/shaft/gear/CPR, mathramp/hardcap/stopmargin/distance, stall/overspeed/mismatch guards, source/hash/testnegative/exactcommand và measuredphysicalgroundtruth. Không tự mở gate speed hay triển khai profile mới trước review. Bài .04/1s không nghiệm thu mục tiêu phòng/map/homepositionheading; mock/build/status/Seen không thay nghiệm thu thực địa.
