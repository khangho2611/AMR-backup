# Giải trình công việc liên quan đến xe AGV

Ngày: 01/10/2026, Asia/Bangkok. Phạm vi kết quả đã đối soát đến 18:35; tài liệu này không khẳng định trạng thái motor hoặc tiến trình trên Pi đang live tại thời điểm đọc.

**Đã có nạp firmware và một bài chạy xe thật. Xe chưa chạy ổn, chưa khám phá toàn phòng hoặc quay về gốc. Sau bài đầu, phần lớn công việc là sửa và kiểm thử phần mềm offline.**

Mục tiêu Khang giao: khám phá toàn phòng, lập bản đồ rồi về đúng vị trí và hướng ban đầu. Bot Khang AI Assistant thực hiện implementation, thao tác Pi/nạp/chạy theo bước được duyệt. Codex đọc nguồn, giao việc, kiểm độc lập và đối chiếu bằng chứng; không viết implementation AGV hoặc trực tiếp phát lệnh motor.

## 1. Những hạng mục đã thực hiện

| Hạng mục | Việc đã làm | Kết quả và giới hạn |
|---|---|---|
| Đọc và đánh giá folder | Đọc firmware, Python, ROS/web, launcher, tài liệu thiết kế; build và kiểm logic | Xuất DANH_GIA_VA_TRIEN_KHAI_XE_TU_HANH.md: ưu/nhược điểm, rủi ro, hướng triển khai; xác định14nhóm lỗi. Đây là đánh giá ban đầu, không phải nghiệm thu xe |
| An toàn firmware/motor | Giao bot sửa STOP, timeout, latch ARM/DISARM/FAULT, boot và driver I2C; review nguồn/hash, rebuild và QA | Đã chọn bản firmwaref5bf cho bài bench. Driver địa chỉ0x42 được đối chiếu; bản auto-clearFAULT tự nạp của bot bị bác dùng để chạy. QA giả lập có giới hạn |
| Backup và nạp thật | Bot sao lưu flash4MB, nạp ứng dụng; Codex đối chiếu command/exit/hash và dữ liệu | Bản cuốif5bf nạp verify thành công; preflight12mẫuDISARMED target/PWM/RPM0, lệnh điều khiển lúcDISARMED bị từ chối. Đây là bằng chứng trước bài13:57, không phải trạng thái sau mọi reboot |
| Supervisor bài chạy | Review chu kỳ phản hồi, deadline, giới hạn quãng đường, STOPfinally và xác nhận sau dừng | Serial/clockmock tái hiện các lỗi và kiểm bản cuối; dùng supervisor1bd trong bài thật. Không thay giám sát liên tục tại Pi hoặc người trực |
| Một bài chạy xe thật lúc13:57 | Bot chạy thẳng manual V0.05m/s trong khoảng2giây, có giới hạn và STOP cuối bài | Có20mẫuRUN+3POSTSTOP. Xe chưa bám tốc độ/quãng đường; không đạt motiontracking. Không thửAUTO, quay, névật hoặc toànphòng |
| Phân tích xe ít chuyển động | Đối chiếu RPM/PWM/odom; giao phân tích PID, encoder/CPR, driver, ma sát và điện áp; QA controllerC thật | Reset và clamp PID qua các caseoffline; ma sát/deadzone/encoder chưa có phép đo đủ để xác định nguyên nhân. Không tự tăngPWM/gain để thử mò |
| Cổng phân quyền lệnh Serial | Bot tạo arbiter/gate; Codex kiểm token/epoch, STOP latch, clock, stale telemetry, lỗi ghi | Nhiều counterexample đã sửa trong mock. Vẫn thiếu authsource đầy đủ, bootUNKNOWN/settling và bằng chứng watchdog/timer tích hợp; chưa nghiệm thu trên xe |
| ROS/Odometry/TF/LiDAR | Giao bot xây bridge, freshness, lease và tích hợp nguồn lệnh; đối chiếu với packetfirmware và QA | Đến18:35 filebridge còn helpermock, chưa Node/runtimeROS hoàn chỉnh, chưa adapterclock cho packetfirmware thực. Chưa được coi là ROS hoạt động trên xe |
| Planner/costmap/frontier/home | Bot xây các helper tìm đường, kiểm footprint/reachability, completion và home; Codex kiểmmapthiếu/khenghẹp/coverage/frameepoch/deadline | Có code và mocktest thật, có lỗi đã sửa. Chưa thành hệ thống khám phá/phản hồi chuyển động hoàn chỉnh; chưa chứng minh homeposition+heading/mapfresh/footprintthực |
| Kiểm tính trung thực của bot | Đọc log công cụ, source/hash và chạy lại QA độc lập; bác các claim100% không đúng phạm vi | Có workthật, cũng có báo cáo quá mức. W2Hermes cũ chỉtext/0toolcall bị bác; PASSmock/build không được dùng thay nghiệm thu thực địa |
| Giám sát và tài liệu | Lưu rawlog, JSON, QA và báo cáoMD; gửi nhiệm vụ cụ thể, xác nhận Sent/Seen; bật monitor10phút | GIAO_VIEC_AGV.md ghi mốc, quyền và việc còn thiếu. Monitor kiểm tiến độ/bằng chứng, không phải bộ điều khiển hay watchdog thời gian thực của xe |

## 2. Xe thật đã đạt và chưa đạt gì

| Số liệu bài13:57 | Kết quả |
|---|---|
| Thời gian Vđầu→STOP | 2.0065s |
| Odometry cuối | 2mm; lệnhnominal tương ứng100mm nếu bám tốc độ. Chưa có đo quãng đường ngoài encoder |
| Tốc độ bánh | Target13RPM; peaktrái5.12/phải2.56RPM;18/20mẫu cảhaiRPM0 |
| PWM quan sát | Khoảng14–51 |
| Dừng | MẫuDISARMED target/PWM/RPM0 đầu sau94.4ms;3mẫu sau294.3ms |

