# Điều tra giao diện không điều khiển được — 05/10/2026

## Kết luận
Lỗi phối hợp trạng thái UI/backend khiến một CALLER_TIMEOUT của AUTO khóa cả AUTO và MANUAL; UI báo chờ tiền trạm mặc dù fault không tự hết khi chờ. Không phải mọi nút đều mất kết nối: nhật ký vẫn có STOP HTTP200 và MCU ACK/STOP confirmed. Không gửi bất kỳ lệnh điều khiển nào trong cuộc điều tra này.

## Chứng cứ runtime
Telemetry thực: fault=CALLER_TIMEOUT, latched=true, armed=false, preflight_ready=false, preflight_count=0, MCU DISARMED/PID/target-PWM-RPM0. Owner còn hiển thị AUTO.
Lần AUTO_START lúc 14:44:29.302 (Asia/Bangkok) được chấp nhận; khoảng 155 ms sau phát CALLER_TIMEOUT, tuổi lệnh cuối 227 ms vượt 200 ms. D0 lúc lỗi mới 6 ms, scan159 ms. Nguyên nhân gây chậm phát lệnh đầu chưa được profile xác định.
Các STOP từ phía người sử dụng lúc 14:46–14:47 được server và MCU xác nhận. Không lấy việc thiếu request lái tay trong journal làm bằng chứng duy nhất; đã kiểm chứng nhánh chặn bằng JS offline.

## Các lỗi xác nhận từ code và chạy JS offline
HTML thực được GET / trả về SHA256 79f57b9627035f6790cfac1f8ee0df14630e64625f6af5e023e7b9da95e1def0.
1. updateTrialUI dòng539–556: fault làm disabled cả btnAuto, btnArm, 6 nút lái tay. Mô phỏng với telemetry thực xác nhận tất cả disabled.
2. toggleAuto dòng400–413 và startDrive dòng636–647: armed=false/preflight_ready=false trả về ngay; không fetch lệnh. Gọi các hàm thực offline ghi nhận requests=[] và thông báo chờ, WASD báo 8s.
3. Backend ingest chỉ tích lũy preflight khi not fault; preflight_ready cũng yêu cầu not fault. CALLER_TIMEOUT được giữ, count=0. Do đó thời gian chờ8s là chỉ báo sai trong trạng thái hiện tại, không phải countdown có thể hoàn tất nếu cứ đợi.
4. Telemetry UI dòng603–619 ưu tiên WARNING trước fault. Với telemetry thật, badge thành CẢNH BÁO VA CHẠM và che CALLER_TIMEOUT.
5. startDrive await ARM rồi mới đặt driveCmd; stopDrive trước khi ARM xong thấy active=false nên không hủy thao tác đang chờ. Mô phỏng offline: nhấn -> chờ ACK -> nhả -> ACK tới vẫn ghi yêu cầu M140140 và driveCmd còn hoạt động. Đây là lỗi độc lập của xử lý bất đồng bộ, không khẳng định xe đã thực hiện ngoài đời trong phiên này.
6. Backend có nhánh phục hồi riêng cho lệnh manual sau timeout, nhưng UI chặn trước khi gửi, nên nhánh đó không được gọi qua luồng đang lỗi. RESET nằm trong mục vị trí; backend RESET hiện tự gán stable_start=now-11/stable_count=100 thay vì một quy trình phục hồi thống nhất có bằng chứng mới. Không gửi RESET để thử.

## Cần sửa theo thứ tự
- Tách rõ trạng thái lỗi, đang kiểm tra, sẵn sàng, đang lái tay và AUTO; thông báo lý do thật và đường phục hồi ngay cạnh nút điều khiển.
- Đồng bộ UI/backend về phục hồi timeout sau khi xác nhận xe dừng; không tạo vòng chờ vô hạn hoặc gán giả kết quả preflight.
- Sửa bàn giao MANUAL/idle sang AUTO để không hụt nhịp trước lệnh đầu; xác định đoạn tính toán gây chậm, không chỉ nới timeout.
- Ưu tiên lỗi điều khiển trên nhãn trạng thái; không dùng cảnh báo khoảng cách thay thế fault.
- Hủy yêu cầu lái còn đang chờ khi nhả phím/nút, mất focus hoặc STOP; kiểm tra mã thế hệ thao tác sau mỗi await.

## Phạm vi kiểm chứng
Đọc HTTP/SSH; chạy nguyên JavaScript được server phục vụ trong Node VM với DOM, timers và fetch giả. Không chạy click trên trình duyệt thực, không mở Serial, không sửa/deploy source, không ARM/RESET/M/V/STOP thật. Kết quả JS là kiểm chứng luồng điều khiển offline, không phải nghiệm thu xe.

Tệp cùng thư mục: snapshot.json (HTML, telemetry, diagnostic và nguồn backend đã đọc), offline_ui_results.json (kết quả 5 tình huống). Main SHA c153e729b303cf0d4deec8e9b927bb1fe068a6f2e98cfb73bcc86cbdf2e375ce; session SHA17ea819e9c678c9c914d1894b02afd6f500a809dae13065fca89054f9349fc82.