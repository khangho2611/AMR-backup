# BẢNG GIẢI TRÌNH CHI TIẾT CÁC THÔNG SỐ ĐIỀU KHIỂN & HỆ THỐNG AGV (SYSTEM PARAMETERS AUDIT)

> **Dự án:** Robot Tự Hành AGV / AMR - SLAM Navigation & Lidar RPLIDAR C1  
> **Nền tảng:** ROS 2 Jazzy + Raspberry Pi 4 Model B + ESP32/STM32 MCU  
> **Căn cứ kỹ thuật:** File tính toán thiết kế `TINH_TOAN_THIET_KE_XE_TU_HANH.docx` kết hợp hệ thống thực địa `agv_unified_brain.py`

---

## 1. THÔNG SỐ CƠ KHÍ & ĐỘNG HỌC HÌNH HỌC (KINEMATICS)

| STT | Ký hiệu | Tên thông số | Giá trị chuẩn hóa | Đơn vị | Căn cứ tính toán & Ý nghĩa kỹ thuật |
| :---: | :---: | :--- | :---: | :---: | :--- |
| **1** | $m$ | Khối lượng bản thân xe | **$1.75$** | $\text{kg}$ | Cân thực tế khung xe, pin 12V, cụm truyền động và cảm biến LiDAR. |
| **2** | $M$ | Tải trọng thiết kế tối đa | **$2.10$** | $\text{kg}$ | Khối lượng xe kèm dự phòng tải chuyên chở $0.35\text{ kg}$. |
| **3** | $L$ | Chiều rộng cơ sở (Wheelbase) | **$0.1875$** ($18.75$) | $\text{m}$ ($\text{cm}$) | Khoảng cách tâm giữa 2 vệt bánh xe chủ động sau. **Quyết định góc quay $\omega = \frac{v_R - v_L}{L}$. Nếu sai lệch $1\text{mm}$, mỗi góc quay 90° sẽ bị lệch tích lũy, làm rách bản đồ SLAM.** |
| **4** | $R$ | Bán kính hiệu dụng bánh xe | **$0.0366$** ($36.6$) | $\text{m}$ ($\text{mm}$) | Chu vi bánh lốp cao su dưới tải: $C = 0.23\text{ m} \implies R = \frac{C}{2\pi} \approx 0.0366\text{ m}$. Chuyển đổi từ vận tốc góc sang vận tốc dài: $v = \omega \cdot R$. |
| **5** | $PPR$ | Độ phân giải đĩa Encoder | **$11$** | $\text{xung/vòng}$ | Đĩa từ 11 cực trên trục động cơ trước hộp giảm tốc. |
| **6** | $G$ | Tỉ số truyền hộp số GA25 | **$21.3 : 1$** | - | Hộp giảm tốc hành tinh/bánh răng kim loại động cơ GA25-370. |
| **7** | $CPR$ | Tổng xung một vòng bánh xe | **$937.2$** | $\text{xung/vòng}$ | Công thức: $CPR = PPR \times 4\text{ (chế độ x4 cạnh xung)} \times G = 11 \times 4 \times 21.3 = 937.2$. |
| **8** | $\Delta s$ | Độ phân giải quãng đường | **$0.2454$** | $\text{mm/xung}$ | Quãng đường xe nhích được trên mỗi xung encoder: $\Delta s = \frac{C}{CPR} = \frac{230\text{ mm}}{937.2} \approx 0.2454\text{ mm}$. |
| **9** | $N_{1m}$ | Số xung trên 1 mét chạy | **$4075.4$** | $\text{xung/m}$ | Số xung tích lũy khi xe di chuyển đúng $1.0\text{ m}$: $N = \frac{1000\text{ mm}}{0.2454} \approx 4075.4\text{ xung}$. Dùng để kiểm chuẩn thước dây Odometry. |

---

## 2. THÔNG SỐ ĐỘNG LỰC HỌC & CÔNG SUẤT ĐỘNG CƠ (ACTUATION & PWM)

