# Phân tích trực tiếp Raspberry Pi và hướng xử lý AGV — 08/10/2026

## Kết luận

**Ưu tiên sửa quyền điều khiển, STOP và tính nhất quán dữ liệu trước khi chỉnh PID hoặc tăng tốc.** Log trên Pi chứng minh vòng lặp `SCAN_TIMEOUT → STOP → CLEAR_FAULT → ARM`, và có lệnh xoay được gửi sau khi API đã trả `STOP_CONFIRMED`. Đây là lỗi phần mềm đã có bằng chứng, không cần yêu cầu người vận hành tái hiện va chạm để xác nhận.

Chưa xác định đầy đủ nguyên nhân vật lý của lần chạm tường lúc khoảng 14:19. Tiến trình được kiểm tra khởi động lúc 16:03:25 và có source sửa lúc 16:02:59. Không dùng log phiên 16 giờ để khẳng định chính xác đường thực thi của phiên 14 giờ.

Trong lần phân tích này chỉ SSH đọc file, đọc process/environment, GET telemetry/diagnostics và tải bản sao về máy. Không mở serial, không ARM/STOP/chạy xe, không restart/deploy/flash. Các lệnh motor trong bài tái hiện chỉ ghi vào bộ nhớ trên máy tính.

## 1. Đã xác định đúng hệ thống đang chạy

SSH: `khangho@100.90.252.15`, hostname `khang`. Snapshot chính: **16:10:56 ngày 08/10/2026, UTC+7**.

| Thành phần | Kết quả kiểm tra |
|---|---|
| Controller | PID `29898`, `python3 -B -u agv_unified_brain.py --operator-control` |
| Thư mục controller | `/home/khangho/agv_codex_reader_20261003_0652` |
| UART động cơ | `/dev/ttyUSB0`, owner PID 29898 |
| LiDAR | `sllidar_node`, PID 2254, `/dev/ttyUSB1`, baud 460800 |
| SLAM | `slam_toolbox`, PID 2288, `slam_scan_fix.yaml` trong thư mục controller |
| TF tĩnh | `base_footprint → laser`, x/y/yaw bằng 0 |
| Web | Cổng 8080 |
| Telemetry tại snapshot | `auto=false`, `DISARMED`, target/RPM/PWM/v/w đều 0; `stop_confirmed=true`, fault null |
| Khoảng cách gần nhất tại snapshot | 0,49 m; không phải khoảng cách lúc chạm tường |

Bốn file chính trên Pi (`agv_unified_brain.py`, `agv_command_session.py`, `agv_navigation.py`, `index_cyberpunk.html`) trùng SHA256 với workspace tại thời điểm so sánh. Hash các file đã tải ổn định qua lần đọc kiểm chứng tiếp theo. Source trên đĩa có thời gian sửa trước thời điểm tiến trình khởi động; không kiểm tra bytecode trong bộ nhớ tiến trình.

### Các thư mục liên quan

| Thư mục trên Pi | Vai trò và đánh giá |
|---|---|
| `agv_codex_reader_20261003_0652` | Bản đang hoạt động; đã đọc sâu controller, session, planner, cấu hình, launcher và diagnostics. |
| Các bản `agv_codex_20261002_1915`, `diag`, `operator`, `escape`, `body`, `manual_cruise`, `manual_tf`, `resume`, `sync`, `document` | Các snapshot triển khai lịch sử. Đã lập danh sách source và hash; không có controller riêng của những bản này trong danh sách process kiểm tra. |
| `rplidar_c1_ws` | Driver ROS LiDAR đang được sử dụng; đã đọc launch C1. |
| `rplidar_c1_test` | Bộ công cụ cũ có app tránh vật cản, bridge/web và nhiều launcher; đã đọc README, launcher và trích đoạn controller. Một launcher cũ có thể chạy bridge khác trên cùng UART/cổng 8080. |
| `robot_ws` | Không tìm thấy file trong phạm vi kiểm tra sâu 3 cấp; không có bằng chứng đây là source controller hiện tại. |
| `firmware`, `firmware_bench` | Chứa binary firmware/bootloader/partitions. Không xác nhận được binary nào hiện nằm trên MCU bằng việc chỉ liệt kê file. |
| Các script `fix_*`, `apply_*`, `upgrade_*` ở home | Nhiều công cụ vá lịch sử; không thực thi. Cần quản lý phiên bản để tránh chạy lại patch cũ. |

