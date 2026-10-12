# Báo cáo kiểm toán mã nguồn AGV — Cổng nghiệm thu độc lập

## 1. Kết luận điều hành

**VERDICT: REVISION_REQUIRED**

Mã nguồn hiện tại chưa đủ điều kiện nghiệm thu. Lý do trực tiếp là bộ kiểm thử UI tại root đang thất bại: trạng thái `latched=true`, `armed=false`, `preflight_ready=true` vẫn làm nút AUTO khả dụng do điều kiện tại `index_cyberpunk.html:576-598` không loại trừ `latched`; lỗi được tái hiện bởi `node --test tests\test_agv_pid_ui.cjs`, exit code `1`, tại `tests/test_agv_pid_ui.cjs:99`. Ngoài ra, chưa có bằng chứng build firmware hiện hành vì PlatformIO không được cài, nên không thể xác nhận nguồn trong `robot_stm32_f103/` biên dịch thành công hoặc trùng với firmware thực tế. Không phát hiện bằng chứng P0 trong phạm vi đọc tĩnh: watchdog firmware vẫn dừng và DISARM sau 300 ms, do đó lệch timeout phía Python chủ yếu gây mất tính sẵn sàng, không phải mất fail-safe. Tuy vậy, các sai khác timeout, giới hạn lệnh và ngữ nghĩa `RESET` giữa Python và firmware là lỗi giao diện liên tầng phải được sửa trước nghiệm thu.

## 2. Phạm vi và bản đồ thẩm quyền kiến trúc

### Phạm vi đã kiểm toán

- Bộ điều khiển Python tại root: `agv_unified_brain.py`, `agv_command_session.py`, navigation, journal và preflight collector.
- Web UI đang được bộ test root sử dụng: `index_cyberpunk.html`.
- Firmware tại root: `robot_stm32_f103/src/main.cpp`.
- Bộ test root trong `tests/`.
- Candidate biệt lập: `candidates/agv_rpm140_20261003/`.
- Tài liệu bàn giao, kho lưu trữ và evidence lịch sử; không coi các khu vực này là nguồn thực thi hiện hành.
- Không mở serial, không truy cập GPIO/motor, không chạy launcher, không flash firmware và không thay đổi source.

### Bản đồ thẩm quyền

| Khu vực | Vai trò | Mức thẩm quyền |
|---|---|---|
| Root Python, HTML và `robot_stm32_f103/` | Nguồn đang được test root và là đối tượng kiểm toán chính | **Nguồn chuẩn của audit này** |
| `candidates/agv_rpm140_20261003/` | Đề xuất profile 140 RPM biệt lập | **Không phải bản đã triển khai**; `candidates/agv_rpm140_20261003/README.md:1` ghi rõ `NOT DEPLOYED` |
| `archive/`, `archive/reports/`, `archive/legacy_evidence/` | Lịch sử, báo cáo cũ và snapshot | Không có thẩm quyền runtime |
| `evidence_agv_20261001/` | Chứng cứ các phiên trước | Chỉ có giá trị theo thời điểm và hash được ghi; không chứng minh trạng thái hiện tại |
| `baocao/`, `docs/` | Báo cáo và kế hoạch | Tài liệu tham khảo, không phải nguồn thực thi |

Tài liệu bàn giao xác nhận candidate 140 RPM chưa được nạp tại `README_CODEX_AGV_TIEP_TUC.md:13` và `README_CODEX_AGV_TIEP_TUC.md:363-371`. Candidate có bản sửa UI đúng hướng tại `candidates/agv_rpm140_20261003/index_cyberpunk.html:501-509`, nhưng thay đổi đó chưa nằm trong root. Thư mục cũng không phải Git repository, nên không có commit, tag, merge-base hoặc lịch sử diff tin cậy để chứng minh nguồn nào đã được phát hành.

## 3. Các phát hiện ưu tiên cao nhất

