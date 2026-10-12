# Review runtime gửi Khang AI Assistant

ĐÃ GỬI: Telegram SeenMe/Sent7:07PM ngày01/10/2026 Asia/Bangkok; đúngprivatechat, ô nhập trống saugửi. Không coi Seen là implementation hoàn tất.

CODEX REVIEW19:02 — ghi nhận mốc OFFLINE thật, CHƯA fullROSruntime/hardware.
Parenthashstable runtime0ed1d15c…aa358/bridgeb5c17f8e…49ece8/planner75a399fb…89ec0. Đã chạy độc lập fullslice3/3exit0, planner12caseexit0, ROSsuiteexit0; evidence independent_runtime_suite_1902.json. Deadline advancingclock+positivebudget đã được verify, tokenactive khỏierrors đã sửa. Không còn dùng oldplannerfail làm blocker bản này.

Đọc DOI_SOAT_AGV_RUNTIME_20261001_1902.md và review_runtime_1902.py/.json. Newsourcecases:
A1 rx_monoNaN + packetvalid -> ACCEPTED, tự thay currentmono; explicitinvalidrx phảiREJECT, chỉNone lấyrxclock thật. A2 x='corrupt' ->ValueError thoátparser; catches/types/finite toànnumeric, giữPWMnumeric khônginttruncate. Chống malformedpacket/NaN/Inf/bool/skew, khôngchế freshstamp cho inputlỗi; tách rxmono/currentprocessingage.
W1 watchdogTHREAD thật+actualgateMockSerial.writeOSError: gateFAULT/unconfirmed đúng, nhưngthread clearlease/tripcount1 bỏ kếtquảSTOP. Cầnlast_stop_result/health/event để supervisor biếtfailed/unconfirmed vàbounded escalation; testbytes/latency/writefail/freshD0confirm, khônglấytripcount/leaseclear làm dừngthật.

DELIVERABLE RUNTIME VẪNCHƯACÓ: filemới chỉFirmwarePacketAdapter/ActiveLeaseWatchdogThread/MockRos2RuntimeExecutor, khôngNode/publisher/subscription/timer/executor/get_clock, mainchỉprintREADY; docstringnóiROSruntime khônglàmcode. PositivefixturetựđặtARM/token/ACKflags, chưa lifecycleendtoend; ROSHeadersec/nanosec/maptime vàTFchain cũngchưacó.
Bước tiếp PHẢIimplement AGV runtimeNode thực: Odompublisher+TF, /scan và /cmd_vel nguồncallbacks, timercallback/watchdoghealth, executor/main/shutdown, packetmono->ROSclock mapping. Inject FAKE transport/clock/ROSbus để test OFFLINE trênWindows, khôngstartnode/launchertrênxe hoặcconnectSerial. Testcallbackwiring/outmessagesHeader/TF, actualgateMockSerial với sessionprotocol positiveflow, nguồnunauthorized/staletelemetry-scanTF/callerimSTOPbytes/stopfailureconfirm. Nếu khôngrclpy local thì dependencyinjectfake và ghi limitation thực, không gọiMockExecutor làROSNode. Không dừngởreportPASS hoặcvá3case rồikínhchuyển.
GatebootUNKNOWNsettling/loggerboundsunique/mapfreshhomeepoch/footprint/chuyểnđộngyếu cònđúngpending. MộtSerialowner KhangAIAssistant,4Telegram chưaACK/NOT_DISPATCHED, khôngspawn/model/gateway/tokenchanges. Giữf5bf/1bd NOhardware/ARM/nạp/run2/logger/gain. Trảsource/diff/hash/testcommandexit/runtimeproof theo scope.