Đây là kiểm kê các thư mục và đọc sâu đường chạy hiện tại, không phải tuyên bố đã đọc từng file của mọi bản lưu.

## 2. Các lỗi ưu tiên cao có bằng chứng

### P0 — STOP không thu hồi hoàn toàn quyền AUTO

`agv_command_session.py:487` tăng generation nhưng ở operator mode không latch và không đặt `autonomy_allowed=False`. `agv_unified_brain.py:258` tắt `state.auto_mode`, nhưng callback AUTO đã đọc trạng thái trước đó vẫn có thể tiếp tục. Khi callback này gọi `drive()` sau STOP, nó lấy generation mới và có thể được chấp nhận.

**Log thật:** event 3721 trả HTTP `STOP_CONFIRMED`; event 3725 gửi đầy đủ `ARM\nV 0.000 -0.450`; event 3726 ghi `accepted=true`. Khoảng cách giữa phản hồi STOP và lần TX tiếp theo khoảng **3,14 ms**. MCU sau đó ACK ARM và ACK lệnh V. Đây là bằng chứng gửi lệnh sau STOP, chưa tự chứng minh quãng dịch chuyển vật lý sau STOP.

**Tái hiện offline:** STOP → D0 mới xác nhận DISARMED → lệnh AUTO mới vẫn trả `SENT` và ghi `ARM\nV 0.000 0.350`.

**Hướng sửa:** STOP phải thu hồi token/quyền AUTO ở tầng session; callback mang token từ đầu lượt tính toán đến lúc ghi UART. Chỉ thao tác tiếp tục rõ ràng mới cấp token mới. Giữ cơ chế hủy lệnh đang chờ writer, đồng thời chặn cả lệnh của callback cũ được tạo sau STOP.

### P0 — Tự xóa lỗi và ARM lại làm mất tác dụng chốt dừng

- `agv_unified_brain.py:319`: watchdog tự gửi `CLEAR_FAULT\nARM` khi có lỗi và `motion=false`.
- `agv_command_session.py:438`: `drive()` tự đặt armed, bỏ latch, xóa cả `STOP_UNCONFIRMED` trong operator mode.
- `agv_command_session.py:462`: ghép ARM vào lệnh chạy; nếu MCU FAULT còn ghép CLEAR_FAULT.
- `agv_unified_brain.py:790`: AUTO START tự clear/arm và báo STARTED mà không đi qua bộ kiểm tra của nhánh strict.

Trong 512 command events còn lưu, khoảng thời gian **11,478 s** chứa **55 STOP vì SCAN_TIMEOUT**, 2 USER_STOP. Event 3124 gửi STOP; 3125 gửi CLEAR_FAULT/ARM; 3128 lại SCAN_TIMEOUT. Đây là vòng lặp thực tế trong phiên trước khi thu snapshot, không phải suy luận từ tên biến.

**Hướng sửa:** tách MANUAL/AUTO khỏi cơ chế bảo vệ. FAULT, STOP chưa xác nhận và mất telemetry phải chặn mọi lệnh chuyển động. Xóa lỗi và ARM là các chuyển trạng thái riêng, cần ACK và dữ liệu mới tương ứng; loại bỏ auto-heal gửi ARM từ watchdog. Sau mất nguồn driver có thể tự kiểm tra phục hồi, nhưng không tự cấp lại quyền chuyển động của phiên cũ.

### P0 — STOP có thể được xác nhận bằng D0 cũ

`agv_command_session.py:529` và `:591` có fallback `already_safe`, chỉ xét nội dung `latest`, không yêu cầu D0 mới hơn lần ghi STOP thành công. Vì vậy thông báo STOP_CONFIRMED không luôn bảo đảm đã quan sát dừng sau chính lệnh đó.

