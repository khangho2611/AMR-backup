# Đánh giá dự án xe tự hành: ưu điểm, nhược điểm, rủi ro và phương án triển khai

Ngày đánh giá: **01/10/2026**. Thư mục: `D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH`.

## 1. Kết luận và hướng triển khai phù hợp

**Dự án có nền tảng tốt cho đồ án hoặc robot thử nghiệm trong nhà: firmware ESP32 điều khiển hai bánh bằng PID, encoder phần cứng, odometry và chương trình Raspberry Pi tích hợp LiDAR, ROS 2, bản đồ SLAM, dashboard. Tuy nhiên, mã hiện tại chưa đủ tin cậy để bật tự hành không giám sát.**

Các vấn đề cần xử lý trước tiên là mất lệnh nhưng xe không tự dừng, STOP có thể bị lệnh tiếp theo ghi đè, sử dụng scan cũ hoặc chưa có scan, phân loại trái/phải sai quy ước ROS, và tính vận tốc né vật cản không giới hạn đúng. Chức năng khám phá toàn phòng/quay về gốc hiện còn thiếu bộ tìm đường và sử dụng chưa đúng hệ tọa độ.

Hướng phù hợp nhất:

1. Giữ ESP32 + driver + encoder và hoàn thiện lớp dừng an toàn tại ESP32.
2. Chọn **một phiên bản Python chính thức**, lấy `agv_unified_brain_v2_1.py` làm điểm xuất phát để sửa vì đã có TF và telemetry; không coi phiên bản này đã sẵn sàng vận hành.
3. Nghiệm thu điều khiển thủ công, hiệu chuẩn bánh xe và SLAM trước.
4. Nếu mục tiêu chỉ là demo né vật cản, giữ thuật toán đơn giản sau khi sửa các lỗi ưu tiên cao.
5. Nếu mục tiêu là đi đến điểm, khám phá phòng và quay về gốc ổn định, dùng Nav2 làm lớp dẫn đường; frontier chỉ chọn mục tiêu để gửi cho Nav2.

**Chưa có căn cứ cần thay vi điều khiển hoặc viết lại toàn bộ firmware. Ưu tiên sửa kiến trúc điều khiển, kiểm tra dữ liệu và quy trình triển khai trước khi mua thêm phần cứng.**

## 2. Phạm vi và mức độ xác minh

Đã đọc các thành phần mã nguồn chính, cấu hình firmware, script khởi động, dashboard và các script vá/giám sát/sinh tài liệu; trích xuất nội dung văn bản của `TINH_TOAN_THIET_KE_XE_TU_HANH.docx`. Ảnh PNG và sản phẩm build được nhận diện là tài liệu/artifact phụ, không dùng làm bằng chứng nghiệm thu thực tế.

Đã thực hiện:

| Kiểm tra | Kết quả | Giới hạn |
|---|---|---|
| Phân tích cú pháp 28 file Python bằng `ast.parse`, Python 3.12.10 | 28/28 qua; hai cảnh báo chuỗi escape trong script sinh Word | Không xác nhận thư viện ROS đã cài hoặc chương trình chạy được trên Pi |
| `platformio run -e esp32dev` trong thư mục firmware | SUCCESS; Espressif32 7.0.1; RAM 46.284/327.680 byte, flash 859.461/1.310.720 byte | Build tăng dần với cache hiện có; không nạp firmware, không đo hành vi động cơ |
| Chạy các hàm Python được tách bằng AST với state, logger, thời gian và Serial giả | Tái hiện lỗi phân vùng LiDAR, chưa có scan, vận tốc quá lớn, STOP bị ghi đè, hoàn thành giả và phát hiện kẹt sai | Kiểm tra logic cô lập; không thay thế thử nghiệm ROS/robot thật |
| Đối chiếu công thức, cấu hình và tài liệu Word | Có sai khác thông số và khẳng định chưa có dữ liệu gốc chứng minh | Chưa xác minh cơ khí, dòng điện, pin hoặc sai số trên sàn |

Không chạy script vá, script giám sát có lệnh START hoặc script gửi Telegram; không truy cập Pi hay phát lệnh điều khiển xe. Báo cáo này phân tích trạng thái folder, không xác nhận mã đang chạy trên Pi hoặc firmware đang nằm trong ESP32 giống bản lưu ở đây. Không có đặc tả nghiệm thu độc lập trong folder để đối chiếu đầy đủ.

## 3. Cấu trúc và kiến trúc hiện tại

### 3.1. Thành phần trong folder

| Thành phần | Vai trò | Nhận xét |
|---|---|---|
| `robot_stm32_f103/platformio.ini`, `src/`, `include/` | Firmware motor, encoder, PID, odometry, Serial và Wi-Fi | **Thực tế là ESP32/Arduino**, không phải STM32 F103 |
| `agv_unified_brain.py` | Cầu nối ROS/Serial/web, né vật cản phản xạ | Không phát TF; chưa tự cung cấp đủ chuỗi TF cho SLAM |
| `agv_unified_brain_v2_1.py` | Thêm TF, giữ hướng và chế độ quét/chạy SLAM | Đầy đủ hơn bản gốc nhưng còn nhiều lỗi an toàn |
| `agv_master_explorer.py` | FSM khám phá frontier và quay về home | Có chọn frontier; chưa triển khai A*/costmap như mô tả |
| `index_cyberpunk.html`, `index_master_explorer.html` | Radar, bản đồ, telemetry và nút điều khiển | Cần sửa STOP, hiển thị dữ liệu cũ và đồng bộ chế độ |
| `launch_full_system.sh`, `run_brain.sh` | Khởi động hệ thống trên Pi | Đường dẫn cố định, chọn bản Python gốc, thiếu kiểm tra readiness |
| `patch_*.py`, `apply_auto_server.py`, `clean_py.py`, `fix_syntax.py` | Vá các file trên Pi bằng thay chuỗi | Không phải mã runtime thống nhất; kết quả phụ thuộc bản file và thứ tự vá |
| `monitor_and_correct.py`, `live_monitor_v2_1.py` | Cho xe chạy, đọc telemetry, gửi báo cáo và hỏi model | Có tác động điều khiển ngay ở top-level; không phải công cụ chỉ đọc |
| `build_*.py`, `generate_calc_doc.py`, `update_exact_hshop.py`, file Word | Tính toán và sinh tài liệu | Nhiều phiên bản ghi cùng tài liệu, một số nội dung lệch mã hiện tại |
| `update_wifi.py` | Ghi đè toàn bộ `wifi_controller.cpp` | Có thể làm mất sửa đổi mới nếu chạy lại |
| `.pio/`, `.vscode/`, ảnh PNG | Artifact build, cấu hình máy phát triển, ảnh chụp | Không thay cho source, cấu hình deploy hay dữ liệu đo gốc |

Folder hiện không được nhận diện là Git repository khi chạy `git rev-parse`. Chưa thấy README, manifest phụ thuộc Python/ROS, package ROS hoàn chỉnh, cấu hình SLAM/Nav2, bộ test hoặc bộ dữ liệu rosbag trong phạm vi folder.

### 3.2. Luồng điều khiển đang có

    LiDAR C1 -> driver ROS -> /scan -> Python -> quyết định chuyển động
                                        |
                                        +-> dashboard HTTP :8080
    SLAM Toolbox -> /map ----------------+

    Python -> Serial 115200 -> ESP32 -> PID hai bánh -> I2C MKE-M18 -> động cơ
                               ^                         
                               +-- encoder -> odometry -> JSON về Python

    Trình duyệt -> Wi-Fi ESP32 :80 -> bộ xử lý lệnh motor dùng chung

