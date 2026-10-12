# Đối soát sau review18:18 — 01/10/2026, 18:32 Asia/Bangkok

Chưa duyệt phần cứng/ARM/nạp/bài chạy thứ hai. Tất cả QA dưới đây chỉ nguồn thật + SerialMock, không mở cổng hoặc chạy ROS node trên xe.

## Tiến bộ giới hạn

ROS34ac93630a7581af63c324d57c67203ecdea826fce014f6544271b0381213f53; plannerc7047ff715914475f1d130136582ddbf7ad7ece68ea25726865d5955bab5e7da. Gate/logger chưa thay đổi.

I1–I7 fixture cũ khớp kỳ vọng, evidence review_bridge_integration_1832.json. Riêng I1 kết hợp thiếu odom và auth/scan, nên việc chặn thiếu odom không chứng minh sửa auth/scan. Parent suiteROSexit0 nhưng plannerWindowsexit1 ởtest6/dòng212 cùnghash; independent_ros_planner_suite_1832.json. Không nhận claim WindowsPASS12/12. Deadlinefixture1e-7 phải thay bằng clockdeterministic và có positivecase ngân sách thực tế; không dựa một run trên Pi hoặc ép None mọi ngân sách nhỏ.

## Lỗi còn lại và lỗi STOP mới

Harness review_bridge_residual_1832.py/JSON; exit0 chỉ tái hiện xong, không phải productPASS. Hashtrước/sau ổn định.

| ID | Kịch bản | Quan sát | Kỳ vọng |
|---|---|---|---|
| R1 | Actualgate có phiênmock hợp lệ, bridgeproduction có odomfresh, khôngscan/TF, sourcelease chưa đăng ký | COMMAND_ACCEPTED, SerialMock nhận V0.04; bridge vẫn lấy active_token của gate | Auth/sourceepoch/lease và scan/TF NAV guard phải độc lập với odomguard |
| R2 | STOP ghi mockSerial thành công, chưa D0 sau STOP | EMERGENCY_STOP_ENFORCED nhưng gate.stop_confirmed=False | STOP_REQUESTED/writeOK-unconfirmed; chỉ confirmed khi D0fresh sau request |
| R3 | STOP có TTL100s | REJECT_INVALID_DEADLINE_TTL_EXCEEDED_BOUND; không ghiSTOP, mockgate vẫnARMED | STOP độc lập trường TTL/lease/velocity của lệnh chạy, kênh an toàn phải ưu tiên |

ROSfile vẫn chỉ helpermock; chưa Node/publisher/subscription/timer/executor/main/packetadapterclock. Source yêu cầu trường t không có trong telemetryfirmware. Comment “token của chính lease_id” không có kiểm lease_id/token/source thực. Không nhận hoàn tất lát cắt tích hợp chỉ từ fixturecũ7/7.

## Nhiệm vụ tiếp tục

Sửa kênhSTOP ưu tiên và request/write/confirmed rõ, authsource/sessionmapping/scanTF guard thật. Tạo tests gắn gate thật MockSerial gồm odomfresh nhưng sourceunauthorized, missing/stale scan/TF, STOP với TTL/lease/velocity rác, writefailure, callerim watchdogthread/timer thực. Thực hiện tiếp runtimeROS + source-linkedpacketadapter bằng faketransport offline; chưa chạy xe. Positiveflow authorized và reject từng điều kiện riêng tránh fixture nhiều lỗi che nhau. GatebootUNKNOWN/settling/loggerbounded/unique/mapfreshness/homeepoch/footprint vẫn pending. Bốn Telegrambot vẫn chưa actualACK.
