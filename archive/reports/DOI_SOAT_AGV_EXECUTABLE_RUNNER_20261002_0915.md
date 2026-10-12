# Đối soát runner — 02/10/2026 09:15 Asia/Bangkok

Nguồn runner SHA256 9e2b7ff8877b6f54eadbf45da772e8e9d6e6df5d9317ed1f91ca233824f636d9 ổn định trước/sau QA. Broker9052 đã có HardwareMotionRunner/reader/watchdog/nhánh main thực; công nhận tiến bộ này, bỏ blocker chỉ ERRORexit1 trước đây.

Evidence độc lập: evidence_agv_20261001/review_executable_runner_20261002_0915.py/.json, Python3.12.10, actualclass + actualgate với UART giả phản hồi theo ARM/STOP. Không kết nối Serial thật, không thay implementation. Harness exit0 là ghi lại kết quả, không productPASS.

- Normal nhận STOPzero xác nhận và đóng fakeport, nhưng exit0/PASS kèm evidence_save_error json undefined; file evidence rỗng và tx_records0.
- Overspeed100RPM kích hoạt STOP/noV, vẫn exit0/PASS_MOTION_VERIFIED sau zero. Clock cùng giá trị có thể ghi đè faultreason; không lấy finalreason thay toàn lịch sử trip. STOPconfirmed không đủ chứng minh motion đạt.
- D0zero kèm errorMKE_M18_INIT_FAILED/faultTrue vẫn ghi ARM rồi3V và PASS: runtime dùng gateparser bỏ mixederror/schema, khác collector đã review.
- nominal_time=-.1 vẫn ARM/PASS, thiếu bounds trước mở cổng/ARM.
- Cùng raw/rx_mono bị parse2 lần reader và STOPcallback.
- Lệnh đề xuất thêm --output-dir bị argparse từ chối exit2; kiểm an toàn qua --mock. Parser chưa khai báo option nhưng realmain truy cập args.output_dir.

Đối soát source còn yêu cầu: fullstartup/settling/postdiag10s sameowner; sessionACK/freshARMED/latch; STOPfirstdeadline idempotent/sharedhealth khi inactive; finally hiện tắt reader rồi STOP thêm sau confirm và nuốt lỗi; evidence toànRX/TX, không cắt50; cleanup boundedthread/close/lock; exclusive advisory sauOPEN và exception nuốt không chứng minh TIOCEXCL. --mock CLI còn chạy helper riêng; cần fakeUART đi cùng actual productionentry.

Review block: action=motion_cli; args=/dev/ttyUSB0,115200,target_v=.04,nominal_time=1,hard_time_cap=1.5,output_dir=/home/khangho/evidence_motion_live,outertimeout5s; outcome=NOT_APPROVED; reason=CLI không khớp, runtime cho ARM mixederror, PASS sau safetytrip, evidencefail vẫnPASS, startup/STOP/cleanup chưa đầy đủ. Đây là kết luận QA Codex, không phải autoapproval rejection hay quyền hardware mới. Outer5s không chứa preflight10s + ARM/motion/STOP; phải review tổng bound riêng, không tăng motionhardcap.

TIN_CHO_KHANG_AI_ASSISTANT_20261002_0914.md ĐÃ GỬI09:15 private KhangAI Assistant UISeenMe/Sent9:15AM/composerempty sau refresh. Giao sửa gộp source/entry/profile/tests, không report dài, không đợi toànROS. Không gửi lại khi đang xử lý. Quyền static0857 đã dùng, cửa sổ09:00 không permanentfresh; chưa ARM/run2/flash/gain/ROS/logger/retrySerial. Cleararea/người trực hiện tại chỉ chốt khi bundle reviewready. Monitor ACTIVE.
