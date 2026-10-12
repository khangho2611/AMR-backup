# Đối soát tích hợp AGV — 01/10/2026, 18:18 Asia/Bangkok

Chưa duyệt phần cứng, nạp, ARM hoặc bài chạy thứ hai. Chỉ kiểm nguồn và mock Serial; không mở cổng, không chạy ROS node trên xe.

## Kết quả đã xác minh

- ROS bridge SHA256 `dc4d1e95c751a31a68df98b845b18624838764c8a4968eebc4d61e473d4cfe67`; planner `76b9b41f6be07e5c35018d236a392879f7e7cb7c794b62ee95b403ee19cfb686`. Gate/logger không đổi. Hash trước/sau QA ổn định.
- B1–B7/P3–P5 đã khớp kỳ vọng giới hạn; evidence `evidence_agv_20261001/review_ros_planner_1820.json`. B6 kết hợp nhiều điều kiện nhưng chỉ được sửa phần TTL NaN, chưa chứng minh sensor freshness hoặc missing gate được chặn.
- Suite ROS 4 mock case exit0; suite planner Windows exit1 ở test6/dòng212 timeout1e-7. Evidence `independent_ros_planner_suite_1820.json`. Không công nhận claim cả Windows và Pi PASS12/12. Test dùng độ phân giải thời gian cực nhỏ chưa đủ kết luận lỗi scheduler; cần clock giả deterministic và budget thực tế, không tăng timeout để che lỗi.
- Tool7402 exit0 có số benchmark thật: Windows P50/P95/P99 0.936/1.188/1.695ms; Pi4.303/4.374/4.605ms. Đây là fixture A*20x20, chưa có baseline trước/sau, runtime ROS20Hz/timer/supervisor hay tải đồng thời để kết luận không jitter/không nghẽn CPU.

## Counterexamples tích hợp nguồn thật

Harness `evidence_agv_20261001/review_bridge_integration_1818.py`; raw JSON cùng tên. Exit0 nghĩa tái hiện hoàn tất, không phải sản phẩm PASS. ARM chỉ là chuỗi được ghi vào SerialMock trong fixture; không có phần cứng.

| ID | Kịch bản | Quan sát | Yêu cầu |
|---|---|---|---|
| I1 | Gate mock được chuẩn bị phiên hợp lệ; bridge không có scan/odom, nguồn đưa lease bất kỳ | Bridge tự lấy token active và ghi `V 0.040 0.000` | Source/auth/epoch/token phải ràng buộc phiên đã cấp riêng; bắt sensor/TF freshness cho NAV |
| I2 | TTL lease100s | Nhận lệnh, lease deadline200.04 tại clock100.04 | TTL hữu hạn có biên tối đa200ms; deadman thực phải dừng khi caller im |
| I3 | `is_mock=False`, không gate/scan/odom | COMMAND_ACCEPTED, vẫn MockRos2Publisher | Production thiếu transport/runtime phải fail closed; mock hành vi phải tách rõ |
| I4 | STOP không gate | EMERGENCY_STOP_ENFORCED | Báo unavailable/unconfirmed, không báo dừng phần cứng |
| I5 | Góc scan đảo, ranges âm | Nhận scan | Validate geometry/count/range bounds và giữ ranges để guard/costmap dùng; no-return semantics cần định nghĩa đúng nguồn |
| I6 | Start=goal, now100 deadline100.01 nhưng clock101 | Vẫn path1điểm | Kiểm deadline trước nhánh nhanh |
| I7 | Start=goal, nowNaN | Vẫn path1điểm | Validate clock trước mọi work/nhánh nhanh |

ROS file vẫn helper publisher/TF mock, không Node/subscription/publisher/timer/executor/main; telemetry yêu cầu `t` chưa có adapter cho packet firmware thực không có `t`. Đọc token từ gate không thay nguồn ủy quyền. TypeError fallback gọi signature khác có thể gọi lần hai sau lỗi nội bộ; không dùng như đường vòng protocol.

## Công việc giao tiếp

Ưu tiên một lát cắt tích hợp hoàn chỉnh: packet firmware thật và Pi receive timestamp -> adapter monotonic/ROS clock đúng -> Odometry/TF/scan dữ liệu thật -> source lease/auth/epoch/deadline -> gate protocol -> STOP request/write/confirm. QA fake transport gắn gate thật cần positive authorized flow, rejection, stale/no-data, caller im, epoch invalid và write failures. Sau đó ROS runtime thực bằng fake transport, chưa triển khai lên xe. Không dừng ở sửa riêng counterexample hoặc báo cáo.

Gate bootUNKNOWN/settling, logger finite bounds/unique logs, map/home freshness/epoch/footprint và mục tiêu phòng/home vẫn pending. Chỉ một broker Serialowner, không spawn thêm; bốn bot Telegram chưa có actualACK vẫn NOT_DISPATCHED/UNVERIFIED.
