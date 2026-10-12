# Đối soát nguồn số đo và hệ thống AGV — 02/10/2026, 13:24 Asia/Bangkok

Codex chỉ đối soát/QA và giao sửa; không viết implementation, không Serial OPEN/TX, không deploy/start trên Pi. Giữ nguyên Word, Markdown người dùng đưa và assembly.

## Căn cứ gốc và thứ tự ưu tiên

Người dùng yêu cầu tiếp tục và đọc kỹ: SolidWorks chỉ là bản vẽ; số đo thực dùng tài liệu Word. Đã đọc toàn bộ body, bảng và Office Math của `TINH_TOAN_THIET_KE_XE_TU_HANH.docx` (SHA256 `ad9d7a45fdc7cc16982df7a22cb4e277bc2794dcbd3efacfdb8cad40853981ca`). Trích xuất đầy đủ: `evidence_agv_20261001/parent_word_full_extraction_20261002_1320.json`.

Đã đọc đầy đủ `BANG_GIAI_TRINH_THONG_SO_AGV_CHUAN.md`, SHA256 `f7f59be260780f8d8fbcac16e0ed8f470bce627e90056622610acd0a97f0cc93`. Đây là bảng tổng hợp broker vừa tạo (DB10535–10541), không phải mọi số đều là kết quả đo. Không lấy các khẳng định trong bảng làm quyền chạy hay nghiệm thu hiện tại.

Assembly người dùng chỉ định: `D:/HoMinhKhang/PROJECT/GITHUB_PROJECT/XETUHANH/AGV_SOLIDWORKS_V2_NATIVE/AGV_2TIER_FRAME_20260916/video/Assem3.SLDASM`, 330860 bytes, SHA256 `40be4cb4dcd486545bfa6193ca531aa7293ebef41c32a33779da21ec57e92973`. Đã xác minh danh tính file; chưa render/đọc hình học native bằng SolidWorks. Không suy kích thước thực từ file này. Metadata lưu `parent_assembly_identity_20261002_1320.json`.

| Thông số | Căn cứ Word | Kết luận dùng cho QA |
|---|---|---|
| Khối lượng 1.75 kg | Mục 1: cân xe hoàn chỉnh | Số đo người dùng đã lưu; cập nhật nhận định cũ thiếu provenance |
| Chu vi bánh 0.23 m | Mục 2: thước dây đo trực tiếp | Số đo gốc; Word không nói đã đo chu vi lăn dưới tải, không tự thêm điều đó |
| Khoảng cách tâm hai bánh 0.1875 m | Mục 2: đo trực tiếp | Track width, không phải chiều dài/cả footprint |
| R ≈ 0.0366 m | C/(2π) | Giá trị suy ra, khớp cấu hình; chưa tự hiệu chuẩn mới |
| M = 2.10 kg | 1.75 × hệ số dự phòng 1.2 | Khối lượng thiết kế, không số cân tải tối đa |
| 11 PPR, gear 21.3, CPR 937.2 | Mục 6: thông số encoder/hộp số, x4 | Giữ căn cứ tài liệu và cấu hình; không coi là phép đếm xung mới của bài đang xét |
| 1m đạt 995–1005mm | Bảng nghiệm thu cuối Word | Kết quả lịch sử được tài liệu ghi nhận; không chuyển thành nghiệm thu snapshot mới |
| Góc quay/caster | Bảng ghi “thẳng băng 100%”, không bảng số góc trước/sau | Chưa có số đo sai số heading định lượng để nghiệm thu về hướng gốc |

Động cơ 280RPM là thông số bộ GA25 đã mua ghi ở mục 4.2, không phép đo RPM có tải hiện tại. Với C=0.23m: 140–150RPM bánh tương ứng 0.5367–0.5750m/s. Mục tiêu người dùng giữ nguyên theo lộ trình có giới hạn; không thay RPM bằng số PWM. Gear43.8 suy đoán trước đây không được ưu tiên hơn tài liệu gốc21.3; muốn sửa CPR cần bằng chứng riêng.

## Những chỗ không được chép thành cấu hình hay chứng minh vật lý

- Word khuyến nghị PID Kp12–18/Ki1.5–2.5/Kd0.2–0.5 ở chu kỳ20ms. Firmware hiện khác thang đo/chu kỳ: .5/1.5/.010/.45, 50ms. Không nạp gains Word trực tiếp khi chưa đối soát đơn vị RPM/v, dt, đạo hàm và feedforward.
- Mức PWM120–130 là ước tính tỷ lệ tốc độ130/280 trong Word. Không chứng minh công suất/điện áp/mô-men có tải tuyến tính. Deadband60–80 xuất hiện trong MD nhưng không có phép quét đo tương ứng trong Word. Chỉ có bằng chứng sau này PWM120 ở MAN tạo RPM và người dùng xác nhận chạy được; không suy ngưỡng tối thiểu/nguồn tốt/CPR tuyệt đối đúng.
- 70/30 phân bổ tải, hệ số cản lăn .02, hiệu suất .85, a tăng.3 và hãm.5 là giả thiết/chọn thiết kế. Cự ly dừng37.5–40cm dựa trên trễ50ms và hãm.5, chưa đo stop margin thật. STOP không cấp quyền tự lùi vào vùng chưa quét.
- Ví dụ Word “1m đo9187.5mm”, “tăng187.5mm lên86mm”, “giảm187.5 xuống84mm” mâu thuẫn rõ; giữ nguyên tài liệu, đánh dấu cần đính chính. Không nạp86/84mm hoặc công bố hết sai số100%. Dung sai±5mm trên1m là≤0.5%, không luôn<0.5%.
- Offset LiDAR+.05m/+.12m, vùng75/42cm và frontier<15ms có trong MD nhưng không có phép đo/benchmark tương ứng trong Word. Cần provenance riêng, đặc biệt footprint đầy đủ/origin yaw/frame map.