**Tái hiện offline:** D0 DISARMED từ 10 giây trước, gửi STOP, không nhận thêm byte phản hồi, watchdog vẫn đặt `stop_confirmed=true`.

**Hướng sửa:** cần full-byte STOP write, mã thao tác hiện tại, D0 có timestamp/sequence nhận sau khi TX hoàn tất và đủ mới. D0 cũ chỉ được hiển thị là “lần cuối quan sát bằng 0”. Không dùng để hoàn tất STOP.

### P1 — Ngưỡng tuổi scan mâu thuẫn và cấu hình khởi động bị thiếu

Environment của PID 29898 không có biến `AGV_*`. Khối cấu hình source vì vậy cho kết quả:

| Tham số | Tiến trình hiện tại suy ra từ code + environment | Launcher `start_agv_system.sh` |
|---|---:|---:|
| `AGV_SCAN_MAX_AGE_S` | 0,25 s | 1,5 s |
| `AGV_PROGRESS_TIMEOUT_S` | 1,5 s | 3,5 s |
| `body_bounds_m` | `None` | `(-0.16,-0.12,0.10,0.12)` |
| `body_radius_m` | 0,20 m | 0,20 m |

Ở operator mode, `drive()` chấp nhận tuổi scan đến **ít nhất 1,2 s** (`session:452`), trong khi watchdog dùng **0,25 s** của tiến trình (`session:576`). Callback nhận scan còn kiểm timestamp 0,25 s (`brain:382`).

**Tái hiện offline:** scan cũ 0,5 s → lệnh xoay được gửi → watchdog ngay sau đó phát SCAN_TIMEOUT/STOP. Log thật cũng có lệnh được chấp nhận khi scan age khoảng 0,53 s, xen với các STOP vì scan timeout.

**Hướng sửa:** một nguồn cấu hình có kiểm tra hợp lệ, in toàn bộ cấu hình hiệu lực lúc khởi động và công khai qua diagnostics. Mọi tầng dùng cùng chính sách tuổi dữ liệu. Đo độ trễ `/scan`, timestamp, callback, mutex và thời gian planner để sửa nguyên nhân chậm. Không chỉ tăng timeout để che vòng lặp. TF được chấp nhận đến 20 s trong `brain:653` cũng cần xem lại theo tốc độ và sai số định vị cho phép.

### P1 — Phản hồi động cơ cũ không chặn chạy trong operator mode

`session:451` và `:574` chỉ kiểm D0 timeout khi strict. Với operator, có thể gửi chuyển động khi không còn phản hồi động cơ mới.

**Tái hiện offline:** D0 cũ 10 s, scan được giả lập mới → lệnh AUTO xoay vẫn `SENT`.

**Hướng sửa:** telemetry freshness là điều kiện chung cho cả AUTO và MANUAL. MCU watchdog vẫn phải độc lập; không coi việc UART write thành công là chứng minh driver/motor đã nhận và thực hiện.

## 3. Những điểm khiến né/thoát kẹt chưa đáng tin

### Hình học thực tế phụ thuộc cách khởi động

`brain:143` parse biến bounds rỗng gây ValueError; nhánh except bỏ qua, nên giữ `None`, không lấy bộ bounds ở nhánh else. Kết quả này đã được chạy lại từ chính khối cấu hình đã tải với environment thu được.

Không có bounds thì recovery dùng đĩa bán kính 0,20 m; `navigation:242` còn từ chối xoay recovery khi v=0. Nếu xe đã sát tường hơn bán kính bảo thủ, lùi thoát cũng có thể bị coi là va chạm từ vị trí bắt đầu. Với bounds được cấu hình thì đi qua thuật toán khác. Đây là khác biệt hành vi có thể kiểm chứng từ code, chưa xác định nó giải thích toàn bộ lần kẹt trước đó.

### Nhánh xoay recovery có lỗ hổng kiểm tra góc thân

