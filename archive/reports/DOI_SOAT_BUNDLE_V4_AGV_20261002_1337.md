# Đối soát bundle V4 — 02/10/2026, 13:37 Asia/Bangkok

Codex QA nguồn/offline; không implementation, không Serial OPEN/TX, không ROS/deploy/Pi motion. Đánh giá snapshot final DB10571, không bản đang sửa. Giao 13:24 đã Sent, không gửi lại.

## Snapshot và phạm vi bằng chứng

Candidate `candidate_agv_unified_brain_v4.py`: SHA256 `ecf2fabc531cb201729670c056851bb142255203a455e2d0f809445e8e059bc5`; trước/sau QA khớp. Broker test `test_bundle_v4_production.py`: `1c0ebdc8303b39052b937ef4271f15ff71eafb031921c00663733cf08c43e149`. Report broker `BAO_CAO_HOAN_THANH_OFFLINE_BUNDLE_V4_20261002.md`: `2f044796362db0140f19f95c6d950a71153ac2845e3a82cf2f8c8fb2d9af7300`.

Tool10564 chạy sáu component suites exit0 thật. Các assertions này có ích: không chèn ARM vào send_raw; request_arm từ chối latch có sẵn; heading lệch pi chưa completed; tuning zero/range/timeout xử lý được ở fixture. Chưa phải full production: test gọi trực tiếp lớp/step và gán timestamps/state, FakeUART.write trả None, không full startup/preflight/reader/runtime/watchdog/HTTP/UI/TF. Fixture BFS 10x10/res.05/robot5,5 có toàn bộ khoảng cách từ robot tới cell <.4m, dưới min_frontier_distance: None không tự chứng minh island rejection là do BFS. Không đổi kết quả exit0 thành test giả, nhưng loại claims “100% không còn lỗi/production/all seven fixed”.

Parent script `evidence_agv_20261001/review_v4_residuals_20261002_1335.py`, output cùng tên `.json`, chạy 13:36:31, exit0 = tái hiện thành công 12 checks, **không** product PASS. Import actual module/lớp/parser/navigator; FakeUART trả byte count thật/partial. HTTP thực thi actual handler với in-memory response sink, không network/hardware. Race chỉ chặn scheduling seam quanh actual BFS, giữ kết quả planner thật; không viết implementation. Các timestamps scan/home là component fixtures, không typed ROS integration hay soleowner proof.

## Lỗi tái hiện trên snapshot mới

1. **F14/F11 — Entry chưa executable system.** Chạy đúng candidate main bằng Python offline chỉ in INITIALIZED và exit0. Không tạo reader/scheduler/watchdog/server/ROS subscription/TF, không nối audited gate/runtime/planner. Không deploy entry này và gọi là hệ thống tích hợp.
2. **F02/F12 — STOP/TX false success.** send_raw98 bỏ byte count: STOP CRLF expected6, FakeUART write1 vẫn returnTrue. request_stop126 phát ba STOP nhưng không lưu outcome/fault/deadline/freshD0zero/cleanup. Không gọi burst là guarantee.
3. **F03/F08/F12 — ARM stale/protocol.** parse_line163 đọc `state`, bỏ actual D0 `safety`. ACK ARM/ARMED rồi D0 safetyDISARMED và FAULT vẫn mcu_stateARMED. Với ser=None, request_arm112 vẫn True từ trạng thái cũ dù ARM TX fail. Bất kỳ JSON PONG cũng làm fresh telemetry; x="NaN" được nhận. Chưa D0 validation/session/boot-epoch/preflight/ACK correlation.
4. **F02/F07/F08 — V sau STOP đã latch.** Actual BFS trả goal(1.55,1.0), count40; pause caller sau tính goal, request_stop hoàn tất, resume actual navigator: TX `[STOP, STOP, STOP, V 0.12 0.00]` dù latchedTrue/autoFalse. tx_lock chỉ serialize, không authorization/latch check tại dispatch. Không kết luận xe vật lý chuyển động từ fake; đây là lỗi gửi command.
5. **F03/F07 — Watchdog thiếu độc lập và latch.** stale step gửi STOP nhưng autoTrue/latchFalse; fresh timestamps + obstacle tick sau phát V. Không gọi step .65s sau V: không có STOP từ component watchdog vì không thread/scheduler độc lập. Không xét MCU watchdog trong case này, không nói motor không dừng.
6. **F09/F10 — Home và false completion.** Fresh component fixture + obstacle front20: V turn ngay khi home_capturedFalse/mcuUNKNOWN. Map chưa nhận + không UART: ba step capture→RETURNING_HOME→COMPLETED, không fresh postSTOP D0. Có heading check là tiến bộ giới hạn nhưng không chứng minh khám phá/home completion; absence/invalid/stale/filtered frontiers phải health/coverage riêng.
7. **PID/F12/F14 — ACK sai và HTTP false ok.** Request [.5,1.5,0,.45], ACK TUNING [19,49,4,4] vẫn APPLIED; current_gains chưa cập nhật/history0. API/cmd V với UARTNone vẫn HTTP200/statusok. RELEASE_LATCH với MCUUNKNOWN vẫn clear. Cần transaction ACK/readback khớp, single-owner queue, status phản ánh failure; không arbitrary raw commands bypass bounds/auth/recovery.

