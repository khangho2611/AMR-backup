# Codex triển khai web và một phiên AUTO, 02/10/2026 19:58 Asia/Bangkok

Theo yêu cầu người dùng, Codex tự sửa/triển khai. Không gửi Telegram, gọi bot
hoặc flash MCU. Người dùng xác nhận khu thử trống, trực nguồn; xác nhận khung
và LiDAR giữ như Assem3; đã trả lời “rồi” sau khi controller dừng và được yêu
cầu đặt xe thoáng ít nhất 50cm. Các quyền/chứng cứ cũ vẫn là lịch sử.

Đã mở Assem3 bằng SolidWorks COM chỉ đọc: khung260×207mm, trục bánh/LiDAR XY0;
bán kính góc xa nhất từ trục .19057m, lấy bao .20m cộng đệm .15m. Người dùng
xác nhận bố trí này đúng xe hiện tại; đây là cấu hình bảo thủ dựa trên CAD đã
xác nhận, không số đo vật lý mới. Chu vi bánh .23m/track .1875m theo Word,
không thay bằng bánh65mm/track180mm trong CAD. Tia0 hướng đầu xe; TF planar
base_footprint->laser XY/yaw0. Z0 là biểu diễn2D, không chiều cao vật lý.

Bundle riêng /home/khangho/agv_codex_20261002_1915, bản cũ backup_previous.
Pi boot305c4d73-736c-4871-968d-a84b997be21e, Python3.12.3/ROS Jazzy.
Main hiện778e144133c39e59aaf8ceda4e9746d507c8dba7aa9e287d9d9b325fe93a96af;
navigation22c46260dfdfff1b05d544f8dc08e2b8c5b1034bb076c2d91575f0d5a0cf9e14;
session91b14da3e29f00a9d34db831b55386e00cfff2be2e29a9179104061d12d18803;
HTMLba249a6b4b2b793759436eb3520ef46d3776234c1594a090c85599ab58ed1b63.
Pi hash manifest và web/root HTML khớp. PID controller14214, args
AGV_BODY_RADIUS_M=.20 python3 -B -u agv_unified_brain.py --motion-window-s15.
Shared flock+exclusive USB0/115200, reader50ms/write200ms, watchdog20ms.
HTTP bind trước OPEN; setupTF/ROS trước OPEN; SIGTERM cleanup hiện đã thực sự
đóng controller10385/nhảUSB0 sau STOP xác nhận. Controller observe2459 cũ
không thoátSIGTERM; chỉ SIGKILL đúng PID/cwd sau chứng cứ STOP mới, giữ audit.
Không blanket kill, không chạy launcher cũ.

Lúc observe, map đánh dấu occupied gần .2965m; placement không đủ bao .35m.
Sau người dùng chuyển xe, minscan .56m nhưng map còn UNKNOWN gần .273m.
Đối soát nguồn Karto cho thấy AddScan bỏ +inf và range>=maxRange, nên các tia
không phản hồi để lại lỗ trong map. Sửa topic /scan_slam: chỉ +inf được mã hóa
15.99m dưới sensor16m nhưng trên threshold12m; raytrace không thêm endpoint
occupied. NaN/-inf/invalid giữ nguyên, raw /scan an toàn không sửa. Không
thay UNKNOWN bằng0, không hạ footprint/đệm. Đối chiếu [nguồn Karto](https://raw.githubusercontent.com/SteveMacenski/slam_toolbox/jazzy/lib/karto_sdk/include/karto_sdk/Karto.h).

Tối ưu inflation bằng hợp các đoạn raster giữ đúng khoảng cách tới ô vuông;
không xấp xỉ/shrink. Pi build map thật trước19ms, map hiện28ms trong budget50ms.
Snapshot ready_live_1958.json: map86×86/res.05, safe361 ô, origin traversable;
selector nguồn thật trên Pi tìm5 frontier reachable,5 goals khác nhau,
unknown4952, tính32ms. Chưa có motion từ Codex; không khẳng định coverage phòng.

Live19:58: orderedstartupstage3/count1124/preflight_readyTrue, D0age28.3ms,
DISARMED/PID target/PWM/RPM/vw0, armedFalse/trial_usedFalse/faultNone.
STOPop4/writeok/confirmedTrue là telemetry sau TX, không physical100% proof.
Web http://100.90.252.15:8080/ đã mở trong tabIAB4, AX xác nhận nút MỞ PHIÊN
TEST15GIÂY enabled và AUTO disabled trước ARM. Tab lỗi2 bị policy chặn trang
data lỗi; mở tab mới đúng URL đã thành công, không bỏ qua security warning.

Action APPROVED_FOR_SINGLE_OPERATOR_TRIAL_START, args/source/limits như trên,
lý do human deployment/test/current field+geometry+placement và QA snapshot.
Code startsDISARMED; operator tự ARM rồi AUTO, explicitACKARM+freshARMEDD0.
15s tính từ ARM confirmation, V<=.04m/s/w<=.35rad/s, RPM guard35, không MAN/PID;
ARM đầu tiêu thụ bài duy nhất, no automatic reARM/retry/CLEAR_FAULT.
Hết15s/mấtD0/scan/caller thì STOP+FAULT; nếu chưa xác nhận và xe vẫn động,
người trực ngắt nguồn. Heartbeat10phút không thay watchdogPi/human.
Firmware/gains không đổi; target140–150RPM chưa test, không PWM140=RPM140.

QA cuối verification_20261002_195206:48Python +8JS groups exit0, AST/hashstable.
Callback publisher giữheader/angles/raw và khôngfake hit; constructor wiring,
session timeout/limits/no-reARM, emergencySTOPexactlyone/idleblurnoSTOP thật.
Evidence193825 JS regression giữ nguyên, đã sửa trước triển khai. Offline
FakeUART không physicalPASS. Actual ROS/main/UART/SLAM/TF đã startup và đọc
dữ liệu thật giới hạn; sole-owner process hiện14214, không toàn bộ crashcase,
encoder/STOPmargin/fullroom/homepositionheading acceptance. Chờ người dùng
test, không nói mục tiêu toàn phòng đã hoàn thành.

Evidence: evidence_agv_20261001/codex_deploy_prep_20261002_1915 gồm CAD identity,
live maps/STOP/retirement/manifests/startplans. Hai preparation chưa ARM được
retire trước bản scanfix; không tính là motion mới, không dùng lại trial cũ.
Runtime mới runtime_scan_fix, giữ các marker/log lịch sử. Bản test sẵn sàng
cho operator; không tự bấmARM/AUTO qua browser hoặc API.