## Thay đổi thật từ checkpoint 11:04

DB task đúng session `20260925_200222_e933f7d8`, đã đọc tới10547. Các user9809/9819 yêu cầu chạy,9953 nói “RỒI OK CHẠY ĐƯỢC RỒI ĐÓ GIỜ CHẠY TOÀN BỘ HỆ THỐNG CHO TAO”;10436 yêu cầu tích hợp frontier/PID input/lịch sử/xuất Excel. Đây là lời người dùng trong lịch sử task; không lấy lời broker làm quyền. Câu hỏi cũ bánh có chạy đã có xác nhận lịch sử9953; không hỏi lại.

Tools9828–9829 thật chạy candidate.08/1.2/1.8;9848–9849 thật chạy.15/1.2/1.8. Khác profile1/1.5 đã được review trước; Codex chưa nghiệm thu chúng. Tools9944–9945 ARM rồi M120;9948–9949 text command M130 nhưng ACK/D0 lại M120/PWM120. Cần đối soát raw/timeout, không bỏ qua mâu thuẫn lệnh. D0 DISARMED/PWM0 còn RPM47–60 ở những mẫu đầu, cho thấy zeroPWM không đồng nghĩa đã dừng vật lý.

Tools10527–10528 xác nhận PID46022 chạy brain12:16. Một số commands/outputs sau compaction là replay historical, không đếm thành nhiều bài mới. Không ghi firmware binary đã đổi nếu không có flash/hash chứng minh.

SSH chỉ đọc lúc13:15 (Pi Unix1790921740.7226765): boot mới `1a219e09-b897-49c1-b0e3-a1649833aaf7`, không tiến trình AGV/ROS/SLAM, fuserUSB0 exit1 stdout/stderr rỗng. Boot khác b9714… cũ. **Đây không phải fresh D0 DISARMED hay bằng chứng đã tắt motor**. Evidence `parent_pi_readonly_status_20261002_131405.json`. Đọc hash Pi13:20 trong `parent_pi_source_hash_20261002_1322.json` khớp nguồn brain và HTML local; chương trình có trên Pi nhưng chưa chạy sau reboot ở cửa sổ kiểm tra này.

## QA candidate.08: chấp nhận giới hạn offline

Runner907c5882620b2a65b78c7f69a21893e941c073102f5e3c56ba192370688a2750; gate95c8667ffd66a1076e68ce55a381afaee5f9618c7a705c991b61ae2e9978213d ổn định trước/sau. Broker6case là componentfixtures, không fullproduction. Parent đã bổ sung QA actual `execute_lifecycle`/gate/reader/watchdog, realclock10s/80, chỉ thay physicalOPEN/lock; không hardware.

Evidence: `evidence_agv_20261001/parent_candidate_brain_20261002_1318/review.json`, script `review_candidate_and_brain_20261002_1318.py`.

- Positive.08/nominal1/hard1.5:126D0/span10.063s,ARM1,V20,STOP1,exit0,confirmed,closed,threadsdead.
- Overspeed30RPM, stallPWM85/RPM0 sau.8, mismatch20/2 giữ>100ms: STOP, fault vàexit1, freshzero xác nhận dừng giới hạn.
- PartialSTOP1/5 + independentzero: FAULT, runnerunconfirmed,exit1; gateconfirmed riêng không biến thànhPASS.
- Caller bị chặn1.8s sau start (seam giả lập caller; watchdog/reader không sửa): WATCHDOG_HARD_TIME_CAP/STOP/exit1,confirmed,khôngV.
- InvalidPWM chuỗi: gate telemetry dừng cập nhật, stale rejection/STOP/exit1. Không kết luận mọi malformed field đều đạt.

Không chứng minh soleowner thật, crash/kill/physicalstop, encoder hay hiệu quả khởi động. Bỏ blocker cũ sourcecap.05/guards chưa implement đối với candidate907/95; không tự cấp quyền chạy từ PASS offline.

## Lỗi nguồn hệ thống đang triển khai — cần sửa trước chạy tự hành

`agv_unified_brain.py` SHA256 `ff009266bc744da14b625c83b98f52c15f0cfd0d55cf3b047c2f541e7c1608e6`, hash Pi khớp. HTML `d7ae756030363875908bec39e4b944d9181c427553a1d419f5a59c00947110c1`.