## Khoảng trống nguồn khác, chưa gọi là case đã test

V4 planner có BFS chọn candidate nhưng không xuất parent/path/waypoints; navigator vẫn pursuit thẳng tới goal/home. Chưa map freshness/origin quaternion yaw/frameid/TF/map epoch/coverage unknown-vs-inaccessible; map_epoch khai báo không dùng. Inflation radius .15m là số chọn trong candidate, không full footprint đo từ Word; int(.15/.05) còn làm tròn xuống. BFS chỉ cản occupied>50 trong footprint, không reject unknown/out-of-map footprint. Không tuyên bố disconnected map đã tái hiện thất bại trên V4 nếu chưa có fixture tương ứng.

UI cũ HTML d7ae…110c1 chưa nằm trong bundle mới; parseFloat(value)||default/false applied history của review13:24 chưa được sửa trong file UI. V4 route `/` 404, không CSV/history lifecycle thực; imported HTTP classes không nghĩa đã serve dashboard. Chưa typed SCAN/MAP/TF readers để xác nhận angle/source clock mapping.

Giữ Word m1.75/C.23/L.1875 và CPR937.2 thông số; assembly chỉ bản vẽ. Không ép đo lại số đã lưu. PID Word khác units/dt current gains, không nạp mù. Target140–150RPM giữ staged (.5367–.575m/s theo C); không thay bằng PWM. Parent .08 runner907/gate95 production QA13:18 đã đạt giới hạn, không rerun unchanged hoặc bỏ mọi tiến bộ đó vì lỗi mới V4.

## Review block và một bàn giao tiếp theo

Action: deploy/restart/start tự hành hoặc tuning/recovery trên Pi sau reboot. Args: candidate V4 ecf2…9bc5; USB0/115200; `/api/auto?act=START`, `/api/cmd` ARM/RELEASE_LATCH/V/M hoặc `/api/pid`; command runtime cụ thể chưa có. Decision: **NOT_APPROVED**. Reason: entry chỉ print; ARM stale từ D0 safety bị bỏ; partialSTOP false success; V sau latch; watchdog caller-dependent; missingmap false completion; PID ACK/HTTP status sai. Đây là QA Codex, không automatic approval rejection. General human intent chạy/tích hợp vẫn có; chưa plan reviewed/current conditions sau boot mới.

Giao đúng một bundle SOURCE OFFLINE: tận dụng gate/runtime/planner đã QA, nối actual main/reader/scheduler/independent watchdog/HTTP+UI/typedSCAN-MAP-TF. Chốt shared dispatch+STOP health/session/preflight/ACK correlation tại write boundary, immutable TX outcome/deadline/fault/confirmed cleanup; không tự clear/reARM. Chốt map validation/path/coverage/home pose+heading before ANY motion; typed PID0-valid ACK readback/history state/CSV. Full actual entry với ONLY physical OPEN/lock replaced FakeUART, unscaled fresh startup10s80, typed streams và HTTP/UI commands, positive+12 residuals, hashes/diff/exact command/backuprollback. Không helper-only tests rồi claim production; sửa claims đúng scope.

Không xin implementation permission đã có; không đợi ROS thật/framework/spawn/fake fourbot ACK. Sau snapshot+plan ready mới chốt hiện trường trống/người trực HIỆN TẠI, fresh same-owner D0/ARMACK. Không mở lại Serial, deploy/flash/gain/PWM/logger/ROS trong lúc sửa. Boot1a219… mới; Pi readonly13:15 không proc/fuserfree không fresh DISARMED/physical STOP proof. Mục tiêu room/map/homeposition+heading còn pending.
