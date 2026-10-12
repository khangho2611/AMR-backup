# Đối soát V4.3 — 02/10/2026 14:14 Asia/Bangkok

**Chưa đạt production; không duyệt deploy/restart/chạy xe snapshot này.** Broker10671 đã bàn giao cuối, khác trạng thái đang sửa10640. Đọc nguồn, harness và báo cáo mới; không rerun V4.2 hoặc các module đã QA không đổi.

## Snapshot / bằng chứng

Source candidate_agv_unified_brain_v4_3.py SHA256 f573ae4f98c978f589709be1b03255921b1c195de0a88e0b58b673ec9a142aa1; test f46d69bdb177f55311cc692625aaad226febe43271ff15599d3fd142891eb095; HTML35ab348006b16f2ede16fc2289b49cbeb4a2a3ea4e16038b249927353c8a10e9 khớp report mới. Seven suites10662 exit0 thật; các failure10646/54/58 trong quá trình sửa không coi là final product failure.

Parent evidence mới review_v4_3_actual_20261002_1415.py/.json: actual main/reader/HTTP với FakeUART và localhost listener, component/parser/planner/actual HTTP method; đồng hồ thật không scale, không set preflight_passed. Hash trước/sau ổn định. Không hardware Serial/Pi/ROS hoặc typed streams acceptance. Log Connected USB0 là fake transport.

Audit parent_broker_pending_audit_20261002_1410.json chụp tới10671 nhưng field final_handoff_observed=False là snapshot metadata chưa đọc final; **đã đối soát10670 report và10671 final, trạng thái ấy được supersede bởi review này**, giữ evidence nguyên vẹn.

## Tám sửa giới hạn được công nhận

ARM count0 bị từ chối không TX; fresh ARMED không được release; minimal D0 không refresh; partial V hiện có ba STOP attempt; /api/auto STOP noUART trả500; actual HTTP CSV quote và parse8cột; malformed map một ô giữ EXPLORING; vertical unknown fixture goal1.35/1 cáchunknown.25m>=radius.186, path23. Bỏ tương ứng blocker V4.2 ở đúng path đã xác minh; không ghi partial không STOP hoặc CSV lỗi cho V4.3 nữa.

## Bảy residual được đối soát

1. **Protocol nguồn thật không khớp:** firmware main.cpp emission line347 có l_tgt/r_tgt và v/w. Candidate đòi target_l_rpm/target_r_rpm, không mapping. Actual parser với full firmware-schema D0 count0/UNKNOWN; actual main reader nhận5gói cùng schema vẫn count0. Mock fixture dùng tên trường tự đặt nên bỏ lọt incompatibility. Không sửa firmware theo mock, không flash để chữa parser.
2. **Actual main preflight sai contract vẫn ARM:** fake stream giữ nguyên production path, 81gói trong4.266s, có gap1.7s, targetL/R100RPM, RPM.2, v/w1, không startup diagnostic. preflight_passed=True. Sau lastage.593s (stale theo chính source), HTTP ARM vẫn TX ARM và trả200 nhờ một D0 ARMED, không ACK ARM. Chưa10s80/continuousgap/lastage/exactzero/bootFSM/session. Source dùng4s, chỉ safety/PWM/RPM<.5, bỏ targets/v/w; cached passed không reset khi unsafe/stale sau đó. Negative này dùng fake target_* schema candidate, không claim MCU phát schema sai ấy.
3. **Partial STOP không có outcome/confirmation:** fullV.04 rồi partialV.08 1/10, helper phát3STOP nhưng cả ba written1/expected6; helper bỏ kết quả, state is_moving=False/latchTrue/không confirmed field. Có attempt là sửa thật, không có bằng chứng dừng. Watchdog còn not latched nên không tiếp tục STOP health/deadline.
4. **STOP true khi MCU vẫn ARMED:** request_stop trả True/OK sau3full TX nhưng không có ACK/postSTOP DISARMED zero; state MCU vẫn ARMED. HTTP status và COMPLETED chỉ localTX, không fresh observation/confirmed/public escalation.
5. **False completion chưa sửa tổng quát:** map3×3/data2 (không chỉ data1)→RETURNING_HOME→COMPLETED với UARTNone/noSTOPconfirmation. Validator planner len!=w*h trảNone, FSM vẫn coi là hết frontier. Invalid schema/map/res/frame/freshness khác cần HOLD/FAULT, không completion.
6. **Footprint provenance/math:** Word có track.1875, chưa bodylength.28/fullwidth đo. Báo cáo lại gọi .28 từ Word là sai nguồn. Công thức sqrt((.1875/2)^2+(.28/2)^2)+.02=.188490541m, không .186. Track cũng không thay fullbodywidth. Radius mới cải thiện fixture nhưng không full swept-body guarantee; không ép đo lại m1.75/C.23/L.1875 đã lưu.
7. **Main real-schema count0** là kiểm tra actual entry độc lập bổ sung cho parser-case1, không hardware trial. Không kết luận parser đã chạy với firmware từ suite85gói target_*.

