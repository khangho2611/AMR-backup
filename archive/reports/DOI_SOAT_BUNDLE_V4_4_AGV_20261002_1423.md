# Đối soát V4.4 — 02/10/2026 14:23 Asia/Bangkok

**Có sửa thật, chưa nghiệm thu production/chạy xe.** Final broker10705/source56e9e4cbcb070363fd3d29612fa0452cb435455b03ec2a2476c7bb7ba6fe7f15; test08661a38eb83c0498068899de0612698309f324b4fae372e042ef73cf46d9196; HTML35ab348…a10e9. Đọc diff V4.3→V4.4, test và report. Eight suites10698exit0 thật, không full acceptance; lỗi10690 trong lúc sửa không coi final failure.

## QA mới và sửa được xác minh

Evidence review_v4_4_entry_20261002_1424.py/.json chạy actual main-reader-HTTP với FakeUART và localhost listener, clock thật không scale/không gán passed hay đổi timestamps của product. Các component case chỉ cho seams mới. Hash nguồn trước/sau ổn định, không hardware/Pi/ROS. Connected USB0 trong log là fake.

Công nhận7fixgiới hạn:
- Parser dùng schema firmware l_tgt/r_tgt/v/w, component count1 và actual reader81D0/span9.547s; bỏ blocker protocol mismatch.
- Nonzero target và v reset preflight; gap>.5 reset về count1 theo contract source hiện tại.
- Malformed3×3/data2 giữ EXPLORING; bỏ falsecompletion của chính fixture cũ.
- Công thức provisional geometry cho radius.1885 khớp phép tính.188490541, bỏ lỗi số học .186; **không công nhận full-body provenance**.
- Main có reader hoạt động. Chưa startupFSM/bootdiagnostic/session/typedstreams acceptance.

## Residual mới tái hiện

1. Actual main81D0/span9.547s đã preflight_passed=True, không boot banner/I2Cdiag. Contract được giao continuous10.0s/80; code đổi thành9.5s chưa review. Sau lastage.610s vẫn cachedpassed, HTTP ARM TX và200 nhờ1D0ARMED sau TX, không ARMACK/sessionMCUbinding. Cần at-write revalidation và source-linked startupFSM, không chỉ tăng số giây.
2. Full-schema D0 có thêm error=I2C_FAULT vẫn tăng preflightcount1→2/latchFalse. Pure validator audited đã cấm mixed/error/fault keys; source clone bỏ mất contract này. Component synthetic adverse payload, không claim firmware đã phát packet đó.
3. Shape-valid map3×3/data9 nhưng resolution0 làm actual navigator.step ZeroDivisionError. Product nav thread không catch/FAULT cho validation này (source inspection); chưa typed map/frame/originyaw/epoch/freshness boundary.
4. Reproduction actualmain sau lastage.610/ARMnoACK là actual entry riêng; không hardware trial/physical motion hoặc field permission.

## STOP/runtime còn nguyên — không chạy lại test không đổi

Evidence parent_v4_4_unchanged_seams_20261002_1423.json xác nhận AST của _fire_physical_stop_internal, request_stop, _watchdog_loop giống V4.3. Do đó residual persistent partial STOP3×1/6 helper nuốtoutcome/isMovingFalse, requestSTOPTrue khi MCU cònARMED/nopostD0, watchdog skip latched vẫn chưa sửa theo code. Header V4.4 nói records write outcome/verifiesfreshzero nhưng chưa implementation ấy. Chưa shared firstreason/deadline/publicconfirmedhealth/unconfirmed escalation.

Không import audited gate/runtime/collector/planner (actual AST imports=[]). Main chỉ đổi banner; no ownerflock/write_timeout/fullproducerSCANMAPTF/clockmapping/frame/yaw/epoch/mapfreshness/coverageunknowninaccessible/full-body footprint provenance/homepath/boundedjoin/server_close/close-outcome/sink. request_tuning AST diff do docstring, chưa thấy lifecycle delivery/readback model đổi; HTML unchanged giữ review UI FAILED/PENDING/persist1405 không rerun.

Home heading/dist check có source; COMPLETED vẫn gọi request_stop rồi setCOMPLETED không outcome/freshzero. Malformed data2 đã sửa, không suy ra coverage/fullgoal/passallmaps. Các residual nguồn giữ nguyên, không gán thành newhardwarefail.

## Harness không chứng minh thời gian hữu cơ

Test suite2 không còn gán preflight_passed nhưng **gán state.preflight_start_mono=time.monotonic()-9.8** sau mẫu đầu rồi feed85×2ms. Đây là backdating state timestamp, không virtual clock advance trên actualcontract. Report “organically/no manual flags/10s” nói quá. Partial fixture reset write_limit lần đầu nên chưa persistent outcome. CSV vẫn tựwriter trong test; parent không chạy lại endpoint đã đạtV4.3. Cleanup flags+sleep.1/print, không join/close/exit assertions hoặc actual main. Không claim toolcalls/code fake; phạm vi kết quả thật bị diễn giải quá.

Footprint .28 body length và full width chưa đo nguồn trong Word; track.1875 không fullbody. Label provisional/configured; giữ số Khang đã lưu, không ép đo lại m1.75/C.23/L.1875, không CAD thay physical. Radius đúng phép tính không chứng minh footprint đúng xe.

## Một bàn giao OFFLINE và review block

Ưu tiên tích hợp actual audited module đã nêu, không clone/làm lại guard tiếp. Handoff ba seams hoàn chỉnh chung một entry:
1. owner-lock/reader→collector4b32 validator+startupFSM→session ARMACKfresh, continuous10s80/gap/lastage/exactzero/forbiddenkeys/reset unsafe, at-write bound/auth.
2. sharedSTOP cho HTTP/manual/AUTO/FAULT/watchdog: bytes/outcome/deadline/freshD0 confirmed vs observed/public health/escalation, persistentfailure và bounded join/close/sink/exit.
3. typedSCANMAPTF/validatedres-shape-frame-originyaw-epoch-freshness/full-footprint provenance/knownfree reachablepathcoverage/homeposheading/COMPLETED sau confirmedSTOP; PID/UI lifecycleCSV giữ review trước.

Actual production FakeUART chỉ thay physicalOPEN+lock; clockthật hoặc virtualclock advance chung, không product timestamp backdate/flag writes. Positive startup10s80 và negative bootdiagmissing/forbiddenmixedpayload/gapunsafeafterpass/staleARM/noACK/persistentpartialSTOP/noCaller/invalidmapresandframes/streamloss/heading/PIDconcurrent/UIFAILED/cleanup. Sourcehash/diff/exactcommand/backuprollback và logs scope thật trước report. Không cần xin lại quyền source implementation; chưa yêu cầu currentfield vì planbundle chưa READY.

Action deploy/restart V4.4/main/autoSTART/USB0 ARM-release-drive-PID.
Args source56e9…7f15/USB0/115200/HTTP; realprofile/rollback chưa reviewed-ready.
Decision **NOT_APPROVED**.
Reason startup at-write/session/STOPconfirmation/lifecycle/typedmapruntime. Đây là Codex QA nguồn, không automatic approval rejection.

NoCodeximplementation/Serialhardware/deploy/flash/gainPWMloggerROSrecovery; expected firmwaref5bf/supervisor1bd giữ. Human9953movement historical resolved/generalintent persists; khi bundleplanREADY mới chốt field/person hiện tại. Target140–150RPMstaged/Wordưu tiên/Assem3drawing; phòngmaphomeheadingchưađạt.
