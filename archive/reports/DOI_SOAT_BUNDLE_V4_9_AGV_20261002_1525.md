# Đối soát V4.9 — 02/10/2026 15:25 Asia/Bangkok

Final10940 source `7cf850b304460b2195412510deab1d2075a1e707147b5670d410169f10050b8f`, test `e03d1a70a6f8d2eee11472e33fec2ec52590db2234322f60f1dc864f714b9fb1`, HTML `35ab348006b16f2ede16fc2289b49cbeb4a2a3ea4e16038b249927353c8a10e9`. Đã đọc full diff4.8→4.9/harness/report/changed call paths. Sixcomponent10933exit0 thật, không production100%. Intermediate10917 không finalproductFAIL. Harness vẫn backdate producttimestamp(now-10.1), suite2 chỉ feedzero sau .04s không chặnwrite/trướcTX, mapDIRECTstate/cleanupprint. Negative ARM test cuối còn đổi D0ARMED thành DISARMED nên không chứng minh đúng negative đã yêu cầu. Source10929 giữ preflight khi ARMED để sửa test, chưa được chấp nhận là contract safe. Report15:45futuretimestamp khôngdelivery. Không hardwareproof10912–10940.

Parent NEW `evidence_agv_20261001/review_v4_9_entry_20261002_1521.py/.json`: actual MAIN-reader-localhostHTTP/FakeUART và changed STOP/classifier/PID seams, REALCLOCK, không producttimestamp/count/passed assignments, hashbeforeafterstable. Collectorvalidator function identity thật. Log ConnectedUSB0 là mock, không xe/Pi/ROS. QA exit0 nghĩa là assertions xác minh các fix và tái hiện residual, không productPASS.

## Bốn fix giới hạn được công nhận

1. Component mixedboot bị từ chối; addr0x00 và VIN0 khôngfound không chuyển stage3. Bỏ corresponding4.8 acceptance đúngcase này.
2. **STOP đầu tiên**: khi chờTXmutex op0/confirmedFalse; khi firstSTOPwrite đang bị chặn op1/write_complete0 vẫn khôngconfirmed. PostTXlatefullzero updatesconfirmed giữFAULT timeout. Bỏ preTXfalseconfirm cũ trong firstoperation, không suy ra secondoperation đúng.
3. Oldtimeoutop1→newreaderFAULT3STOPALL1/6 tạoop2, writefaultTrue, freshzeroOBSERVED/confirmedFalse. Bỏ lỗi4.8 tái dùng oldop cho readerfault đúngcase.
4. Actualrequest_tuning + exactfirmwareerror INVALID_TUNING_RANGE trảREJECTED/historyREJECTED ngay, khônghardwareSTOP/latch. Bỏ regressionPIDtimeout4.8.

Source đã thêm ARM_ACK flag và request_arm yêu cầu ACK; không lặp runtimeclaim V4.8 ARM200onlyD0 cho bản này. **Chưa xác minh positive ARM fullentry mới** vì healthy startup bị block dưới đây; UUIDlocal/ACKbool vẫn chưa đủ MCU session attribution. Không giả flag/timestamp để vượt blocker.

## Ba residual đã chạy thật offline

**A — Deadline startup3.5s áp cả lên postdiag10s, positive không thể hoàn tất.** ActualMAIN exactboot→scan→found0x42→VIN12033 đúng thứ tự rồi82fullDISARMEDzeroD0 gửi organic10.157s/maxgap.141s. Khoảng3.55s có STOP3 bởi STARTUP_DEADLINE_EXCEEDED; snapshot quan sáttrip3.641s/stage0/count0. Sau fullstream actualHTTPARM422/REFUSED_LATCHED_STOP/0ARM. Mẫu không unsafe; classifier checks stage>0 bao gồm stage3 nên tự đánh trượt cửa sổ cần10s. Đây là newpositive-entry failure, không được “sửa test” bằng backdate/tăngdeadline/làmngắnpreflight. Diagnostic deadline/settling và postdiag stable window phải có pha riêng theo collector4b32.

**B — Completion timestamp cũ vẫn mở confirmation cho STOP operation mới.** ActualoldrequestSTOP fullbytes timeout tạoop1/completion cũ. NewrequestSTOP vào mutex tạoop2 nhưng KHÔNGreset stop_write_complete_mono; FakeUART chặn firstwrite mới, readerzero khiếnconfirmedTrue dùTX mới chưa có, chỉ baSTOP cũ. Sau thảwrite, request mới trảFalse/STOP_UNCONFIRMED_TIMEOUT mà publicflag confirmedTrue. Firstoperation đã fix, secondoperation vẫn lỗi. Phải invalidate completion khi cấp operation và lưu completion/outcome cùngID; zeroafterfullTX cùngop, không dùng thời điểm củaop khác. Readerfault helper cũng giữ completion cũ trước lúc cập nhật là sourceimplication, chưa thêm runtimecase riêng.

