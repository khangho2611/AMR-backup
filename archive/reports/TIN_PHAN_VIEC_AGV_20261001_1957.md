KHANG CHỈ THỊ MỚI 01/10 19:57 — Codex đã đọc README_TELEGRAM_BOTS.md. Khang cho phép nhờ CHÍNH Khang AI Assistant phân việc thoải mái cho bốn bot có sẵn; Codex chỉ liên lạc privatechat này, không tự code implementation.

README nêu lead @subagent_leader_bot, coder @suagent_coder_Bot, tester @subagent_tester_Bot, writer @subagent_writer_bot, nhóm -5550053050. Hãy đối chiếu actualidentity với tên hiển thị trong ảnh, dùng backend/hub có sẵn nếu hoạt động; gửi taskID/runID/ACK + kết quả công cụ/file thật. Nhãn vai trò/@mention không phải proof dispatch. Không spawn thêm Hermes. Nếu route chưa dùng được, báo lỗi thật và tiếp tục offline tuần tự, không dừng AGV để sửa model/gateway/token; không xin/in secret hoặc tự khởi động hub chưa review. Bạn giữ Serial/hardwareowner duy nhất.

Ưu tiên phân việc:
Lead: chốt kiến trúc, ownership/snapshot và kế hoạch nghiệm thu theo từng bước.
Coder: sửa Node runtime + adapter/sourcelease/scanTF/STOP lifecycle.
Tester: QA độc lập qua actualgate+FakeSerial/ROSbus, kiểm constructor/callback/output thật.
Writer: ledger/hash/test/giới hạn và kế hoạch triển khai; không claim100% hoặc zero-defect.

REVIEW nguồn runtime15f460b1…930a9b / bridgeb5c17f8e…49ece8 stable, evidence_agv_20261001/review_node_1912.py/.json:
N1 constructor Node offline NameError Odometry undefined.
N2 scan stamp0/unknownframe bị callback đổi stamp100/frame laser rồi accepted.
N3 scan thiếu payload bị tạo [1.0]*628 và accepted.
N4 callback bare cmd tự lấy active_token rồi ghi V0.0400.000 vào MockSerial khi freshodom/scan — thiếu source/session/epoch/command-age binding.
A1/A2/W1 cũ đã sửa giới hạn; fullslice4/4exit0 chưa instantiateNode nên không chứng minh runtime.

Sửa một lát cắt hoàn chỉnh: fake message types/bus/clock cho constructor bình thường; không __new__ bỏ constructor. Scan giữ header/time/frame, mappingROS→mono, measurement-age khác receive-age, chặn missing/stale/future/unknownTF; không chế defaults. Cmd qua trusted adapter nguồn/lease/session/epoch/deadman, không tự trao active_token cho mọi callback. Firmwarepacket→Node phải thực publish /odom/TF và clockmapping; hiện chỉ create_publisher. Healthtimer đang bỏ STOPoutcome: dùng chung thread path request/write/confirmed/failure/escalation, freshD0confirm, main/executor/shutdown an toàn OFFLINE.

QA cần constructorNode + fakebus subscription/executor, positive protocol D0→ARMrequest→ACK→freshARMED chỉ mock, stale/missing scan/TF, unauthorized caller, caller im, STOPwritefail và freshD0confirm; command/exit/hash/raw outputs. Xem DOI_SOAT_AGV_NODE_20261001_1912.md.

Đính chính các tin trả Khang: 2mm là ODOM, chưa đo quãng đường thật; ma sát/encoder/CPR vẫn giả thuyết. Không yêu cầu chứng minh “100% zero-defect”; cần tiêu chí cụ thể và bằng chứng. 192.5mm trackwidth không tự là footprint toàn xe. Không suy mockwatchdog thành phần cứng đã chứng minh ngắt. README model/chi phí/token và “an toàn tuyệt đối/DISARMED” là claim chưa verify.

GIỮ NO hardware/Serial thật/startROS trênPi/flash/ARM/run2/logger/gain trước review snapshot+kế hoạch. Boot sau reboot chưa LIVE D0. Chuẩn bị preflight bounded/noTX source để review và kế hoạch đo motion thực, không tự chạy. Mục tiêu cuối vẫn toàn phòng/map/home position+heading, chưa đạt. Gửi báo cáo gọn mỗi mốc có proof, không tạo báo cáo dài lặp.
