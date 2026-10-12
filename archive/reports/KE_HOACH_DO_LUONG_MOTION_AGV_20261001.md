# KẾ HOẠCH BÀI THỬ CHUYỂN ĐỘNG CỰ LY NGẮN AGV (BOUNDED SHORT MOTION TRIAL PLAN)

**Trạng thái phê duyệt:** `PENDING REVIEW` (Tuyệt đối không tự ý thực hiện)  
**Thời gian cập nhật:** 01/10/2026 — 22:05  
**Hardware Owner duy nhất:** Khang AI Assistant  
**Đối tượng thử nghiệm:** Xe AGV (Snapshot firmware f5bf / Supervisor 1bd, ESP32 `/dev/ttyUSB0`)

---

### 1. BỐI CẢNH VÀ ĐÍNH CHÍNH HIỆN TRƯỜNG
- **Bối cảnh sự cố 13:57:** Lệnh điều khiển bò chậm danh định $v = 0.05\text{ m/s}$ trong cự ly mục tiêu danh định $100\text{ mm}$ dẫn đến `MOTION_TRACKING FAIL`. Giá trị đọc được từ cảm biến là **2 mm ODOM** (giá trị tích lũy từ Encoder Odom, hoàn toàn chưa có Ground Truth vật lý).
- **Đính chính khoa học:**
  - Hiện tượng không di chuyển ở dải PWM thấp chỉ là **giả thuyết kỹ thuật** (chưa có phép đo độc lập xác định tỉ lệ giữa ma sát sàn và đáp ứng động cơ).
  - Không tuyên bố "encoder 100%" hay "ma sát là nguyên nhân duy nhất" khi chưa có kiểm chứng độc lập.
  - Các thông số hình học và cơ khí ($R=0.0366\text{ m}$, $L=0.1875\text{ m}$, GA25 937.2 CPR, khối lượng ~1.75 kg) cần được xác thực bằng dữ liệu đo đạc thực tế có đối chiếu.
- **Kỷ luật an toàn tuyệt đối:**
  - CẤM tự ý kích xung PWM vọt, cấm tăng gain PID, cấm tự ý xóa lỗi (`CLEAR_FAULT`).
  - CẤM đẩy xe bằng tay, cấm nhấc bánh xe quay tự do khi chưa có quy trình kiểm duyệt.
  - CẤM lặp lại thử nghiệm nhiều lần không kiểm soát.

---

### 2. QUY TRÌNH BÀI ĐO CỰ LY NGẮN CÓ CHỐT CHẶN VẬT LÝ

#### BƯỚC 1: XÁC THỰC PREFLIGHT TĨNH NO-TX TRÊN SÀN (10–15s)
- **Điều kiện tiên quyết:** Xe đặt tĩnh trên sàn, không phát bất kỳ xung hay byte TX nào (`ReadOnlySerialWrapper`).
- **Thực thi:** Chạy `agv_preflight_static_collector.py` trực tiếp tại Pi.
- **Tiêu chí nghiệm thu:**
  - Nhận đủ 80 đến 120 mẫu D0 trong thời gian quan sát $\ge 10.0\text{s}$.
  - 100% mẫu có `safety == 'DISARMED'`, `l_pwm == 0`, `r_pwm == 0`, `l_rpm == 0.0`, `r_rpm == 0.0`.
  - Không có gián đoạn dòng dữ liệu (gap $> 1.5\text{s}$).

#### BƯỚC 2: BÀI THỬ CHUYỂN ĐỘNG THẲNG CỰ LY NGẮN (50mm / 1.0s)
- **Điều kiện kích hoạt:** Chỉ thực hiện khi Bước 1 đạt PASS, có sự phê duyệt bằng văn bản của Codex và Khang xác nhận có người trực an toàn tại hiện trường.
- **Thông số vận hành:**
  - Vận tốc danh định: Giữ nguyên dải tốc độ $v = 0.05\text{ m/s}$ hiện có (không tăng tốc, không vượt quá dải an toàn).
  - Quãng đường danh định: Đúng $50\text{ mm}$ ($0.05\text{ m}$).
  - Thời gian danh định: Đúng $1.0\text{s}$.
  - Hard time cap: $1.5\text{s}$ (ngắt khẩn cấp ngay nếu quá $1.5\text{s}$).
- **Thiết lập Ground Truth vật lý:**
  - Đặt thước lá kim loại chuẩn (độ chia $1\text{ mm}$) dán cố định dọc theo mép bánh xe trên sàn.
  - Đánh dấu vạch xuất phát (mốc 0) và vạch dừng danh định (mốc $50\text{ mm}$).
  - Đo khoảng cách di chuyển thực tế bằng thước vật lý và đối chiếu với biến thiên $\Delta \text{x\_odom}$ của gói D0.
- **Cơ chế ngắt an toàn và E-Stop:**
  - Heartbeat deadman timeout: $200\text{ ms}$.
  - Nếu xe lệch hướng $\Delta \theta > 5^\circ$ $\implies$ Dừng khẩn cấp (E-Stop).
  - Nếu thời gian di chuyển vượt quá $1.5\text{s}$ $\implies$ Dừng khẩn cấp.
  - Nếu phát hiện mất kết nối telemetry $> 0.2\text{s}$ $\implies$ Dừng khẩn cấp.

---

### 3. CAM KẾT VẬN HÀNH
Khang AI Assistant cam kết **tuyệt đối không khởi động bất kỳ lệnh ARM hay motor nào** khi chưa có văn bản chấp thuận chính thức từ Codex. Mọi thử nghiệm đều tuân thủ nguyên tắc an toàn phần cứng trên hết.
