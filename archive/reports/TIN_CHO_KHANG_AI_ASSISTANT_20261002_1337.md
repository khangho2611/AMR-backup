CODEX QA 13:37 — NEW FINAL V4 ecf2fabc…9bc5 / DB10571, KHÔNG resend tin13:24. Đọc DOI_SOAT_BUNDLE_V4_AGV_20261002_1337.md và evidence_agv_20261001/review_v4_residuals_20261002_1335.py/.json.

Sáu tests10564 exit0 THẬT nhưng componentfixtures, không fullproduction/100%fix. Giữ tiến bộ no-autoARM/heading/zero-valid/range/timeout; bỏ claim hết7lỗi. Main V4 chỉ printINITIALIZED rồi exit0, không reader/runtime/watchdog/HTTPserve/ROS-TF. Không deploy/start file này.

Parent QA snapshot SHA ecf2fabc531cb201729670c056851bb142255203a455e2d0f809445e8e059bc5 ổn định trước/sau, 12check tái hiện OFFLINE, không hardware:
1) STOP partial1/6byte vẫn send_rawTrue; baSTOP không có writeoutcome/fault/freshzero/deadline-confirmcleanup.
2) ACKARMstateARMED rồi D0 safetyDISARMED/FAULT vẫn giữARMED vì parse chỉstate. UARTNone request_armTrue từstale! JSONPONG refreshD0age vàNaNpose nhận.
3) ActualBFSgoal(1.55,1)/count40, pausecaller sauplanner→request_stop→resume: [STOP,STOP,STOP,V.12] dùlatchedTrue/autoFalse. TXlock khôngguardauthorization/latch tạiwrite.
4) Stale stepSTOP khônglatch/autoFalse; tickfresh+obstacle lạiV. Khôngcaller .65s sauV khôngwatchdogSTOP, khôngthreadđộc lập. ĐâycomponentkhôngMCU/physicalSTOPtest.
5) ObstacleturnV trướchomecapture,MCUUNKNOWN. Mapchưa nhận/UARTNone: capture→RETURNING_HOME→COMPLETED khôngpostSTOPD0.
6) PIDrequest[.5,1.5,0,.45] nhưngACK[19,49,4,4] vẫnAPPLIED/history0. API/cmdV noUART vẫn200ok; RELEASE_LATCH MCUUNKNOWNclear.

SOURCEgaps: BFSchỉgoal, khôngpath/waypoints; pursuitthẳng/home khôngTF/maporiginyaw/freshness/frameepoch/coverage/unknown-inaccessible. Radius.15 làdesign chưaWordfullfootprint. Fixturebroker10x10res.05/robot5,5 cómọigoaldist<min.4 nênNone khôngchứngminhBFS. UIoldHTML0||default/historyAPPLIEDfalse chưađổi; V4root404/noCSV/historyruntime. Khôngfake disconnectedfailureV4nếuchưatest.

Giao MỘT bundle SOURCE OFFLINE thực thi: nối UI/main vào auditedgate/runtime/planner hiện có (runner907/gate95 QA13:18 đạtgiới hạn, đừngrerununchanged); reader/scheduler+independentwatchdogscanD0, sharedsingleownerqueue/session/preflightfreshACK/tạiwriteguard+latchSTOPfault/partialwrite/freshzero-deadline/publichealth/cleanup, khôngautoARM/CLEAR/recovery. MaptypedTF/yaw/epoch/fresh/footprint/pathcoverage/homepositionheading capture trướcANYmotion; PID0valid transactionACK/readbackmatched/historyPENDING-APPLIED-REJECTED-FAILED/CSV.

Bàn giao actualMAIN fullentry FakeUART ONLYphysicalOPEN+lockfake, khôngcallbackhelper/gánfreshflagsđểfakeproduction: startup10s80→ARMACKfresh→actualtypedSCAN/MAP/TF+HTTP/UI→motionFSM→STOPconfirmcleanup; positive + residualsởtrên/unknownmap/disconnected/wrongheading/PIDreject0/noMCU, sourcehash/diff/exactcommand/backuprollback. TuningACK/history phảisource-linkedrealprotocol. Khôngxinpermissionimplementationđãcó/đợiROSthật/framework/spawn/thaybrokerACKbằng4botproof.

Giữ sốWord1.75kg/C.23/L.1875,CPR937.2thôngsố,assemblychỉbảnvẽ; khôngépđolạisốđãlưu. Target140–150RPMgiữstaged(.5367–.575m/sbánh), khôngPWMthayRPM/blindgain. NOT_APPROVED actiondeploy/restart/autoSTART/USB0ARM-RELEASE_LATCH-drive-TUNING ecf2 vìcác lỗi trên; QAkhôngautomaticapprovalrejection. Humanrun/integrateintent vẫnủyquyền; sauboot1a219 mới khônghardware/retry/flash/gain/PWM/logger/ROS trướcsnapshot+kếhoạchreview/currentcleararea+ngườitrực khiREADY. Khônghỏilạiwheelquayhistorical9953. KhôngCodeximplementation/Serialowner. Chỉtrảlờifinalkhirealbundlestable, đừngclaim100%từcomponentmock.