Không gán P0 vì không có bằng chứng xác nhận đường điều khiển có thể vượt watchdog hoặc cấp chuyển động khi DISARMED. P1 dưới đây là lỗi nghiệm thu, tích hợp hoặc trạng thái điều khiển nghiêm trọng; không đồng nghĩa tất cả đều là nguy cơ gây chuyển động mất kiểm soát.

| ID | Mức | Trạng thái | Vị trí chính xác | Bằng chứng | Tác động | Khắc phục |
|---|---|---|---|---|---|---|
| AGV-01 | P1 | CONFIRMED | `index_cyberpunk.html:575-598`; `tests/test_agv_pid_ui.cjs:96-100` | Root tính `active=(armed || preflight_ready) && !fault`, không xét `latched`. Test mong `btnAuto.disabled=true` nhưng nhận `false`; Node exit `1`. | UI cho phép người vận hành bấm AUTO trong phiên đã khóa. Backend vẫn có gate tại `agv_command_session.py:393-406`, nên chưa xác nhận chuyển động vật lý; đây là lỗi human-factor và sai biểu diễn trạng thái an toàn. | Dùng `active = c.armed && !c.latched && !c.fault`; khóa cả AUTO/MAN khi latched. Chạy lại test root. |
| AGV-02 | P1 | RISK | `robot_stm32_f103/platformio.ini`; `robot_stm32_f103/src/main.cpp:24-26` | `pio`/PlatformIO không được cài; firmware hiện hành chưa được build trong phiên audit. | Không thể nghiệm thu cú pháp, liên kết, cấu hình board hoặc xác nhận binary tương ứng với nguồn. Đây là thiếu bằng chứng phát hành, không phải bằng chứng firmware chắc chắn lỗi. | Cài toolchain cố định phiên bản, chạy build sạch và lưu command, exit code, binary hash, board target. |
| AGV-03 | P1 | CONFIRMED | `agv_command_session.py:498-520`; `robot_stm32_f103/src/main.cpp:26`; `robot_stm32_f103/src/main.cpp:447-457` | Python cho tuổi caller AUTO tối đa `0.50 s`; firmware DISARM nếu không nhận lệnh hợp lệ quá `300 ms`. | Firmware dừng trước khi Python tuyên bố `CALLER_TIMEOUT`. **Fail-safe vật lý được bảo toàn**, nhưng phiên AUTO có thể dừng/disarm ngoài dự kiến, gây lỗi availability và trạng thái Pi–MCU lệch nhau. | Giảm deadline phía host xuống dưới 300 ms với margin đo được, ví dụ 200 ms; không tăng watchdog firmware để che độ trễ. |
| AGV-04 | P1 | CONFIRMED | `agv_command_session.py:345-360`; `agv_unified_brain.py:62-65`; `agv_unified_brain.py:1153-1159`; `robot_stm32_f103/src/main.cpp:201-214`; `robot_stm32_f103/src/main.cpp:294-310` | Host nhận `V` đến `0.35 m/s`, `0.95 rad/s` và `M` đến ±140; MCU root giảm `V` xuống ±0.15/±0.60, wheel target xuống ±65 RPM và `M` xuống ±120. | Lệnh được host báo `SENT` nhưng xe nhận giá trị khác. Chủ yếu làm xe chậm/khác quỹ đạo dự kiến; không phải vượt trần an toàn vì MCU clamp chặt hơn. | Dùng một hợp đồng giới hạn duy nhất hoặc xác nhận ACK hiệu dụng. Không coi `M 140` là 140 RPM. |
| AGV-05 | P2 | CONFIRMED | `agv_unified_brain.py:248-268`; `robot_stm32_f103/src/main.cpp:166-180` | Python xử lý `RESET` hoàn toàn cục bộ và trả `RESET_OK`; không gửi chuỗi `RESET`. Firmware chỉ reset encoder và odometry khi thật sự nhận `RESET`, rồi trả ACK. | Tên lệnh trùng nhưng tác dụng khác. Người vận hành/API có thể tin rằng reset đã áp dụng xuống MCU trong khi encoder/odometry không thay đổi. | Tách tên `RESET_SESSION` và `RESET_ODOMETRY`; lệnh MCU phải chờ exact ACK và chỉ được phép khi DISARMED. |
| AGV-06 | P2 | CONFIRMED | `robot_stm32_f103/src/main.cpp:91-98`; `robot_stm32_f103/src/main.cpp:182-223`; `robot_stm32_f103/src/main.cpp:285-310`; `robot_stm32_f103/src/main.cpp:315-337` | Buffer firmware chỉ giữ 79 byte; phần dư bị bỏ im lặng. `STOP` dùng so sánh prefix bốn ký tự; `V/M` dùng `sscanf` hai trường và không kiểm tra ký tự dư. | Dữ liệu quá dài hoặc có hậu tố có thể bị diễn giải thành lệnh hợp lệ bị cắt ngắn. Host hiện gửi lệnh ngắn và kiểm tra ba token, nên đường bình thường ít bị ảnh hưởng; parser MCU vẫn thiếu fail-closed. | Reject toàn bộ frame quá dài, yêu cầu hết chuỗi sau tham số, dùng so sánh chính xác cho lệnh không tham số và thêm native parser tests. |
| AGV-07 | P2 | RISK | `agv_unified_brain.py:1007-1021`; `agv_unified_brain.py:1263-1273` | Shutdown có gửi STOP, chờ xác nhận, dừng thread, đóng serial và cleanup lock; finalizer ném lỗi nếu STOP/cleanup chưa xác nhận. Chưa có kiểm chứng phần cứng trong audit. | Thiết kế source là fail-closed, nhưng chưa chứng minh hành vi khi serial treo, thread không join hoặc MCU mất nguồn. | Thêm test mô phỏng từng failure path và một nghiệm thu HIL có người trực nguồn, không chạy trong audit đọc tĩnh. |
| AGV-08 | P2 | CONFIRMED | `candidates/agv_rpm140_20261003/tests/run_agv_tests.py:16`; `candidates/agv_rpm140_20261003/tests/test_rpm140.py:16,41,64` | Runner candidate dùng pattern `test_agv*.py`: chạy 100 test; standard discovery `test_*.py` chạy 105 test. | Runner được tài liệu hóa có thể xanh trong khi bỏ sót toàn bộ `test_rpm140.py`, đúng phần đặc thù của candidate 140 RPM. | Đổi pattern thành `test_*.py` hoặc liệt kê suite tường minh; thêm assertion số test tối thiểu. |

