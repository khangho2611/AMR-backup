# Đối soát ROS bridge và planner — 01/10/2026 18:03 Asia/Bangkok

**Tiếp tục sửa offline; chưa duyệt nạp/ARM/chạy lần2.** Có file implementation mới và tool execution thật, nhưng bridge mới chưa phải node ROS hoạt động; lỗi tích hợp xuống gate và xác nhận STOP chưa đạt.

Snapshot: bridge SHA c3fa55c02c4f3d8b62ca2d0a5b0a2b8b298c0bd955b591c66d14a94f328248ab; planner ed7bdda832e63b702a5648716aa8521cd98a588243ad5470d87360c08e84273b. Gate e7967…a7bd/logger ff2de…f3f6 giữ nguyên. Hash trước/sau QA ổn định.

## Bằng chứng và giới hạn

Bot có SCP/SSH/test trên Pi thật: tool7332 hash khớp, tool7334 combined mock suites exit0. Chấp nhận đã thực thi offline, không bác toàn bộ là giả. Parent chạy test_ros2_arbiter_bridge.py exit0 (4 test) nhưng fixture không gắn serial_arbiter; **test_costmap_planner_v2.py vẫn exit1 tại case6/dòng212 trên Windows**, hash source không đổi trong lần chạy. Output đầy đủ evidence_agv_20261001/independent_ros_planner_suite_1800.json. Không nhận “PASS100% trên cả hai môi trường” hoặc suy tối ưu toàn hệ thống từ một số đo microsecond.

File agv_ros2_arbiter_bridge.py có import rclpy/Node nhưng không kế thừa/tạo Node, không publisher/subscription/timer thật, không executor/main; is_mock=False cũng chỉ tạo MockRos2Publisher/MockRos2TransformBroadcaster. Hiện nhận là **helper mock có source**, chưa ROS runtime/integration web-nav/Serial owner.

## Counterexample nguồn thật

Lệnh `python -X utf8 evidence_agv_20261001/review_ros_planner_1800.py` exit0 nghĩa harness tái hiện xong, không phải PASS sản phẩm. Không connect Serial, không khởi ROS node. JSON evidence_agv_20261001/review_ros_planner_1800.json chứa10case:

| Case | Quan sát sai | Điều kiện cần |
|---|---|---|
| B1 | Gắn SerialArbiterGateV3 thật với SerialMock rồi submit_cmd_vel gây TypeError unexpected keyword linear_v | Đúng signature v/w/epoch/token/command_deadline, quản lý session hợp lệ; structured rejection và không crash |
| B2 | Gate trả (False,REJECT_FAULT), bridge vẫn COMMAND_ACCEPTED | Unpack tuple, truyền đúng thất bại; cập nhật lease sau khi gate đã nhận, không giả chấp nhận |
| B3 | send_stop trảFalse vẫn EMERGENCY_STOP_ENFORCED | STOP REQUESTED/WRITE_FAILED/CONFIRMED phân biệt; fault latch/error ra caller; chỉ telemetry mới xác nhận |
| B4 | now_mono=NaN vẫn nhận telemetry | Clock/time domains finite/positive/age/order trước phát odom/TF |
| B5 | Scan angleNaN/step0/rangeNaN/framewhitespace vẫn nhận | Validate angle geometry/range validity và frame/TF; giữ dữ liệu ranges để guard/costmap thực |
| B6 | Chưa scan/odom/gate, leaseTTLNaN vẫn COMMAND_ACCEPTED | Fail closed, finite TTL có giới hạn, epoch/sourcelease/deadman và scan/TF guard nối tới đường lệnh thật |
| B7 | source=-1 cướp quyền manual | Source enum/type/auth hợp lệ, khôngbool/âm/unknown; preemption có quyền rõ |
| P3 | now_mono100 biến clock_fn thành lambda constant100; deadline100.01 đãhết tại clock101 vẫn sinhpath | Inject clock callable tăng theo thời gian; now_mono chỉ là mốc gốc, budget kiểm thực xuyên vòng; không đóng băng thời gian |
| P4 | timeoutInf vẫn sinhpath | Timeout finite có bound, không budget vô hạn |
| P5 | timeoutTrue vẫn sinhpath | Loại bool, finite/type gate trước xử lý map/path |

Firmware robot_stm32_f103/src/main.cpp dòng347 in telemetry **không có trường t**, trong khi bridge mới bắt buộc t. Serial gate hiện có latest_odom.timestamp theo thời gian nhận monotonic. Cần adapter source-linked cho thời gian nhận, freshness, ROS time mapping và clock skew/reset; không tuyên bố “timestamp từ chip” khi protocol không phát. Chưa base_footprint→base_link hay base→laser TF proof.

Các lỗi sáu case trước đã sửa trong phạm vi test; không có nghĩa mọi P0 đóng. Logger finite duration/bound/unique evidence, gate boot UNKNOWN/settling/watchdog thread, map freshness/originyaw/home epoch/footprint đo thực vẫn pending. F01–F14 giữ ID gốc, không mapping theo tiêu đề helper.

## Nhiệm vụ tiếp

1. Sửa bridge→gate/protocol/session/STOP result; test gắn source gate thật và MockSerial, bắt từng lỗi cùng negative control.
2. Sửa clock/deadline bằng QA deterministic, không chữa test bằng tăng time budget hoặc clock bất động; hoàn thiện timer/watchdog/sourceTTL/freshscan/TF fail closed.
3. Triển khai node/runtime ROS thật trong môi trường test dùng fake transport; nối publishers/subscriptions/TF/web-nav, chứng minh output ROS hợp lệ. Không khởi node/launcher/hardware trên xe.
4. Đo tối ưu có fixture/môi trường/hashes, CPU và p50/p95/p99 thời gian planner/tick/jitter trước–sau, không đổi STOP/TTL/gain/PWM để qua kiểm tra.

Bốn bot Telegram vẫn NOT_DISPATCHED/UNVERIFIED; bot chính tiếp tục tuần tự đúng quyền, không spawn thêm hay giả ACK. Pi online chưa chứng minh live DISARMED sau reboot. Chưa kiểm động cơ mới.