Bản V2.1/explorer phát TF `odom -> base_footprint -> laser`. TF `map -> odom` cần do lớp SLAM/định vị cung cấp. Python hiện có nhiều nguồn phát lệnh: vòng tự hành, HTTP thủ công, chức năng quét; ESP32 còn có web và bài test tự động riêng. Chưa có một bộ phân quyền nguồn lệnh để quyết định nguồn nào được phép điều khiển ở từng thời điểm.

### 3.3. Thông số đang nằm trong mã

| Thông số | Giá trị | Nơi lấy |
|---|---|---|
| Board/framework | `esp32dev`, Arduino | `robot_stm32_f103/platformio.ini`, dòng 8–11 |
| I2C SDA/SCL | GPIO 21/22 | `src/main.cpp`, dòng 15–16 |
| Encoder trái A/B | GPIO 18/19 | `src/main.cpp`, dòng 18–19 |
| Encoder phải A/B | GPIO 25/26 | `src/main.cpp`, dòng 21–22 |
| Driver | Địa chỉ mặc định 0x40; motor A trái, B phải | `include/mke_m18.h`, `src/robot_motor.cpp` |
| Bán kính bánh | 0,0366 m | `include/odometry.h`, dòng 21 |
| Khoảng cách bánh hiệu dụng | 0,1925 m | `include/odometry.h`, dòng 22 |
| Xung trên vòng bánh | 937,2 | `include/encoder.h`, `include/odometry.h` |
| Chu kỳ encoder/PID | 50 ms, 20 Hz | `include/encoder.h`, dòng 11–12 |
| Telemetry ESP32 | 100 ms, 10 Hz | `src/main.cpp`, dòng 24 |
| PID đang dùng | Kp 0,50; Ki 1,50; Kd 0,010; Kf 0,45 | `src/main.cpp`, dòng 41–44 |
| Giới hạn lệnh S/V | ±280 RPM mỗi bánh | `src/main.cpp`, dòng 115–118, 156–159 |
| Pi/ROS theo script | ROS 2 Jazzy, ESP32 `/dev/ttyUSB0`, LiDAR `/dev/ttyUSB1` | Python chính và `launch_full_system.sh` |

Đây là thông số trong source, không phải kết quả đo mới. Khoảng cách cơ khí 0,1875 m và khoảng cách hiệu dụng 0,1925 m có thể khác nhau do hiệu chuẩn; cần ghi rõ ý nghĩa và bằng chứng hiệu chuẩn thay vì tự kết luận giá trị nào sai.

## 4. Ưu điểm

| Ưu điểm | Căn cứ | Lợi ích thực tế |
|---|---|---|
| Phân chia Pi và MCU hợp lý | Pi xử lý ROS/web, ESP32 đóng vòng PID | Giữ được nền tảng để phát triển SLAM và dẫn đường |
| Firmware có các module riêng | Motor, driver, encoder, PID và odometry tách file | Có thể sửa/test từng phần, không cần viết lại tất cả |
| Encoder dùng PCNT phần cứng và giải mã x4 | `encoder.cpp`, dòng 20–68 | Giảm gánh CPU so với đếm xung bằng xử lý cạnh thuần phần mềm |
| PID có feedforward, giới hạn tích phân và đạo hàm theo đo | `pid.c`, dòng 26–90 | Có cấu trúc điều khiển tốc độ thực chất; giảm derivative kick khi đổi setpoint |
| Có động học thuận/nghịch và tích phân midpoint | `odometry.c` | Lệnh V theo m/s, rad/s thuận tiện để kết nối ROS |
| Có STOP reset target và PID, dừng khi khởi động | `main.cpp`, dòng 80–90, 240–243 | Đã có hành vi dừng cơ bản để tiếp tục xây dựng lớp an toàn |
| Telemetry đầy đủ cho chẩn đoán | RPM mục tiêu/thực, PWM, x/y/theta, v/w | Có thể đo PID và hiệu chuẩn bằng log định lượng |
| Có dashboard dùng trình duyệt | Hai file HTML, web ESP32 | Thuận tiện quan sát và điều khiển trong demo |
| Có lựa chọn QoS cảm biến/bản đồ rõ ràng | BEST_EFFORT cho scan, TRANSIENT_LOCAL cho map | Thể hiện đã chú ý đặc tính truyền dữ liệu ROS; vẫn phải kiểm tra tương thích publisher thực tế |
| V2.1 đã bổ sung TF, explorer có FSM | Các lớp ROS tương ứng | Có điểm xuất phát cho bringup và thiết kế chế độ vận hành |
| Build hiện tại thành công | PlatformIO trả SUCCESS | Có nền tảng firmware đang build được trên máy này |

Những ưu điểm trên nói về thiết kế và mã nguồn; chưa chứng minh độ chính xác định vị hay mức an toàn vận hành thực tế.

## 5. Nhược điểm và lỗi cụ thể cần sửa

### F01 — Chưa có timeout lệnh tại ESP32

**Mức độ: P0 — cần sửa trước khi chạy tự hành.**

`src/main.cpp`, hàm `Execute_Robot_Command()` dòng 74 và `loop()` dòng 268: lệnh S/V đặt target; lệnh M đặt PWM. Không có thời điểm hết hạn hoặc kiểm tra mất heartbeat của nguồn lệnh. Nếu Pi treo, tiến trình bị kill, USB đứt hoặc trình duyệt mất kết nối, target cũ có thể tiếp tục được giữ. Heartbeat JavaScript chỉ gửi lại lệnh, không tạo khả năng tự dừng ở bên nhận.

Sửa: quản lý nguồn lệnh đang hoạt động, timestamp của lệnh chuyển động hợp lệ và timeout tại ESP32; hết hạn thì target/PWM về 0, hủy test và vào trạng thái dừng. Chỉ lệnh chuyển động hợp lệ từ nguồn đang nắm quyền mới gia hạn. Watchdog phần mềm của MCU cần được bổ sung nhưng không thay thế timeout lệnh.

### F02 — STOP chưa có ưu tiên và trạng thái khóa đủ mạnh

**Mức độ: P0.** Có ba tình huống độc lập:

- `main.cpp` STOP chỉ dừng motor; không hủy `s_test_state` nằm trong `wifi_controller.cpp`. Test đang chạy có thể gửi V lại ở vòng cập nhật tiếp theo. `/test?act=STOP` có hủy test, nhưng STOP qua Serial hoặc `/cmd` không làm điều đó.
- `emergencyStop()` trong hai dashboard và web ESP32 không xóa timer gửi lệnh đang giữ. Nhịp 150 ms tiếp theo có thể tiếp tục gửi S sau STOP.
- V2.1 chụp `auto_mode` đầu callback rồi `time.sleep()`. Nếu web tắt AUTO trong lúc ngủ, callback vẫn có thể gửi lệnh quay theo snapshot cũ. Giả lập đã tái hiện chuỗi **`V -0.10 0.0 -> STOP -> V 0.0 -0.85`**, dù `auto_mode` đã false. Explorer có cùng kiểu rủi ro trong recovery.

Sửa: phân biệt dừng bình thường với dừng khóa; dừng khóa phải hủy mọi chế độ, mọi timer/queue và chặn lệnh chuyển động đến khi có thao tác ARM rõ ràng. Pi cần arbiter và generation ID/cancellation; firmware phải thực thi quyền ưu tiên cuối cùng. Nút dừng vật lý nên ngắt/khóa công suất motor qua phần cứng phù hợp, để độc lập với web, ROS và I2C.

### F03 — Không kiểm tra độ mới và tính hợp lệ của scan/telemetry