| STT | Ký hiệu | Tên thông số | Giá trị chuẩn hóa | Đơn vị | Căn cứ tính toán & Ý nghĩa kỹ thuật |
| :---: | :---: | :--- | :---: | :---: | :--- |
| **1** | $v_{\text{nom}}$ | Vận tốc định mức trong nhà | **$0.50$** | $\text{m/s}$ | Vận tốc tối ưu đạt chuẩn an toàn phòng Lab theo Mục 4.2 của tài liệu thiết kế. |
| **2** | $\omega_{\text{wheel}}$ | Tốc độ vòng quay bánh định mức | **$130 - 140$** | $\text{RPM}$ | Tính từ: $\text{RPM} = \frac{v \times 60}{C} = \frac{0.50 \times 60}{0.23} \approx 130.4\text{ RPM}$. |
| **3** | $PWM_{\text{nom}}$ | Mức xung PWM danh định | **$120 - 130$** | $/255$ | Ước tính tỉ lệ tốc độ 130/280 theo Mục 4.2 của tài liệu thiết kế (chưa phải phép đo công suất có tải). |
| **4** | $PWM_{\text{deadband}}$ | Ngưỡng vượt vùng chết ma sát (HYPOTHESIS/UNMEASURED) | **$60 - 80$** | $/255$ | Giả thiết vùng chết ma sát tĩnh hộp số khi khởi động; chưa đo đạc quét dải điện áp thực nghiệm. |
| **5** | $a_{\text{acc}}$ | Gia tốc tăng tốc tối đa | **$0.30$** | $\text{m/s}^2$ | Đường dốc tăng ga thiết kế (Ramp). Thời gian tính toán: $t = \frac{0.5}{0.3} \approx 1.67\text{s}$, quãng đường $s = 41.7\text{ cm}$. |
| **6** | $a_{\text{dec}}$ | Gia tốc hãm phanh an toàn | **$0.50$** | $\text{m/s}^2$ | Giả thiết thiết kế gia tốc hãm phanh an toàn. |

---

## 3. BỘ THAM SỐ VÒNG KÍN PID & FEEDFORWARD ĐỘNG CƠ

Cấu trúc thuật toán trong Firmware:
$$u(t) = K_f \cdot \text{target\_rpm} + K_p \cdot e(t) + K_i \int e(t) \, dt + K_d \cdot \frac{de(t)}{dt}$$

| STT | Ký hiệu | Tên tham số | Dải an toàn | Giá trị chuẩn | Vai trò & Bản chất vật lý |
| :---: | :---: | :--- | :---: | :---: | :--- |
| **1** | $K_p$ | Hệ số Tỉ lệ (Proportional Gain) | $0.0 - 20.0$ | **$0.50$** | Tạo lực kéo tức thời tỉ lệ với độ lệch tốc độ $e(t) = \text{target} - \text{measured}$. Quyết định độ bốc khi đạp ga. |
| **2** | $K_i$ | Hệ số Tích phân (Integral Gain) | $0.0 - 50.0$ | **$1.50$** | Triệt tiêu sai số xác lập ($\text{Steady-state Error}$). **Tự động bơm tăng thêm PWM khi pin 12V bị sụt áp hoặc bánh xe bị ma sát nặng, ép 2 bánh phải quay chuẩn xác $100\%$.** |
| **3** | $K_d$ | Hệ số Vi phân (Derivative Gain) | $0.0 - 5.0$ | **$0.010$** | Dự đoán xu hướng thay đổi sai số, tạo lực hãm chống hiện tượng vọt lố (Overshoot) và triệt tiêu rung giật khi bám tốc độ cao. |
| **4** | $K_f$ | Hệ số Bơm đón đầu (Feedforward) | $0.0 - 5.0$ | **$0.45$** | Cấp trước một mức PWM cơ bản tỉ lệ với RPM mục tiêu: $PWM_{\text{base}} = K_f \times RPM_{\text{target}}$. Giúp vòng PID không phải đợi tích phân mà xe vẫn nhấc bánh chuyển động ngay lập tức. |
| **5** | $T_{\text{sample}}$ | Chu kỳ lấy mẫu PID | - | **$50$** ($20\text{Hz}$) | $\text{ms}$ | Tần số ngắt phần cứng Timer trên vi điều khiển STM32/ESP32 để tính toán bù sai số. |

---

## 4. THÔNG SỐ VÙNG AN TOÀN & CẢM BIẾN LIDAR C1 (SAFETY ZONES)

