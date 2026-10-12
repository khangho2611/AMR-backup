# Đối soát V4.8 — 02/10/2026 15:12 Asia/Bangkok

Final broker10906: source `6034babff1c72211c20b01624cbe7b433686f3993f2eff554759ceb560b1bd9e`, test `dce8f45af7d05a6b1d16414415e0c5b2210938f648ac959a9fdbfc5bfd74dd95`, HTML `35ab348006b16f2ede16fc2289b49cbeb4a2a3ea4e16038b249927353c8a10e9`. Đọc diff4.7→4.8, full harness/report và các đường gọi liên quan. Fivecomponent10899 exit0 thật; intermediate10887 không phải finalproductFAIL. Harness vẫn backdate product `preflight_start_mono=now-10.1`, tự gán isMoving/map/latch; suite2 chỉ gọi DRIVE SAU khi FAULT đã xử lý, không concurrent in-flight. Cleanup chỉ print, không assert join/close. Timestamp report15:30 là tương lai, không thời gian gửi. Không production100%.

Parent NEW `evidence_agv_20261001/review_v4_8_entry_20261002_1505.py/.json`: actual MAIN-reader-localhost HTTP/FakeUART và changed component seams, REALCLOCK, không gán passed/count/product timestamp. Hai cửa sổ organic82D0/span10.156 và10.141s. Chỉ thay OPEN và HTTP local binding; không cổng xe/ROS/Pi. Log ConnectedUSB0 là UART giả. Hash trước/sau không đổi. Cố định sys.path tới workspace, chứng minh function identity với module collector4b32 thật.

## Sửa đã xác minh giới hạn

- PrebootD0 không tăng preflight; error có chuỗi ScanningI2C không bị nuốt thành banner và latchFAULT.
- Hardwarefault với op0, kể cả partial3x1/6, freshzero chỉ OBSERVED, không CONFIRMED; actualMAIN reader cũng đúng op0.
- Registered requestSTOP với persistentpartial giữ stop_write_fault/khôngCONFIRMED.
- Barrier actualinflightV và readerFAULT nay cho V hoàn tất TRƯỚC STOP3; trạng thái cuối latchTrue/isMovingFalse. Bỏ lỗi cũ STOP3→V hoàn tất sau. Đây là thứ tự completion giả, không physicalbyte/motorproof. Không suy ra đã cancel write đang nằm trong ser.write: khi nó bị chặn, readerfault chờ mutex và latch/fault chưa được ghi. Source chưa có write_timeout/priorityqueue/pendingfault barrier.

## Residual mới đã tái hiện

1. **Startup còn chấp nhận VIN thay found/địa chỉ sai/deadline và mixed keys.** Component boot→scan→vin_mv0 hoặc i2c_found0x00 đều stage3/found_seenTrue/settlingTrue. ActualMAIN đợi3.609s từ entry rồi boot JSON có thêm status_msg, scan, VIN0 KHÔNGfound; organic82D0/10.141s vẫn ARM/HTTP200. Constant STARTUP_DEADLINE_S import nhưng ASTload0; stage3 không thực hiện classifier/settling của collector. Đây là syntheticnegative offline, không nói MCU đã phát những gói này. Case tổng hợp không tách riêng từng nguyên nhân ở actualMAIN; component đã tách VIN/address.
2. **ARM vẫn chỉ dựa freshARMED D0.** ActualMAIN exactboot→scan→found0x42/organic82D0/10.156s rồi requestARM; FakeUART chỉ trả D0ARMED, không ackARM/sessionMCU, HTTP200. TokenUUID local không chứng minh firmware session. Cần ackARM sau TX rồi D0fresh cùng phiên; không flash MCU để khớp mock.
3. **Operation STOP được đăng ký TRƯỚC TX.** Giữ tx_lock, actualrequestSTOP tự tăng op1, reader nhận freshDISARMEDzero: confirmedTrue/observedTrue trong lúc TX còn rỗng. Sau thả mutex, STOP3 mới được ghi nhưng request trả STOP_CONFIRMED_ZERO dựa mẫu trướcwrite. Phải ghi successful full-byte completion trước mở cửa confirmation và chỉ nhận mẫu sau completion cho cùngoperation.
4. **Op cũ bị tái dùng cho readerFAULT mới.** ActualrequestSTOP fullbytes nhưng timeout tạo op1; sau đó I2C_FAULT helper3STOP đều1/6, freshzero vẫn confirmedTrue/stop_write_faultFalse/op1. Helper không đăng ký operation mới, không lưu partial outcome, không vô hiệu confirmation cũ. Bỏ op0falseconfirm cũ đúngcase đã fix, nhưng không gọi mọi pathSTOP đạt.
5. **Regression PID error bị mất trạng thái REJECTED.** Actualrequest_tuning(.5,1.5,.01,.45), parse firmware error INVALID_TUNING_RANGE: error-first hardware handler phátSTOP/latch, transaction không nhận error và timeout FAILED/TIMEOUT_NO_MCU_ACK. V4.7 có handler rejection riêng đã bị xóa. Phải giữ rejection matching transaction, không giả APPLIED hay gán lỗi range thành mất ACK. Đây là FakeUART/parser negative, không tuning xe thật.