Khi **có bounds**, `brain:725` kiểm LiDAR bằng `min(abs(bounds))`, tương đương bán kính 0,10 m với bộ bounds hiện có; không kiểm toàn bộ hình chữ nhật đang xoay với các điểm LiDAR mới. Bản đồ có kiểm riêng nhưng không bảo đảm chứa vật cản vừa xuất hiện.

**Tái hiện với map trống và vật cản chỉ có trong LiDAR:** điểm ở góc 152°, cách 0,19235 m ban đầu ngoài đuôi xe; sau quay 0,175 rad điểm nằm trong hình chữ nhật thân xe, nhưng `_escape_clear(0, 0.35)` trả true. Lỗi này thuộc nhánh có bounds; không gán nó là nhánh đang chạy của PID hiện tại vốn thiếu bounds.

**Hướng sửa:** dùng một phép kiểm swept footprint cho cả tiến, lùi, xoay và cung tròn, kết hợp occupied map với scan mới; xét padding, phần góc thân quét qua và vùng không có dữ liệu. Không thay hình chữ nhật bằng cạnh ngắn nhất. Khi đã sát/chạm, recovery chỉ nhận chuyển động giảm độ xâm nhập hoặc tăng khoảng hở một cách kiểm chứng được.

### Bản hôm nay đã có gọi escape khi vùng đỏ

`brain:1024` hiện gọi `_try_escape()` khi DANGER_STOP hoặc khoảng cách ≤0,35 m. `brain:770` ưu tiên lùi nếu vật cản gần nhất ở phía trước; nhánh stall cũng đã gọi escape. Vì vậy nhận định cũ “vùng đỏ chưa nối trực tiếp với escape” không còn mô tả đúng source hiện tại.

Tuy nhiên, chọn lệnh escape vẫn thử danh sách ứng viên từng tick; chưa chứng minh một chuỗi thoát hữu hiệu. Cần trạng thái rõ `BRAKE → BACKOUT → TURN → REPLAN`, có điều kiện vào/ra, giới hạn thời gian/quãng đường và tiêu chí tiến triển theo pose + khoảng hở. Bánh quay không chứng minh thân đã thoát vì có thể trượt.

## 4. Lập bản đồ, khám phá và quản lý phiên bản

- Có A*, inflation, frontier và đường về home trong code; không cần viết lại toàn bộ từ đầu.
- Khi không tìm được goal, operator mode chạy nhánh reactive ở `brain:1116`, thay vì nhánh kết thúc khám phá/về home của strict. Do đó “xe tiếp tục chạy/quét” chưa chứng minh “khám phá hết vùng reachable rồi về điểm đầu”. Cần phân biệt planner timeout, dữ liệu không hợp lệ, frontier tạm bị chặn và thật sự hết frontier.
- `brain:687` bỏ qua `UNKNOWN_SWEEP` trong operator mode. Vì hàm sweep trả ngay ở vật cản đầu tiên, không nên coi việc bỏ qua một kết quả UNKNOWN là toàn bộ đường đã được kiểm tra với các ô occupied phía sau. Cần sửa chính sách kiểm tra tại geometry/planner, không bỏ qua mã lỗi ở ngoài.
- SLAM log có queue full và timestamp cũ hơn TF cache. Các log này trải qua giai đoạn trước; chưa đủ kết luận scan hiện tại hỏng hay CPU là nguyên nhân. Cần đo thời gian và đồng bộ TF/map khi sửa.
- Có nhiều launcher trỏ tới các source khác nhau; launcher cũ có `pkill -9`, launcher mới vẫn có blanket kill/fuser-k. Đề xuất một entrypoint, file cấu hình duy nhất, deployment manifest/hash, quy trình shutdown có xác nhận dừng, và chọn cổng bằng device identity. Chưa xóa hay sửa các bản lịch sử.
- Thư mục local `robot_stm32_f103` thực tế build ESP32/Arduino theo `platformio.ini`. Không flash nhánh STM32 chỉ dựa vào tên thư mục. Binary firmware trên Pi không chứng minh firmware đang nằm trên MCU.

