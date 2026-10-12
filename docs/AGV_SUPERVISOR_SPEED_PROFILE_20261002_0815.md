# TÀI LIỆU GIÁM SÁT ĐIỀU KHIỂN CHUYỂN ĐỘNG & LỘ TRÌNH VẬN TỐC AGV (EXACT SUPERVISOR ARTIFACT)

**Mã tài liệu:** `AGV_SUPERVISOR_SPEED_PROFILE_20261002_0815.md`  
**Trạng thái phê duyệt:** `PENDING REVIEW` (Tuyệt đối không tự ý thực hiện)  
**Hardware Owner duy nhất:** Khang AI Assistant  
**Đối tượng kiểm soát:** Xe AGV (Bán kính bánh xe $R = 0.0366\text{ m}$, Khoảng cách 2 bánh $L = 0.1875\text{ m}$, GA25 tỉ số truyền 1:43.8, 937.2 CPR)

---

### 1. PHÂN TÍCH ĐỘNG HỌC & CÔNG THỨC QUY ĐỔI VẬN TỐC / RPM

#### 1.1. Phân biệt rõ ràng RPM bánh xe (Wheel RPM) và RPM trục động cơ (Motor Shaft RPM)
- **Tỉ số truyền hộp số (Gear Ratio $G$):** $G \approx 43.8$ (đối với động cơ GA25-370 chuẩn 937.2 xung/vòng).
- **Nếu mục tiêu là 140–150 RPM trục bánh xe (Wheel RPM):**
  - Chu vi bánh xe: $C = 2\pi R = 2 \times 3.14159 \times 0.0366 \approx 0.230\text{ m}$ ($230\text{ mm}$/vòng).
  - Vận tốc dài tương ứng của xe trên sàn:
    $$v = \frac{\text{Wheel RPM} \times 2\pi R}{60} = \frac{140 \times 0.230}{60} \approx 0.537\text{ m/s}$$
    $$v = \frac{150 \times 0.230}{60} \approx 0.575\text{ m/s}$$
  - **Nhận định rủi ro kỹ thuật:** Vận tốc $0.537 - 0.575\text{ m/s}$ ($> 0.5\text{ m/s}$) gấp **hơn 10 lần** vận tốc bò chậm $0.05\text{ m/s}$ lúc 13:57. Ở tốc độ này, với trọng tải 1.75 kg trên sàn gạch, quãng đường phanh trượt cơ học có thể vượt quá $0.5\text{ m}$, lực va chạm lớn và nguy cơ mất kiểm soát cực cao nếu chưa đo được ma sát và hiệu chuẩn PID.
- **Nếu mục tiêu là 140–150 RPM trục motor trước hộp số:**
  - Vận tốc bánh xe: $\text{Wheel RPM} = \frac{140}{43.8} \approx 3.2\text{ RPM} \implies v \approx 0.012\text{ m/s}$ (quá nhỏ, dưới ngưỡng dải chết).
  - Do đó: **Xác nhận mục tiêu Khang chọn là 140–150 RPM trục bánh xe ($v \approx 0.55\text{ m/s}$).**

---

### 2. CƠ CHẾ BẢO VỆ CHUYỂN ĐỘNG & BỘ GIÁM SÁT AN TOÀN (SUPERVISOR GUARDS)

Bộ giám sát supervisor điều khiển motor tuân thủ các chốt chặn fail-closed sau:
1. **Ramp Rate Bounded (Dốc tăng tốc có kiểm soát):**
   - Không nhảy bậc thang PWM. Gia tốc tăng tốc tối đa $a_{\max} \le 0.15\text{ m/s}^2$.
   - Thời gian tăng tốc từ 0 lên $0.05\text{ m/s}$ là $0.33\text{s}$.
2. **Overspeed Guard (Chặn vượt tốc):**
   - Ngắt E-Stop ngay lập tức nếu $v_{\text{odom}} > 1.15 \times v_{\text{target}}$ hoặc $\text{RPM} > 165\text{ RPM}$.