## 4. Ma trận tương thích Python ↔ firmware

| Hạng mục | Python/root | Firmware/root | Đánh giá |
|---|---|---|---|
| TX delimiter | Gửi LF, ví dụ drive tại `agv_command_session.py:409`, STOP tại `agv_command_session.py:451`, idle V0 tại `agv_command_session.py:490` | Kết thúc frame bằng CR **hoặc** LF tại `main.cpp:323-330` | **Tương thích** |
| RX CRLF | Tách tại LF rồi `raw.strip()` ở `agv_unified_brain.py:307-313`, nên loại CR | `Serial.println`/`printf(...\r\n)` tại `main.cpp:109`, `main.cpp:121`, `main.cpp:221` | **Tương thích** |
| Dòng trống | Python bỏ qua tại `agv_unified_brain.py:312` | Firmware chỉ dispatch khi `rx_idx>0` tại `main.cpp:324-330`; LF sau CR bị bỏ qua | **Tương thích** |
| Giới hạn frame | Python RX fault khi frame trên 1024 byte tại `agv_unified_brain.py:302-310` | Firmware buffer 80 byte, chỉ lưu 79 byte tại `main.cpp:318-335`; không báo lỗi khi tràn | **Không đồng nhất**, firmware cần reject fail-closed |
| Trailing input | Python drive yêu cầu đúng ba token tại `agv_command_session.py:345-353` | `STOP...` được nhận theo prefix; `V/M` có thể nhận hai trường rồi bỏ hậu tố tại `main.cpp:97`, `main.cpp:192`, `main.cpp:295` | **Không đồng nhất** |
| ACK STOP | Python chỉ nhận exact `ack=="STOP"`, `state=="DISARMED"` và đúng generation/thời điểm tại `agv_command_session.py:179-185` | Phát `{"ack":"STOP","state":"DISARMED"}` tại `main.cpp:96-109` | **Tương thích, kiểm tra chặt** |
| ACK ARM | Python yêu cầu exact ARM/ARMED và ACK sau thời điểm gửi tại `agv_command_session.py:186-187` | Phát exact ARM/ARMED tại `main.cpp:111-121` | **Tương thích** |
| ACK TUNING | Python yêu cầu chuỗi ACK bằng chính command pending tại `agv_command_session.py:188-191` | Firmware định dạng bốn số cố định tại `main.cpp:229-251`; Python tạo đúng định dạng tại `agv_command_session.py:546` | **Tương thích theo định dạng hiện tại** |
| ACK V/M | Host coi full write là `SENT` tại `agv_command_session.py:409-425`; không chờ ACK hiệu dụng | Firmware ACK giá trị sau clamp tại `main.cpp:221`, `main.cpp:310` | **Thiếu đối soát**, làm lộ mismatch clamp |
| Watchdog | Caller AUTO hợp lệ đến 0.50 s tại `agv_command_session.py:519-520`; telemetry/scan 0.25 s tại `agv_command_session.py:508-512` | Command watchdog 300 ms tại `main.cpp:26`, `main.cpp:453-457` | **Lệch availability**; firmware dừng trước, fail-safe còn nguyên |
| `V` clamp | ±0.35 m/s và ±0.95 rad/s tại `agv_command_session.py:358-360` | ±0.15 m/s, ±0.60 rad/s và ±65 RPM tại `main.cpp:201-214` | **Không tương thích** |
| `M` clamp | Số nguyên đến ±140 tại `agv_command_session.py:358-360`; UI gửi `M 140 140` tại `index_cyberpunk.html:735-746` | Clamp ±120 PWM tại `main.cpp:294-310` | **Không tương thích**; đây là PWM, không phải RPM |
| `RESET` | Chỉ xóa fault/latch và trả `RESET_OK` tại `agv_unified_brain.py:255-268` | Reset encoder/odometry và trả ACK tại `main.cpp:166-180` | **Không tương thích về ngữ nghĩa và transport** |
| Checksum/CRC và byte order | Không có checksum/CRC theo thiết kế; giao thức là JSON/ASCII line, không truyền struct nhị phân | Không có checksum/CRC; tính toàn vẹn dựa vào delimiter, giới hạn frame và exact token/ACK | Byte order **không áp dụng**. Cần framing/length/exact-token tests vì transport hiện không có lớp kiểm tra toàn vẹn riêng |

