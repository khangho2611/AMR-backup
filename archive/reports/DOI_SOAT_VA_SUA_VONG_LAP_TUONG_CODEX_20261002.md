# Đối soát và sửa lỗi xe lặp tại một vùng — 02/10/2026

Người dùng yêu cầu trực tiếp “làm theo yêu cầu trong đây” với prompt.docx, rồi xác nhận ảnh biểu thị xe chỉ quanh quẩn một chỗ dù còn nhiều hướng để đi. Quyền này cho phép Codex sửa source offline, thay giới hạn cũ “Codex không implementation”. Không tự chuyển quyền sửa source thành quyền deploy hoặc thử xe.

Override mới: người dùng yêu cầu Codex làm thay bot, không giao việc cho Khang AI Assistant nữa. Packet bàn giao đã hủy trước nhập/gửi; các tin Sent lịch sử giữ nguyên evidence. Từ đây implementation/QA do Codex trực tiếp thực hiện, không yêu cầu hoặc dựa vào bot như worker/hardware owner hiện tại.

## Kết luận từ nguồn trước khi sửa

Snapshot gốc được giữ nguyên tại `evidence_agv_20261001/codex_prompt_fix_20261002_181609/`. SHA prompt.docx: `76d55e5cf7430fb4391ecb07aa7b524cdc18a47ef67cfdd8b2b0604e70bdd5c5`.

Thông báo của Gemini chỉ đúng một phần. Snapshot đã có hàm A*, nhưng đường thất bại vẫn có thể dẫn tới lệnh chạy thẳng; unknown vẫn được xem như ô có thể đi; inflation phụ thuộc số ô cố định; mục tiêu bị chặn có thể bị đổi vị trí âm thầm. Vì vậy tên hàm A* chưa chứng minh xe đang bám đường hợp lệ. Radar trong ảnh cho biết các tia đo vật cản; vùng không có điểm radar chưa đủ chứng minh toàn bộ thân xe đi lọt hoặc đã có đường trong bản đồ.

Giao diện gốc đã có ba ô Kp/Ki/Kd ở dưới bên phải và Kf cố định 0.45. Vấn đề còn lại là API PID trả thành công ngay sau gửi lệnh, không đối chiếu MCU ACK. Không suy ra phần cứng, encoder, LiDAR hoặc cơ khí tốt từ ảnh/mock hay lời bot.

## Source đã thay đổi

- `agv_unified_brain.py` gọi planner thuần trong `agv_navigation.py`: only known-free, inflation theo mét, body radius + 15cm; A* không cắt góc, không đổi endpoint, không fallback chạy thẳng khi không có đường.
- Frontiers được gom theo vùng liền kề. Một goal không tiến triển trong cửa sổ 1.5 giây hoặc không có đường sẽ loại **cả vùng frontier** đó trong 30 giây; không coi điểm kế bên cùng bức tường là vùng khám phá mới. Khi đã tới goal thì chỉ loại lân cận để tiếp tục quan sát các phần khác. Hết goal do blacklist/timeout/invalid map không đồng nghĩa phòng đã được khám phá.
- Điều hướng giữ goal, bám waypoint kề; AUTO dùng V với PID, bỏ lệnh lùi/turn bằng MAN và sleep phản xạ. TF map→base được dùng cho vị trí+hướng; origin yaw được xử lý. Home được ghi trước motion, cần đúng vị trí+hướng và xác nhận STOP mới chuyển trạng thái về home.
- `agv_command_session.py` chia sẻ writer/reader giữa HTTP và nav. Không autoARM từ M/V; explicit ARM yêu cầu exact boot/scan/found, D0 zero đủ 10 giây/80 mẫu liên tục, full write, ACK ARM và D0 ARMED mới. Watchdog độc lập kiểm tra caller/scan/D0; STOP latch trước chờ writer, hủy drive đang đợi, mỗi STOP có operation riêng và bỏ completion cũ **trước mutex**. Partial/None byte count không được coi là thành công; zero quan sát sau partial vẫn không xác nhận STOP.
- PID serialized, zero hợp lệ, Kf=0.45; only matching ACK→APPLIED, matching firmware range error→REJECTED, timeout/disconnect→FAILED. Timeout chưa rõ kết quả chặn tuning tiếp cho đến reconnect. Không có protocol readback mới trong MCU: APPLIED ở đây nghĩa ACK khớp lệnh, chưa phải đo hiệu năng PID.
- `index_cyberpunk.html` giữ đúng ba input, lịch sử PENDING/APPLIED/REJECTED/FAILED, persist trước khi gửi, CSV quoting, chặn click trùng, không phát drive khi đang gõ input. Dừng khẩn cấp gửi đúng một STOP operation. Thêm nút mở phiên explicit; mất kết nối không dựng RPM=0 giả.
- Bỏ TF LiDAR mounting tự gán từ bản vẽ; yêu cầu TF mounting có nguồn. Scan/map cũ theo ROS timestamp bị từ chối; grid mở rộng cùng frame không xóa home, đổi frame phải hủy phiên AUTO. Odom TF không refresh timestamp bằng telemetry đã cũ.

