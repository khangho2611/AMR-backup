# Đối soát V4.7 — 02/10/2026 14:58 Asia/Bangkok

QA V4.7 — 02/10/2026 14:58 Asia/Bangkok. Final10876/source0fd97a2a87dfb29735653c9f077d26265d8bc7da046ff9412a337046cabe0a16/test29a96459…559130/HTML35ab348…a10e9. Parent NEW review_v4_7_entry_20261002_1456.py/.json actualMAIN-reader-HTTP localhost/FakeUART + changed componentseams; REALCLOCK/nopassedbackdate/countassignment/hashstable/nohardwareROS.

4 FIX GIỚI HẠN: freshsensor fullV→I2C_FAULT phát3STOP ngay+latch; requestSTOPtimeout rồi latefullzero cập nhậtconfirmed và GIỮFAULT/firstreason; originNaN actualstep HOLD/V0; actualMAIN organic82D0/span10.141s thiếubanner trả422/0ARM. Bỏ corresponding4.6bugs đúngpath. NormalcleanupclosedUART/nav/watchdogdeadgiới hạn; khôngphysicalSTOP100%.

NEW BLOCKERS thực:
A) ActualMAIN đã có82D0 TRƯỚC boot. Sau10.156s gửi ngược thứ tự {"error":"Scanning I2C bus failed"} rồi plain "BENCH SERIAL ONLY" và1D0: count83/passedTrue/settlingTrue→ARM+HTTP200 trong.079s saubanner, NOi2c_found/NOpostdiag10s/NOARMACK/sessionMCU. Substring trướcJSON còn nuốt error. StartupFSM thực chưa có thứ tự/deadline/exactkeys/found/settling/reset.
B) Readerhardwareerror gọi helperSTOP NGOÀI tx_lock, rồi mớilatch. Barrier actualsend_guarded-inflightV/FakeUART tái hiện 3STOP hoàn tất rồi V.04 hoàn tất/returnTrue, latchTrue nhưng isMovingTrue. Đây là QA completionorder, KHÔNGclaimxephysicalchạy. Cần ownerqueue/shareddispatch prioritySTOP+cancelpendingdrive, boundedwrite và cùnglatchatwrite.
C) NEW latehandler đặt CONFIRMED chỉ cầnlatched/fullzero/now>=stop_requested. Hardwarefaulthelper khôngđăng kýoperation nên requested=deadline=0. Component persistentSTOP3x1/6 rồi freshzero vẫn confirmedTrue; actualMAIN readerfault3fullSTOP+zero cũngconfirmedTrue vớioperation0. Phải giữ writeoutcomeFAULT và phân biệt ZERO_OBSERVED vs STOP_CONFIRMED; newzero khôngxóa partial/nooperation. Đây là newconfirmationpath test, khôngrerunhelpercũ.

REUSE claim sai phạm vi: importcollector3constants THẬT nhưng ASTloadcounts đều0; khôngvalidate_telemetry_sample/collectorFSM call, khôngimport/call runner907/gate95/runtime/planner. Mainonlybannerchange. TypedSCANMAPTF/frameoriginyaw/epoch/freshness/coverageinaccessible/knownfree/fullfootprint/homepath/ownerflock/write_timeout/shareddeadlinehealthescalation/boundedreaderjoin+close/sinkFAIL/PIDUI lifecycle vẫnpendingSOURCE; CSVHTMLunchangednorerun.
Fivecomponent10869exit0 thật; suite1 vẫnbackdateproducttimestampnow-10.1/bannersSAUpreflight; suite3 gánstop_requested và KHÔNGstartwatchdog; typedmapfixture DIRECTstate; cleanupprint. Lỗi10845/10857 intermediatekhôngfinalproductFAIL; report15:15futuretimestampkhôngdelivery. Khôngfullproduction100%.

Bàn giaoONEactualSOURCEOFFLINE với đườnggọi thật: collector4b32 purevalidator/startupFSM nối cùngownerreader (khôngreuseNoTXtransportwrapperđểghiTX), auditedgate95/runner907/runtime/planner quaownerlockqueue; startup strictschema/banner+scan+found/deadline/settling/postdiagcontinuous10s80/explicitARMACKafterTX/sessionfresh; sharedSTOP serializedallpaths/writeoutcome/operationIDfirstreasondeadline/latezeroobserved/publicFAULTescalation/cancelpendingV/boundedcleanupFAIL; typedSCANMAPTFvalidatefresh/coveragehomeheading/UI/PIDCSV. FullactualENTRYFakeUARTONLYOPENlockfake/unscaledclock khôngproductbackdate/flag, positive+exactnegativeA/B/C/noCaller/typedstreamloss/homewrongheading/cleanup, hashdiffexactcommandbackuprollback.

Actiondeploy/restart0fd9USB0ARMrelease-drivePID115200HTTP NOT_APPROVED reasonstartup/STOPwriterace-falseconfirm/typedruntimecleanup; CodexQA nguồnkhôngautomaticapprovalrejection. NoCodeximplementation/Serialhardware/PideployflashgainPWMloggerROSrecovery/frameworkspawn/permissionrepeat. Wordknownsốđo giữ/Assem3drawing/140–150RPMstaged/human9953movementresolved/currentfieldonlywhenplanreviewREADY. Room/map/homeheading chưađạt.

## Phạm vi

Evidence evidence_agv_20261001/review_v4_7_entry_20261002_1456.py/.json. Four fixes limited/five residual entries (hardwareerror operation missing là component và actualreader cùngseam, khôngnămindependentbugs). Callback fixture blockingV mô phỏng completionorder tại Serialwrite seam; không hardware-byte trace hoặc measuredphysicalmotion. 3STOP trướcV khiwriterfault vượtmutex là reproduction sourceconcurrency cần sửa chung, không tănggain/PWM.

Importedconstants loadcount0 theoAST không có loader fallback logs; statementcollectorimport có thật, chỉ phầnreuse validator/FSM chưacall. Request latezero sau requestSTOP được verifyfixed và faultkept, khôngđòi tựclearfault. Partialhelperruntime chỉ dùng đểkiểm latehandler NEWfalseconfirmation; khôngrerun unchanged4.6suites.

Pi trạng thái13:15historical khôngđược biến thành currentlyphysicallystationary. No new hardwarecommands trongbroker10840–10876 được đọc. Khối actionblocklàsourceQA, khôngautomaticapprovalrejection.

