# Đối soát nguồn offline — 03/10/2026

Người dùng yêu cầu “tiếp tục đi đừng cho xe chạy nhé”. Codex sửa trực tiếp trên máy, chỉ đọc SSH Pi. Không deploy/restart/Serial OPEN/ARM/AUTO/drive, không bot. Mục tiêu xe chạy có điều khiển, khám phá phòng và về đúng home position+heading chưa nghiệm thu.

Nguồn và bàn giao đầy đủ: [README_CODEX_AGV_TIEP_TUC.md](README_CODEX_AGV_TIEP_TUC.md), mục17. Evidence: [verification.json](evidence_agv_20261001/codex_no_motion_20261002_234614/verification.json).

## Kết quả có chứng cứ

- Pi chỉ đọc23:51: boot6c0476e0, không AGV/ROS, USB0 không owner, không HTTP8080. Không có D0 fresh; không gọi snapshot này là physical STOP proof.
- Cung tiến được kiểm disk thân+.15m trên trajectory v/w trong map known-free và scan mới, gồm phía hông, unknown, map yaw/subcell edge và kiểm freshness/generation lại trước write. Không hạ radius/margin. Front flag riêng không đủ cấp lệnh tiến cong nữa.
- D0 không ghi đè command history512. HTTP outcomes lưu JSONL riêng, giới hạn2MiB×2 và RAM32; lỗi ghi không biến command reject thành success. File IO không chạy trong UART/watchdog.
- AUTO trả từng blocker và gate snapshot; UI hiển thị và giữ lại lỗi độc lập với telemetry. ARM_CONFIRMED không còn hiện đang chờ ACK.
- 75 Python tests exit0/17.613s,11 nhóm JS exit0; AST/node syntax exit0; source hashes ổn định trong static verification. Test có actual reader/watchdog/localhostHTTP/typed callbacks, organic10s80, FakeUART; không dùng hardware hoặc cờ PASS/backdate sản phẩm.

## Review action/args/reason

| Action | Args/phạm vi | Quyết định và lý do |
|---|---|---|
| Sửa nguồn và QA | main/session/navigation/journal/HTML/tests local | Đã thực hiện theo quyền offline |
| SSH đọc trạng thái | `/proc` inventory, `fuser /dev/ttyUSB0`, `ss -ltn` | Đã thực hiện; không open thiết bị |
| Deploy/restart/Serial/ARM/AUTO/drive | Pi100.90.252.15/USB0/115200 | Không thực hiện: người dùng yêu cầu không chạy xe |
| Flash/gain/PWM/timeout/reARM/recovery | Firmware và phiên đã USED | Không thay đổi, không thử lại |

Đây là phạm vi người dùng và QA nguồn, không phải automatic approval rejection. Không có permission question mới. Xác nhận hiện trường cũ không được dùng lại sau reboot/gián đoạn.

## Giới hạn và việc còn thiếu

Không khôi phục được response ARM/AUTO gốc của lần không chuyển động; không kết luận phần cứng hỏng/khỏe hoặc lỗi gate là nguyên nhân cuối cùng. Margin/horizon chưa thay phép đo dừng vật lý. Frame/time epochs, ownership của điều khiển tay, crash/close, recovery lùi có scan/path, coverage và full home acceptance còn cần tiếp tục. Candidate front-only ở mục15 README đã được thay tiêu chí; 59 test cũ không phải motion acceptance.

Đọc README mục17 để tiếp tục offline. Chỉ xem xét kế hoạch nạp/test mới khi người dùng yêu cầu trở lại; không bật controller/xe trong lượt này.