**C — PartialSTOP directwrite trả500 nhưng publicFAULT null.** ActualMAIN HTTPSTOP chỉwrite1/6, response500/PARTIAL_FAULT; ngay sau đó /api/telemetry trảfault_code:null/first_fault_reason:null/FSM IDLE trong khi latchedTrue/stop_write_faultTrue. Directrequest_stop đã bỏ send_guarded nhưng nhánh lỗi chưa commit publicFAULT/firstreason/deadline-health. Watchdog có thể vềsau ghi timeout; đây không chứng minh “FAULT永遠null”. Phải commit writefault ngay, giữ nguyên cause, trả confirmed/unconfirmed/outcome/escalation thống nhất.

## Phạm vi còn thiếu

Main/owner/parser/watchdog/map/PIDUI khác giữ sourcepending từ1512, không rerun unchanged. Auditedimports chỉcollector; gate95/runner907/runtime/planner vẫn chưa có callpath thực. Main khôngownerflock/write_timeout; readerfault còn đợiTXmutex trướclatch; typedSCANMAPTF ingestion/frame/originyaw/epoch/freshness/coverageunknowninaccessible/knownfreefullbody/returnhomepathheading chưa nối. HTML/CSVunchanged giữresidual1405. Radius.1885provisionalmath/.28fullbody không số đoWord. Source10929 khôngresetunsafeARMED cần negative chuyênbiệt ở handoff, chưa parentruntimeclaimviolation case này.

NormalmainUARTclosed/nav+watchdogdead/noexception chỉ scope shutdown này. FinalflagconfirmedTrue trong khi finalfaultSTOP_UNCONFIRMED_TIMEOUT tiếp tục cho thấy cần outcome nhất quán; không coi printresourcesreleased là boundedSTOPconfirmed/readerjoin/close-fail/crash/ownerproof.

## Một bàn giao source offline

Kết nối đúng ownerflock/queue/readersameport với collectorclassifierFSM: OPEN/bootdiagdeadline+settling riêng, POST_DIAG10s80 continuousgap/age/exactzero không chịu startup3.5s, unsafe resets/latches rõ; explicitARMACKafterfullTX cùngsession+freshARMEDD0. Gate95/runner907/runtime/planner import/call thực, không commentREUSE hoặc anotherlooseclone; collectorNoTXwrapper không dùng phátlệnh.

SharedSTOP ALLmanualAUTOHTTPreaderFAULT/watchdog: pendingfaultlatch trước chờboundedwriter; peroperation completion ban đầu unset, fullbytes success+completion boundID mới mở confirm, error ngaypublicFAULT/firstreason/deadline/unconfirmed/escalation/latezeroobserved giữfault; queuedVcancel/boundedcleanupFAILnonzero. PIDreject/history/UI0lifecycleCSV, fulltypedSCANMAPTF/homeposheading/coverage/knownfree measuredfullbody và COMPLETEDafterconfirmedSTOP vẫn trong cùngbundle.

ONEactualENTRY FakeUART ONLYphysicalOPEN/lockfake, real/advancingvirtualclock đúngcontract, không productbackdate/flags. Bắt buộc positiveexactdiagnostics→10s80→ACKARM+freshARMED→boundedV→STOPconfirmed; negative missingfound/late/mixed/unsafeARMED/noACK, secondSTOPpreTXzero, oldopnewpartialfault, partialSTOPpublichealth, PIDreject/noCaller/typedloss/wrongheading/cleanup; exactsourcehash/diff/command/backuprollback. Không xin lại SOURCEpermission/đợiROSphysical/frameworkspawn.

Actiondeploy/restart7cf8 `/dev/ttyUSB0`115200 HTTPARMrelease-drivePID **NOT_APPROVED**, reasonpositivepreflightblocked/STOPsecondoperation-falseconfirm/publicwriteFAULT/typedruntimecleanup. Đây là CodexsourceQA, không automaticapprovalrejection. KhôngCodeximplementation/Serialhardware/Pideploy/gainPWM/flash/logger/ROS/recovery. Generalhumanrunintent giữ/currentfieldonlywhenreviewedbundleplanREADY; Wordm1.75/C.23/L.1875accepted/Assem3drawing/140–150RPMstaged. No fullroommaphomeheading proof.