**Mức độ: P0.** Cả ba chương trình Python khởi tạo các vùng bằng 999 cm. Không thấy `last_scan_time`, timeout telemetry hoặc điều kiện chỉ ARM sau khi có dữ liệu hợp lệ. Scan mất hoặc toàn bộ tia invalid có thể bị diễn giải là đường trống; trạng thái SAFE cũng có thể chỉ dựa trên dữ liệu cũ.

Giả lập bật AUTO khi chưa nhận scan cho kết quả:

- Bản gốc: `V 0.10 0.00`.
- V2.1: `V 0.22 0.00`.

Sửa: dùng timestamp monotonic cho thời điểm nhận và kiểm tra stamp của cảm biến; tách UNKNOWN/STALE/INVALID khỏi FREE. Có điều kiện kiểm tra scan hợp lệ theo vùng cần di chuyển, kết nối Serial và độ mới telemetry trước khi phát lệnh. Thiếu dữ liệu phải dừng. Tia `inf` có thể có ý nghĩa khác nhau tùy driver; cần quy tắc dựa trên driver thực tế, không mặc định mọi tia không hữu hạn là đường trống.

### F04 — Phân vùng trái/phải không đúng quy ước LaserScan

**Mức độ: P0.** `scan_cb()` trong cả ba bản gán vùng 68–113° thành `right`; các vùng trái/phải còn lại cũng đảo tương tự. Trong ROS, góc 0 theo +X, góc dương quay ngược chiều kim đồng hồ quanh +Z; +Y là trái. Giả lập tia +90°, 0,25 m được gán thành **`right: 25`** ở cả ba bản. [Nguồn định nghĩa LaserScan](https://raw.githubusercontent.com/ros2/common_interfaces/jazzy/sensor_msgs/msg/LaserScan.msg), [quy ước REP-103](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-0103.rst).

Kết luận này áp dụng khi driver và lắp đặt đúng quy ước ROS; cần kiểm tra frame/yaw LiDAR thực tế. Sửa bằng phép đổi từ frame laser sang frame thân xe và ánh xạ vùng thống nhất; đồng bộ hướng trên radar. Kiểm tra bằng vật cản đặt trước/trái/phải/sau và đối chiếu RViz trước khi cho xe né tự động.

### F05 — Tính ratio né vật cản không giới hạn, có thể phát lệnh rất lớn

**Mức độ: P0.** Bản gốc dòng 220–226; V2.1 dòng 275–283: vào nhánh né vì một vùng chéo gần, nhưng tính ratio chỉ bằng khoảng cách vùng trước. Nếu front=999 cm còn front_right=50 cm, giả lập thu được:

| Bản | Lệnh phát ra |
|---|---|
| `agv_unified_brain.py` | `V 1.43 13.27` |
| `agv_unified_brain_v2_1.py` | `V 0.15 14.98` |

Firmware chặn RPM từng bánh nên không thực hiện nguyên v/w trên, nhưng có thể bão hòa thành chuyển động nhanh hoặc quay mạnh, mất tỷ lệ động học dự kiến. Sửa: dùng khoảng cách hiệu dụng nhất quán với nhánh được kích hoạt, clamp ratio vào [0,1], giới hạn v/w và gia tốc tại Pi; thêm giới hạn vận hành tại ESP32 cho cả V, S và M. Giới hạn ±280 RPM tương đương khoảng 1,07 m/s khi hai bánh cùng tốc độ, quá rộng cho demo ban đầu.

### F06 — Lùi và quay recovery chưa kiểm tra khoảng trống tương ứng

**Mức độ: P1 — phải sửa trước khi bật recovery.** Bản gốc/V2.1 thấy vật cản trước sẽ lùi; explorer dòng 281–289 đọc `b_cm` nhưng không dùng để quyết định lùi. Các đoạn quay tại chỗ cũng chưa kiểm tra vùng quét của toàn thân xe. Explorer lùi 0,15 m/s trong 0,8 s tương đương khoảng **0,12 m lý thuyết**, khác comment “0,3 m”.

Sửa: trước mọi chuyển động lùi phải kiểm tra vùng sau và độ mới dữ liệu; khi quay phải kiểm tra footprint quét. Dùng trạng thái recovery không chặn, có giới hạn quãng đường/thời gian và khả năng bị STOP hủy. Mặc định dừng nếu không xác nhận được đường thoát.

### F07 — Callback chặn và chu kỳ điều khiển bị giả định cố định

**Mức độ: P1.** ROS spin hiện dùng executor mặc định; `time.sleep()` trong callback có thể chặn xử lý scan, telemetry và TF. Recovery explorer ngủ tổng 1,8 s. Trên ESP32, web có `delay(500)` khi lưu Wi-Fi, `delay(300)` giữa bước test; quét I2C nhiều địa chỉ cũng có thể chặn.

`main.cpp` vẫn tính RPM/PID với dt=0,05 s và dùng `last_sample_ms += 50` sau khoảng trễ dài. Một mẫu encoder tích lũy lâu có thể bị chia cho 50 ms, rồi xuất hiện các vòng bắt kịp với rất ít xung. Sai số tốc độ làm PID điều khiển bất thường. Đọc và clear PCNT là hai thao tác riêng, có cửa sổ mất xung nhỏ; đây là rủi ro cần đo, chưa phải sai số đã xác nhận.

Sửa: tách vòng motor/timeout thành tác vụ định kỳ ưu tiên phù hợp; dùng dt thực cho đo tốc độ, báo trễ và không chạy hàng loạt bước PID với dt giả. Mọi chờ chuyển trạng thái dùng deadline, không dùng sleep chặn. Không quét bus/lưu cấu hình trong lúc xe được ARM. Chỉ đổi 20 Hz lên 50–100 Hz sau khi đo được khả năng lấy mẫu và tune lại PID.

### F08 — RESET encoder/odometry không đồng bộ

**Mức độ: P1.** `main.cpp` dòng 98–102 xóa tổng xung; `Odometry_Reset()` trong `odometry.c` dòng 36 chỉ xóa pose/vận tốc, không cập nhật `prev_left_count`/`prev_right_count`. Mẫu tiếp theo lấy tổng mới bằng 0 trừ tổng cũ nên tạo chuyển động giả.

Ví dụ suy từ source: sau khoảng 4.075 xung mỗi bánh, RESET tạo delta khoảng −4.075 xung, tương đương gần **−1 m** ở lần cập nhật sau. Sửa: thực hiện reset cùng snapshot encoder trong trạng thái dừng, cập nhật baseline và bỏ mẫu đang dở. Khi SLAM đang chạy, không reset odom tùy tiện làm gián đoạn TF.

### F09 — Explorer trộn tọa độ map với odom, chưa có tìm đường thực sự

**Mức độ: P1.** `map_cb()` lấy OccupancyGrid trong frame bản đồ, nhưng `find_best_frontier()` và FSM dùng `robot_x/y/th` nhận trực tiếp từ encoder, tức pose trong odom. Không có `lookup_transform()` đổi pose sang map. Sau khi SLAM hiệu chỉnh `map -> odom`, hướng tới frontier/home có thể sai. Dashboard explorer cũng vẽ pose odom trực tiếp lên map.

Đầu file ghi A*, costmap, clustering, nhưng thực tế chỉ chọn ô frontier gần nhất rồi lái thẳng theo góc. `heapq` được import nhưng không dùng; `current_path` không được tính/theo dõi. Kiểm tra vài ô lân cận không thay cho footprint/inflation hoặc kiểm tra đường đi. Home cũng được tiếp cận bằng góc trực tiếp; `home_th` lưu nhưng chưa dùng để hoàn tất hướng đỗ.

Sửa: nhận pose trong map qua TF, lưu home trong frame đó và gửi mục tiêu cho planner/controller có costmap. Nếu giữ A* tự viết cho mục đích học tập, phải bổ sung inflation, kiểm tra reachable, đường đi, bám đường và replanning; không thể chỉ thêm tên “A*” hoặc chỉnh gain.

### F10 — Có thể báo hoàn thành khi chưa quét phòng; phát hiện kẹt sai

**Mức độ: P1.** Explorer đọc `has_map` tại dòng 245 nhưng không dùng làm điều kiện chặn. `find_best_frontier()` trả None khi chưa có map, khi không thấy frontier trong vùng lọc hoặc khi bỏ sót do nhảy bước 4 ô. FSM đều diễn giải thành chuyển về home.

Giả lập EXPLORING với map trống, home tại pose mặc định: sau hai lần gọi FSM, trạng thái thành **COMPLETED**. Vì vậy không thấy frontier không đồng nghĩa đã khám phá 100% phòng. Chỉ số phần trăm hiện tính theo hình chữ nhật OccupancyGrid thay đổi theo thời gian, không phải coverage của một vùng phòng xác định.

Ngoài ra, kiểm tra kẹt đòi di chuyển ≥4 cm trong mỗi tick 0,2 s. Xe đi 0,18 m/s chỉ dịch 3,6 cm/tick, vẫn bị tính là kẹt; sau 8 tick giả lập đã kích hoạt lùi recovery dù xe đang đi.

Sửa: trạng thái WAITING_FOR_MAP/DATA riêng; phân biệt không có dữ liệu, không tìm thấy mục tiêu tạm thời, không reachable và hoàn thành. Đánh giá tiến độ trên vùng nhiệm vụ xác định. Phát hiện kẹt theo cửa sổ thời gian, vận tốc được yêu cầu và tiến bộ tới mục tiêu; không dùng ngưỡng cố định cho mỗi tick.

### F11 — Tích hợp SLAM và launcher chưa đầy đủ để tái triển khai

**Mức độ: P1.** `launch_full_system.sh` dòng 22 và `run_brain.sh` đều chọn `agv_unified_brain.py` gốc; bản này không phát TF. V2.1/explorer có `odom -> base_footprint -> laser`, nhưng folder chưa có YAML cấu hình SLAM để xác nhận `base_frame` phù hợp, hoặc driver xuất đúng `frame_id=laser`.

Ba chương trình chưa publish `nav_msgs/Odometry` và chưa nhận `cmd_vel` làm interface dẫn đường. Việc thiếu `/odom` không tự nó chứng minh SLAM không chạy nếu TF đã đủ, nhưng là khoảng trống cần bổ sung khi tích hợp Nav2 và các node sử dụng odometry. TF hiện đóng dấu thời gian mới lên pose lưu gần nhất mà không kiểm tra telemetry cũ. Transform cố định của laser đang phát như dynamic TF và có thể trùng publisher từ driver.

Launcher dùng sleep cố định thay cho readiness, không tạo/kiểm tra thư mục logs, không chặn chạy trùng driver/SLAM, và dùng `pkill -9` bỏ qua cleanup STOP. Sửa: có một bringup ROS, tham số cấu hình rõ ràng, một publisher cho mỗi TF, healthcheck và supervisor; không dùng kill cưỡng bức làm quy trình bình thường.

### F12 — API và Serial thiếu xác thực, kiểm tra lệnh và phản hồi thực thi

**Mức độ: P1.** HTTP trên Pi bind `0.0.0.0:8080`, CORS `*`, đổi trạng thái bằng GET; web ESP32 có giao diện điều khiển tương tự. Chưa thấy xác thực hoặc phân quyền. Mọi client có đường mạng tới server có thể gửi START/S/V/M/TUNING/RESET qua các route hiện có. CORS không phải cơ chế xác thực.

`/api/cmd` trả ok ngay cả khi Serial không mở/ghi thất bại hoặc chưa nhận ACK. Serial được ghi từ ROS thread và HTTP thread nhưng chưa có queue/arbiter thống nhất. Pi không tự kết nối lại sau lỗi mở cổng. Firmware chưa kiểm tra `isfinite()` với số nhập; NaN có thể vượt qua các phép so sánh giới hạn rồi đi vào phép tính.

Sửa: allowlist lệnh theo mode, validate số hữu hạn/dải/tham số, tách endpoint vận hành khỏi tuning, queue một nơi ghi Serial, timeout ghi/ACK và status lỗi trung thực. Giới hạn mạng điều khiển, thêm cơ chế xác thực phù hợp; nếu truy cập ngoài mạng riêng thì dùng lớp bảo vệ đường truyền/truy cập. Sau reconnect, mặc định DISARMED và yêu cầu ARM lại.

### F13 — Lỗi I2C chưa được nâng thành trạng thái lỗi hệ thống

**Mức độ: P1.** Driver trả bool và có fault flag, nhưng `robot_motor.cpp` bỏ kết quả khi set motor/STOP; setup bỏ kết quả khởi tạo. Một lần ghi thành công có thể xóa flag dù lần ghi khác vừa lỗi. `MKE_M18_Scan()` dòng 139 chọn thiết bị ACK đầu tiên làm địa chỉ driver, không xác nhận đúng MKE-M18.

Sửa: cấu hình địa chỉ driver rõ ràng, xác nhận danh tính/giao thức theo module; scan chỉ phục vụ chẩn đoán. Lỗi truyền điều khiển phải ghi log, latch FAULT, khóa nguồn lệnh và thử dừng theo chính sách có giới hạn. Không thể bảo đảm motor đã ngừng chỉ vì đã gọi STOP nếu bus hỏng; cần đường dừng công suất độc lập và xác minh khả năng timeout của driver.

### F14 — Script vá, giám sát và tài liệu gây khó tái lập kết quả

**Mức độ: P1 cho script tác động vận hành; P2 cho tổ chức mã/tài liệu.**

- Nhiều patch sửa file tuyệt đối trên `/home/khangho/...` bằng `str.replace()`. Chuỗi không khớp vẫn có thể in SUCCESS; qua cú pháp không chứng minh tính năng đã được chèn. Khối `old_move` của `patch_choke_point.py` không khớp explorer hiện có, cho thấy phụ thuộc thứ tự/bản vá trước.
- `update_wifi.py` ghi đè toàn bộ firmware web bằng một bản nhúng cũ; `restore_clean.py` đọc file nhưng chưa có thao tác ghi để restore như tên gọi.
- Hai script monitor phát START khi chạy, STOP chỉ nằm ở cuối luồng bình thường và không có `finally` bảo đảm dừng khi ngắt/lỗi. Chúng gửi Telegram và hỏi model, nhưng không có đoạn áp dụng gain mới; tên “correct” và lời báo “điều chỉnh trực tiếp” không chứng minh đã tune.
- `patch_hardware_deadband.py` nâng mọi RPM nhỏ lên tối thiểu 38 RPM và dùng L=0,1875 m. Với R hiện có, 38 RPM tương đương khoảng 0,146 m/s mỗi bánh. Cách này đổi vận tốc/quỹ đạo mong muốn, không phải chỉ bù PWM vượt ma sát; cần xử lý feedforward/deadzone trong vòng motor và đo thực tế.
- File Word ghi dt=20 ms/50 Hz, L=0,1875 m, dải Kp=12–18, trong khi firmware dt=50 ms/20 Hz, L hiệu dụng=0,1925 m và Kp=0,50 theo RPM. Không được chép gain giữa các đơn vị/chu kỳ điều khiển khác nhau.
- Word có ví dụ chạy 1 m nhưng “S_thuc=9187.5 mm”, tăng L từ 187,5 mm lên 86 mm; đây là mâu thuẫn nội dung cần sửa. Khẳng định sai số ±2–5 mm, “triệt tiêu hoàn toàn”, an toàn/đạt chuẩn chưa có log đo gốc hoặc quy trình độc lập trong folder để kiểm chứng.

Sửa: quản lý một bộ source được đánh phiên bản, đưa patch cũ vào archive; không dùng patch thay chuỗi làm quy trình deploy. Tách monitor chỉ đọc khỏi thao tác chạy, có timeout/finally và chế độ dry-run. Báo cáo kết quả phải sinh từ log/rosbag và bảng đo thật, không từ lời mô tả hoặc kết luận của model.

## 6. Ma trận rủi ro vận hành

Mức xác suất dưới đây là đánh giá định tính từ mã, không phải thống kê tần suất lỗi thực nghiệm. P0 cần xử lý trước khi chạy tự động; P1 phải hoàn thành trước khi nghiệm thu tính năng liên quan; P2 là chất lượng, bảo trì và khả năng tái lập.

| Rủi ro | Tình huống kích hoạt | Hậu quả | Khả năng theo thiết kế hiện tại | Ưu tiên/biện pháp |
|---|---|---|---|---|
| Xe giữ chuyển động khi nguồn lệnh mất | USB/mạng/Pi/process lỗi | Va chạm | Dễ xảy ra nếu mất liên lạc khi đang chạy | P0: F01, timeout tại MCU và dừng vật lý |
| Dừng rồi tự chạy lại | Timer giữ phím, callback cũ, test chưa hủy | Mất kiểm soát dừng | Đã tái hiện logic callback | P0: F02, khóa dừng và arbiter |
| Chạy với scan cũ/chưa có | LiDAR chưa khởi động, toàn tia invalid hoặc ngừng phát | Không phát hiện vật cản | Đã tái hiện khi chưa có scan | P0: F03 |
| Né sai hướng/quay mạnh | Trái/phải đảo hoặc ratio ngoài dải | Va tường/sườn xe | Đã tái hiện logic | P0: F04–F05 |
| Va phía sau/cạnh thân | Recovery lùi/quay mà không kiểm tra footprint | Va chạm | Phụ thuộc môi trường | P1: F06, kiểm tra theo hướng chuyển động |
| Định vị/đường về sai | SLAM loop closure, trượt bánh, reset | Đi sai mục tiêu, không về được | Cao khi chạy lâu hoặc có hiệu chỉnh bản đồ | P1: F08–F09 |
| Báo hoàn thành sai, recovery liên tục | Chưa có map hoặc đi chậm dưới 0,20 m/s | Demo không đáng tin, quét thiếu | Đã tái hiện logic | P1: F10 |
| STOP không đến được driver | I2C hỏng hoặc chọn sai slave | Motor có thể giữ trạng thái cũ, tùy driver | Chưa đo phần cứng | P1: F13 và đường ngắt công suất độc lập |
| Điều khiển ngoài ý muốn | Client khác truy cập API | START/tuning/reset trái ý người vận hành | Phụ thuộc phạm vi mạng | P1: F12 |
| Sụt nguồn, nóng driver, LiDAR bỏ sót vật thấp | Motor khởi động/kẹt, dây yếu, vật ngoài mặt quét | Reset hoặc va chạm | Chưa có dữ liệu đo | P1: kiểm tra nguồn/dòng/nhiệt và giới hạn môi trường thử |
| Deploy sai phiên bản | Copy nhầm brain, USB đổi thứ tự, patch không khớp | Map không chạy, serial tranh chấp | Cao nếu dùng nguyên quy trình hiện tại | P1: F11–F14 |
| Kết quả nghiệm thu không đáng tin | Dựa ảnh chụp hoặc lời “an toàn 100%” | Đánh giá sai khả năng hệ thống | Đã thấy khẳng định thiếu dữ liệu gốc | P2: lưu log, phương pháp đo và phiên bản |

Các thông số dòng, điện áp và thời lượng pin trong Word chưa được xác minh trong lần đánh giá này. Cần kiểm tra đúng SKU Pi, LiDAR, driver, UPS/cell pin và sơ đồ cấp nguồn; không dùng thông số ghi trong tài liệu làm cam kết công suất hay thời lượng.

## 7. Chọn phương án theo mục tiêu

| Mục tiêu | Phương án phù hợp | Điều kiện |
|---|---|---|
| Đồ án/demo thủ công và né vật cản trong phòng trống | Giữ PID ESP32 và brain V2.1 đã sửa; chưa cần toàn bộ Nav2 | Hoàn thành P0, nghiệm thu manual, dữ liệu mới, tốc độ thấp |
| Tạo bản đồ để quan sát/báo cáo | Điều khiển thủ công có giám sát + SLAM Toolbox | TF đúng, odometry ổn, log/rosbag và map lưu được |
| Đi tới điểm, quay về home, khám phá nhiều khu vực | Giữ ESP32, thêm bridge ROS chuẩn + Nav2 + frontier goal selector | `/odom`, TF, footprint, costmap, planner/controller và recovery qua kiểm thử |
| Vận hành lâu, có người/vật động/tải hàng | Cần yêu cầu kỹ thuật và xác minh hệ thống riêng | Folder hiện chưa đủ căn cứ nghiệm thu cho mức sử dụng này |

**Đề xuất mặc định:** hoàn thành hai mục tiêu đầu để có một demo đáng tin, sau đó mới mở chức năng tự khám phá. Không tiếp tục tăng tốc hoặc chồng thêm patch để chữa triệu chứng né vật cản.

## 8. Kiến trúc đề xuất

    Dashboard / teleop / frontier selector
                   |
                   v
          Bộ quản lý mode và quyền điều khiển
                   |
          Planner/controller (Nav2 khi cần)
                   |
             Giới hạn vận tốc/gia tốc
                   |
        Kiểm tra va chạm + độ mới cảm biến
                   |
          Bridge ROS <-> Serial duy nhất
                   |
          ESP32: ARM/STOP/timeout/FAULT
                   |
              PID -> driver -> motor

Bridge phải phát `/odom`, TF động và telemetry có timestamp; nhận topic lệnh vận tốc đã qua quản lý quyền/kiểm tra. Chọn `Twist` hay `TwistStamped` theo cấu hình stack Jazzy cụ thể và dùng nhất quán; không dựa tên topic để giả định loại message.

Chuỗi frame có thể chọn:

    map -> odom -> base_footprint -> base_link -> laser

`base_link` nên đặt theo một mốc thân xe rõ ràng, liên hệ với tâm trục dẫn động. Laser có TF tĩnh dựa trên đo lắp đặt, không lấy mặc định 5 cm/12 cm nếu chưa đo. Có thể dùng `base_footprint` làm base frame trực tiếp nếu cấu hình đồng bộ toàn stack; tên frame không tự quyết định hệ thống đúng/sai. Mỗi transform chỉ có một nguồn phát.

FSM đề xuất: DISARMED, MANUAL, MAPPING, AUTO, ESTOP, FAULT. Chuyển mode hủy command cũ; ESTOP/FAULT khóa chuyển động. AUTO chỉ được vào khi scan, telemetry, TF và các thành phần cần thiết hợp lệ. Khi về home, dùng pose trong map và tiêu chí vị trí/hướng đã định nghĩa.

Nav2 Collision Monitor, Velocity Smoother và costmap là công cụ bổ sung cho lớp Pi, không thay thế timeout ESP32 hoặc nút dừng vật lý. Cần xem đúng cấu hình/khả năng phiên bản Jazzy trước khi tích hợp.

## 9. Lộ trình triển khai cụ thể

### Giai đoạn 0 — Chuẩn hóa bản triển khai

Đầu ra: một bộ source được quản lý phiên bản, một entrypoint, cấu hình có thể tái tạo.

- Lưu bản hiện tại, tạo Git repository hoặc đưa vào repo chính; thêm README và hướng dẫn build/run.
- Đổi tên thư mục firmware thành tên ESP32 ở lần tổ chức mã riêng; không đổi tên đồng thời với hiệu chuẩn để tránh khó đối chiếu.
- Chọn V2.1 làm baseline sửa, ghép thay đổi cần thiết bằng diff có kiểm tra; chuyển patch/monitor cũ sang archive hoặc tools với hướng dẫn rõ.
- Pin PlatformIO theo phiên bản vừa build được: `platform = espressif32@7.0.1`; lưu phiên bản framework/toolchain và Python/ROS. Thử build sạch trong môi trường mới trước khi gọi là tái lập được.
- Thay `/home/khangho/...`, tên cổng USB, HTML path và ngưỡng bằng tham số/config.

Cấu trúc đề xuất, chưa phải cấu trúc đã được tạo:

    firmware/esp32_agv/
    ros2_ws/src/agv_bridge/
    ros2_ws/src/agv_bringup/launch/
    ros2_ws/src/agv_bringup/config/
    ros2_ws/src/agv_exploration/
    web/
    tools/
    docs/
    tests/

### Giai đoạn 1 — Dừng và quyền điều khiển

Đầu ra: F01–F05 được sửa, mọi nguồn lệnh tuân thủ mode.

- Thêm ARM/DISARM, timeout lệnh và fault latch ở ESP32; STOP khóa hủy cả test và các nguồn lệnh khác.
- Sửa timer web: STOP xóa command/timer; xử lý mất focus/visibility; trạng thái trên màn hình phải lấy từ phản hồi thật.
- Queue Serial một nơi ghi, dùng generation/cancellation để lệnh cũ không chạy sau STOP.
- Thêm timeout scan/telemetry, kiểm tra finite, clamp ratio/v/w, giới hạn S/M và gia tốc.
- Sửa trái/phải theo TF; chuyển recovery sang FSM không sleep và kiểm tra phía sau/footprint.
- Xác nhận nút dừng phần cứng, nguồn motor và đường khóa công suất.

Có thể bắt đầu thử timeout khoảng 300 ms khi chu kỳ gửi chuyển động 100 ms và timeout scan/telemetry khoảng 300–500 ms với dữ liệu 10 Hz. **Đây là giá trị khởi điểm để đo và điều chỉnh, không phải ngưỡng an toàn đã được xác nhận.** Chúng phải phù hợp jitter thực tế và khoảng dừng; giảm tốc nếu phải kéo dài timeout.

### Giai đoạn 2 — Kiểm tra phần cứng, PID và odometry

Đầu ra: tham số motor/encoder/hình học có bảng đo lặp lại.

1. Kiểm tra pinout theo bảng ở mục 3.3, chung GND và mức điện áp encoder/I2C phù hợp ESP32; không suy từ pull-up nội rằng encoder ngoài chắc chắn an toàn điện áp.
2. Kiểm tra điện áp/dòng khi motor khởi động và kẹt có giới hạn; tách/thiết kế nhánh cấp nguồn Pi và motor phù hợp phần cứng thật.
3. Khi bánh được nhấc khỏi sàn, kiểm tra từng bánh, dấu motor và encoder, STOP và mất kết nối. Chỉ thử trên sàn sau khi điều kiện dừng đạt.
4. Sửa RESET và dt; đo step response ở nhiều RPM trước khi tune. Feedforward/PID theo từng bánh nếu chênh lệch rõ; không áp dải gain trong Word trực tiếp.
5. Đo số xung qua nhiều vòng bánh để xác nhận tỷ số encoder; đo bán kính hiệu dụng từng bánh và wheelbase hiệu dụng bằng các lượt thẳng/quay có đo ngoài.
6. Đo nhiều lượt chạy thẳng, quay 90°/360° và hình vuông kích thước phù hợp khu thử; lưu mean, độ phân tán, sai lệch hướng và mức pin/tải.

Test quay 360° trong `wifi_controller.cpp` hiện dùng góc chuẩn hóa gần góc ban đầu cùng điều kiện tối thiểu 1 s; chưa xác minh đã hoàn tất một vòng khi bánh bị kẹt/trượt. Nên dùng tổng góc quay liên tục và kiểm tra tiến độ/timeout. Quét “18 giây x 0,35 rad/s” cũng chỉ là tính theo thời gian yêu cầu, không đo vòng quay thực tế.

### Giai đoạn 3 — Bringup ROS/SLAM có thể lặp lại

Đầu ra: scan, odom, TF và map hoạt động trên cấu hình Pi đã xác nhận.

- Xác nhận model Pi, RAM, hệ điều hành và driver LiDAR thật. Dùng ROS 2 Jazzy trên nền tảng được hỗ trợ, tham khảo tài liệu chính thức ở mục 12.
- Cài các gói ROS/driver và `pyserial` theo manifest; folder chưa chứa workspace driver hoặc các module avoidance cũ được script tham chiếu.
- Dùng `/dev/serial/by-id/` hoặc udev alias cho ESP32/LiDAR; không cố định thứ tự ttyUSB. Kiểm tra baud LiDAR từ launch/driver đúng C1, không lấy baud ESP32 áp sang LiDAR.
- Bridge mở cổng duy nhất, phát `nav_msgs/Odometry` với pose/twist/covariance và timestamp, TF động; TF laser dùng static broadcaster/URDF.
- Ghi YAML SLAM: frame map/odom/base/scan đúng source thực tế, resolution và tham số tốc độ xử lý phù hợp Pi. Kiểm tra không trùng TF laser với driver.
- Khi dùng launch async SLAM trên robot thật, truyền rõ `use_sim_time:=false` và `slam_params_file:=<YAML đã kiểm tra>`; launch upstream Jazzy có mặc định sim-time true. Không phụ thuộc mặc định khi không có `/clock`. [Launch chính thức](https://raw.githubusercontent.com/SteveMacenski/slam_toolbox/jazzy/launch/online_async_launch.py).
- Bringup theo readiness: bridge/odom và driver/scan hợp lệ, sau đó SLAM/map; web giám sát có thể lên sớm nhưng khóa ARM khi hệ thống chưa đủ điều kiện.
- Sau cùng dùng ROS launch và systemd để start/stop/log; shutdown gửi STOP rồi đóng Serial. Khi service restart, xe luôn DISARMED.

Các lệnh chẩn đoán chạy trên Pi sau khi đã triển khai cấu hình và source sửa:

    source /opt/ros/jazzy/setup.bash
    source ~/agv_ws/install/setup.bash
    ros2 topic hz /scan
    ros2 topic hz /odom
    ros2 run tf2_ros tf2_echo odom base_footprint
    ros2 run tf2_ros tf2_echo base_footprint laser
    ros2 run tf2_ros tf2_echo map base_footprint
    ros2 topic echo /map --once

`~/agv_ws` là đường dẫn triển khai đề xuất, chưa có trong folder hiện tại. Kiểm tra interface và tên frame theo cấu hình đã chọn; nếu thêm `base_link`, điều chỉnh phép kiểm tra TF tương ứng.

### Giai đoạn 4 — Demo SLAM/né vật cản có giám sát

Đầu ra: demo ổn định, dữ liệu nghiệm thu đủ để biết giới hạn.

- Bắt đầu khoảng 0,08–0,12 m/s trong khu thử có người giám sát; đây là dải thử ban đầu, không cam kết an toàn chỉ từ tốc độ. Tăng sau khi đo PID và dừng đạt.
- Lập bản đồ bằng điều khiển thủ công có deadman và mọi giới hạn dừng; chưa dùng explorer để đồng thời kiểm chứng cả SLAM lẫn dẫn đường.
- Thử mất LiDAR/USB/mạng/process và STOP trong mọi chế độ. Đo độ trễ từ sự kiện đến tốc độ thực về 0, không chỉ đến lúc gửi chuỗi STOP.
- Lưu map và rosbag, đo đường đi so với mốc trên sàn; kiểm tra khi đi lại một vòng có loop closure.
- Sửa dashboard để hiển thị age dữ liệu, FAULT, phiên bản và mode thật. Cyberpunk hiện lấy map khi đổi tab, chưa refresh map định kỳ; explorer tải cả map 5 Hz và vẽ từng ô mỗi animation frame, cần giảm theo tốc độ cập nhật/map version.

### Giai đoạn 5 — Dẫn đường và khám phá phòng

Chỉ triển khai khi các giai đoạn trên đạt tiêu chí.

- Cấu hình Nav2 với footprint đo thật, inflation theo độ hở và sai số, global/local costmap, planner, controller, smoother, collision monitor và recovery phù hợp.
- Kiểm tra đi đến vài goal tĩnh và quay về home trong frame map trước khi thêm frontier.
- Frontier nên gom cụm, chọn mục tiêu có thể tiếp cận, dùng thông tin đường đi/chi phí, giữ goal đủ lâu, blacklist mục tiêu thất bại và có điều kiện kết thúc riêng.
- Gửi goal qua action dẫn đường, theo dõi feedback/result; không phát V trực tiếp từ frontier song song với controller.
- Nghiệm thu ở phòng đơn giản, cửa hẹp và nhiều phòng theo từng mức. Không bật mọi tính năng đồng thời khi chưa tách được nguyên nhân lỗi.

## 10. Xác định ngưỡng dừng và tiêu chí nghiệm thu

### 10.1. Ngưỡng dừng phải dựa trên phép đo

Công thức khởi điểm:

    d_an_toan = v * t_tre + v² / (2 * a_ham) + d_du_phong

Nếu khoảng cách LiDAR đo từ tâm laser, còn phải tính phần thân xe nhô theo hướng chuyển động và hình học footprint. Khi quay/lùi, dùng vùng kiểm tra tương ứng, không dùng duy nhất khoảng cách phía trước.

Ví dụ minh họa, **chưa phải kết quả đo của xe**: v=0,12 m/s, t_trễ=0,30 s, a_hãm=0,30 m/s², đệm=0,10 m thì phần khoảng dừng tính từ mốc chuyển động là khoảng 0,16 m, trước khi cộng phần thân nhô và sai số cảm biến. `a_ham` phải đo trong điều kiện tải/sàn/pin thực tế; lệnh PWM=0 hoặc STOP không tự chứng minh hãm đạt mức giả định.

Tài liệu Word giả định t_trễ=50 ms trong khi callback có thể ngủ đến 1,8 s và firmware có chờ web/bus. Do đó không dùng nguyên ngưỡng 38–40 cm trong tài liệu làm bảo đảm hiện tại.

### 10.2. Các bài kiểm tra bắt buộc

Các giá trị dung sai là mục tiêu ban đầu cho prototype, cần chốt theo nhiệm vụ thật trước nghiệm thu.

| Bài kiểm tra | Điều kiện đạt đề xuất |
|---|---|
| Mất nguồn lệnh/Serial/process | MCU hết hạn lệnh, motor dừng trong ngân sách thời gian/quãng đường đã đo; không tự ARM lại |
| STOP khi giữ phím/test/AUTO/recovery/SLAM spin | Không xuất hiện lệnh chuyển động có hiệu lực sau STOP khóa; cần ARM mới được chạy |
| Chưa có scan, scan cũ, toàn invalid, telemetry cũ | Khóa AUTO hoặc vào dừng/FAULT; UI hiển thị đúng lý do |
| Vật cản trước/trái/phải/sau | Các vùng đúng vị trí vật; né đúng hướng, lùi/quay chỉ khi đủ khoảng trống |
| Nhánh né với front=999 và vùng chéo gần | v/w hữu hạn, trong dải và đúng chiều; không bão hòa bất ngờ |
| RESET sau khi đã di chuyển | Không xuất hiện bước nhảy pose do baseline encoder; reset bị chặn khi không phù hợp mode |
| Điều khiển tốc độ | Sai số xác lập, overshoot và thời gian ổn định nằm trong dải đã chốt; không dùng một lượt quan sát để kết luận |
| Chạy thẳng 1 m, tối thiểu 10 lượt | Mục tiêu ban đầu sai số quãng đường ≤3–5%; ghi riêng sai lệch ngang/hướng và độ phân tán |
| Quay góc đo ngoài | Mục tiêu ban đầu ≤5° cho một lượt 360°; đánh giá cả hai chiều và nhiều lượt |
| SLAM | TF liên tục, map hợp lý theo mốc ngoài, có log và bản map; không suy chất lượng chỉ từ kích thước lưới |
| Explorer chưa có map hoặc chưa có frontier tạm thời | WAITING/retry/failed đúng ngữ nghĩa, không báo COMPLETED giả |
| Phát hiện kẹt | Không recovery khi xe vẫn tiến theo vận tốc được yêu cầu; phát hiện được cản thực |
| Home/goal navigation | Đi theo đường khả thi, đạt dung sai vị trí/hướng đã chốt trong frame map; ghi tỷ lệ thành công nhiều lượt |
| Lỗi I2C/khởi động lại service | FAULT rõ ràng, đường dừng phần cứng còn hiệu lực, không chạy lại từ lệnh cũ |
| Tải web/nhật ký | Dashboard không gây trễ vòng điều khiển; log ghi được nguyên nhân dừng và dữ liệu gốc |

## 11. Thứ tự công việc và đầu ra cần bàn giao

| Đợt | Việc chính | Đầu ra để chuyển bước |
|---|---|---|
| 1 | F01–F05: timeout, STOP khóa, freshness, trái/phải, clamp | Test logic và bài mất lệnh/STOP trên bánh nhấc đạt |
| 2 | F06–F08, F13: recovery, dt/reset, lỗi driver; kiểm tra nguồn | Bảng đo PID, hình học, dừng và fault; source firmware được đánh phiên bản |
| 3 | F11–F12, F14: bridge ROS, cấu hình, launcher, API và bản source chuẩn | Bringup Pi có thể tái tạo, manifest/cấu hình và log khởi động |
| 4 | SLAM manual, dashboard và bộ dữ liệu đo | Map/rosbag, bảng sai số, giới hạn môi trường và hướng dẫn vận hành |
| 5 | F09–F10: Nav2, frontier, home và hoàn thành nhiệm vụ | Bài dẫn đường/exploration nhiều lượt đạt tiêu chí riêng |

Không đưa ước tính lịch cứng khi chưa biết model Pi, phiên bản trên robot, sơ đồ điện và mục tiêu đồ án. Có thể giữ phạm vi ở đợt 4 nếu nhiệm vụ chỉ cần điều khiển, tránh vật cản và lập bản đồ; đợt 5 là một bước phát triển riêng.

Bộ bàn giao nên gồm source tag/commit, firmware đúng bản, manifest phụ thuộc, cấu hình geometry/PID/frame/ports, hướng dẫn build/run/stop, log/rosbag và bảng kết quả đo. Sửa tài liệu Word sau khi chốt thông số đo, phân biệt giá trị thiết kế, giá trị hiệu chuẩn và kết quả thực nghiệm.

## 12. Nguồn đối chiếu kỹ thuật

Mã local là bằng chứng cho các lỗi được nêu; số dòng trong báo cáo ứng với bản source tại thời điểm đánh giá. Các nguồn bên ngoài phục vụ kiểm tra quy ước và chọn phương án triển khai, không chứng minh robot đã đạt kết quả thực nghiệm.

1. [Định nghĩa LaserScan, nhánh Jazzy](https://raw.githubusercontent.com/ros2/common_interfaces/jazzy/sensor_msgs/msg/LaserScan.msg): góc, frame, timestamp và dải đo.
2. [REP-103, kho chính thức](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-0103.rst): SI, trục thân xe và chiều yaw.
3. [REP-2000, bảng nền tảng ROS](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-2000.rst) và [hướng dẫn Raspberry Pi cho Jazzy](https://raw.githubusercontent.com/ros2/ros2_documentation/jazzy/source/How-To-Guides/Installing-on-Raspberry-Pi.rst): Ubuntu 24.04 arm64 là lựa chọn binary phù hợp khi model Pi được hỗ trợ; Jazzy được hỗ trợ đến tháng 5/2029. Tier hỗ trợ không chứng minh hiệu năng của một model Pi cụ thể.
4. [README SLAM Toolbox Jazzy](https://raw.githubusercontent.com/SteveMacenski/slam_toolbox/jazzy/README.md), [YAML async mẫu](https://raw.githubusercontent.com/SteveMacenski/slam_toolbox/jazzy/config/mapper_params_online_async.yaml) và [launch async](https://raw.githubusercontent.com/SteveMacenski/slam_toolbox/jazzy/launch/online_async_launch.py): đầu vào scan/TF, frame, thời gian và cách truyền cấu hình.
5. [Launch RPLIDAR C1 của Slamtec](https://raw.githubusercontent.com/Slamtec/sllidar_ros2/main/launch/sllidar_c1_launch.py): cấu hình driver C1 upstream có baud 460800 và frame laser; cần đối chiếu phiên bản thực cài trên Pi.
6. [Thiết lập TF Nav2 Jazzy](https://docs.nav2.org/jazzy/configuration_and_development/first_time_robot_setup_guide/transformation/setup_transforms/) và [định nghĩa Odometry Jazzy](https://raw.githubusercontent.com/ros2/common_interfaces/jazzy/nav_msgs/msg/Odometry.msg): quan hệ frame và dữ liệu pose/twist.
7. [Footprint Nav2 Jazzy](https://docs.nav2.org/jazzy/configuration_and_development/first_time_robot_setup_guide/footprint/setup_footprint/) và [Inflation Layer](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/inflation/): hình dạng xe, vùng chi phí và giới hạn của cách xấp xỉ.
8. [Collision Monitor Jazzy](https://raw.githubusercontent.com/ros-navigation/navigation2/jazzy/nav2_collision_monitor/README.md), [hướng dẫn tích hợp](https://docs.nav2.org/jazzy/tutorials/general_tutorials/using_collision_monitor/using_collision_monitor/) và [cấu hình node](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/collision_monitor/configuring_collision_monitor_node/): đặt monitor cuối chuỗi vận tốc và bật timeout cảm biến; lớp này không phải hệ thống dừng có chứng nhận an toàn.
9. [Velocity Smoother Jazzy](https://raw.githubusercontent.com/ros-navigation/navigation2/jazzy/nav2_velocity_smoother/README.md) và [tham số Jazzy](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/configuring_velocity_smoother/): giới hạn vận tốc/gia tốc; CLOSED_LOOP phụ thuộc odometry mới, đúng; thống nhất loại message lệnh.
10. [Hướng dẫn chuyển Arduino-ESP32 2.x sang 3.x](https://docs.espressif.com/projects/arduino-esp32/en/latest/migration_guides/2.x_to_3.0.html) và [ESP-IDF 5.0 PCNT migration](https://docs.espressif.com/projects/esp-idf/en/v5.0/esp32/migration-guides/release-5.x/peripherals.html#pulse-counter-driver): API PCNT legacy cần lưu ý khi nâng toolchain; không kết luận không build được chỉ vì deprecated. Báo cáo pin 7.0.1 dựa trên build thực tế tại máy này, không tự đổi sang phiên bản mẫu khác.

## 12.1. Mục tiêu người dùng xác nhận sau đánh giá

Thông tin mới nhất người dùng đính chính ngày 01/10/2026: **xe đang đặt trên sàn; mục tiêu cuối là khám phá toàn phòng rồi quay về gốc**. Thông tin này thay thế câu trả lời trước đó về việc kê bánh. Người dùng yêu cầu dùng bot hiện có để thực hiện công việc, trợ lý giữ vai trò giao việc, giám sát và nghiệm thu thay vì tự viết mã.

Do đó chọn lộ trình tới giai đoạn 5. Ở đợt triển khai đầu chỉ được kiểm tra/sửa phần mềm và giữ motor khóa; không thử quay bánh, phát START/AUTO/recovery hoặc khởi động tiến trình có thể khiến xe chuyển động. Tích hợp/nạp chỉ khi đã chứng minh trạng thái khởi động dừng, ngăn nguồn lệnh cũ và không tự ARM. Bài thử motor hoặc chạy trên sàn cần xác nhận điều kiện khu thử và người trực dừng khi chuyển sang thực địa. Build/test phần mềm không đủ để nghiệm thu né vật cản, SLAM khi di chuyển, khám phá phòng hoặc quay về gốc.

## 13. Phụ lục: kết quả kiểm tra logic cô lập

Các lớp/hàm được tách bằng AST; không import chương trình dự án để tránh các tác động top-level. Mọi gửi lệnh chỉ ghi vào list giả lập; sleep được thay bằng hàm giả. Không kết nối Serial, mạng điều khiển hoặc robot.

| Trường hợp | Kết quả quan sát |
|---|---|
| Một tia +90°, 0,25 m trong `scan_cb` | Cả ba bản gán `right=25` |
| Bật AUTO khi chưa nhận scan | Bản gốc gửi `V 0.10 0.00`, V2.1 gửi `V 0.22 0.00` |
| front=999 cm, front_right=50 cm | Bản gốc gửi `V 1.43 13.27`, V2.1 gửi `V 0.15 14.98` |
| STOP trong khoảng ngủ callback V2.1 | Tiếp tục gửi `V 0.0 -0.85` sau STOP |
| Explorer đang EXPLORING, map trống, home tại pose mặc định | Sau hai tick thành COMPLETED |
| Explorer tiến 0,036 m mỗi tick 0,2 s, 8 tick | Kích hoạt recovery lùi dù đang tiến 0,18 m/s |
| So khớp patch theo chuỗi, không thực thi patch | Deadband/wide-corners có khối khớp bản local; `old_move` của choke-point không khớp |
| Quét lời gọi publisher/TF lookup trong ba brain | Không có `create_publisher()` hoặc `lookup_transform()` |

Phép tính suy từ cấu hình: 0,245374 mm/xung; 110 RPM ≈0,422 m/s; 130 RPM ≈0,498 m/s; 280 RPM ≈1,073 m/s; 38 RPM ≈0,146 m/s. Do đó nút manual 110 RPM trên dashboard Pi và 130 RPM trên web ESP32 nhanh hơn đáng kể mức demo 0,08–0,12 m/s đề xuất; cần giới hạn tất cả nguồn lệnh theo cùng mode.

**Điều kiện để đưa dự án vào chạy thử có giám sát là hoàn thành lớp dừng/timeout, xác nhận hướng cảm biến và kiểm soát vận tốc. Điều kiện để mở khám phá phòng/quay về gốc là có thêm định vị theo map, tìm đường và tiêu chí nghiệm thu tương ứng.**
