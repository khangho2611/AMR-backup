# Đối soát offline bridge và planner — 01/10/2026 15:02 Asia/Bangkok

Codex kiểm source thật bằng mock trên máy trạm, không mở Serial hay chạy phần cứng. Các module là bản mới độc lập, chưa tích hợp vào ROS/web/nav và chưa thay snapshot firmware f5bf/supervisor1bd. Không cấp quyền nạp/ARM/chạy lần2 từ review này.

## Bằng chứng và phạm vi

Bridge SHA256 `432cd2136e463eac8e8ad5cc36daa64961fdf424b7f17b98822b1e571aaa5954`; planner `0793a8d5b4ac2cd96fdf7fc98543bb9fc4f25829ad427bc05b384b4a9a7cc2dc`. Test `test_serial_arbiter_mock.py`5/5 và `test_reachability_planner_offline.py`4/4 chạy độc lập với Python -X utf8, exit0. Lần gọi subprocess đầu thiếu UTF8 ở child gây lỗi encoding, không dùng lần đó làm kết luận.

Dữ liệu counterexamples độc lập: `evidence_agv_20261001/arbiter_planner_review_1500.json`. Gọi lớp thật với MockSerial:

- NaN/Inf ở vận tốc được clamp thành `V 0.050 0.000` và ACCEPTED thay vì reject.
- Telemetry timestamp100, now90 vẫn nhận lệnh vì age âm không bị chặn.
- STOP chưa latch: `send_stop(); send_velocity_command(.04,0,100.1)` xuất STOP rồiV khi state vẫnARMED.
- Mockwrite ném OSError nhưng hàm command trả ACCEPTED; không chốt lỗi và không xác nhận STOP/DISARM thật.
- Watchdog chỉ kiểm khi gửi lệnh; không có tick tự dừng khi caller im, không có TTL/epoch từng nguồn command.
- Planner chưa nhận map đã mặc định FREE và trả path.
- Corridor rộng1ô50mm vẫn có path vì thiếu footprint/inflation. Khoảng cách hai bánh192.5mm là một dấu hiệu xe lớn hơn ô, chưa dùng nó làm bề rộng toàn thân đã đo.

Serial flock sau open chỉ là khóa phối hợp, chưa chặn chương trình cũ không flock; handle phải close khi connectfail. Source không có ROSNode/Odometry/TF publish, scan freshness, nối web/nav, map origin/frame/stamp hoặc homepose/heading/lifecycle nghiệm thu. BFShelper không chứng minh hoàn tất toàn phòng/home. Các nhãn F01–F14 trong file bot bị đánh lại số, cần đối chiếu ID gốc từ báo cáo đánh giá.

Logger passive đã đọc source, chưa thực thi: chấp nhận ARMED/thiếuPWM/sốNaN, trảTrue cả0mẫu, mainkhôngexitfail; không có gate DISARMED0 hay counts từngbánh. Mở Serial có thể đổiDTR/reset, flock chỉ phối hợp. Cần logger có thời hạnfinite, preflight freshD0, abortunsafe/stale, evidencekhôngoverwrite và humanhalt nếu bất thường; không tự phát lệnh hay nhờ Khang đẩy tay trước review.

Codex gửi bot review mang nhãn15:02 (Telegram Sent/Seen15:01) với các sửa cụ thể, ưu tiên gate/latch/watchdog/writeerror rồi tích hợp ROS/costmap. Chưa công nhận P0/F01–F14 đã xong, chưa có nghiệm thu thực địa mới.
