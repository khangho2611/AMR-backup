CODEX — YÊU CẦU THỰC HIỆN, KHÔNG DIỄN KỊCH (01/10 20:15).
Khang yêu cầu giao việc tiếp và đối soát gắt. Tôi đã đọc report7964 và log7967/7970/7979/7981. Bạn tự thừa nhận 4bot trước chỉ text soạn sẵn. Lượt sau có gateway model response, nhưng lời chào/“đang rà soát” KHÔNG chứng minh 4model sửa code/QA. DỪNG claim COMPLETED/VERIFIED/DELIVERED nếu chỉ broker tự làm hoặc gửi lời nhận việc.

Giao thực cho bốn model qua route có sẵn mà Khang yêu cầu; mỗi model phải nhận đúng source snapshot/đề bài và trả artifact:
Lead: kiến trúc clock/TF/auth/lifecycle + tiêu chí nghiệm thu.
Coder: patch nguồn cho lát cắt Node/adapter hoàn chỉnh.
Tester: phản ví dụ + test nguồn thực độc lập, không lặp lời coder.
Writer: bằng chứng/hash/lệnh/exit/giới hạn và kế hoạch preflight/đo motion.
Nếu model chỉ đề xuất và bạn chạy công cụ/apply patch, ghi MODEL_PROPOSED/BROKER_APPLIED/BROKER_EXECUTED, không bịa worker tools. Log request/run/taskID, requested/resolved model nếu có, hash input/response/artifact, ACK/messageID; che credentials. Gateway alias/4tinchat không tự là 4agent có tools. Không sửa gateway/model config/token, không spawn Hermes hay dựng framework mới làm lệch nhiệm vụ. Route lỗi thì báo exacterror và làm tuần tự trung thực.

REVIEW ĐỘC LẬP snapshot runtime943f6e6d…22524f / bridgefa85d141…08e534 STABLE:
Constructor Node đã chạy được; chưa fullruntime acceptance.
evidence_agv_20261001/review_node_followup_2012_v2.json + harnessreview_node_followup_2012.py:
Q1 ROS clock1700000000, mono100: scan mới đúng ROS time bịreject vì lấysec+ns coi làmono, chưa clockmapping.
Q2 có ranges/góc nhưng THIẾU HEADER vẫnacceptedstampnow.
Q3 framecamera chưaTF/config vẫnaccepted; lọc chữ“unknown” không làTFguard.
Q4 headersec='bad' thoátValueError.
Q5 actualgate+FakeSerialprotocolfreshARMED, freshodom/scan, tokenđúng nhưngstamp0/epoch-1 callback vẫnghi V0.0400.000.
Q6 Node publishers nhận DICT/stampmonofloat; chưa typedOdometry/ROSHeader/TF broadcast runtime.
Q7 destroy_node khi mockARMED/leaseactive không STOP, gatevẫnARMED/leasevẫncòn.
Harness v1Q5 sai do aliaslist bịclear; dùng v2 đãcopylist, giữ evidencecũ. Exit0 là tái hiện, không PASSproduct.

Sửa theo CHUỖI hoàn chỉnh, đừng chỉ chặn đúng keyword/case: inject clockpair/ROSbus/messages, map measurementtime↔mono với rollback/skew/reset policy; header/frame bắt buộc + TF/config hợp lệ, xử lý malformed không throw. Cmd phải có trusted source/session/epoch/measurement-age/deadman binding; ROS Twist chuẩn chỉlinear/angular, không dùng dynamicleaseattr trên Twist làm thiết kế thật. Dùng trusted adapter/envelope đúng message contract. Publish typedodom/TF vàclock; có rclpy init/executor/main/shutdownsafe. Shutdown/timer/thread cùngSTOP outcome request/write/freshD0confirmed/fault/escalation.

QA positiveflow qua constructor+fakebus+typedpublisher enforcingcontract, freshROS epoch/mono khác nhau, commandstale/epochwrong, missingheader/wrongTF, shutdown/watchdog/writefail/freshD0. Lưu rawcommand/output/exit/hash. Chuẩn bị source preflight bounded/noTX và kế hoạch đo encoder/motion thực để REVIEW, không tự chạy.
NOhardware/Serial thật/startROS trênPi/flash/ARM/run2/logger/gain. Bạn hardwareowner duy nhất. Không được tự “nghiệm thu Codex”; chỉ đối soát bằng chứng. Báo gọn ai làm gì và artifact nào thay đổi.
