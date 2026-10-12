# Tin chờ gửi — chỉ Khang AI Assistant

**ĐÃ GỬI lúc17:28 ngày01/10/2026, Telegram hiển thị Sent và Seen.** Lỗi kích hoạt trước đó đã hồi sau khi khôi phục cửa sổ bị thu nhỏ. Đây là bằng chứng Khang AI Assistant đã nhận chỉ thị; chưa phải bằng chứng bốn bot Telegram đã nhận nhiệm vụ. Không gửi trực tiếp nhóm hoặc dùng token/API làm đường vòng.

KHANG ĐÍNH CHÍNH: “4 con bot” là bốn BOT TELEGRAM ĐÃ TẠO SẴN trong nhóm AI Engineering Lab: tên hiển thị @Khang_LeadBot, @coder_agent, @Tech_Writter, @QA_Tester. Khang yêu cầu CHÍNH BẠN (Khang AI Assistant) giao việc cho bốn bot này. Codex chỉ nhắn bạn; không trực tiếp giao nhóm. Bốn Hermes child deleg_6fdd7c97 là hiểu nhầm, không spawn/respawn thêm. Hãy xác minh actual username và chatID nhóm bằng công cụ được phép; nếu không gửi/nhận được phải báo exact error/toolproof, không giả ACK, không sửa privacy/gateway/model/reset để vượt chặn. Handoff kết quả child cũ, giữ bằng chứng, phân quyền không tranh file.

Bạn giữ đầu mối Serial/phần cứng duy nhất. @Khang_LeadBot điều phối/tích hợp offline; @coder_agent sửa gate/logger/ROS/planner theo lead; @Tech_Writter sửa tài liệu, manifest, hash/lệnh/exit code/phạm vi; @QA_Tester kiểm độc lập nguồn thật+counterexample. Không ARM/nạp/chạy lần2/recovery/gain/minPWM/reARM/CLEAR_FAULT hoặc nhờ Khang đẩy tay.

REVIEW 17:13: đọc DOI_SOAT_AGV_WORKERS_20261001_1713.md và evidence_agv_20261001/review_workers_1710.json. Ba suite hiện exit0 có thật nhưng chưa đủ, 6case nguồn thật mới FAIL:
G1 send_stop() lúc clock101 lấyanchor100 từtelemetrycũ; D0 timestamp100.5 vẫnstop_confirmed=True. Dùng mốc STOP thật/clockinject thống nhất, rejectbuffered sample.
G2 PWM+.5/-.5 bị int thành0, gate nhậnARM_REQUESTED/ghiARMmock; L1 logger cũngsuccess. PWM phải strictprotocol/zero chính xác trước conversion.
L2 loggerreadline OSError sau10mẫu vẫnreturnTrue; mọi readerror phảifailed/exit1.
P1 map20x20:6cộtfree/1cộtoccupied/13cộtunknown, coverage31.6%<85%, nofrontier, ởhome vẫnCOMPLETED. BáoPARTIAL/UNKNOWN/UNREACHABLE, chưatoànphòng.
P2 đổi frame map→different_map giữhomecũ khôngTF màCOMPLETED; gắn homeframe/mapepoch, invalidate hoặc chuyểnTFcóproof.
Các hashstable: gatebaeec6…f4843/loggera1807b…5d57/plannerd6d539…5986. Thêm regressioncase và test watchdogTHREAD thực khi callerimlặng, durationfinite/bounded trướcmởSerial, filelogunique khôngoverwrite, mapfreshness/originrotation/footprintđothực. Không đánhlại F01–F14 gốc; xem bảng trongreview.

BÁC “W2 HOÀN THÀNH/PASS Mock Bus”: session20261001_165058_1b0281 chỉ2messages/0toolcalls/1API, chưaimplementation/test. “Priority Queue + Mock Transport” khôngphảiSHA. W1/W3/W4 cótool thật nên khôngbác toàn bộ, nhưng100%triệtđểkhôngđạt. Sửa báo cáo trungthực.
Uptime/PORTS_FREE khôngchứngminhLIVE DISARMED haymotorngắtđiện saureboot. Giữfirmwaref5bf/supervisor1bd; sourcepreflightbounded/noTXphảireviewtrướcdùnghardware. Kết quả mock khôngthaynghiệmthuthựcđịa. Báo taskmessageID/ACK của từng bot sẵn có và output/testhash thật, mộtđầu mối tíchhợp. Nếu chưa giao được ghiBLOCKED exacterror và tiếp tục công việc offline đangđượcủyquyền, khôngtự nhận4botđãchạy.
