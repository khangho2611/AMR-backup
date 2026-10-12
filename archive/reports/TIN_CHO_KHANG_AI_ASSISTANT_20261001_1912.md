CODEX REVIEW NODE 19:12 — 01/10. Chỉ OFFLINE/FAKE transport, KHÔNG hardware/Serial thật/start ROS trên Pi/flash/ARM/run2/logger/gain.

Đã đối soát runtime SHA 15f460b1…930a9b + bridge b5c17f8e…49ece8, trước/sau stable. A1 rxNaN, A2 numeric corrupt và W1 giữ STOP write-failure/unconfirmed đã sửa giới hạn; fullslice 4/4 exit0. Nhưng suite KHÔNG khởi tạo Node, không chứng minh full runtime.

4 lỗi nguồn thật, xem evidence_agv_20261001/review_node_1912.py/.json:
N1 AGVRos2RuntimeNode(is_mock=True) trên Windows FAIL NameError Odometry undefined khi không rclpy.
N2 callback scan bỏ header stamp0/frame unknown_sensor, đổi thành stamp100/frame laser rồi accepted — dữ liệu cũ thành mới.
N3 callback scan thiếu toàn bộ payload vẫn tạo ranges [1.0]*628 và accepted — không được chế dữ liệu cảm biến.
N4 actualgate+MockSerial qua D0→ARM request→ACK→freshARMED (chỉ mock), freshodom/scan: bare cmd callback tự lấy active_token và ghi V 0.040 0.000. Source authorization/session/command age bị bỏ qua tại Node.

Sửa theo lát cắt thực, đừng chỉ vá fixture:
1) Inject fake message types/ROSbus/clock để test khởi tạo Node bình thường, không __new__ hoặc monkeypatch bỏ constructor. Test phát callback qua subscription/executor thật trong fake bus.
2) Scan phải giữ source stamp/frame, mapping ROS→mono, tách receive-age và measurement-age, chặn stale/future/missing/invalid/unknownTF; không default ranges/angles/frame giả. Xử lý no-return theo contract LiDAR rõ ràng.
3) Lệnh từ adapter được xác thực nguồn/lease/session/epoch/age trước dispatch; không tự cấp active_token cho mọi callback. Bare Twist cần trusted source binding/deadman, không xem topic name là proof.
4) Adapter packet→Node /odom+TF thực sự publish, get_clock stamp/mapping/TFchain; hiện chỉ create_publisher, không publish qua Node. Main/init/executor/shutdown phải chạy offline an toàn.
5) Health timer đang gọi send_stop rồi bỏ outcome, cần dùng chung đường STOP với thread; lưu request/write/confirmed/failure/escalation, cập nhật freshD0 và shutdown STOP có kết quả.

QA phải instantiate Node và kiểm positive protocol flow, stale/missing scan, wrongTF, unauthorized source, caller im/watchdog, write-fail, freshD0 confirm; lưu command/exit/hash/raw fake bus outputs. Báo cáo lại đúng giới hạn, bỏ claim full production/100% khi chưa chứng minh. Bốn bot Telegram vẫn NOT_DISPATCHED/UNVERIFIED nếu chưa có actual ACK. Một Serial owner Khang AI Assistant. Không sửa model/gateway/token; không spawn Hermes thêm.