Bảy evidence entries là các trường hợp của năm nguyên nhân, không bảy lỗi độc lập. Các mẫu zero xác minh telemetry scope; không physical100%STOP.

## Đường tích hợp còn thiếu theo source

Collector validator/banners đã import VÀ gọi thật (ASTloads1), công nhận tiến bộ; không lặp claim unused allconstants của4.7. STARTUP_DEADLINE_S vẫnunused. Không import/call auditedgate95/runner907/runtime/planner; main serial.Serial khôngownerflock/write_timeout, reader khôngSTOP khi exception, normalfinally không bounded readerjoin/close-failure/nonzero outcome; normalQA closedUART/navwatchdogdead không crash/ownerproof. TypedSCAN/MAP/TF ingestion/frame-originyaw-epoch-freshness/coverageunknown-inaccessible/knownfree measuredfullfootprint/returnhomepath+heading và publicSTOPfirstreason/deadline/escalation vẫn pendingSOURCE. HTML/CSV unchanged giữ residual1405, không rerun. Radius.1885 provisional math; Wordtrack.1875 không fullbody/.28 measurement.

## Một bàn giao source offline

Chốt cùng ownerreader/queue/flock đường gọi thực: collector4b32 classifier/validator/FSM exactkeys/addr1..127/VINoptional uint32>0/startup deadline+settling/postdiag10s80; gate95/runner907/runtime/planner, sessionARMACKafterfullTX+freshD0. Không dùng NoTX wrapper của collector để phát lệnh.

SharedSTOP ALL readerFAULT/HTTPmanualAUTO/watchdog: pendingfault latch trước chờ writer, boundedwrite/serializedprioritydispatch/cancel queuedDRIVE; mỗi sự kiện operation mới, firstreason/deadline cố định, fullbytes completion, zeroafterTX cùngop, partial/noTX chỉ OBSERVED giữFAULT, publicconfirmed/unconfirmed/escalation, boundedcleanupFAILnonzero. PID errors matching tx→REJECTED ngay và history; UI0/lifecycleCSV. Typedstream validframe/yaw/epoch/coverage/fullbodyprovenance/homeposheading từ trướcmotion, COMPLETED sau confirmedSTOP.

ONE fullactualENTRY FakeUART chỉphysicalOPEN/lockfake, unscaled real hoặc advancingvirtualclock, không producttimestampbackdate/PASSflags. Positiveorderedstartup10s80+explicitARMACK và negatives late/mixed/missingfound/invalidaddr, preTXzero, oldop+newpartialfault, PIDerror, noCaller/typedstreamloss/wronghomeheading/cleanup. Sourcehash/diff/exactcommand/backuprollback. Không thêm looseclone/commentREUSE, không framework/spawn/đợiROSphysical hoặc xin lại quyềnSOURCE đã có.

Action: deploy/restart V4.8 hoặc `/dev/ttyUSB0`115200 HTTP ARM/RELEASE_LATCH/DRIVE/PID. Decision **NOT_APPROVED**. Reason: startup classifier/sessionARMACK/sharedSTOPoperation-write-confirmation/typedruntime-cleanup và PID rejection còn lỗi. Đây là Codex QA nguồn, không automaticapprovalrejection. Không Codex implementation/Serialhardware/Pideploy/gainPWM/flash/logger/ROS/recovery. Generalhumanrunintent giữ; currentcleararea/person chỉ hỏi khi bundleplanreviewREADY. Wordknownm1.75/C.23/L.1875 giữ, Assem3drawing, target140–150RPM staged. Pi13:15 chỉhistoricalreadonly khôngLIVE/physicalSTOP. Room/map/homeheading chưa nghiệm thu.