## 5. Sổ kiểm thử và xác minh

| Command/kiểm tra | Exit code | Kết quả | Diễn giải |
|---|---:|---|---|
| `python tests\run_agv_tests.py` tại root | `0` | `111 tests OK` | Regression Python root xanh; không bù được lỗi UI hoặc build firmware thiếu. |
| `node --test tests\test_agv_pid_ui.cjs` tại root | `1` | Thất bại tại `tests/test_agv_pid_ui.cjs:99`: mong `btnAuto.disabled=true`, thực tế `false` | Hard gate nghiệm thu thất bại; xác nhận AGV-01. |
| `python tests\run_agv_tests.py` trong candidate | `0` | `100 tests OK` | Runner candidate xanh nhưng bỏ sót `test_rpm140.py`; xác nhận AGV-08. |
| `python -m unittest discover -s tests -p "test_*.py"` trong candidate | `0` | `105 tests OK` | Standard discovery bao gồm năm test mà runner tùy biến bỏ sót. Candidate vẫn không phải root/deployed authority. |
| `node --test tests\test_agv_pid_ui.cjs` trong candidate | `0` | PASS | Xác nhận candidate đã có logic khóa UI tốt hơn tại `candidates/agv_rpm140_20261003/index_cyberpunk.html:501-509`. |
| `python -m py_compile` trên core modules và toàn bộ test Python root | `0` | Compile thành công | Chỉ xác nhận cú pháp/import compile-time; không xác nhận ROS, serial hay phần cứng. |
| PlatformIO build firmware root | N/A | Không chạy: `pio` không được cài | Firmware hiện hành chưa có bằng chứng build trong audit. |
| Bash syntax check launcher | N/A | Không chạy: Windows `bash` trỏ WSL nhưng thiếu `/bin/bash` | Không kết luận launcher hợp lệ. Launcher cũng bị cấm chạy theo phạm vi audit. |
| Kiểm tra Git | N/A | Thư mục không phải Git repository | Không thể xác minh provenance bằng commit/diff/tag. |
| Kiểm tra tĩnh framing/ACK/parser | N/A | Đối chiếu các dòng trong mục 4 | Xác nhận LF/CRLF và ACK cơ bản tương thích; phát hiện trailing/overlong chưa fail-closed. |

