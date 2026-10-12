# Một phiên chẩn đoán lý do xe không chạy

Codex trực tiếp. Source offline đã thêm history in-memory 256 events, giữ riêng history và snapshot ở lỗi đầu tiên; RX D0 gap/targets/PWM/RPM, ACK, TX bytecount/thời lượng/error, lý do V bị chặn, path/rotation failure và STOP confirmation. API `/api/diagnostics` chỉ đọc, không ghi disk/network trong UART hoặc watchdog. Không tăng timeout/tốc độ/PWM/gain/đổi GPIO. Đây là chẩn đoán, chưa sửa được nguyên nhân TELEMETRY_TIMEOUT của phiên thật thiếu timeline.

Candidate main SHA `511491ec6cdc6dd1baf95d661b822656f43a2f1cc0654f58894c6621d7877bcf`; session SHA `47e7d973fd8a1c95c1d0c0c3a9e71be0b5be95c5dbfbc0f9b9b2486301630d93`. Navigation `22c46260dfdfff1b05d544f8dc08e2b8c5b1034bb076c2d91575f0d5a0cf9e14`, HTML `ba249a6b4b2b793759436eb3520ef46d3776234c1594a090c85599ab58ed1b63` giữ nguyên. Firmware artifact f5bf và supervisor 1bd4 không sửa/flash. ZIP chỉ là tham chiếu khai báo chân, không nạp ZIP.

QA `evidence_agv_20261001/codex_diagnostics_20261002_201411/verification.json`: 56 Python tests exit0, 16.223s, AST PASS, hash trước/sau ổn định. Bảy test diagnostic/session/navigation và một actual localhost HTTP test mới. RED failures giữ nguyên: missing history, endpoint trả HTML, path fail không có reason. FakeUART/ROS imports mocks; actual reader/watchdog/HTTP methods có chạy, không hardware acceptance. JS/HTML unchanged, giữ kết quả 8 nhóm JS trước đó, không rerun vô ích.

## Trình tự triển khai khi hiện trường được xác nhận hiện tại

1. Chỉ đọc HTTP control và SSH kiểm boot/cwd/controller USB0 owner/source hashes. Không suy snapshot 20:08 thành trạng thái hiện tại. Lưu trạng thái trước thay bản và diagnostic cũ nếu endpoint tồn tại; phiên cũ đã USED.
2. Dừng đúng controller hiện tại bằng shared HTTP STOP, chờ fresh DISARMED target/PWM/RPM/vw0 sau TX. SIGTERM đúng PID/cwd đã xác minh, chờ cleanup bounded và USB0 được nhả. Nếu không xác nhận dừng hoặc cleanup, dừng kế hoạch; người trực ngắt nguồn nếu xe còn động. Không blanket kill, không fallback launcher cũ.
3. Tạo thư mục Pi mới `/home/khangho/agv_codex_diag_20261002_201411`; chép đúng sáu file candidate main/session/navigation/root+web HTML/frozen collector từ manifest mới. Giữ nguyên thư mục live cũ, log và marker USED. Verify SHA, Python import mock offline, backup/rollback.
4. Giữ LiDAR/staticTF/SLAM hiện có nếu danh tính/topic đúng, không tạo owner USB1 thứ hai. Start đúng một controller trong cwd mới, `AGV_BODY_RADIUS_M=.20 python3 -B -u agv_unified_brain.py --motion-window-s 15`; USB0/115200, HTTP8080. Không AUTO/ARM lúc start. Same-owner startup boot/scan/found/10s80 exact-zero + fresh scan/map/TF.
5. Nếu startup/mapping không đủ thì HOLD, thu `/api/diagnostics`, không ARM/retry. Khi ready, operator tự mở đúng một phiên ARM rồi AUTO trên web. Một lần ARM fullwrite tiêu thụ phiên, kể cả ACK timeout. Limits giữ V<=.04m/s, w<=.35rad/s, RPM guard35, hard15s từ ACK+fresh ARMED; không MAN/PID/reARM/CLEAR_FAULT. Watchdog Pi 20ms, D0/scan250ms, caller200ms; người trực nguồn liên tục.
6. Codex thu HTTP diagnostic trước/sau, đặc biệt frozen first fault; không mở cổng Serial khác. Nếu mất dữ liệu/bất thường, STOP/DISARM; chưa xác nhận dừng và xe còn động thì ngắt nguồn. Thu quan sát thật của operator và so đối với TX/RPM/PWM/odom; không suy mock hoặc D0zero thành khám phá phòng thành công.

Rollback: giữ source/runtime cũ và candidate trong thư mục riêng; dừng candidate theo đúng STOP/cleanup. Không tự restart bản cũ, không tự chạy lại vì bản cũ cũng đã USED và có TELEMETRY_TIMEOUT.

Action thay controller/current USB0 owner và một operator trial mới: PLAN_REVIEWED_PENDING_CURRENT_FIELD. Reason snapshot/QA/giới hạn/kế hoạch cụ thể đã có, cần xác nhận khu thử còn trống và người trực nguồn hiện tại trước start. Không xin lại quyền source hoặc quyền triển khai chung; không automatic approval rejection. Whole-room map/home position+heading chưa đạt.
