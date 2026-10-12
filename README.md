# 🤖 AGV / AMR AUTONOMOUS MOBILE ROBOT SYSTEM

> **Hệ Thống Robot Tự Hành Trong Nhà (Indoor Autonomous Mobile Robot)**  
> **Điều hướng tự động (Autonomous Navigation) • Quét phủ kín mặt sàn (Coverage Patrol) • SLAM 2D LiDAR • Điều khiển vòng kín PID kép**

[![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.12-blue)](https://www.python.org/)
[![ROS 2](https://img.shields.io/badge/ROS%202-Jazzy%20Jalisco-green)](https://docs.ros.org/en/jazzy/)
[![Unit Tests](https://img.shields.io/badge/Unit%20Tests-136%2F136%20PASS%20(100%25)-brightgreen)](tests/)
[![Platform](https://img.shields.io/badge/Hardware-Raspberry%20Pi%204%20(8GB)-red)](https://www.raspberrypi.com/)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

---

## 📌 MỤC LỤC
1. [Tổng Quan Hệ Thống](#-1-tổng-quan-hệ-thống)
2. [Sơ Đồ Khối Hệ Thống (Block Diagram)](#-2-sơ-đồ-khối-hệ-thống-block-diagram)
3. [Lưu Đồ Thuật Toán Tự Hành (Flowchart)](#-3-lưu-đồ-thuật-toán-tự-hành-flowchart)
4. [Cấu Trúc Thư Mục Dự Án](#-4-cấu-trúc-thư-mục-dự-án)
5. [Thông Số Kỹ Thuật Phần Cứng & Động Học](#-5-thông-số-kỹ-thuật-phần-cứng--động-học)
6. [Hướng Dẫn Khởi Động & Vận Hành](#-6-hướng-dẫn-khởi-động--vận-hành)
7. [Hệ Thống REST API & Giao Diện Web](#-7-hệ-thống-rest-api--giao-diện-web)
8. [Kiểm Thử Chất Lượng (Unit Testing)](#-8-kiểm-thử-chất-lượng-unit-testing)

---

## 🚀 1. TỔNG QUAN HỆ THỐNG

Dự án phát triển nền tảng **Xe Tự Hành AMR (Autonomous Mobile Robot)** phục vụ cho vận chuyển trong nhà xưởng / lau dọn phủ kín mặt sàn thông minh:
- **Bộ não xử lý trung tâm (SBC):** Raspberry Pi 4 Model B (RAM 8GB) chạy hệ điều hành Ubuntu Linux + ROS 2 Jazzy.
- **Cảm biến dẫn đường chính:** Cảm biến laser 2D **RPLiDAR C1** quét 360° tần số 10Hz, tầm xa đo đạc lên đến 12m–16m.
- **Cơ cấu chấp hành:** Hệ dẫn động vi sai 2 bánh chủ động (**Differential Drive**) dùng động cơ giảm tốc **GA25-370 12V 140 RPM** gắn đĩa encoder từ tính độ phân giải cao (937.2 xung/vòng bánh).
- **Bộ điều khiển cấp thấp (MCU):** Vi điều khiển STM32F103 / ESP32 chạy thuật toán điều khiển phản hồi vòng kín **PID + Feedforward (Kf)** ở tần số lấy mẫu 20Hz (50ms).
- **Thuật toán điều hướng cấp cao:** Tích hợp bộ lập kế hoạch A* tối ưu, FSM chuyển trạng thái thông minh, cơ chế tự động thoát ngõ cụt 180° bằng cách quay tại chỗ thuần túy ($v = 0.000\text{ m/s}$), và tự động quay về điểm xuất phát (Return-to-Home) an toàn.

---

## 🏗️ 2. SƠ ĐỒ KHỐI HỆ THỐNG (BLOCK DIAGRAM)

```mermaid
graph TD
    subgraph HARDWARE_LAYER ["1. TẦNG PHẦN CỨNG & CẢM BIẾN (HARDWARE)"]
        LIDAR["RPLiDAR C1 (Quét laser 360°)"]
        BATTERY["Pin Li-ion 3S 12.6V (Mạch đo Vin)"]
        MOTORS["2x Động cơ GA25 12V + Bánh cao su R=36.6mm"]
        ENCODERS["2x Đĩa Encoder từ tính (937.2 CPR)"]
        MCU["Vi điều khiển STM32F103 / ESP32 (Điều khiển PID)"]
        PI4["Raspberry Pi 4 Model B (Cortex-A72 4 lõi, 8GB RAM)"]
        
        LIDAR -->|USB UART /dev/ttyUSB1| PI4
        BATTERY --> MCU
        ENCODERS -->|Ngắt phần cứng đếm xung| MCU
        MCU -->|Cầu H L298N/TB6612 PWM| MOTORS
        MCU <-->|USB UART 115200 /dev/ttyUSB0| PI4
    end

    subgraph MIDDLEWARE_LAYER ["2. TẦNG ROS 2 & SLAM MIDDLEWARE"]
        SLLIDAR["Node Driver: sllidar_ros2 (/scan topic, 10Hz)"]
        TF2["Node TF2: static_transform_publisher (base_footprint -> laser)"]
        SLAM["SLAM Toolbox (Online Async Mapping -> /map OccupancyGrid)"]
        
        PI4 --> SLLIDAR
        PI4 --> TF2
        SLLIDAR --> SLAM
        TF2 --> SLAM
    end

    subgraph BRAIN_LAYER ["3. BỘ NÃO ĐIỀU KHIỂN TRUNG TÂM (AGV UNIFIED BRAIN)"]
        SESSION["CommandSession & Serial Protocol (/dev/ttyUSB0)"]
        GRID_MAP["GridPlanner & Clearance Sweeper (Lưới 5cm)"]
        FSM["StateMachine: IDLE -> EXPLORE / COVERAGE -> RETURNING_HOME"]
        ASTAR["A* Path Planner & Lookahead Waypoints Tracker"]
        ESCAPE["Dead-End Detector (U-Turn 180° In-Place Rotation)"]
        SAFETY["Safety Watchdog: Giảm tốc & E-Stop tự động"]
        
        SLAM -->|/map & TF2 pose| GRID_MAP
        SLLIDAR -->|360° ranges| SAFETY
        SAFETY --> ESCAPE
        GRID_MAP --> ASTAR
        FSM --> ASTAR
        ESCAPE --> SESSION
        ASTAR -->|V v_mps w_rads| SESSION
        SESSION -->|Lệnh ASCII Gửi xuống MCU| MCU
    end

    subgraph UI_LAYER ["4. GIAO DIỆN ĐIỀU HÀNH WEB & GIÁM SÁT REALTIME"]
        WEB_SERVER["Built-in Async HTTP Server (Port 8080)"]
        DASHBOARD["Mission Control Dashboard (index_cyberpunk.html)"]
        CANVAS["Canvas Render: Bản đồ SLAM + Pose + Quỹ đạo + Điểm đích"]
        API["REST API: /api/telemetry, /api/auto, /api/auto_config, /api/pid"]
        
        PI4 --> WEB_SERVER
        WEB_SERVER --> API
        API <--> DASHBOARD
        DASHBOARD --> CANVAS
    end
```

---

## 🔄 3. LƯU ĐỒ THUẬT TOÁN TỰ HÀNH (FLOWCHART)

```mermaid
flowchart TD
    START(["BẮT ĐẦU VẬN HÀNH (Web UI: Bấm START)"]) --> INIT["Khởi tạo: Arm động cơ, nạp PID tối ưu, ghi nhớ tọa độ Home (0,0)"]
    INIT --> CHECK_MODE{"Chế độ nhiệm vụ?"}
    
    CHECK_MODE -->|EXPLORE| FRONTIER["Tìm ranh giới chưa khám phá: find_best_frontier()"]
    CHECK_MODE -->|COVERAGE| COV["Tìm ô sàn trống chưa lăn qua: find_best_coverage_goal()"]
    
    FRONTIER --> EVAL_GOAL{"Có tìm thấy mục tiêu?"}
    COV --> EVAL_GOAL
    
    EVAL_GOAL -->|Không còn mục tiêu| CHECK_FINISH{"Tất cả vùng đã sạch / hết Unknown?"}
    CHECK_FINISH -->|Đúng| RET_HOME["Chuyển trạng thái: RETURNING_HOME (Mục tiêu = Home)"]
    CHECK_FINISH -->|Chưa| SPIN_SCAN["Xoay nhẹ tại chỗ 360° quét cập nhật bản đồ"]
    SPIN_SCAN --> CHECK_MODE
    
    EVAL_GOAL -->|Có mục tiêu| SENSOR_CHECK["Đọc LiDAR 360°: f_dist (trước), l_dist (trái), r_dist (phải)"]
    
    SENSOR_CHECK --> CHECK_DEADEND{"HÀNH LANG CỤT?\n(l_dist < 0.38m VÀ r_dist < 0.38m\nVÀ f_dist < 0.42m)"}
    CHECK_DEADEND -->|ĐÚNG: Kẹt ngõ cụt| UTURN["KÍCH HOẠT U-TURN THOÁT HIỂM:\nv = 0.000 m/s (Đứng im tại chỗ)\nw = ±3.194 rad/s (Quay tròn 80 RPM)\nKhóa hướng 1.80s hoặc đến khi f_dist >= 0.50m"]
    UTURN --> SEND_CMD
    
    CHECK_DEADEND -->|SAI| CHECK_DANGER{"Cản quá gần trước mặt?\n(f_dist < 0.26m)"}
    CHECK_DANGER -->|ĐÚNG| SPIN_AVOID["Xoay tại chỗ né cản:\nv = 0.000 m/s, w = ±3.194 rad/s"]
    SPIN_AVOID --> SEND_CMD
    
    CHECK_DANGER -->|SAI| CHECK_BUFFER{"Vùng đệm cản?\n(0.26m <= f_dist < 0.45m)"}
    CHECK_BUFFER -->|ĐÚNG| BUFFER_STEER["Né cản vùng đệm:\nv = 0.000 (nếu f_dist < 0.35m) hoặc cruise\nw = ±0.45 rad/s"]
    BUFFER_STEER --> SEND_CMD
    
    CHECK_BUFFER -->|SAI: Đường thoáng| CHECK_HEADING{"Lệch góc mục tiêu\n|heading_err| > 45° (0.80 rad)?"}
    CHECK_HEADING -->|Góc lệch lớn| IN_PLACE_TURN["Xoay ngắm thẳng hướng mục tiêu:\nv = 0.000 m/s, w = ±3.194 rad/s (80 RPM)"]
    IN_PLACE_TURN --> SEND_CMD
    
    CHECK_HEADING -->|Đã thẳng hướng| CRUISE["CHẠY TIẾN TỐC ĐỘ ĐỊNH MỨC (80 RPM):\nv = 0.307 m/s\nw = clamp(0.8 * heading_err, -0.50, 0.50)"]
    CRUISE --> SEND_CMD
    
    SEND_CMD["Truyền lệnh xuống MCU qua UART: V v_mps w_rads"] --> CHECK_ARRIVE{"Cách mục tiêu <= 0.22m?"}
    CHECK_ARRIVE -->|Đã đến| CLEAR_GOAL["Xóa mục tiêu đã hoàn tất, chuẩn bị tìm mục tiêu mới"]
    CLEAR_GOAL --> CHECK_MODE
    CHECK_ARRIVE -->|Đang trên đường| LOOP_DELAY["Lặp chu kỳ điều khiển (10Hz / 100ms)"]
    LOOP_DELAY --> SENSOR_CHECK
    
    RET_HOME --> HOME_ARRIVE{"Cách tọa độ Home <= 0.28m?"}
    HOME_ARRIVE -->|ĐÃ VỀ TỚI NHÀ| STOP_COMPLETE["DỪNG XE HOÀN TOÀN (V 0.000 0.000)\nBáo trạng thái: COMPLETED & Tắt Auto"]
    HOME_ARRIVE -->|Chưa về tới| SENSOR_CHECK
    STOP_COMPLETE --> END(["KẾT THÚC NHIỆM VỤ"])
```

---

## 📂 4. CẤU TRÚC THƯ MỤC DỰ ÁN

Toàn bộ cây thư mục được sắp xếp tinh gọn, rõ ràng theo đúng chuẩn kỹ thuật công nghiệp:

```
CODE XE TU HANH/
│
├── 🧠 BỘ NÃO ĐIỀU KHIỂN & GIAO DIỆN CHÍNH (ROOT CORE)
│   ├── agv_unified_brain.py            # Node não trung tâm: Web server 8080, FSM tự hành, A*, SLAM Bridge
│   ├── agv_command_session.py          # Quản lý giao thức Serial nhị phân/ASCII, FSM tiền kiểm Preflight
│   ├── agv_navigation.py               # Lớp hình học GridPlanner, thuật toán A* occupancy grid, quét an toàn
│   ├── agv_command_journal.py          # Nhật ký ghi nhận và đối soát toàn bộ lệnh phát xuống phần cứng
│   ├── agv_preflight_static_collector.py # Bộ thu thập kiểm chuẩn tĩnh phần cứng trước khi cho phép chạy
│   ├── index_cyberpunk.html            # Giao diện Web điều khiển thời gian thực (Mission Control Cyberpunk)
│   ├── start_agv_system.sh             # Script khởi động tự động toàn bộ hệ thống (LiDAR + SLAM + Brain)
│   ├── README.md                       # Tài liệu thuyết minh toàn diện hệ thống
│   └── .gitignore                      # Bộ lọc loại trừ các file tạm cache, file log không cần thiết
│
├── 📁 docs/                            # TÀI LIỆU KỸ THUẬT & TÍNH TOÁN THIẾT KẾ
│   ├── BANG_GIAI_TRINH_THONG_SO_AGV_CHUAN.md # Bảng giải trình chi tiết thông số cơ khí, PID, động học
│   ├── DANH_GIA_VA_TRIEN_KHAI_XE_TU_HANH.md  # Kế hoạch và đánh giá thực nghiệm xe tự hành
│   ├── TINH_TOAN_THIET_KE_XE_TU_HANH.docx    # Hồ sơ tính toán động lực học, chọn động cơ và pin
│   ├── README_CODEX_AGV_TIEP_TUC.md    # Hướng dẫn chi tiết quy trình tiếp nhận và vận hành hệ thống
│   ├── README_TELEGRAM_BOTS.md         # Hướng dẫn kết nối thông báo trạng thái qua Telegram Bot
│   └── prompt.docx                     # Yêu cầu đầu bài và tiêu chuẩn thiết kế ban đầu
│
├── 📁 robot_stm32_f103/                # MÃ NGUỒN FIRMWARE ĐIỀU KHIỂN ĐỘNG CƠ (C/C++)
│   ├── Core/                           # Mã nguồn khởi tạo ngoại vi HAL (UART, TIM Encoder, PWM)
│   ├── include/                        # Các file header: pid.h, motor.h, encoder.h, protocol.h
│   ├── src/                            # Mã nguồn thực thi thuật toán điều khiển PID và giao thức truyền thông
│   └── platformio.ini                  # Cấu hình biên dịch nhúng PlatformIO cho chip STM32F103C8T6
│
├── 📁 slam_calibration_tools/          # CÔNG CỤ HIỆU CHUẨN SLAM & LIDAR
│   ├── slam_tuned.yaml                 # File cấu hình tham số tối ưu cho SLAM Toolbox trên xe thật
│   ├── auto_angular_calibrator.py      # Script tự động tính toán sai số góc quay và tỉ số wheelbase
│   ├── manual_angular_tuner.py         # Công cụ tinh chỉnh góc thủ công từng bước
│   └── run_slam_tuned.sh               # Script chạy SLAM với bộ tham số đã hiệu chuẩn
│
├── 📁 tests/                           # BỘ KIỂM THỬ TỰ ĐỘNG (136/136 PASS 100%)
│   ├── test_agv_wall_escape_fix.py     # Kiểm thử thuật toán thoát ngõ cụt 180° & hành trình 80 RPM
│   ├── test_agv_coverage_patrol.py     # Kiểm thử thuật toán phủ kín mặt sàn và tự động về Home
│   ├── test_agv_navigation_fix.py      # Kiểm thử thuật toán tìm đường A* và kiểm tra va chạm
│   ├── test_agv_operator_speed.py      # Kiểm thử kiểm soát tốc độ hành trình và giới hạn gia tốc
│   └── test_bundle_production.py       # Bộ kiểm thử tích hợp toàn diện quy trình vận hành
│
├── 📁 archive/                         # LƯU TRỮ PHIÊN BẢN CŨ & THÀNH PHẦN NGHỈ HƯU (LEGACY)
│   ├── legacy_candidates/              # Các bản build trước đây
│   ├── legacy_patches/                 # Các bản vá lịch sử
│   └── reports/                        # Các biên bản nghiệm thu trước đây
│
└── 📁 baocao/ & scratch/               # BÁO CÁO THỰC ĐỊA & CÁC SCRIPT KIỂM TRA NHANH (PROBES)
```

---

## ⚙️ 5. THÔNG SỐ KỸ THUẬT PHẦN CỨNG & ĐỘNG HỌC

| Thông số | Giá trị | Đơn vị | Ý nghĩa & Giải thích kỹ thuật |
| :--- | :---: | :---: | :--- |
| **Khối lượng toàn xe ($m$)** | $1.75$ | kg | Cân nặng đo thực tế đã lắp pin, LiDAR và khung |
| **Bán kính bánh xe ($R$)** | $0.0366$ ($36.6$) | m (mm) | Bánh lốp cao su có độ bám cao (chu vi $C = 0.23\text{ m}$) |
| **Khoảng cách 2 bánh ($L$)** | $0.1875$ ($18.75$) | m (cm) | Chiều rộng cơ sở bánh chủ động; quyết định tốc độ góc $\omega = \frac{v_R - v_L}{L}$ |
| **Độ phân giải Encoder ($CPR$)**| $937.2$ | xung/vòng | $11\text{ PPR} \times 4\text{ (chế độ x4)} \times 21.3\text{ (hộp số GA25)}$ |
| **Tốc độ hành trình chuẩn** | **$80.0$** | **RPM** | Tốc độ định mức vận hành mượt mà ($v \approx 0.307\text{ m/s}$) |
| **Tốc độ quay tại chỗ ($w$)** | **$80.0$** | **RPM** | Tương đương $\omega \approx 3.194\text{ rad/s}$ ($v = 0.000\text{ m/s}$ thuần túy) |
| **Bộ thông số PID nạp chuẩn** | $K_p=1.0, K_i=3.2, K_d=0.01, K_f=1.80$ | - | Bù sụt áp pin và tải trọng, triệt tiêu trễ ma sát tĩnh |
| **Bán kính thân xe (Footprint)**| $-0.16, -0.11, 0.10, 0.11$ | m | Bán kính bao: đuôi -16cm, mũi +10cm, rộng ±11cm |
| **Khoảng cách dừng khẩn cấp** | $0.26$ | m (26cm) | Ngưỡng laser phát hiện cản để lập tức chuyển sang xoay tại chỗ |

---

## 🖥️ 6. HƯỚNG DẪN KHỞI ĐỘNG & VẬN HÀNH

### Cách 1: Khởi động tự động bằng Script duy nhất (Khuyên dùng)
Kết nối SSH vào Raspberry Pi 4 và chạy lệnh:
```bash
cd /home/khangho/agv_codex_reader_20261003_0652
bash ./start_agv_system.sh
```
*Script sẽ tự động giải phóng các cổng bận, nạp môi trường ROS 2 Jazzy, khởi chạy RPLiDAR C1, node Static TF, SLAM Toolbox và node não `agv_unified_brain.py`.*

### Cách 2: Khởi động lại riêng node não (Brain Node)
```bash
bash ./restart_brain.sh
```

---

## 🌐 7. HỆ THỐNG REST API & GIAO DIỆN WEB

Sau khi khởi động, truy cập trình duyệt tại địa chỉ: **`http://<IP_RASPBERRY_PI>:8080/`** (hoặc `http://100.90.252.15:8080/`).

### Các API điều khiển chính:
- **`GET /api/telemetry`**: Lấy toàn bộ trạng thái thời gian thực (vận tốc bánh, RPM, PWM, góc quay, điện áp pin VIN, 360 tia LiDAR, tọa độ SLAM).
- **`GET /api/auto?act=START&mode=EXPLORE`**: Kích hoạt chế độ tự hành khám phá mở rộng bản đồ.
- **`GET /api/auto?act=START&mode=COVERAGE`**: Kích hoạt chế độ tự hành phủ kín toàn bộ mặt sàn nhà.
- **`GET /api/auto?act=STOP`**: Dừng khẩn cấp và chuyển về chế độ thủ công an toàn.
- **`GET /api/auto_config?speed=80.0&turn=80.0`**: Cấu hình tốc độ hành trình và tốc độ xoay (mặc định chuẩn 80 RPM).
- **`GET /api/reset_map`**: Xóa trắng bản đồ SLAM cũ và khởi tạo lại phiên bản đồ mới.

---

## 🧪 8. KIỂM THỬ CHẤT LƯỢNG (UNIT TESTING)

Dự án đi kèm bộ kiểm thử tự động gồm **136 bài test** bao phủ 100% các tình huống logic:
- Chống kẹt góc tường, nhận diện hành lang cụt 180°.
- Điều khiển tốc độ hành trình không bị bóp nghẽn.
- Đồng bộ hóa truyền thông nối tiếp và khôi phục khi mất nguồn driver.
- Độ trễ đọc dữ liệu cảm biến và kiểm tra an toàn hình học thân xe.

Chạy toàn bộ bài test:
```bash
python -m unittest discover tests
```
**Kết quả kiểm chuẩn:**
```text
Ran 136 tests in 2.227s
OK
```

---
*Bản quyền phát triển © 2026 bởi Khang Ho. Hệ thống đã được kiểm chuẩn thực tế trên xe tự hành AMR.*