Nguồn inspection còn không nối audited gate/runtime/collector4b32: session UUID local không MCU binding, no ownerflock/command-class validation/write_timeout, no typed SCAN/MAP/TF producer/originyaw/frameepoch/map freshness/coverage/inaccessible/returnhome path. Home+heading conditional có source nhưng COMPLETED thiếu STOP confirmed. Body inflated range còn cho probability1..50 thay vì mọi ô known-free val0 theo claim. Main no bounded join/server_close/close outcome/evidence, silentmock khi realOPENfail. HTML không đổi từ review1405, giữ residual FAILED/PENDING/persist đã giao, không test lại.

## Vì sao harness chưa nghiệm thu

Suite1 85gói mỗi5ms rồi **gán trực tiếp state.preflight_passed=True**, không validate4s hoặc10scontract. FakeUART patch10652 reset write_limit sau lầnpartial đầu để STOP sau luôn full; đó là transient fixture, không persistent partial/write-fail coverage. CSV suite tự csv.writer trong test, không endpoint; parent đã bổ sung actual endpoint đạtgiới hạn. Cleanup chỉ flags+sleep.1/printPASS, không assert thread joined/UARTclose/HTTPmain. Không full main/startup/typed protocols/plan/backuprollback. Không gọi tất cảsource fake; calllog và code thật nhưng phạm vi PASS bị nói quá.

## Giao một bundle OFFLINE

Bắt buộc reuse audited gate95/runner907/runtime/planner/collector4b32 vào actual main/UI/owner queue, không tạo tiếp bản clone guard rút ngắn. Pure validator source-linked dùng đúng firmware l_tgt/r_tgt/mode/v/w với startupFSM/diag/settling/10s80/gap/age/exactzero/reset/unsafe-latch; same-owner ARMACK/sessionfresh. SharedSTOP outcome cho mọi caller/FAULT/latch, attempt/completion bytecounts/firstreason/deadline/confirmed freshDISARMEDtargetPWMvwzero/publicunconfirmedescalation, continuouswatchdog và boundedcleanup nonzero.

Typed SCAN/MAP/TF+validatedmap/yaw/epoch/measuredfullfootprint provenance/reachableknownfreefrontierstandoff/path/coverage/homepositionheading beforemotion; none/malformed/unreachable không falsecomplete; completion sau confirmedSTOP. PID/UI0/lifecycleCSV giữ review trước.

Full ACTUAL ENTRY positive và source-real-schema/startup10s80/noACK/unsafe-after-pass/gap/stale-target/persistentpartialSTOP/no-caller/malformedmapmanyshapes/heading/typedstreamlost/PIDconcurrent/UI0FAILED/cleanup negative. Chỉ fakephysicalOPEN+lock, clockthật hoặc virtualclock giữcontract, không gán passed; sourcehash/diff/exactcommand/backuprollback/logbounded.

## Review block

Action deploy/restart mainV4.3/autoSTART/USB0 ARM-release-drive-PID.
Args f573…2aa1, USB0/115200/HTTP; concrete bounded profile/current field/fresh transport/rollback chưa ready.
Decision **NOT_APPROVED**.
Reason protocol mismatch + unsafe4spreflight/cache/session + STOP confirmation/falsecompletion + typedruntime/footprint/cleanup. Codex QA nguồn, không automatic approval rejection.

Không Codex implementation/Serialhardware/deploy/flash/gainPWMloggerROS/recovery. Firmwareexpectedf5bf/supervisor1bd giữ. Human9953historicalmovement resolved/generalrunintent persists; chỉ hỏi khu thử/người trực HIỆN TẠI khi reviewedbundleplanREADY. Word measurednumbers ưu tiên/Assem3drawing/140–150RPMstaged. Pi13:15readonly không currentLIVE/physicalSTOP; roommaphomeheading unfinished.
