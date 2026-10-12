# BÁO CÁO PHÂN TÍCH OFFLINE: KHẢO SÁT TOÁN HỌC VÀ CÁC GIẢ THUYẾT VỀ LỖI MOTION_TRACKING

- **Thời gian phân tích:** 2026-10-01 14:15
- **Tập tin raw log bài chạy thật 13:57:** `/home/khangho/agv_bench_run.log` (SHA-256: `0b4d82...bec1a`).
- **Tình trạng phần cứng:** Xe đang đứng yên trên sàn, firmware `firmware_f5bf.bin`, trạng thái phần mềm `DISARMED` (phần mềm ngừng phát xung, nguồn pin vẫn cấp phần cứng). **TUYỆT ĐỐI KHÔNG ARM, KHÔNG CHẠY LẠI (NO RERUN)**.

---

## 1. DỮ LIỆU ĐO ĐẠC THỰC NGHIỆM TRONG RAW LOG
- Lệnh: `V 0.05 0.0` $\rightarrow$ Target 2 bánh: $13.04\text{ RPM}$.
- Thời gian chạy: $2.0065\text{ s}$ (20 mẫu chu kỳ RUN từ `5417.4378s` đến `5419.4443s`).
- Chi tiết các mốc động học đo được:
  - Bánh PHẢI có mẫu nhích đầu tiên: $\text{RPM} = 2.56$ tại mốc $t = 5418.3388\text{ s}$ khi $\text{PWM} = 28$.
  - Sau đó bánh PHẢI lại về $0.00\text{ RPM}$ ở các mốc $\text{PWM} = 31, 33, 36, 38, 41, 44$.
  - Bánh TRÁI có mẫu nhích: $\text{RPM} = 5.12$ tại mốc $t = 5419.439\text{ s}$ khi $\text{PWM} = 48$.
  - Tổng quãng đường ghi nhận trên Odometry sau $2.0\text{ s}$: $0.0020\text{ m}$ ($2\text{ mm}$, tương đương ~2% so với $10\text{ cm}$ lý thuyết).

---

## 2. KHẢO SÁT TOÁN HỌC TRỰC TIẾP TỪ NGUỒN `pid.c` THẬT
Đã biên dịch và liên kết trực tiếp `pid.c` thật thành thư viện C shared (`libpid.so`) và chương trình kiểm thử C (`test_real_pid_c_qa_v2.c`) trên Raspberry Pi:
1. **Toán học bộ tích phân $K_i$ giải thích độ dốc Ramp của PWM ($14 \rightarrow 51$):**
   - Lưu ý về tần số lấy mẫu: Telemetry gửi lên Pi ở tần số $10\text{ Hz}$ ($\Delta t = 0.10\text{ s}$ giữa các gói tin), trong khi vòng lặp PID nội tại trên firmware ESP32 chạy ở $20\text{ Hz}$ ($\Delta t = 0.05\text{ s}$). Khảo sát 20 mẫu $10\text{ Hz}$ là phép xấp xỉ bậc 0 (Zero-Order Hold / ZOH) do thiếu dữ liệu nội suy giữa các chu kỳ $50\text{ ms}$.
   - Tại chu kỳ đầu tiên với sai số $e = 13.04\text{ RPM}$:
     $$u_0 = K_f \cdot \text{setpoint} + K_p \cdot e = (0.45 \times 13.04) + (0.5 \times 13.04) \approx 12.4\text{ PWM}$$
   - Ở mỗi chu kỳ PID ($\Delta t = 0.05\text{ s}$), khi vận tốc đo được phần lớn bằng 0:
     $$\Delta u_i = K_i \cdot e \cdot \Delta t = 1.5 \times 13.04 \times 0.05 \approx 0.978\text{ PWM / chu kỳ}$$
   - Sau $2.0\text{ s}$ ($40$ chu kỳ $20\text{ Hz}$): Lượng tích phân tích lũy được là $\approx 39\text{ PWM}$.
   - Tổng PWM xuất ra: $12.4 + 39 \approx 51.4\text{ PWM}$.
   - **Kết luận toán học:** Độ tăng tuyến tính từ $\text{PWM} = 14$ lên $\text{PWM} = 51$ hoàn toàn là do hành vi tích lũy toán học của thuật toán PID trong `pid.c`, độc lập với các yếu tố cơ khí bên ngoài.
2. **Kiểm chứng cơ chế dừng và Anti-Windup:**
   - Khi $\text{Setpoint} = 0.0$: `pid.c` lập tức xóa sạch tích phân (`pid->integral = 0.0f`) và trả về `0.0f`, chứng minh khi phát lệnh STOP không hề xảy ra xung kick giật từ tích phân cũ.
   - Khi stall kéo dài: Bộ tích phân cần $20\text{ s}$ ($400$ chu kỳ $0.05\text{ s}$) để chạm ngưỡng bão hòa và bị kẹp cứng ở $\text{max\_integral} = 170.0$, không bị tràn số (Anti-windup an toàn).

---