## 5. Thứ tự thực hiện đề xuất

1. **Khóa bản nguồn để sửa và chốt cấu hình hiệu lực.** Dùng snapshot hiện tại làm baseline, chọn bounds theo dữ liệu hình học đã có; không tự suy lại từ wheel track. Ghi hash/controller PID/environment vào evidence.
2. **Sửa STOP/FAULT/quyền điều khiển trước.** Thu hồi AUTO token, không auto-rearm, xác nhận dừng bằng D0 mới; kiểm mất D0 cho mọi mode. Tiêu chí: callback AUTO đang chạy và mọi lệnh cũ không phát chuyển động sau STOP.
3. **Sửa pipeline thời gian.** Đồng nhất ngưỡng scan; đo độ trễ dưới tải map/planner/web; tách tính planner nặng khỏi đường xử lý cảm biến khi số đo xác nhận nghẽn. Scan mất/cũ phải dẫn tới dừng ổn định, không lặp STOP–ARM.
4. **Sửa geometry và recovery.** Kiểm swept footprint thống nhất; các ca tường trước, góc tường, cột, vật cản mới xuất hiện, vùng mù và kẹt bánh đều có replay offline. Xác nhận khoảng hở thật tăng trước khi quay/chạy lại.
5. **Nghiệm thu exploration/home rồi mới tối ưu tốc độ.** Ghi coverage vùng reachable, lý do bỏ qua vùng, số lần intervention, vị trí/góc home và STOP cuối. Kiểm vật lý ở đợt riêng sau khi các kiểm tra offline đạt; không nghiệm thu từ build/test giả lập.

Không đề xuất thay PID, tăng lực bánh hoặc nới tất cả timeout trong đợt đầu: hiện đã có lỗi điều phối đủ để phá hỏng hành vi ngay cả khi motor và LiDAR hoạt động.

## 6. Bằng chứng và cách kiểm tra lại

Thư mục bằng chứng: [pi_audit_20261008_160842](pi_audit_20261008_160842/).

- [inventory.json](pi_audit_20261008_160842/inventory.json): danh mục source, kích thước, mtime, SHA256 các thư mục liên quan.
- [runtime_snapshot.json](pi_audit_20261008_160842/runtime_snapshot.json): telemetry, diagnostics, environment AGV/ROS và đuôi log đã thu trên Pi.
- [critical_timeline.json](pi_audit_20261008_160842/critical_timeline.json): các event STOP/ARM/V quan trọng.
- [source_verification.json](pi_audit_20261008_160842/source_verification.json): kiểm lại process/hash, trích source các thư mục cũ và diff backup hôm nay.
- [effective_config.json](pi_audit_20261008_160842/effective_config.json): chạy lại riêng khối cấu hình bằng environment đã thu; không khởi tạo phần cứng.
- [reproduce_audit.py](pi_audit_20261008_160842/reproduce_audit.py) và [offline_repro_results.json](pi_audit_20261008_160842/offline_repro_results.json): sáu kiểm tra điều kiện an toàn trên bản sao source Pi, UART trong bộ nhớ, ROS imports giả lập.

Chạy từ workspace bằng Python 3:

```powershell
python -B .\baocao\pi_audit_20261008_160842\reproduce_audit.py
```

**Kết quả đã chạy: exit 1, cả 6 điều kiện an toàn đều không đạt.** Đây là bài tái hiện lỗi để xác định công việc cần sửa; không phải kết quả nghiệm thu và không phải đã sửa được xe. Bài xoay geometry dùng cảnh tổng hợp; hai vấn đề STOP và scan timeout còn được củng cố bằng log thật.

SHA256 snapshot:

```text
agv_unified_brain.py   9051d83aec5777765d76984cba4cb2ccd231e0f14a3603b305d4c49644292ffb
agv_command_session.py 379e67b4c249997cd09971ee2b3edd7034fa9975c883976bf3d76ff10692802f
agv_navigation.py      f8c47533a9e983cffd2209e48ffb8cb544b6ba4de91e5e8fb00333dad0c6eb9c
```
