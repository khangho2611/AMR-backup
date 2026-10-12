# Kế hoạch điều khiển liên tục — 03/10/2026

## Sửa né vùng đỏ theo yêu cầu tiếp theo

### Kết quả thật và sửa hình dạng thân

Phiên `actual_auto_run.json`: ARM200/ARM_CONFIRMED, START200/STARTED,204telemetry/22s nhưng chỉV0, targetPWM/RPM/odom0. Không lỗi timeout; actual blockerHOLD. `escape_block_explained.json` chỉ rõ scan25cm, mapoccupiedsquare bắt đầu cách tâm17.8868cm; enclosingcircle20cm giao cell nên không thể thoát bằng circle. Không kết luận hardware hỏng/khỏe.

Native `cad_native_read.json` có AABB x[-.16,.10],y[-.1035,.1035]m so với axle/LiDAR0. Khung/bố trí đã được human xác nhận; Wordtrack.1875 ưu tiên CADtrack.180, bù3.75mm/bên và thêm12.75mm/bên cho bbox thiết kếy[-.12,.12]. Đây là bao bảo thủ từ CAD+Word, không số đo vật lý mới. Góc xa nhất vẫn.20. Nạp `AGV_BODY_BOUNDS_M=-0.16,-0.12,0.10,0.12` vào controller mới `/home/khangho/agv_codex_body_20261003_0106`. Recovery kiểm SAT orientedrectangle vs cellunknown/occupied, padding cả chuyển vị tâm và góc quay giữa mẫu; scan vẫn kiểm enclosingcircle. Giữ warning35cm/A*margin15cm. Test bằng map+scan thật đã ghi cho lùi vòng ra xa, không clear pixel/map giả.

STOP đầu khi retire trả422 do D0ARMED đang trên đường trước STOP bị phân loại nhầm UNSAFE_PREFLIGHT_D0; product phát STOPop2 và freshDISARMEDzero xác nhận. Đã retire4207 sau xác nhận/ownerreleased; sửa phân loại chỉ trong STOPpending, giữ deadline/fullbyte/FAULTsticky, không tăng timeout. Thêm regression actualwriterbarrier+D0ARMED và rectangle rearcorner/unknown/edge. Sau fullQA mới khởi động bundle mới DISARMED rồi explicitARM/AUTO theo quyền continuous hiện tại.

Live mới cho thấy vật cản bên phải cách tâm25cm, phía trước60cm, controllerDISARMED/preflightready; vùng đệm35cm chặn cell xuất phát. Người dùng tiếp tục yêu cầu đỏ tự né. STOP được ACK/freshD0 xác nhận, retire đúng PID2076/cwd mới, ownerUSB0 đã nhả. Giữ LiDAR2073/SLAM2107/staticTF hiện có; controller mới nạp thư mục riêng `/home/khangho/agv_codex_escape_20261003_0044` với cùng `--operator-control`.

Điều hướng bổ sung recovery của vùng đệm: enclosingbody.20 vẫn phải hoàn toàn known-free và không chạm vật cản; unknown/mapedge vẫn chặn. Hành lang thoát phải không giảm minimumclearance trên cả map và scan, endpoint phải tăng khoảng cách. Chọn tiến vòng ra xa hoặc lùi theo hành lang trống; không xoay/lùi mù theo timer. Writer duy nhất xác thực lại hình học+freshness+generation. Ngưỡng cảnh báo35cm và A*margin15cm giữ nguyên; chỉ cho thoát một vi phạm vùng đệm đã tồn tại, không cho chủ động vào vùng đỏ từ ngoài. Khi không đủ thân xe phải HOLD/STOP. Bằng chứng kiểm offline81Python; chưa coi là physical movement.

Người dùng yêu cầu chạy xe, xác nhận khu trống và trực nguồn, rồi yêu cầu bỏ tối đa15giây. Yêu cầu này thay giới hạn trial lịch sử và lệnh không chạy của lượt trước. Codex làm trực tiếp; không Telegram/bot.

Action: nạp nguồn đã kiểm thử vào `/home/khangho/agv_codex_operator_20261003_002911`, khởi động LiDAR/staticTF/SLAM và controller `AGV_BODY_RADIUS_M=0.20 python3 -B -u agv_unified_brain.py --operator-control`. Pi snapshot boot `6c0476e0-29bf-4510-a153-b7708dcbbec7`: không controller, không ownerUSB0, HTTP8080 chưa bind. USB0CH340 MCU/USB1CP2102N LiDAR đối soát by-id. Không kill PID lịch sử sau reboot.

