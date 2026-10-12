# Đối soát Node AGV — 01/10/2026, 19:12 (Asia/Bangkok)

Chỉ kiểm tra nguồn và fake Serial/ROS offline. Chưa chấp nhận snapshot để triển khai hoặc chạy xe. Báo cáo bot 7844 có thay đổi nguồn thật, nhưng claim full runtime chưa được chứng minh.

## Snapshot và bằng chứng

- Runtime `agv_ros2_runtime_adapter.py`: SHA256 `15f460b1f81a566b7381307de275d1434722302d9ebe3d95d7de4db748930a9b`.
- Bridge `agv_ros2_arbiter_bridge.py`: SHA256 `b5c17f8e84329bd0f54b3cfa8e30c8752f6de3bcbaaccec4c9f66a516949ece8`.
- `evidence_agv_20261001/review_node_1912.py/.json`: hash trước/sau ổn định, tái hiện bốn lỗi bên dưới. Harness exit0 chỉ có nghĩa hoàn tất tái hiện.
- `review_runtime_1912.json`: rxNaN và trường số hỏng được từ chối, không thoát exception; watchdog thread giữ STOP write-failure/unconfirmed. Công nhận giới hạn các case A1/A2/W1.
- `independent_runtime_suite_1912.json`: fullslice 4 tests exit0, nhưng không khởi tạo Node; chưa chứng minh callback, publisher hoặc executor wiring.

## Lỗi mới tái hiện từ nguồn thật

| ID | Kết quả quan sát | Yêu cầu |
|---|---|---|
| N1 | Khởi tạo Node offline thất bại `NameError: Odometry is not defined`, không có rclpy | Inject message types/ROS bus để khởi tạo Node bình thường trên Windows |
| N2 | Scan stamp0/frame unknown_sensor bị đổi thành stamp100/frame laser và accepted | Giữ header nguồn, mapping clock và kiểm freshness/TF |
| N3 | Message scan thiếu payload được tạo 628 ranges dương mặc định rồi accepted | Từ chối thiếu dữ liệu; không chế giá trị cảm biến |
| N4 | Callback bare cmd tự lấy token gate, viết `V 0.040 0.000` vào MockSerial | Xác thực source/session/lease/epoch/command age tại adapter/callback |

N2–N4 dùng `object.__new__` chỉ để cô lập callback nguồn thật sau khi constructor N1 đã thất bại. Đây không phải Node đã khởi tạo thành công, không phải phương án bypass để triển khai. N4 dùng protocol D0/ARM request/ACK/freshARMED hoàn toàn qua fake Serial, không phát lệnh phần cứng.

## Khoảng trống tích hợp

Nguồn Node tạo publisher nhưng không publish Odometry/TF từ adapter; chưa wiring stamp qua get_clock, TF chain, executor/main/shutdown hoàn chỉnh. Health timer gọi STOP nhưng bỏ outcome, trong khi helper thread mới giữ được outcome. Cần một đường STOP chung có request/write/confirmed/failure/escalation và xác nhận freshD0.

Yêu cầu bot test khởi tạo Node bình thường, fake bus phát subscription/executor, kiểm output /odom/TF, clock mapping, scan stale/missing/invalid-frame, unauthorized source, caller im/watchdog, write-failure và freshD0 confirm. Không dùng số test helper PASS để tuyên bố toàn bộ Node hoàn thiện.

## Quyết định

Không hardware/Serial thật/start ROS trên xe/flash/ARM/run2/logger/gain. Giữ firmware và supervisor đã nạp trước đó. Boot sau reboot vẫn UNKNOWN, cần preflight live D0 được review riêng. Chưa chứng minh bốn bot Telegram ACK hoặc mục tiêu toàn phòng/map/home.

Nguyên văn nhiệm vụ sửa lưu ở `TIN_CHO_KHANG_AI_ASSISTANT_20261001_1912.md`; trạng thái gửi được ghi riêng trong ledger sau xác nhận UI, không suy ra từ file này.
