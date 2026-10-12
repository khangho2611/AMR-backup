CODEX — ĐÃ CHẤP THUẬN ĐÚNG MỘT BÀI CHẠY NGẮN 10:28 ngày02/10.

Khang vừa xác nhận trực tiếp trong Codex: quanh xe trống ít nhất1,5m và ĐANG có người trực công tắc nguồn. Quyền chạy chung đã có. Thực hiện ngay theo CHO_PHEP_MOT_BAI_MOTION_AGV_20261002_1028.md; đọc file này, không hỏi lại permission implementation/run chung, không chờ ROS/map hoàn tất.

Snapshot FREEZE runner15cdfc6c6d86582df3ae219b8f301eb1dbb7bbdd0da742d43052242cda50f928 + gate6f4a2106622e99fe60212199b621cdcbbd2a76b2e639519796b15d5a703e3d1d. Parent fullproduction FakeUART/unscaled10s80 + exact .04/1/1.5 positive exit0/STOPconfirmed/threadsjoined/closed; thiếufound/late/unsafe chặnARM; partialSTOP+freshzero exit1/FAULT/unconfirmed. Evidence1024/1026 đã lưu. Không sửa snapshot khi chạy; không flash/ghiđè firmwaref5bf/supervisor1bd/gain/PWM.

SCP hai SOURCE vào thư mục MỚI /home/khangho/agv_trial_20261002_1028/, giữ nguyên checkout/bản cũ để rollback. Chốt hash/PiPython/boot, import hoặc --mock chỉ OFFLINE xác nhận môi trường, không thay fullentry proof. VisibleAGVproc và fuserUSB0 ngay trước OPEN: phải khôngownerkhác/fuserexit1stdoutstderrempty; không ||true cheexit. Nếu có owner/error/hash khác thì DỪNG và báo, không launch ROS/brain/bridge/logger.

ĐÚNG MỘT invocation real được duyệt (không --mock):
/usr/bin/timeout --kill-after=2s 30s /usr/bin/python3 -X utf8 /home/khangho/agv_trial_20261002_1028/agv_motion_supervisor_runner.py --port /dev/ttyUSB0 --baud 115200 --target-v 0.04 --nominal-time 1.0 --hard-time-cap 1.5 --output-dir /home/khangho/evidence_motion_live_20261002_1028

Output/stdout/stderr MỚI unique/noclobber, giữ exit thật. Cùng owner/transport phải startup+postdiagfresh10s80→ARMreq/ACK/freshARMED→V→STOPwrite/freshD0confirm→cleanup. Không reuseD009:00; không tách mở cổng collector khác. Invocation bắt đầu=quyềnUSED; FAILkhôngretry/reARM/CLEAR_FAULT. ContinuousPiwatchdog và người trực xuyên suốt. STOP lỗi/unconfirmed/mấtdata/process/chuyển động bất thường: STOP/DISARM và người trực ngắt nguồn nếu không xác nhận dừng. TimeoutkillkhôngmotorSTOP.

Trả rawRXTX/request-write-confirmtimings/ARM-V-STOPcounts/RPMtargetPWM/ODOM/hashbeforeafter/exit/postowner/process + QUÃNG ĐƯỜNG/HƯỚNG THẬT được người trực đo/quan sát. Xe không đi thì báo không đi, không tăngPWM. .04m/s1s có ramp, không40mmexact; sourceMCUtimeout300ms/Piguard250ms, không claim200msMCU. Chưa140–150RPM, target đó vẫn giữ cho lộ trình đo vàSTOPmargin sau bài này. Không claim room/map/home/fullPASS từ runnerstatus. Helper --mock riêng không chứng minh hardware production hoặc xóa mọi lỗi ngoài scope.