Kết luận: **nạp/preflight có bằng chứng; dừng đã quan sát được trong bài ngắn; chạy bám lệnh chưa đạt**. Chưa thử mấtheartbeat thật, mấtscan thật, chướngngạivật, SLAMkhichạy, exploration, returnhome hay độ bền lặp lại. Không có bằng chứng xe đã hoàn thành100%.

Rawlogstraight_1357_raw.log có SHA2560b4d82d5c6ab2867cb295828340eca2acc732294110e4e7543f70628baabec1a, khớp filePi đã đọc độc lập. Báo cáo chi tiết: KET_QUA_NAP_VA_CHAY_THU_AGV_20261001.md.

## 3. Hạng mục đang giao sửa ở checkpoint18:35

1. **STOP ưu tiên:** kiểm thửmock phát hiện STOP bị reject khi leaseTTL100s, không gửiSTOP và mockgate vẫnARMED. Tách kênhSTOP khỏi validationTTL/lease/velocity của lệnh chạy; không báoENFORCED chỉ từ ghi thành công khi chưaD0freshconfirm.
2. **Quyền nguồn lệnh:** odomfresh vẫn không ngăn callerleasebấtkỳ mượn active_token của gate. Cần nguồn/lease/sessionepoch được cấp quyền rõ, NAV cầnscan/TFfresh, chặn nguồnkhôngđăngký.
3. **Tích hợp ROS thực:** packetfirmware→timestamp nhậnPi→mappingclockROS→Odometry/TF/scan→arbiter→gate→STOP. Cần Node/publishers/subscriptions/timers/executor thật, testfake transport trước triển khai. FileimportROS hoặc publishergiả chưa đạt mục này.
4. **Planner và nghiệm thu room/home:** còn mapfreshness/originyaw/epoch, footprintthực, frontierreachable và điều kiện homeposition+heading; suiteplannerWindows vẫnexit1case6 trong snapshotđãđốisoát. Cần testclockdeterministic, không tuyên bốPASSWindows từ kết quảPi.
5. **Chuẩn bị phép đo xe:** bootD0live saureboot, loggerboundedkhôngghiđè, kếhoạchđoencoder/motiontracking cógiới hạn, rồi mới reviewbài chạy tiếp. Chưa có nguyên nhân chuyển động yếu đã xác minh.

CODEX REVIEW18:32 đã gửi đúng Khang AI Assistant, TelegramSeen/Sent18:35. Bot được yêu cầu triển khai tiếp một luồng tích hợp hoàn chỉnh, không dừng ở sửa vài testcase hoặc viết báo cáo. Chưa duyệt nạp/ARM/bài chạy2/logger thật/gain mới.

## 4. Việc bốn bot và phần chưa làm được

Đã có hiểu nhầm: bot tạo4Hermessubagent mới thay vì4botTelegramKhang đã tạo. Ba child có toolwork thật; childW2 chỉtext không được tính hoàn tất. Đã đính chính yêu cầu: Khang AI Assistant phải làm broker giao cho @Khang_LeadBot/@coder_agent/@Tech_Writter/@QA_Tester có sẵn, không spawnthêm.

**Chưa có bằng chứng bốn botTelegram nhận/chạy nhiệm vụ**; trạng thái NOT_DISPATCHED/UNVERIFIED. Không báo giả đã phối hợp4bot. Broker được tiếp tục offline tuần tự trung thực khi chưa có cơ chếdispatch/ACK hợp lệ.

Chưa có bài chạythật2; chưa chạy/hiệuchuẩnSLAMthực địa; chưa bật tự khámphá; chưa đo quãngđường/góchome độc lập; chưa nghiệmthu toànphòng. Có codehelper và nhiều kiểm thử không đồng nghĩa các chức năng này đã hoàn thiện.

## 5. Vì sao nhiều công việc chưa làm xe chạy

Các lớp đang sửa đều nằm trên đường điều khiển xe: STOP ngăn chuyển động ngoài ý muốn; arbiter quyết định nguồn nào được gửi motor; scan/TF/odomfresh ngăn dùng dữ liệu cũ; planner/costmap chọn đường thực sự lọt thân xe; map/home xác định đường quay về.

Tuy nhiên, cần nói rõ giới hạn tiến độ: **đã mất nhiều lượt sửa các lỗi cục bộ nhưng luồngROS→motor→map/home chưa được tích hợp hoàn chỉnh**. Các nhãnPASS100% của bot vượt quá bằng chứng đã bị bác. Chưa thể nói xe hoạt động đúng mục tiêuAGV. Mốc tiếp theo phải là testintegrationpositiveflow và watchdog/STOP thực bằng faketransport, rồi preflight và bài chạy có đo thật; không chỉ thêm báo cáo hoặc testcase.

## Tài liệu và bằng chứng truy vết

- DANH_GIA_VA_TRIEN_KHAI_XE_TU_HANH.md: đánh giá folder và14nhóm lỗi gốc.
- KET_QUA_NAP_VA_CHAY_THU_AGV_20261001.md: nạp, preflight, rawlog và kết quả xe thật.
- GIAO_VIEC_AGV.md: lịch sử giao việc/đốisoát, quyền và checkpoint.
- DOI_SOAT_AGV_RESIDUAL_20261001_1832.md: lỗi còn lại ở snapshot gần nhất đã kiểm.
- evidence_agv_20261001/: rawlog, toolproof, hash, kết quả test và QA độc lập.