Không tuyên bố các phần chưa chạy là PASS.

## 6. Kế hoạch khắc phục ưu tiên

### Now — bắt buộc trước lần review kế tiếp

1. Sửa root UI theo gate `armed && !latched && !fault`, đồng thời khóa ARM/AUTO/MAN nhất quán khi latched.
   - Acceptance: `node --test tests\test_agv_pid_ui.cjs` exit `0`.
   - Giữ test tại `tests/test_agv_pid_ui.cjs:96-100` làm regression bắt buộc.

2. Chốt một hợp đồng clamp root và đối soát ACK hiệu dụng. Đây là hạng mục P1 đồng cấp với lỗi UI vì ảnh hưởng trực tiếp tới mô hình điều khiển kín.
   - Acceptance: host không chấp nhận giá trị vượt firmware root, hoặc firmware mới được build/promote có giới hạn thống nhất; test phải xác nhận giá trị ACK hiệu dụng.
   - Phân biệt đúng đơn vị: `0.35 m/s`, `0.95 rad/s`, và `M 140` là PWM chứ không phải RPM.

3. Đồng bộ watchdog host–MCU mà không nới watchdog firmware.
   - Acceptance: deadline caller AUTO không quá 200 ms hoặc có keepalive zero được chứng minh gửi dưới 300 ms; test boundary tại 199/201/299/301 ms.

4. Tách `RESET_SESSION` và `RESET_ODOMETRY`.
   - Acceptance: reset local không giả vờ là reset MCU; reset odometry chỉ thành công sau exact `{"ack":"RESET"}` khi DISARMED.

### Next — bằng chứng tích hợp

1. Harden parser firmware: reject frame quá dài, trailing token và command prefix không chính xác.
   - Acceptance: native tests cho LF, CRLF, dòng trống, 79/80/81 byte, `STOPjunk`, `M 1 1 junk`, NaN/Inf và ACK exact.

2. Thiết lập firmware build tái lập.
   - Acceptance: PlatformIO exit `0`, ghi phiên bản toolchain, target board, binary SHA-256 và source hash.

3. Sửa runner candidate để chạy `test_*.py` hoặc suite tường minh.
   - Acceptance: runner tùy biến và standard discovery đều chạy cùng 105 test hoặc nhiều hơn.

4. Chạy toàn bộ root suite sau khi sửa.
   - Acceptance: Python `111/111`, Node UI PASS, py_compile PASS và không giảm số test.

### Later — nghiệm thu triển khai và vận hành

1. Xác minh source-to-flash identity và thực hiện staged HIL: boot DISARMED, ARM, lệnh tốc độ thấp, watchdog, STOP, RESET và shutdown.
2. Đo tracking, overshoot và khoảng dừng trước khi cân nhắc profile 140 RPM.
3. Đưa dự án vào Git hoặc hệ thống provenance tương đương; tách rõ root, candidate và archive.
4. Nghiệm thu riêng mục tiêu khám phá toàn phòng, coverage, quay về đúng vị trí và hướng; tài liệu hiện tại vẫn ghi chưa hoàn thành tại `README_CODEX_AGV_TIEP_TUC.md:11-13`.

