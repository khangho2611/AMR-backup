# Review runtime AGV — 01/10/2026, 19:02 Asia/Bangkok

Phạm vi: nguồn thật/SerialMock, threadCPU hữu hạn. Không mở cổng thật, không ROS node trên xe, không nạp/ARM/run2.

## Mốc đã kiểm chứng

Source runtimeadapter0ed1d15c…aa358, bridgeb5c17f8e…49ece8, planner75a399fb…89ec0; hashtrước/sau ổn định. Parent chạy test_full_integration_slice.py3/3exit0, test_costmap_planner_v2.py12caseexit0 và test_ros2_arbiter_bridge.pyexit0. independent_runtime_suite_1902.json chứa log/hash/exit. Planner đã có advancingclockfixture và positivebudget, không còn assertionmicrotimeflaky. Tokenactive đã bỏ khỏi rejectmessage.

Có adapter packetfirmware khôngt và threadleasewatchdog thực; đây là tiến bộ offline, chưa fullROS runtime hay wholeAGV accept.

## Phạm vi còn thiếu

agv_ros2_runtime_adapter.py có3class FirmwarePacketAdapter/ActiveLeaseWatchdogThread/MockRos2RuntimeExecutor; AST không cócreate_publisher/create_subscription/create_timer/spin/add_node/get_clock. Chưa Nodeinstance/subclass, ROSHeadersec/nanosecmapping hoặc TFchain thực. main chỉ in READY. Docstring liệt kê Node/pubs/subs/timers nhưng implementation chưa có. Positivefixture tự đặt gate ARMED/token/ACKflags, không phải fullpacket/ARM/session lifecycle; watchdogcase chỉ assertleaseclear/tripcount, không assertSTOPbytes/latency/writefailure/confirmation.

## QA bổ sung nguồn thật

review_runtime_1902.py/.json; exit0 nghĩa tái hiện xong, không phải sản phẩm PASS:

| ID | Kịch bản | Quan sát | Yêu cầu |
|---|---|---|---|
| A1 | parse_and_ingest packetvalid, rx_monoNaN | TrảTrue và tự thay bằng time.monotonic mới | Explicit invalidrx phải reject, chỉ None được lấy receiveclock thật |
| A2 | JSON hợp lệ nhưng x='corrupt' | ValueError thoát parser | Validate/catch type/finite toàn bộ numeric fields, trả rejection, không chết receiver |
| W1 | Thread thật hếtlease, actualgateMockSerial.write raiseOSError | GateFAULT/stopunconfirmed, threadclearlease/tripcount1; không giữ outcome/emit event | Gate đã latchFAULT đúng, nhưng supervisor cần biết STOPfailed/unconfirmed, bounded escalation và threadhealth; không lấy leaseclear/tripcount làm đã dừng |

Adapter ép intPWM có thể mấtfraction; giữnumericvalidation thật, khôngtruncate dữ liệu actuator. Adapter dùng rxmono làm t để helperingest không đồng nghĩa mappingROSclock hoặc tuổi packet khi xử lý trễ. Phải phân biệt receptiontime và currentprocessingtime/freshness.

## Deliverable tiếp theo

Tạo Node runtime thực có publisherOdom/TF, scan và cmdsubscriptions, timer/watchdog/health callback, executor/main có lifecycle rõ. Inject fake transport/clock/ROSbus cho test offline, không connectSerial hoặc chạy node trênxe. Chứng minh outputROSHeader/time mapping, TFchain, subscriptioncallback qua authenticatedgate và callerimSTOPbytes/outcome. Sửa A1/A2/W1 bằng testindividual và positiveflow; gatebootUNKNOWN/settling, loggerboundsunique/maphomefootprint pending. Snapshot không được dùng nạp/run2 chỉ vì3suitePASS. BốnTelegrambots vẫn chưaACK.
