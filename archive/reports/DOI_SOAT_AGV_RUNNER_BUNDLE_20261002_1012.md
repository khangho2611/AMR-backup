# Đối soát runner 02/10/2026, 10:12 (Asia/Bangkok)

Snapshot broker9429/source9428: `agv_motion_supervisor_runner.py` SHA256 `01903753bb7855d119e490e6899e6a82fd60b5a9b39454b2eef3f3bebb7a8113`. Hash trước/sau các kiểm tra không đổi. Codex chỉ viết QA, không sửa implementation.

## Bằng chứng mới

- `evidence_agv_20261001/review_runner_bundle_20261002_1006.py/.json`: actual execute_lifecycle + gate + reader/watchdog, chỉ thay OPEN/lock bằng UART giả; clock thật, contract 10s/80 không scale. Positive ready/scan/found/VIN/postdiag126D0 trong10.062s: exit0/ARM1/V4/STOP1/freshD0 gate+runner confirmed/file finalstatus+TX6/closed. UnsafePWM100: exit1/noARM/noV. Đây là OFFLINE, không xe chạy thật.
- Cùng harness: scan→D0 thiếu found/error vẫn exit0/ARM1/V3/PASS. Reader chuyển state2→5 tại610–613, bỏ mất kết quả scan bắt buộc.
- Gap1s-only được nhận: maxgap1.0s/exit0. Collector4b32 MAX_GAP_S/MAX_AGE_S là1.5s; không coi case này là lỗi mới. Case P2 cũ unknown+gap không tách được nguyên nhân. Corrupt dòng đầu trong settling cũng không tự chứng minh vi phạm; không dùng làm blocker.
- `review_runner_deadlines_20261002_1010.py/.json`: ready tới4.172s rồi scan/found/VIN và10sD0 vẫn ARM1/exit0. Reader chỉ giới hạn35 dòng, thiếu STARTUP_DEADLINE3.5s/settling2s15dòng của collector. Component riêng no-caller dùng ARMreq→ACK→freshARMED thật trong gate, không giả flags: watchdog STOP/gate+runner confirmed đã sửa giới hạn. Component này chủ động bỏ preflight; không fullentry/hardware proof.
- `review_partial_stop_protocol_20261002_1012.json`: actual gate protocol; STOP chỉ write1/5byte→gate localFAULT/confirmedFalse. Sau D0 zero fresh mô phỏng (có thể do watchdog MCU độc lập), gate+runner lại confirmedTrue, runnerfaultFalse/stop_write_successFalse. TransportWrapper còn ghi successTrue cho partial write. Đây là lỗi gắn kết write-outcome và confirmation, không chứng minh xe dừng bởi STOP.

## Giao sửa gộp

Chốt FSM startup chung với collector4b32: scan phải có found hợp lệ trước stable; VIN optional; deadline/settling/count/lastage/maxgap theo contract nguồn. Không mở lại banner/uint/range/unsafe cũ đã sửa. Chốt STOP một chủ trạng thái: lưu bool write/partial/flushfailure, fault latching, firstreason/firstdeadline không đổi; freshzero có thể ghi OBSERVED nhưng không biến lỗi write thành PASS. TX ghi attempt/completion/expected/written/outcome thật. No-caller/write-fail/timeout/cleanup phải trả health/outcome nhất quán.

Một bàn giao source/hash + positive fullentry + thiếufound/late startup + partialSTOP/OSError/freshzero + callerim + CLI/profile. Không report dài hoặc framework/ROS mới; không sửa collector đã đạt nếu không có bằng chứng cần sửa.

## Review block

Action: chạy motion trên Pi. Args: `/dev/ttyUSB0`,115200, `--target-v .04 --nominal-time 1 --hard-time-cap 1.5 --output-dir <unique evidence_motion_live>`, outer bound cụ thể chưa chốt. Decision: **NOT_APPROVED**. Reason: startup thiếufound/late vẫn ARM; partial STOP bị ghi success và confirmed mà không latch runnerFAULT. Đây là Codex review nguồn, không phải automatic approval rejection.

STATIC08:57 đã dùng hết; LIVE_D009:00 không còn fresh cho ARM. Chưa ARM/run2/flash/gain/Serialretry/ROS/logger. Khi source+profile đạt thì chốt khu thử/người trực HIỆN TẠI, không xin lại quyền chung. Target140–150RPM giữ theo lộ trình đo/STOPmargin, chưa nâng blind. Mục tiêu phòng/map/homepositionheading chưa đạt.
