# Đối soát bundle V4.2 — 02/10/2026 14:05 Asia/Bangkok

Codex chỉ QA và giao sửa. **Chưa đạt nghiệm thu production; không duyệt chạy snapshot này trên xe.** Kết quả dựa vào nguồn cuối DB10635 và QA độc lập, không suy ra từ dòng “100% OK”.

## Snapshot và phạm vi

- candidate_agv_unified_brain_v4_2.py SHA256 7953bef2af04338fc61d89dde3537b142103b952fdc7dfa814b6296684238bf1.
- test_bundle_v4_2_production.py SHA256 edf4eed43a68917eeee074d6c0a717933b03610b73036de630ffd41204510a98.
- index_cyberpunk.html SHA256 35ab348006b16f2ede16fc2289b49cbeb4a2a3ea4e16038b249927353c8a10e9; báo cáo broker ghi 24d42…8ca7, chưa khớp artifact hiện tại.
- Evidence mới: evidence_agv_20261001/review_v4_2_runtime_20261002_1400.py và .json; hash nguồn trước/sau ổn định. Không rerun snapshot cũ.
- QA có actual main/reader/HTTP/watchdog, Serial thay FakeUART, HTTP bind localhost cổng tạm; đồng hồ thật không scale. Các ca khác chạy actual component/parser/planner. Không Serial phần cứng, Pi, ROS hoặc typed SCAN/MAP/TF thật. Log Connected USB0 từ main là fake transport.

## Các sửa đã công nhận có giới hạn

Stale D0 từ chối DRIVE; partial DRIVE chốt FAULT và từ chối tiếp; /api/cmd STOP không UART trả 500; firmware INVALID_TUNING_RANGE trả REJECTED ngay; late ACK khi không còn active transaction không sửa history. Actual main nhận manual V rồi independent watchdog phát STOP khi thiếu SCAN; evidence chỉ chụp STOP đầu và fault=null tại thời điểm đó, không xác nhận toàn bộ FAULT/STOP lifecycle. Main normal shutdown đóng FakeUART/running=False; QA tự join thread và server_close nên chưa là product bounded cleanup.

Nguồn hiện có reader và HTTP thực, không còn main print-only của V4. UI đã bỏ 0||default và chỉ ghi APPLIED khi backend APPLIED; đây là đối soát nguồn, chưa chạy browser end-to-end. Không phủ nhận những sửa này.

## Lỗi còn tái hiện

1. **Actual main ARM trước preflight:** /api/cmd ARM khi fresh_d0_count=0 vẫn TX ARM; chỉ một D0 ARMED sau TX, không ARM ACK/banner/diagnostic/session, HTTP200 sau 31ms/count1. Chưa 10s/80 mẫu DISARMED target/PWM/v/w0; boot_session=null. Fresh sau TX không thay preflight trước ARM.
2. **FAULT chưa phát STOP:** full V .04 rồi partial V .08 (1/10) chốt latch nhưng tx không STOP, is_moving=True; actual watchdog skip vì not latched. Cờ local không chứng minh MCU/xe dừng.
3. **Release không đúng trạng thái/schema:** fresh ARMED zero vẫn LATCH_RELEASED; minimal D0 chỉ x/y/th/safety DISARMED thiếu trường cũng count1/default RPM/PWM0 rồi release. Thiếu strict full D0/target/mode/v/w/session; không tự clear/reARM trên xe.
4. **False completion:** nonempty map 2×2 nhưng data một ô → RETURNING_HOME → COMPLETED với UART=None, không postSTOP D0. Map cần kiểm tra schema/freshness/TF/origin yaw/frame epoch; planner None không đồng nghĩa hết phòng.
5. **STOP API không nhất quán:** /api/auto?act=STOP không UART vẫn HTTP200/status ok; /api/cmd STOP đã sửa500. request_stop đánh is_moving=False theo local TX, chưa fresh zero confirmation/deadline/escalation.
6. **Footprint/frontier:** actual goal(1.55,1), path27, cách unknown0.05m nhỏ hơn radius0.16; inflation chỉ occupied. Nguồn mới gọi width0.2425/length~0.28 là measured nhưng chưa provenance; Word L0.1875 là track, không full body. Nếu dùng rectangle đó thì corner radius0.185207>0.16. Cần full footprint/path clearance và frontier standoff trong known free, reachable coverage/unknown/inaccessible, home position+heading trong map TF.
7. **CSV lỗi:** actual history_csv có header8 cột nhưng ACK_MISMATCH row15 cột do reason chứa dấu phẩy không quote; chưa RFC4180 dù báo cáo khẳng định. UI nhận FAILED JSON vẫn ghi REJECTED; catch disconnect dùng RPM/PWM0 tổng hợp và chưa persist/cap như success path (source inspection).

