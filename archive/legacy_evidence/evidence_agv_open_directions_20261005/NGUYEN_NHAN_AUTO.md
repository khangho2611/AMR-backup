# Nguyên nhân AUTO đứng tại chỗ dù còn hướng đi — 05/10/2026

Quan sát read-only khoảng 15:11 Asia/Bangkok. Không điều khiển, sửa, deploy hoặc restart xe. Đối chiếu thư mục nguồn của tiến trình PID29828: /home/khangho/agv_codex_reader_20261003_0652. Main SHA387d8a8b9e0c74584347aeb7c29c98dd23b4c33abbb13e1b81c591c7ec4944ce ở lần đọc cuối; snapshot trước đó SHA5bfea2049a2fb0f8a2859d15cbb0c11d810913961146111486c9f352c0e5a8d6. Các hàm _follow/_enter_cautious/_restore_normal_clearance nêu dưới giữ cùng logic ở cả hai lần đọc. Navigation SHA6343103f0b7f9433d1a594ea41548399cac9e85b71c741d5154e82d6c65a7615. Metadata file có mtime trước thời gian khởi động tiến trình; không trích xuất bytecode trong RAM.

1. Bộ điều khiển bắt xoay trước khi tiến. _follow dòng745 đặt v=0 nếu sai hướng >0,25 rad (14,3 độ). Hai đường tới mục tiêu của nhật ký có sai hướng đầu khoảng +89,66 và -97,70 độ khi replay bản đồ. Vì chưa xoay được nên không xuất lệnh tiến.
2. AUTO đổi mục tiêu trước khi tạo được tiến triển quay. Runtime nhận V0±0.880, MCU ACK V0±0.60 -> RPM hai bánh ±15,1. RPM quan sát chủ yếu0, PWM thấp; trước đó có một vài xung1,28RPM nhưng pose gần như giữ nguyên. auto_nav_loop vẫn có pose-progress1,5s và stall-bánh2s; khi không tiến triển bỏ mục tiêu/HOLD, lặp sang hướng khác. Không kết luận duy nhất ma sát hoặc không có lỗi cơ điện.
3. Lỗi nhất quán giữa vùng đệm và mục tiêu: _enter_cautious đặt đệm3cm. _restore_normal_clearance dòng536 chỉ kiểm tra đoạn tiến ngắn tại vị trí hiện tại với đệm15cm; sau2s bật lại chế độ thường mà không kiểm tra mục tiêu/đường hiện tại. Hai mục tiêu đang dùng hợp lệ với3cm nhưng nằm trong vùng cấm của15cm. GridPlanner.path dòng276 trả None ngay khi ô đích không traversable; _follow gán NO_SAFE_PATH. Vòng ngoài lại vào cautious, giữ goal và xóa blocked_regions/progress. Như vậy có thể lặp 3cm ->15cm ->NO_SAFE_PATH ->3cm, dù có đường tới các mục tiêu khác.

Bằng chứng replay offline bằng đúng module navigation, map86x86/res0,05 đã lấy từ xe, và pose trong navigation-event (map frame):
- Đệm15cm: start_safe=true, đoạn forward kiểm tra0,1m clear=true; tìm được3frontier. Hai goal đang lặp đều goal_safe=false, path=None.
- Đệm3cm: tìm được5frontier; hai goal có đường13 và16điểm, heading error+89,66/-97,70độ.
- Đây là kiểm chứng hình học snapshot trên máy local, không chứng minh chạy thật tất cả đường hoặc tương đương thời gian tính trên Pi.

Kết luận: dữ liệu bác bỏ cách giải thích 'hết hướng đi'. Xe còn ứng viên hợp lệ, nhưng chọn goal phải quay gần90độ, không quay đạt rồi liên tục thay goal; đồng thời chuyển chế độ khoảng đệm làm goal bị vô hiệu mà không lập lại mục tiêu theo cùng cấu hình. Đổi ngưỡng đơn lẻ không xử lý hết các lỗi này. Cần giữ nhất quán goal/path/footprint, sửa phục hồi theo tiến triển, và xác định điều khiển quay cơ điện trước khi coi AUTO hoạt động.

Tệp chứng cứ: snapshot.json và map_replay.json cùng thư mục. Chỉ phân tích, chưa sửa code.