Kiểm thử ghép đã phát hiện ACK nhanh đôi khi có cùng timestamp với TX khi Python Windows dùng GetTickCount64 (resolution 15.625ms). Controller chuyển sang perf_counter (resolution đo được 0.1µs), các so sánh trong controller dùng cùng clock. Không trộn perf_counter với monotonic cho D0/scan session.

## Kiểm thử và evidence

Kết quả cuối lưu tại `evidence_agv_20261001/codex_prompt_fix_20261002_181609/verification_20261002_185201/`:

- `test_1.txt`: **29 Python tests**, exit 0, 13.840s. Bao gồm tái hiện lỗi đường qua unknown, inflation, goal sát tường, map lỗi; A* vòng qua tường; đổi hẳn frontier trái→phải; kẹt/heading home; no autoARM/no ACK; STOP trước mutex và preTX zero của operation mới; PID reject/timeout.
- Bốn ca integration gọi **reader thật, HTTP localhost thật và scan/map/TF callback thật** trên FakeUART và ROS imports giả. Ca positive dùng thời gian thật, toàn bộ 10 giây D0 được reader thu nhận; không gán passed/count/backdate vào source. HTTP ARM→ACK+fresh D0→AUTO/frontier đổi vùng→V→STOP confirmation→PID ACK/reject. Các ca còn lại kiểm tra partial STOP health tức thời, stale stamps và map expansion/frame change.
- `test_2.txt`: **7 nhóm JS assertions**, exit 0; thực thi script dashboard với DOM tối thiểu/fetch giả, không phải visual browser acceptance.
- `summary.json`: hashes trước/sau không đổi, AST syntax pass, args/exit/scope. Hai diff so với backup được lưu trong cùng thư mục.

Các tests đỏ trước sửa đã tái hiện bốn lỗi planner. Ca mới cho blacklist một goal vẫn chọn pixel bên cạnh cùng tường đã FAIL trước gom vùng, PASS sau sửa. Ca second STOP chờ mutex đã FAIL trước invalidation-at-intent, PASS sau sửa. Các failure integration ACK sớm được xử lý trước snapshot cuối; không giấu bằng đổi packet hay tăng timeout startup.

Offline commands có thể tái lập:

```text
python -B -X utf8 -m unittest discover -s tests -p test_agv_*.py -v
node tests/test_agv_pid_ui.cjs
```

Không chạy main hoặc mở Serial thật để QA. Test loader chặn physical Serial OPEN. Node constructor, ROS executor thật, sole-owner liên tiến trình và rủi ro RTS/DTR/reset vẫn chưa nghiệm thu bằng ca integration trên.

## SHA-256 source cuối

| File | SHA-256 |
|---|---|
| agv_unified_brain.py | b95f963afd8d457a6224004821acd1788fc7bcf6b1bbdb0de1de7d98fd9fd30e |
| agv_navigation.py | 0486eaaaefb3a5fd4ff6a8bad6ab08fae79ecadf9187005bb9688b7ff1b93b41 |
| agv_command_session.py | 3354da4ec8cf0dcf4e7fa4f7f734a969ef1353e84c14c8bd79243bc9ebe97b3c |
| index_cyberpunk.html | 97716ab0fb49c639d465ecc7c1a35b0e2444504c43ee66636a95c1584e6f7af7 |

## Giới hạn và gate phần cứng

**SOURCE_FIX_OFFLINE_VERIFIED — NOT_DEPLOYED / NOT_HARDWARE_ACCEPTED.** Không có lần mở Serial, ARM, flash, restart ROS, chạy logger, nâng PWM/gain hoặc thử motion trên xe trong lượt này. Không gán source hash thành firmware binary proof.

15cm là policy khoảng đệm tường, chưa phải khoảng dừng đo thật. Body radius phải là bán kính bao đầy đủ thân xe, có nguồn đo/config `AGV_BODY_RADIUS_M`; mặc định thiếu thì AUTO HOLD. Số Word đã có m=1.75kg, C=0.23m, track L=0.1875m được giữ; track không phải full-body footprint. Assem3 chỉ bản vẽ. Không ép đo lại số đã lưu. TF mounting LiDAR, clock ROS/TF epoch sau reset, coverage/inaccessible accounting đầy đủ, ROS/main end-to-end, hardware crash/close/owner và vật lý về home vẫn cần review riêng.