Nguồn còn chưa nối audited gate/runtime/collector/planner vào owner/session; không flock, write_timeout, command-class auth chặt; serial-open-fail âm thầm mock, reader exception bị nuốt. Chưa typed SCAN/MAP/TF producer, map yaw/epoch/coverage, bounded join/close/STOP confirmation và immutable final evidence. Các mục source inspection này không gọi là ca hardware thất bại.

## Một bàn giao sửa OFFLINE

Dùng lại gate95/runner907/runtime/collector4b32 đã QA giới hạn, nối actual entry/UI qua cùng ownerlock+reader+queue, startup FSM diagnostic/settling/strict D0 continuous10s/count80/gap/age/zero rồi session ARM ACK fresh. Shared FAULT luôn yêu cầu STOP dù latch đã true; write outcome/first reason/deadline/fresh zero observation tách confirmed/public health; watchdog mọi motion, cleanup bounded/joins/close/sink fail nonzero. Không tự viết lại guard thành lớp lỏng.

Typed SCAN/MAP/TF vào đúng runtime; validate map/frame/yaw/epoch/freshness/footprint provenance, path/standoff/coverage và home cả vị trí+hướng capture trước motion, chỉ COMPLETED sau STOP confirmed. PID serialized matching ACK/error/timeout/history và UI0/PENDING/APPLIED/REJECTED/FAILED/CSV quoting cần full entry test.

Bàn giao source hash/diff/exact offline+real command/backup/rollback; full production FakeUART chỉ thay physical OPEN+lock, startup real hoặc virtual clock giữ contract10s80 không scale. Positive + no-preflight/noACK/partial-after-motion/no-caller/latched-fault/manual-stale/releaseARMED/minimalD0/malformedmap/unknown-footprint/wrong-home-heading/PIDerror-timeout-concurrent/UI0-FAILED/CSV/cleanup negative. Không chỉ component suites hoặc claim100%.

## Review block

Action: deploy/restart V4.2 main/autoSTART/USB0 ARM-release-drive-PID.
Args: candidate7953…8bf1; USB0/115200; HTTP ARM/autoSTART/DRIVE/TUNING; chưa có reviewed bounded profile/real command/backup rollback phù hợp.
Decision: **NOT_APPROVED**.
Reason: unsafe preARM startup/session; partial-write FAULT không STOP; release/schema/STOP confirmation; invalid map falsecompletion; footprint/typed runtime/cleanup chưa hoàn chỉnh. Đây là Codex QA nguồn, không automatic approval rejection.

Không Codex implementation/Serial owner. Giữ firmware f5bf…5050/supervisor1bd…6bfd; không hardware retry/deploy/flash/gain/PWM/logger/ROS/recovery. General human intent chạy/tích hợp còn hiệu lực; chỉ chốt điều kiện khu thử/người trực HIỆN TẠI khi bundle+plan đã review READY. Human9953 đã xác nhận xe từng chạy, không hỏi lại wheel question cũ. Word m1.75/C.23/L.1875 ưu tiên; không ép đo lại số đã lưu; Assem3 chỉ bản vẽ. Target140–150RPM staged; mục tiêu phòng/map/homeheading chưa đạt.