## 3. CÁC GIẢ THUYẾT KỸ THUẬT VỀ NGUYÊN NHÂN `MOTION_TRACKING FAIL` (HYPOTHESES - CHƯA XÁC MINH)

Lưu ý: Các mô hình mô phỏng Plant chỉ là giả định toán học, chưa thể coi là bằng chứng khẳng định nguyên nhân thực tế. Việc Odometry đo được $2\text{ mm}$ với vài xung không chứng minh được bánh xe có quay thật hay trượt. Trạng thái `PWM = 0` và `DISARMED` là trạng thái phần mềm ngừng phát xung, không đồng nghĩa với việc ngắt nguồn điện vật lý tới mạch công suất. Dưới đây là các giả thuyết cần được cô lập và kiểm chứng:

- **Giả thuyết 1: Độ nhạy ngưỡng khởi động động cơ / Ma sát tĩnh thực tế (Static Friction / Deadband):**
  - Mặc dù bánh phải có nhích $2.56\text{ RPM}$ tại $\text{PWM} = 28$, nhưng sau đó lại đứng yên cho đến tận $\text{PWM} = 48$. Điều này có thể do đặc tính ma sát tĩnh không đồng đều của bề mặt sàn hoặc hộp số GA25 khi chịu tải trọng xe.
- **Giả thuyết 2: Chiều quay hoặc đấu nối phần cứng của Encoder (Encoder Direction / Phase):**
  - Cần kiểm tra lại cấu hình chiều xung `enc->direction_factor` trong `encoder.cpp` so với chiều tiến thực tế của xe.
- **Giả thuyết 3: Tỉ số xung Encoder (CPR) và thông số cơ học:**
  - Định nghĩa hiện tại `#define COUNTS_PER_OUTPUT_REV 937.2f` trong `encoder.h` (tương đương 11 xung/vòng motor $\times$ tỉ số truyền 1:21.3 $\times$ 4 cạnh = 937.2). Cần đối chiếu với datasheet thực tế của dòng động cơ GA25 đang lắp trên xe.
- **Giả thuyết 4: Mức sụt áp khi tải dòng (Battery Sag):**
  - Khi hai động cơ cùng ăn dòng ở dải PWM thấp, điện áp cấp vào driver MKE-M18 có thể bị dao động gây giảm mô-men khởi động.

---

## 4. KẾ HOẠCH HIỆU CHUẨN ĐỀ XUẤT CÓ GIỚI HẠN (ĐỀ XUẤT TRÌNH CODEX DUYỆT - CHƯA THỰC HIỆN)

Tuyệt đối **KHÔNG TỰ Ý THỰC HIỆN BẤT KỲ BƯỚC NÀO** dưới đây trên xe thật khi chưa có phê duyệt:

1. **Hiệu chuẩn tĩnh kiểm tra Encoder bằng tay (Passive Hand-Spin Test - An toàn, không cấp điện động cơ):**
   - Xe ở trạng thái `DISARMED`, người trực dùng tay đẩy xe tịnh tiến thẳng đúng $10\text{ cm}$ (đo bằng thước kẻ vật lý trên sàn).
   - Đọc luồng Odometry Serial xem hiển thị đúng $0.10\text{ m}$ hay không. Nếu hiển thị lệch, xác định ngay nguyên nhân do CPR hoặc chiều quay Encoder mà không cần cấp điện cho động cơ.
2. **Kế hoạch khảo sát ngưỡng khởi động tối thiểu có kiểm soát (Nếu được duyệt):**
   - Từng bước khảo sát đáp ứng của từng bánh xe riêng biệt trong phạm vi ngắn, có chốt chặn an toàn và người trực giám sát.

---

## 5. ĐIỀU PHỐI 4 WORKER OFFLINE (01/10 16:50)

Theo yêu cầu từ Khang và chỉ đạo đối soát Codex 15:06, hệ thống đã khởi tạo 4 subagent chạy song song trong nền (Delegation ID: `deleg_6fdd7c97`) phụ trách từng phân hệ chuyên biệt theo đúng danh mục F01–F14:
- **W1 (`sa-0-a28e3500`):** Sửa lỗi Gate / Serial Safety (`agv_serial_arbiter_bridge_v3.py`), bắt buộc preflight DISARMED 0, chặn future time skew, ràng buộc STOP confirmation sau thời điểm phát lệnh.
- **W2 (`sa-1-25f792c5`):** Xây dựng node ROS 2 tích hợp Arbiter ở chế độ offline/mock, Odometry/TF theo timestamp thật, Freshness guard.
- **W3 (`sa-2-bdfefff6`):** Hoàn thiện Navigation & Costmap Planner V2, cấu hình footprint thực tế, trích xuất & lọc reachable frontiers, map-frame homepose.
- **W4 (`sa-3-15e23e79`):** Đảm bảo chất lượng QA độc lập và khắc phục triệt để lỗi trong `agv_passive_encoder_logger_v2.py`.

Toàn bộ quá trình thực hiện 100% OFFLINE, KHÔNG mở cổng Serial phần cứng trên Pi. Tiến độ được theo dõi tại `AGV_WORKER_MANIFEST.md`.
