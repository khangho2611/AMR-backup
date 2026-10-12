# Đối soát profile 140–150 RPM — 02/10/2026, 10:55 Asia/Bangkok

Broker9603 bàn giao SPEC `KE_HOACH_LO_TRINH_VAN_TOC_140_150_RPM_20261002.md`, SHA256 `cbb25601f78d5ca4e631cfb419963ff07fba56a69e2b5b880fb8492e3eba6865`. Runner15cdf/gate6f4a không đổi. Chỉ đọc nguồn và tính toán, không chạy lại test unchanged, không Serial/Pi motion hoặc sửa implementation.

## Được chứng minh và giới hạn

- Chấp nhận đính chính quan sát rít/nhích0–2mm thành UNVERIFIED. Câu hỏi người trực vẫn pending, không hỏi trùng. Bài thật10:36 đã thực thi lệnh; 10D0 motion đều RPM0/ODOM0. Chưa chứng minh bánh xe quay hoặc nguyên nhân cơ khí.
- `include/encoder.h:21–22` cấu hình 11×4×21.3=937.2; chưa đo xác nhận gear/PPR/CPR phần cứng. `encoder.cpp:74–92` lấy và clear bộ đếm PCNT, cộng delta vào total_count; một count/50ms danh định ≈1.2804RPM. `main.cpp:505–517` dùng dt thực, odometry dùng tổng count. RPM0 tại telemetry10Hz không chứng minh toàn bộ mẫu PID20Hz không có xung; xung thưa vẫn tích lũy total_count. Không kết luận encoder tốt từ không thấy lỗi trong source.
- PID gain khớp main.cpp59–62; pid.c tích phân error×dt, đạo hàm trên measured. Phép u≈9.88+15.6t chỉ giả thiết target10.4 cố định/RPM0/dt chuẩn; bài thật có ramp, không dùng để suy sole cause. PWM23/255 là tỷ lệ giá trị lệnh 9%, không công suất/mô-men đã đo. Chưa đo tải1.75kg/deadband/ma sát hoặc loại trừ driver/nguồn/encoder.
- Quy đổi bánh R=.0366: .08≈20.87RPM, .15≈39.14RPM, 140–150RPM≈.537–.575m/s. Quãng đường commanded lý tưởng ramp .15 tới .08 trong1s là58.67mm. Không là physical hardcap.

## Ba điểm cần chốt trong một bàn giao

1. SPEC bảng giai đoạn1 ghi .115/30RPM, phần3 và chat ghi .08/20.9RPM. Bảng giai đoạn2 ghi .249/65RPM nhưng lệnh V firmware clamp .15 trước inverse → đi thẳng chỉ39.14RPM; RPM65 là giới hạn riêng, không đạt bằng V thẳng .249 trên source hiện tại. Sửa về một profile nhất quán. 165RPM trần runner không chứng minh rated motor speed; tỷ lệ RPM không là công suất.
2. SPEC khẳng định deadband là sole cause/khôngencoderlỗi, stop≤15mm và an toàn tuyệt đối không có raw đo. Đổi thành giả thuyết/chưa đo; tách lệnh STOP, D0zero và dừng vật lý. MKE_M18_StopAll chỉ gửi lệnh STOP, không chứng minh hãm động năng/cự ly. Không lấy trạng thái/fuser cũ thành LIVE hiện tại.
3. Profile .08 chưa thực thi bằng source hiện tại: runner178 clamp .05, constructor442/execute748/CLI959 reject >.05; gate79/373 clamp .05. Guards trong SPEC (1.25×/35RPM, stall0.8s PWM80, mismatch15/100ms) chưa có candidate: source351 là1.15×/165RPM, mismatch356 là20RPM tức thời; chưa stall guard. Cần candidate SOURCE OFFLINE + gate tương ứng + exact CLI/hash/contract và QA whole production path, giữ Pi bản đã chạy. Không fake guards từ tài liệu hoặc --mock helper.

## Review block

Action: chạy bài kế tiếp .08 hoặc target140–150 trên Pi. Args candidate: USB0/115200/target-v .08/nominal1/hard1.5/output unique/outer bound chưa bàn giao. Decision **NOT_APPROVED**. Reason: source giới hạn .05; SPEC không nhất quán/các guard chưa triển khai; groundtruth/deadband/stopmargin chưa đo. Đây là review nguồn, không automatic approval rejection.

Giao broker chuẩn bị candidate offline và kế hoạch đo độc lập/quãng đường/dừng/encoder/driver/nguồn, thu rawRXTX/physical groundtruth, không giả nguyên nhân. Giữ target140–150 theo yêu cầu human, tăng từng mức được review. Quyền motion10:28 USED; không Serialretry/ARM/run3/reARM/CLEAR_FAULT/flash/gain/ROS/logger. Chỉ khi snapshot/plan READY mới chốt khu thử/người trực hiện tại. Không chờ toàn ROS để làm bài manual ngắn riêng. Monitor ACTIVE, goal room/map/home chưa đạt.