| STT | Tên thông số | Giá trị chuẩn | Đơn vị | Công thức & Căn cứ kỹ thuật Mục 8.3 |
| :---: | :--- | :---: | :---: | :--- |
| **1** | **Cự ly Dừng khẩn cấp ($D_{\text{E-Stop}}$)** | **$40$** | $\text{cm}$ | Tính từ công thức quán tính hãm: $s_{\text{dừng}} = s_{\text{trôi (50ms)}} + s_{\text{hãm (0.5m/s²)}} + s_{\text{đệm}} = 2.5\text{cm} + 25.0\text{cm} + 10.0\text{cm} = 37.5 \approx \mathbf{40\text{ cm}}$. Dưới ngưỡng này xe lập tức lùi nhẹ và đổi hướng. |
| **2** | **Cự ly Bắt đầu giảm tốc ($D_{\text{Slow}}$)** | **$75$** | $\text{cm}$ | Vùng đệm cảnh báo từ xa: Khi phát hiện tường trong dải $40\text{cm} - 75\text{cm}$, xe hạ ga xuống $PWM = 95 - 125$ và chủ động lượn sang bên thoáng. |
| **3** | **Vùng Thoáng chạy tối đa ($D_{\text{Clear}}$)** | **$> 75$** | $\text{cm}$ | Đường thẳng không có vật cản: Xe duy trì đều mức xung danh định $PWM = 125$ để vẽ map ổn định. |
| **4** | **Khoảng đệm sườn xe ($D_{\text{Side}}$)** | **$42$** | $\text{cm}$ | Khoảng cách an toàn hai bên hông: Nếu mép tường $< 42\text{cm}$, thuật toán tự động bù lệch ga $\pm 10\text{ PWM}$ để xe không cạ hông vào tường. |
| **5** | **Tần số quét LiDAR C1** | **$10.0$** | $\text{Hz}$ | Cảm biến quay 10 vòng/giây ($600\text{ RPM}$), phát chùm tia laser 360 độ qua giao tiếp Serial `/dev/ttyUSB1` (Baudrate $460800$). |

---

## 5. THÔNG SỐ KHÔNG GIAN TF & BẢN ĐỒ SLAM TOOLBOX

| STT | Khung liên kết (Frame) | Tọa độ Offset $(X, Y, Z)$ | Góc xoay $(R, P, Y)$ | Tần số | Ý nghĩa kỹ thuật |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **1** | `odom -> base_footprint` | $(x_{\text{odom}}, y_{\text{odom}}, 0.0)$ | $(0, 0, \theta_{\text{odom}})$ | $20\text{Hz}$ | Tọa độ tích phân chuyển động của xe từ Encoder theo thuật toán Runge-Kutta. |
| **2** | `base_footprint -> laser` | $(+0.05, 0.0, +0.12)\text{ m}$ | $(0, 0, 0)$ | $20\text{Hz}$ | Vị trí lắp thực tế của tâm mắt quét RPLIDAR C1: Nhô ra phía trước tâm trục bánh sau $5\text{cm}$, cao hơn mặt sàn $12\text{cm}$. **Khử hoàn toàn hiện tượng lệch tâm quét (Ghost Walls) khi xe xoay tròn.** |
| **3** | `Resolution` (Độ phân giải Map) | **$0.05$** ($5\text{cm/ô}$) | - | - | Kích thước 1 pixel lưới trong OccupancyGrid. Đảm bảo bản đồ sắc nét nhưng không gây nghẽn CPU Raspberry Pi 4. |
| **4** | `Frontier Step` (Bước nhảy biên) | **$3$** (ô) | - | - | Bước nhảy quét ma trận tìm ô chưa biết (`-1`). Tối ưu thuật toán tìm đường thám hiểm thời gian thực chỉ mất $< 15\text{ms}$ trên Pi 4. |

---

## 6. LƯU Ý VẬN HÀNH & QUY TRÌNH HIỆU CHUẨN THỰC ĐỊA

1. **Hiệu chuẩn $L$ (Wheelbase):**
   - Cho xe xoay tại chỗ đúng 10 vòng tròn ($3600^\circ$).
   - Nếu góc $\theta$ trên Dashboard báo $> 3600^\circ$: Tăng nhẹ thông số $L$ trong file cấu hình.
   - Nếu góc $\theta$ trên Dashboard báo $< 3600^\circ$: Giảm nhẹ thông số $L$.
2. **Hiệu chuẩn $R$ (Bán kính bánh xe):**
   - Cho xe chạy thẳng 1 đoạn $2.0\text{ m}$ đo bằng thước dây trên sàn gạch.
   - Đối soát giá trị $X$ trên Dashboard. Căn chỉnh bán kính $R$ sao cho sai số cự ly $\le 0.5\%$.
3. **Hiệu chuẩn PID trên Web:**
   - Luôn giữ cố định $K_f = 0.45$.
   - Tăng dần $K_p$ từ $0.3 \rightarrow 0.5$ đến khi xe khởi động dứt khoát không có độ trễ.
   - Tăng dần $K_i$ từ $1.0 \rightarrow 1.5$ để xe chạy thẳng tắp 2 bánh đều nhau và duy trì đúng tốc độ khi leo gờ gạch.