## 7. Sổ điều phối đa mô hình

| Vai trò | Model/kênh | Kết quả và provenance |
|---|---|---|
| Worker | `gemini-3.8-flash-high` qua `agy` | W2 hoàn thành kiểm tra timeout, clamp và RESET. Các kết quả này đã được Sol đối chiếu trực tiếp với source và đưa vào AGV-03 đến AGV-05. |
| Worker rộng | Gemini W1/W3 | W1 và W3 broad worker timeout hai lần; W1 micro cũng timeout. Không coi bất kỳ phần chưa trả kết quả nào là PASS. |
| Reviewer | `claude-opus-4-6-thinking` qua local gateway | Ghi chú được áp dụng: kiểm tra watchdog xuyên seam, bảng framing byte-level, yêu cầu thiết kế command cho W3 và chia micro-check có mục tiêu. |
| Ghi chú Claude được điều chỉnh | Claude reviewer | Đề xuất byte-order/CRC không áp dụng vì transport là ASCII line; thay bằng kiểm tra delimiter, giới hạn frame, exact token, trailing input và ACK. |
| Final gate/author | `gpt-5.6-sol`, effort `high` | Độc lập đọc source root/candidate, đối chiếu bằng chứng command, loại các claim worker chưa xác minh và ra verdict `REVISION_REQUIRED`. |
| Final taste pass | `claude-opus-4-6-thinking` | `CONDITIONAL PASS`; đã áp dụng việc làm nổi bật scope chưa phủ, đưa clamp/ACK lên cùng tier với UI và ghi checksum/framing ngay trong bảng protocol. Bác mô tả nhầm đơn vị của reviewer; giá trị đúng là `0.95 rad/s`. Giữ AGV-08 vì phạm vi người dùng yêu cầu đánh giá toàn thư mục, nhưng chỉ xếp P2 cho candidate chưa triển khai. Lượt taste pass đầu bị gateway cắt sau tiêu đề; retry tóm lược làm ngân sách Claude tăng từ 3 lên 4 lượt. |

Điểm đánh giá cuối: **74/100**. Hard gate không đạt do test root liên quan trực tiếp thất bại và thiếu bằng chứng build firmware hiện hành. Ngoài file báo cáo này, audit không sửa source hoặc cấu hình dự án.

## 8. Limitations & Uncovered Scope

- Không có xác minh phần cứng, serial, motor, GPIO, tốc độ, phanh hoặc khoảng dừng; mọi kết luận vật lý chỉ dừng ở phân tích fail-safe từ source.
- Không biết firmware đang flash trên MCU có trùng `robot_stm32_f103/src/main.cpp` hay không.
- Không có build firmware root, Bash syntax check hoặc Git provenance.
- Candidate 140 RPM có test xanh nhưng chưa triển khai và không được dùng để “chữa” trạng thái root.
- Shutdown có thiết kế fail-closed tốt, nhưng chưa được thử với serial treo hoặc MCU mất phản hồi.
- Parser firmware chưa có evidence test trực tiếp cho overlong/trailing input.
- Các worker Gemini W1/W3 timeout không cung cấp broad-sweep coverage cho `agv_navigation.py`, `agv_command_journal.py`, `agv_preflight_static_collector.py` và toàn bộ ma trận test root/candidate; Sol chỉ xác minh trực tiếp các đường dẫn và finding nêu trong báo cáo. Những khu vực còn lại là khoảng trống, không phải kết quả đạt.
- Chưa nghiệm thu khả năng khám phá toàn phòng, tránh vật cản trong mọi tình huống, lập bản đồ đầy đủ, hoặc quay về đúng vị trí và hướng ban đầu.
