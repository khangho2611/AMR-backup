CODEX QA 02/10 13:24 — ĐỌC KỸ WORD + ĐỐI SOÁT NGUỒN HỆ THỐNG MỚI. Tiếp tục implementation OFFLINE đã có quyền, không hỏi lại quyền chung. Chỉ bạn là hardwareowner; Codex chỉ QA/giao sửa.

Khang vừa chỉ định: SolidWorks Assem3 chỉ là bản vẽ; số thực ưu tiên TINH_TOAN_THIET_KE_XE_TU_HANH.docx. Tôi đã đọc toàn bộ Word/bảng/công thức và BANG_GIAI_TRINH_THONG_SO_AGV_CHUAN.md. Word gốc: cân1.75kg, thước chuvi23cm, tim2bánh18.75cm; R36.6mm suyra. Gear21.3/PPR11/CPR937.2 là căn cứ thông số; ghi đúng provenance, không đòi đo lại các số Khang đã lưu. 2.10kg là hệ số1.2, a/phanh/PWM là mô hình, không nghiệm thu hiện tại. Word có ví dụ1m→9187.5mm và187.5→86/84mm sai; không nạp các ví dụ này. PID12–18/20ms trong Word không cùng scaleRPM/50ms firmware .5/1.5/.010/.45. MD deadband60–80 không có phép đo trong Word, bỏ “chắc chắn nguyên nhân duy nhất/PWMpower/an toàn100%”. Mục tiêu140–150RPM vẫn giữ theo lộ trình.

Đã đọc task DB tới10547: user9953 xác nhận CHẠY ĐƯỢC và yêu cầu chạy toànhệthống;10436 yêu cầu tích hợp frontier+PIDinput+lịch sử+xuấtExcel. Tôi công nhận xác nhận chuyển động lịch sử, không hỏi lại câu wheelquay cũ. .08/1.2/1.8 và.15/1.2/1.8 đã thực thi, khácprofile đãreview; M130tool9948 trảACK/PWM120 cần audit. Không báo WAITINGONE1028 nữa, không đếm replaycompaction thànhnewmotion.

Pi đãreboot: SSHREADONLY13:15 boot1a219e09-b897-49c1-b0e3-a1649833aaf7, noAGV/ROS process,fuserUSB0exit1empty; chưafreshD0DISARMED. HashPi brainff009266…608e6/HTMLd7ae7560…110c1 khớplocal. GIỮ KHÔNGRESTART/ARM/TUNING/FLASH/run/logger/ROS saureboot trước bundle review+freshpreflight+hiệntrườngHIỆNTẠI.

Parent QA .08runner907c5882…a2750/gate95c8667…8213d: full execute_lifecycle+actualgate/reader/watchdog, clockthật10s80, ONLYhardwareOPEN/lockfake;126D0/10.063s→ARM1V20STOP1exit0, overspeed/stall/mismatch đềuSTOP+fault/exit1;partial1/5freshzeroFAULTunconfirmedexit1;no-callerwatchdoghardcapSTOPexit1. Chấp nhận GIỚI HẠN offline này; bỏblockerscap.05/guardchưaimplemented. Broker6componentfixture khôngfullproduction; không dùngPASS này đểclaimxe/chạyroom đạt.

BLOCKERS nguồn brainff009 đã TÁI HIỆN offline exactmethods:
1) send_cmd tựARM trướcM/S/V, khôngACK/fresh/session/preflight/TXlock. Tựhành phátM MAN bypassPID.
2) ChưaSCAN/MAP/D0 vẫnM-120/120; callbacksleep chặnROSreader, khôngwatchdogscan+D0 độc lập.
3) STOP giữaavoidancesleep: [M-115/-115,STOP,M125/-125] khiautoFalse — vẫnTURN/reARM sauSTOP. PhảilatchedSTOP/hủyqueue/job.
4) ROSangle+90° bịzoneRIGHT thayLEFT; kiểmTFmounting trướcfix.
5) Đảo frontier hoàn toànngănwalls vẫngoal(1,1); noA*/reachable/footprint. Maprỗng/None→RETURNHOME→SUCCESS dùheadinglệchπ. HomeghiSAUspin6s, home_thkhôngdùng, tolerancedist20cm, mapcoordssoodomkhôngTF/originyaw/fresh/epoch. Chưa đạtfullgoal.
6) APIpid luônok/noMCUACK; HTML0 bị||default, history“Đã nạpMCU” ngaykểreject/noMCU; MANkhôngPIDcontrol. CSV/localStorageđãcó nhưngchưachứngminhAPPLIED.

GIAO ONEBUNDLE SOURCEOFFLINE ngay: nối UI vào auditedgate/runtime/planner singleownerqueue+session/ACKfresh, STOPFAULTlatch/noautoARM, autonomouswatchdogscan+D0/nonblocking, typedmapTF/yaw/epoch+reachablefootprint/coverage+homepositionANDheading capturedbeforemotion. GiữgeometryWord; inputPIDtypedfinite/0valid/MCUACKreadback; historyPENDING/APPLIED/REJECTED/FAILED/exportCSV thật. Chuẩn bị motor/PIDcause và profilebounded có cơ sởkhởi động+groundtruth/stopmargin, khôngPWMhardcode/nânggain/deploymù.

HandofffullentryFakeUART+typedSCAN/MAP/TF+HTTP/UI tests positive/lossscanD0/STOPduringcallback/missingmap/disconnectedfrontier/wrongheading/PIDrejectzero/noMCU; sourcehash/diff/exactcommand/backuprollback và actualtool evidence. KhôngchờROSthật/khôngxinimplementationpermission/khôngspawnframework/khôngfake4botACK.

Đọc report DOI_SOAT_WORD_VA_HE_THONG_AGV_20261002_1324.md và evidence được trỏ trong đó. Actionrestart/autoSTART/M/tuningUSB0: NOT_APPROVED do cácblockers trên (QAnguồn). Snapshotplanready mới chốtcleararea/ngườitrựcHIỆNTẠI saureboot. Nhận nhiệm vụ và làmoffline tớiroom/map/homeheading.