1. **F12/F03/F08:** send_cmd156–164 tự phát ARM trước mọiM/S/V, không ACK+freshARMED/preflight/FAULT latch/session/source authorization hay TXlock; các HTTP threads và callback có thể tranh writes. Tái hiện exact method với FakeUART: ARM CRLF rồi M120 ngay. Trái yêu cầu không auto reARM.
2. **F03/F07:** auto_nav_loop với scan/map/telemetry mặc định chưa nhận vẫn M-120/120. serial_read_loop chạy while không bound và sleep.25/.35/.4/.5 trong callback chặn executor, không watchdog độc lập kiểm freshnessscan+D0+publicSTOP. Không có timestamp/frameepoch dữ liệu map/scan.
3. **F02/F06/F08:** giả lập STOP/auto_mode=False giữa sleep tránh vật: commands `[M -115 -115, STOP, M 125 -125]`. Callback tiếp tục TURN sau STOP; send_cmd tự ARM. Dừng khẩn phải latch và hủy job/queue, không lùi không rear guard.
4. **F04:** scan góc ROS +90° (trụcY trái) bị ghi zone RIGHT=50cm,LEFT=999. Cần dùng convention+TF đã đo, không sửa hai nhãn mù nếu mounting yaw khác. Offset yaw0 hiện khai báo không đảo được lỗi.
5. **F09/F10:** frontier nearest trực tiếp, không reachable planner/A*/inflation/footprint. Fixture đầu quá chặt bị lọc neighbors không tái hiện; fixture followup tạo đảo free với láng giềng free/unknown và vòng occupied tách hoàn toàn vẫn trả goal(1,1). Evidence `parent_frontier_disconnected_20261002_1322.json`; không đổi kết quả cũ thànhPASS giả. Map chưa có/step3/range.4–3.5 không frontier đều conflatedNone→RETURNING_HOME. Unknown≠chưa đi, free≠đã đi. Coverage cần semantic riêng.
6. **F09/F10/F11:** đang lấy robot poseodom so trực tiếp tọa độmap, bỏ originyaw/frameid/epoch và map→odom TF. Home ghi sau spin6s theo timer chứ không trước motion; home_th lưu nhưng không dùng. Home successdist<.20m bỏ heading. Repro map rỗng, hướng lệchπ vẫn công bố thành công vàautoFalse.
7. **PID/lịch sử:** tự hành chỉ phátM MAN, bypassPID; TUNING không điều khiển hiệu quả vòng kín ởMAN. HTML parseFloat(x)||default thay0hợp lệ; API luônstatusok khôngACK/readback, lịch sử ghi“Đã nạpMCU” dùsendfail/MCUreject/noMCU. localStorage500dòng/CSV là tính năng đã có nhưng không lịch sử áp dụng có nguồnMCU/phiên/thời gian đầy đủ. CSV không phải workbookxlsx.

## Review block và giao việc

Action: restart/deploy/chạy tự hành, reARM hoặc tuning trên Pi. Args: `agv_unified_brain.py` ff009…608e6, `/dev/ttyUSB0`115200, web `/api/auto?act=START`, M±110..140 hoặc `/api/pid`. Decision: **NOT_APPROVED theo QA nguồn hiện tại**. Reason: tự ARM/bypassPID/no freshness/STOP bị ghi đè/goal khôngreachable/homeheading thiếu. Đây là đánh giá Codex, không automaticapprovalrejection; không phủ nhận người dùng đã yêu cầu chạy/tích hợp nói trên.

Giao hardwareowner Khang AI Assistant một bundle source OFFLINE: nối UI với gate/runtime/planner đã đối soát, singleownerqueue/session+ACK+freshD0, latchedSTOP/fault/no autoARM, watchdog độc lập scan/D0 và không block executor; mapTF/epoch/yaw/footprint/reachable/coverage/homepose+heading trướcmotion. Giữ số đo Word, sửa provenance MD và kế hoạch motor/PID có đơn vị, không chữa thiếu lực bằngPWMhardcode haynânggain chưareview. Giữ tính năng PIDinput/history/CSV nhưng chỉAPPPLIED sauMCUACK/readback; phân biệtPENDING/REJECTED/FAILED.

FullentryFakeUART+typedmockscan/mapTF+HTTP/UI commands test là điều kiện bàn giao, gồm mấtscan/D0, malformed, STOP race, blockedfrontier, missingmap, wrongheading, MCUrejectTUNING/0valid/disconnected. Source/hash/diff/exactcommand/backuprollback/preflight cùngprofile và groundtruthbounded phải có trước bài tiếp. Sau reboot phải chốt freshtransport+điều kiện hiện trường hiện tại khi kế hoạch đãready; không hỏi quyền chung lại. User xác nhận chạy lịch sử không thay currentfreshconditions. Không Codeximplementation/Serial/flash/gain/startROS; monitorACTIVE tới room/map/homeheading, không fake4botACK.
