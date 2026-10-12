# Báo cáo quan sát xe đứng yên — 05/10/2026

## Phạm vi
Chỉ đọc HTTP telemetry/diagnostics, tiến trình và mã nguồn trên Pi 100.90.252.15. Không gửi ARM/STOP/V/M, không thay nguồn, tham số, firmware hoặc restart. Khung lấy mẫu trực tiếp 14:23:59–14:24:11 Asia/Bangkok; bộ đệm sự kiện thu được trải 18,514 giây, gồm 185 gói D0 duy nhất. Kết luận chỉ áp dụng cửa sổ này.

## Kết luận
Xe đang mắc ở bước quay chỉnh hướng trong AUTO: hệ thống vẫn ARMED/PID/AUTO và tiếp tục gửi lệnh, nhưng không ghi nhận bánh quay hoặc odometry thay đổi. Không phải lần dừng do fault/latch hay mất truyền thông trong cửa sổ quan sát. Nguyên nhân cơ điện khiến bánh không đáp ứng chưa được xác định hoàn toàn.

## Bằng chứng
- 185/185 gói D0: RPM trái/phải bằng 0; x=-0,968 m, y=0,217 m, th=-3,06 rad không đổi.
- 186 lệnh TX: 92 lần V 0.000 0.350; 75 lần V 0.000 -0.350; 19 lần V 0.000 0.000. Không có lệnh tiến/lùi khác 0 trong bộ sự kiện này.
- 186 sự kiện drive đều accepted, không TX thiếu byte; 186 sự kiện ACK. Ví dụ: V 0.00 0.35 -> RPM -8.8 8.8.
- Mục tiêu bánh khi quay ±8,8 RPM; PWM tuyệt đối quan sát từ 0 tới 22. Đây là đầu ra báo qua telemetry, không phải phép đo điện áp/mômen tại động cơ.
- AUTO=true, armed=true, fault=null; first_fault=null. D0 gap lớn nhất 127,875 ms trong bộ đệm.
- LiDAR gần nhất khoảng 0,63 m, trạng thái WARNING; mẫu đầu phía trước 1,41 m. Không chứng minh không có vật thấp hoặc khung đang cạ ngoài mặt phẳng quét.
- Mục tiêu khám phá đổi qua nhiều tọa độ trong khi pose đứng yên. Có 6 sự kiện navigation_blocked/NO_SAFE_PATH. NO_SAFE_PATH chưa phân biệt không có đường hình học với hết ngân sách tính đường.

## Đối chiếu code đang có trên Pi
/home/khangho/agv_codex_reader_20261003_0652/agv_unified_brain.py:
- _follow(), dòng 734–782: khi sai hướng lớn hơn 0,25 rad, đặt v=0; w bị giới hạn ±0,35 rad/s. Điều này khớp chuỗi lệnh quay và ACK ±8,8 RPM đang quan sát.
- auto_nav_loop(), dòng 828–853: mục tiêu bánh >=5 RPM nhưng phản hồi <1,5 RPM kéo dài >0,8 giây được coi là kẹt; bỏ mục tiêu, gọi HOLD và tìm hướng khác. Dòng 871–875 còn kiểm tra không tiến triển theo pose.
- Dữ liệu cho thấy vòng quay/zero/đổi mục tiêu. Việc quy từng lệnh zero cho nhánh nào cần sự kiện phase chi tiết hơn; không khẳng định toàn bộ 19 zero đều do một nhánh.

## Diễn giải và phần chưa chắc
1. Xác nhận: lệnh đã tới MCU nhưng không tạo ra chuyển động được encoder/odometry ghi nhận; AUTO cứ yêu cầu căn hướng nên chưa chuyển sang tiến dọc đường A*.
2. Giả thuyết phù hợp: mức quay thấp tạo đầu ra chưa vượt ma sát/lực cản khởi động; các lần HOLD và đổi chiều làm quá trình quay bị ngắt. Chưa có đo dòng/mômen hoặc thử cô lập nên không coi đây là nguyên nhân cơ điện duy nhất.
3. Chưa loại trừ khung/bánh bị giữ, nguồn/driver hoặc phản hồi encoder. Không kết luận phần cứng tốt chỉ vì UART có ACK.
4. Cần xử lý phối hợp điều khiển quay ở tốc độ thấp và recovery theo tiến triển thực. Không có bằng chứng để lấy việc hạ ngưỡng LiDAR làm cách chữa cho lần đứng này.
5. stop_confirmed=true trong health đi cùng stop_op cũ không chứng minh phiên hiện tại đã DISARMED: D0 hiện vẫn ARMED, target/PWM có lúc khác 0.

## Định danh
Boot: 3aceed07-d4a9-4f16-b894-b8620386b629; controller lúc bắt đầu PID14964, --operator-control.
Source SHA256:
- main 08074d34958e72b9f1c41316e7df16982c4a77c143a460afb89dad0b712cfa89
- session bc7aba6d69f4f7fade41dd1bcf0aceb9697e016cdc136b5b6135ca6de99e08e4
- navigation 6343103f0b7f9433d1a594ea41548399cac9e85b71c741d5154e82d6c65a7615

Dữ liệu gốc: live_observation.json cùng thư mục. Không chỉnh sửa code trong phiên quan sát này.