Khởi động DISARMED, UART owner/exclusive riêng, kiểm boot/I2C và DISARMED exact-zero10s/80 mẫu. Khi D0/scan/map/TF mới và đường có thể đi, gửi ARM explicit, xác nhận ACK+ARMEDD0 rồi AUTO. Chế độ này không hết hạn15giây; STOP/emergency và watchdog độc lập20ms vẫn hoạt động; mấtD0/scan250ms hoặc caller200ms phải dừng. AUTO V/PID, capV.08/w.35 và swept-body collision; giữ enclosingradius.20 + margin.15. MAN do người dùng giữ nút, PWM đã có trong nguồn không phải đơn vịRPM. Không flash, đổi gain/minPWM/timeout hay xóa lỗi để ép chạy.

Kiểm thực tế: hash remote=local; HTTP command result lưu journal; D0 target/PWM/RPM/odom, phase/goal/path/map và firstfault. Không gọi mocktest/mapfrontier là chứng cứ xe chạy. Nếu lỗi, ghi đúng lỗi và sửa nguyên nhân; không tự ARM lại sau fault. Bài quan sát có thời lượng ghi log, không làm thời lượng dừng xe.

Rollback: trước ARM nếu khởi động lỗi, STOP xác nhận và SIGTERM đúng PID/cwd của controller mới; không fallback controller/bot/V4.x. Trong khi xe đang chạy không ghi đè source. Khi STOP không xác nhận và xe còn chạy, người trực nguồn ngắt nguồn.

Nguồn/backup/test: `evidence_agv_20261001/codex_operator_control_20261003_002911/`. 77 Python test exit0/17.559s;12 JS assertion groups exit0. Đây là kiểm offline, mục tiêu toàn phòng/map/homeposition+heading chưa nghiệm thu.

## Nạp MAN độc lập và cruise 0,20 m/s — 03/10/2026 01:19

Người dùng trực tiếp yêu cầu tăng tốc độ và không để AUTO chặn hướng điều khiển tay. Quyền chạy liên tục/khu trống/người trực đã có trong cùng phiên, không hỏi lặp. Bundle `bundle_manual_cruise`, manifest `manual_cruise_verification.json`: 90 Python exit0/17.809s, 13 nhóm JS exit0, AST/node syntax/hash trước-sau ổn định.

Action: SCP bundle vào `/home/khangho/agv_codex_manual_cruise_20261003_011949`; STOP đúng owner11643, fresh DISARMED exact-zero + confirmed fullbyte; SIGTERM retire và xác minh USB0 released. Retire đúng launcher SLAM/node2107 vì OPEN MCU mới reset odometry, giữ nguyên LiDAR2073/staticTF; lưu map/diagnostics cũ. Khởi động SLAM epoch mới với YAML giữ nguyên và main `--operator-control`, env radius.20/bodybounds[-.16,-.12,.10,.12], startup DISARMED. Verify checksum, organic10s80, fresh scan/map/TF rồi explicit ARM/AUTO theo yêu cầu chạy; không autoARM lúc startup.

MAN: PWM±140 hiện có, bỏ chặn hình học/né của AUTO theo yêu cầu operator; giữ ACK/D0/transport/caller watchdog/STOP. MAN hủy generation queued AUTO; nhả phím V0 giữ phiên, EmergencySTOP riêng. AUTO: cruise tối đa.20m/s (~52.2RPM bánh với C.23m), chọn carrot trên đoạn A* thẳng không cắt bend, swept fullbody trước mọi V tiến. Red escape giữ.04m/s/fullbody kiểm từng tick; radius.20 và margin.15 giữ. Scan thiếu bin không tự thành vật cản nếu known-free full-map footprint xác nhận, occupied/unknown vẫn chặn. Không flash/gain/tăng sensor timeout.

Rollback: lỗi startup/transport giữ DISARMED/STOP; không tự fallback launcher/bot/V4.x hoặc ARM lại bundle lỗi. Source body cũ và evidence chuyển động/STOP được giữ. Bản body đã có actual RPM/odom thay đổi và thoát vùng đỏ tới x-.343/y.127, nhưng chưa whole-room/map/homeheading acceptance. Bản MAN/cruise mới chưa physical acceptance tại lúc duyệt kế hoạch này.
