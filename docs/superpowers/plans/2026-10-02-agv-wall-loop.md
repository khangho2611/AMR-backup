# Sửa dẫn đường lặp vào tường và PID web

Quyền: người dùng trực tiếp yêu cầu Codex sửa theo prompt.docx. Chỉ source offline, chưa deploy hoặc chạy xe. Không sửa firmware/gain/PWM. Không tiếp tục cho broker sửa cùng hai file trong lượt này.

Thiết kế: giữ giao diện và ROS node, tách grid planner thuần để kiểm thử. A* chỉ đi trong vùng known-free có inflation theo mét/body radius + 15cm; chống cắt góc; endpoint chính xác, không đổi goal âm thầm. Frontiers gồm điểm quan sát an toàn trong connected component, không đặt thân xe vào unknown. Bám từng đoạn không vượt góc; giữ goal, blacklist vùng goal bị kẹt có thời hạn. Chưa đủ dữ liệu/map/TF thì HOLD, không giả hết frontier hoặc home thành công. Home capture trước motion, vị trí+hướng, STOP confirmation tách riêng.

Transport: bỏ autoARM trong M/V; STOP latch trước TX mutex, chỉ explicit ARM được phép sau same-owner preflight, ACK và fresh D0. Watchdog độc lập, không tăng speed. PID serialized matching ACK/error; no ACK => FAILED, không fake applied; Kf fixed .45, 0 valid, persistent lifecycle history and quoted CSV.

- [x] Đọc tài liệu/source/firmware/hình radar, sao lưu unique.
- [x] Tái hiện test đỏ unknown shortcut, inflation theo ô, goal relocation, invalid map.
- [x] Implement grid/path/frontier corrections and nav integration.
- [x] Implement matching PID web result and STOP/motion cancellation guards.
- [x] Offline tests for routing, corner, TF yaw, no-path HOLD, STOP race, PID reject/timeout/UI.
- [x] Report actual scope/hash/rollback and update supervision to avoid overwriting this fix.

Human override cuối lượt: Codex làm thay bot, không gửi bàn giao/không giao việc nữa. Packet prepared đã hủy trước nhập/gửi. Automation gi-m-s-t-bot-agv đổi tên “Codex tiếp tục AGV”, vẫn ACTIVE/10 phút nhưng prompt là tiến triển offline trực tiếp; không khôi phục NO-implementation/delegation cũ. Snapshot local đã kiểm thử; nghiệm thu hệ thống trên xe vẫn chưa đạt.

15cm là wall clearance policy, không số đo physical stopping margin. Full-body radius cần measurement/config riêng; Word track .1875m không đủ radius quay. Không cấp chứng nhận whole-room goal từ mock.