3. **RPM Mismatch Guard (Chặn lệch vòng quay 2 bánh):**
   - Khi chạy đường thẳng ($w = 0$), nếu $|\text{l\_rpm} - \text{r\_rpm}| > 20\text{ RPM}$ liên tục trong $> 100\text{ ms}$ (nguy cơ xe quay vòng tròn hoặc trượt một bên bánh) $\implies$ Kích hoạt phanh dừng khẩn cấp (E-Stop).
4. **Hard Time Cap & Bounded Distance:**
   - Quãng đường danh định ở giai đoạn khởi đầu: Đúng **$50\text{ mm}$**.
   - Thời gian danh định: Đúng **$1.0\text{s}$**.
   - Hard Time Cap: Đúng **$1.5\text{s}$** (quá $1.5\text{s}$ tự động hủy lệnh, chuyển gate sang `FAULT`).
5. **Độc lập Watchdog & Kênh xác nhận dừng (STOP Lifecycle):**
   - Luồng watchdog chạy độc lập chu kỳ $50\text{ ms}$, deadman timeout $200\text{ ms}$.
   - Trạng thái dừng chỉ được coi là hoàn tất khi: `STOP request` $\rightarrow$ `write OK` $\rightarrow$ `nhận gói D0 fresh từ firmware với safety='DISARMED', l_pwm=0, r_pwm=0`.
   - Nếu sau $200\text{ ms}$ từ khi phát STOP mà không nhận được gói D0 xác nhận $\implies$ Chuyển gate sang `FAULT` và báo động escalation.
6. **Cấm Auto-Retry & Cấm Re-ARM:**
   - Sau khi E-Stop hoặc Watchdog trip, hệ thống khóa cứng ở trạng thái `FAULT` / `DISARMED`. Tuyệt đối không tự động xóa lỗi (`CLEAR_FAULT`) hay tự nạp lại lệnh ARM.

---

### 3. LỘ TRÌNH THỰC NGHIỆM TĂNG TỐC TỪNG BƯỚC (STEPPED ROLLOUT)

Để đạt tới mục tiêu 140–150 RPM an toàn mà không làm hỏng xe hay mất lái, quy trình bắt buộc đi qua 3 mốc kiểm soát có đo đạc đối chiếu:

```
[MỐC 1: BƯỚC THỬ NGẮN ĐẦU TIÊN]
- Mục tiêu: Đo ma sát tĩnh & kiểm chứng chốt ngắt E-Stop.
- Vận tốc: v = 0.05 m/s (~13 RPM bánh xe).
- Quãng đường: Đúng 50 mm (1.0s, hard cap 1.5s).
- Đo đạc: Thước lá kim loại dán cố định trên sàn + số liệu odom.
- Điều kiện: Khang trực tiếp có mặt giám sát công tắc nguồn.
             │
             ▼ (Chỉ chuyển mốc khi Codex duyệt đối soát Mốc 1)
[MỐC 2: TĂNG VẬN TỐC TRUNG BÌNH CÓ ĐỐI CHIẾU TRƯỢT]
- Mục tiêu: Đo hệ số trượt lốp cao su và độ đáp ứng PID.
- Vận tốc: v = 0.20 m/s (~52 RPM bánh xe).
- Quãng đường: 200 mm trong 1.0s.
- Đo đạc: Thước đối chứng + cảm biến dừng an toàn.
             │
             ▼ (Chỉ chuyển mốc khi Codex duyệt đối soát Mốc 2)
[MỐC 3: TIẾP CẬN TARGET KHANG YÊU CẦU]
- Mục tiêu: Đạt dải vận tốc 140 - 150 RPM (v ≈ 0.55 m/s).
- Quãng đường: 500 mm trong hành lang an toàn đã dọn sạch chướng ngại vật.
- Yêu cầu hiện trường: 2 người trực an toàn ở 2 đầu hành lang.
```

---

### 4. CAM KẾT VẬN HÀNH
Khang AI Assistant cam kết **tuyệt đối không tự ý kích hoạt bất kỳ mốc chuyển động nào** khi chưa hoàn tất bước kiểm tĩnh No-TX và chưa có văn bản phê duyệt chính thức từ Codex.