Nếu chưa cấu hình body radius hoặc TF đúng thì AUTO chưa chạy; đây là dữ liệu thiếu được nêu rõ, không chọn số tùy ý để bật xe. Các radius .05m trong test là fixture tổng hợp, **không số đo xe**. Target 140–150RPM giữ staged; M140 là PWM manual hiện hữu, không thay RPM bằng PWM. AUTO source vẫn giới hạn V≤.08m/s và thường dùng .04m/s; không có phê duyệt profile mới.

Review block: action=`deploy/restart/ARM/drive/tune new bundle`; args=`USB0,115200,brain b95f963a + navigation0486eaaa + session3354da4e + HTML97716ab0`; reason=`ROS/main/hardware owner/reset/footprint/TF/physical stopping margin và current field chưa được review`; status=`NOT_APPROVED_FOR_HARDWARE`. Đây là gate QA, không phải automatic approval rejection.

Rollback local: so khớp current hash ở bảng trước khi thao tác; phục hồi hai file gốc từ backup đã nêu nếu cần. Hai module mới không được source cũ import. Không rollback/deploy trên Pi tự động. Giữ toàn bộ evidence nguyên vẹn và không đổi báo cáo này thành APPROVED.

## Follow-up trực tiếp 19:04 — giữ đúng scope xe thoát vùng lặp

Người dùng nhắc lại Codex tự làm, không gọi Telegram và tập trung việc đang cần sửa. Không có gọi/gửi/delegate cho bot trong follow-up này. Bảng SHA và 29 tests ở trên là snapshot lịch sử 18:52; snapshot mới dưới đây supersede đúng hai module đã đổi, không viết lại evidence cũ.

Counterexample mới: frontier có thể nối thành một vòng quanh phòng. Blacklist nguyên connected component khi kẹt bên trái đã khiến selector trả None dù các hướng khác còn reachable. Test đã tái hiện None trước sửa. Nay component trải trên nhiều hướng được tách theo hướng quan sát; sau một hướng thất bại, ưu tiên hướng khác rõ rệt rồi xét chi phí đường, vẫn A* known-free/inflation/không cắt góc. Hai đoạn frontier rời nhau vẫn được gom riêng, không đổi pixel trên cùng bức tường.

Ca perimeter tổng hợp: robot(.65,1.25), goal cũ(.425,1.025), sau reject chọn vùng khác khoảng(1.475,2.075). Test kiểm tra goal mới cách goal cũ >1m, khác hướng >90 độ và có đường A* hợp lệ; không ép tất cả trường hợp phải đi đúng sang phải. Một assertion thử nghiệm x>3m quá hẹp đã được thay bằng tiêu chí hành vi này, không coi việc đổi assertion đó là một product bug đã sửa. Ca hai frontier trái/phải riêng vẫn bắt buộc selector chọn bên phải và qua.

Trong kiểm tra luồng dừng, phát hiện D0 ARMED lặp lại đã cập nhật last_command ở mỗi mẫu, làm watchdog hiểu nhầm caller còn sống. Đã sửa: chỉ lần xác nhận ARM đầu tiên mở lease; telemetry không gia hạn lease lệnh. Test đỏ thực sự FAIL CALLER_TIMEOUT trước sửa; PASS sau sửa. Integration chạy **watchdog thread thật + reader thật** với FakeUART/scan còn cập nhật, caller im >200ms thì STOP và giữ fault. Không là test xe/MCU thật.

Evidence cuối `evidence_agv_20261001/codex_prompt_fix_20261002_181609/verification_20261002_190347/`: **31 Python tests exit0**, AST pass, hashes trước/sau ổn định, source_snapshot đủ bốn file. UI không đổi nên không chạy lại 7 nhóm JS đã qua ở evidence18:52. Backup trước sửa watchdog và red/green logs giữ riêng `evidence_agv_20261001/codex_watchdog_fix_20261002_1858/`.

SHA mới: navigation=`f7ba0fd572293baafcb7db29f67dc123ad89fcdf5db000b67ada8434b3ac915d`; session=`ea4e0cac36441b6e1d698b908ca3b6de6f37565cfd398c1e3ca7b90ec9f7446f`. Main b95f963a và HTML97716ab0 giữ nguyên. Gate phần cứng vẫn NOT_APPROVED, no deploy/run/SerialOPEN/Pi change; missing footprint/TF/physical proof vẫn giới hạn như trên. Phần mềm chọn vùng khác đã có regression proof offline, chưa chứng minh xe thật thực hiện đường mới.

Bổ sung triển khai thật 19:58: xem DOI_SOAT_NAP_WEB_TEST_CODEX_20261002.md; giới hạn NOT_DEPLOYED ở phần lịch sử trước đã supersede bằng startup live/test operator bounded, không full-goal acceptance.
