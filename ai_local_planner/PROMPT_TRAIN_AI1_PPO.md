# MASTER PROMPT HUẤN LUYỆN AI 1: LOCAL MOTION PLANNER (PPO) CHO XE TỰ HÀNH AGV

> **Mục tiêu của Prompt**: Sử dụng prompt này để nạp cho các AI Agent chuyên gia (ChatGPT, Claude, Codex, DeepSeek) hoặc dùng làm đặc tả kỹ thuật (Technical Specification & Execution Guide) để lập trình và chạy script huấn luyện tự động trên **Kaggle GPU / Google Colab / Local GPU**.

---

## 1. VAI TRÒ & BỐI CẢNH DỰ ÁN (ROLE & CONTEXT)

Bạn là một **Kỹ sư Trưởng về Trí tuệ Nhân tạo Robot (Autonomous Mobile Robot DRL Engineer)** chuyên sâu về Điều hướng Cục bộ (Local Motion Planning), Tránh vật cản phản xạ (Reactive Obstacle Avoidance) và Kỹ thuật thu hẹp khoảng cách Mô phỏng - Thực tế (**Sim-to-Real Domain Randomization**).

Bạn được giao nhiệm vụ xây dựng, huấn luyện và xuất bản mô hình học tăng cường sâu **PPO (Proximal Policy Optimization)** để làm **Não bộ Cục bộ (AI 1 - Local Planner)** cho một xe tự hành công nghiệp AGV hai bánh vi sai (Differential Drive AMR).

### Hệ thống phân tầng hiện tại của AGV:
1. **AI 2 (Global Coverage Planner - ĐÃ HOÀN TẤT & ĐẠT 100% ĐỘ PHỦ)**: Sử dụng Double DQN, nhận bản đồ lưới 2D và xuất ra tọa độ mục tiêu kế tiếp $(X_{goal}, Y_{goal})$.
2. **AI 1 (Local Motion Planner - NHIỆM VỤ NÀY)**: Nhận 360 tia RPLiDAR C1, vector mục tiêu tới $(X_{goal}, Y_{goal})$, và vận tốc hiện tại. Mô hình tính toán và xuất trực tiếp lệnh điều khiển vận tốc tuyến tính $v$ và vận tốc góc $\omega$ ở tần số $10\text{ Hz}$ để xe di chuyển êm ái, bám mục tiêu và luồn lách né vật cản tĩnh/động mượt mà.
3. **Hardware Safety Watchdog (Bất biến)**: Lớp an toàn phần cứng `< 18cm` vẫn được kích hoạt song song. Nếu khoảng cách bất kỳ tia nào $< 18\text{cm}$, hệ thống lập tức phanh dừng khẩn cấp.

---

## 2. THÔNG SỐ VẬT LÝ XE & PHẦN CỨNG THỰC TẾ (GROUND TRUTH HARDWARE SPECS)

Bạn PHẢI tuân thủ nghiêm ngặt các hằng số vật lý sau trong mô phỏng kinematic:
- **Kiểu dẫn động**: Vi sai 2 bánh chủ động + 2 bánh caster tự lựa (Differential Drive).
- **Kích thước xe**: Bán kính thân xe an toàn $R_{robot} = 0.20\text{ m}$ ($20\text{ cm}$), Khoảng cách giữa 2 bánh dẫn động $L = 0.28\text{ m}$ ($28\text{ cm}$).
- **Giới hạn vận tốc tuyến tính**: $v \in [0.0, 0.35]\text{ m/s}$ (chế độ bình thường) hoặc $[-0.10, 0.35]\text{ m/s}$ (cho phép lùi chậm khi phát hiện bẫy ngõ cụt).
- **Giới hạn vận tốc góc**: $\omega \in [-1.5, 1.5]\text{ rad/s}$.
- **Giới hạn gia tốc động cơ**: $a_{linear\_max} = 0.5\text{ m/s}^2$, $a_{angular\_max} = 2.0\text{ rad/s}^2$.
- **Cảm biến LiDAR**: RPLiDAR C1 quét 360°, tầm quét hiệu dụng $0.12\text{ m} \to 12.0\text{ m}$, tần số quét $10\text{ Hz}$ (chu kỳ $\Delta t = 0.1\text{ s}$).
- **Bộ vi xử lý đích**: Raspberry Pi 4 Model B (Broadcom BCM2711 quad-core Cortex-A72 @ 1.5GHz), chạy ONNXRuntime trên CPU, yêu cầu độ trễ suy luận $< 2.0\text{ ms}$.

---

## 3. KHÔNG GIAN TRẠNG THÁI & HÀNH ĐỘNG (OBSERVATION & ACTION CONTRACT)

### 3.1. Observation Vector (365 chiều float32)
Mạng nơ-ron nhận một vector phẳng có kích thước chính xác **(365,)**:
1. `obs[0:360]` (**360 giá trị**): 360 tia khoảng cách LiDAR từ $0^\circ$ đến $359^\circ$ quanh thân xe, được kẹp trong đoạn $[0.12, 12.0]\text{ m}$ và chuẩn hóa về đoạn $[0.0, 1.0]$ bằng công thức:
   $$\text{norm\_range}_i = \frac{r_i - 0.12}{12.0 - 0.12}$$
2. `obs[360]` (**1 giá trị**): Khoảng cách Euclid từ tâm xe đến mục tiêu waypoint $d_{goal} = \sqrt{\Delta x^2 + \Delta y^2}$, chuẩn hóa:
   $$\text{norm\_dist} = \min\left(\frac{d_{goal}}{10.0}, 1.0\right)$$
3. `obs[361]` (**1 giá trị**): $\sin(\Delta\theta)$ với $\Delta\theta = \text{atan2}(y_{goal} - y_{robot}, x_{goal} - x_{robot}) - \theta_{robot} \in [-\pi, \pi]$.
4. `obs[362]` (**1 giá trị**): $\cos(\Delta\theta)$. (Sử dụng cả $\sin$ và $\cos$ để tránh hiện tượng không liên tục tại mốc $-\pi / +\pi$).
5. `obs[363]` (**1 giá trị**): Vận tốc tiến hiện tại $v / v_{max} \in [-0.28, 1.0]$.
6. `obs[364]` (**1 giá trị**): Vận tốc góc hiện tại $\omega / \omega_{max} \in [-1.0, 1.0]$.

### 3.2. Action Vector (2 chiều liên tục float32)
Đầu ra từ Actor Policy là một vector **(2,)** trong đoạn $[-1.0, 1.0]$, sau đó được ánh xạ sang lệnh vật lý thực tế:
- $v_{cmd} = \text{scale}(a_0) \in [0.0, 0.35]\text{ m/s}$ (hoặc $[-0.10, 0.35]\text{ m/s}$).
- $\omega_{cmd} = a_1 \times 1.5\text{ rad/s} \in [-1.5, 1.5]\text{ rad/s}$.
- Áp dụng bộ lọc gia tốc vi sai (Slew Rate Limiter) trước khi nạp vào xe:
  $$v_{applied} = \text{clip}(v_{cmd}, v_{prev} - a_{max}\Delta t, v_{prev} + a_{max}\Delta t)$$
  $$\omega_{applied} = \text{clip}(\omega_{cmd}, \omega_{prev} - \alpha_{max}\Delta t, \omega_{prev} + \alpha_{max}\Delta t)$$

---

## 4. KỸ THUẬT SIM-TO-REAL DOMAIN RANDOMIZATION (BẮT BUỘC)

Để mô hình huấn luyện trong giả lập chạy được trên xe thật mà **không bị vấp ngã hoặc dao động loạn xạ**, môi trường mô phỏng PHẢI tích hợp 5 kỹ thuật Domain Randomization ngẫu nhiên trên mỗi episode:

1. **LiDAR Gaussian Noise**:
   Mỗi tia $r_i$ được cộng thêm nhiễu ngẫu nhiên $\mathcal{N}(0, \sigma^2)$ với $\sigma$ dao động từ $0.02\text{ m} \to 0.05\text{ m}$ (mô phỏng nhiễu đo đạc quang học của RPLiDAR C1).
2. **LiDAR Ray Dropout & Multi-path Glitch**:
   Tỷ lệ $3\% \to 5\%$ số tia ngẫu nhiên bị đặt thành giá trị tối đa $12.0\text{ m}$ (mô phỏng tia bị hấp thụ bởi bề mặt đen/kính trong nhà) hoặc giá trị cực tiểu (tia bị phản xạ lóa).
3. **UART Communication Delay (Trễ truyền thông 40–100ms)**:
   Mô phỏng hàng đợi trễ (FIFO Buffer) độ trễ 1 bước ($\Delta t = 0.1\text{ s}$). Lệnh vận tốc đưa ra ở bước $t$ sẽ chỉ có tác dụng lên xe ở bước $t+1$, ép mô hình phải học cách dự đoán quán tính xe.
4. **Traction Imbalance & Wheel Slip (Sai lệch động cơ & trượt bánh)**:
   Mỗi episode, gán ngẫu nhiên tỷ lệ hiệu suất động cơ trái/phải lệch nhau $\pm 5\% \to \pm 10\%$:
   $$v_{left} = v_{cmd\_left} \times (1 + \delta_{left}), \quad v_{right} = v_{cmd\_right} \times (1 + \delta_{right})$$
   với $\delta \sim \mathcal{U}(-0.10, 0.10)$.
5. **Chướng ngại vật ngẫu nhiên có độ rung vị trí (Position Jitter)**:
   Các vật cản tĩnh có độ rung nhẹ $\pm 2\text{ cm}$ giữa các bước để chống overfitting.

---

## 5. THIẾT KẾ HÀM THƯỞNG (REWARD SHAPING)

Hàm thưởng tại bước $t$ được tính theo công thức đa thành phần:
$$R_t = R_{progress} + R_{goal} + R_{collision} + R_{clearance} + R_{smoothness} + R_{heading} + R_{step}$$

Chi tiết từng trọng số:
- **Thưởng tiến tới đích ($R_{progress}$)**:
  $$R_{progress} = 15.0 \times (d_{t-1} - d_t)$$
  Thưởng dương khi xe thu hẹp khoảng cách tới đích, phạt âm nếu xe đi lùi ra xa.
- **Thưởng chạm đích ($R_{goal}$)**:
  $$R_{goal} = +100.0 \quad \text{nếu } d_t < 0.20\text{ m}$$
- **Phạt va chạm ($R_{collision}$)**:
  $$R_{collision} = -50.0 \quad \text{nếu } d_{min\_lidar} \le R_{robot} \ (0.20\text{ m})$$
  Episode lập tức kết thúc (`done = True`).
- **Phạt áp sát nguy hiểm ($R_{clearance}$)**:
  $$R_{clearance} = -2.0 \times \left(0.35 - d_{min\_lidar}\right) \quad \text{nếu } 0.20\text{ m} < d_{min\_lidar} < 0.35\text{ m}$$
  Răn đe xe không được liếm sát góc tường hoặc vật cản.
- **Phạt giật lái & lắc hướng ($R_{smoothness}$)**:
  $$R_{smoothness} = -0.10 \times |\omega_t - \omega_{t-1}|^2 - 0.05 \times |v_t - v_{t-1}|^2 - 0.05 \times |\omega_t|$$
  Triệt tiêu hoàn toàn thói quen "lắc lư qua lại" (wobbling/chattering) của mạng DRL thông thường, đảm bảo xe chạy trên sàn êm và tiết kiệm cơ cấu bánh răng.
- **Thưởng hướng đầu xe về đích ($R_{heading}$)**:
  $$R_{heading} = 0.5 \times \cos(\Delta\theta) \times \frac{v_t}{v_{max}}$$
  Khuyến khích xe quay đầu hướng thẳng về mục tiêu trước khi tăng tốc lớn.
- **Phạt thời gian sống ($R_{step}$)**:
  $$R_{step} = -0.05$$
  Phạt nhẹ mỗi bước để ép robot tìm con đường ngắn nhất, không đứng yên chần chừ.

---

## 6. CHIẾN LƯỢC HUẤN LUYỆN 6 KỊCH BẢN (CURRICULUM LEARNING)

Huấn luyện theo 6 giai đoạn lũy tiến, tự động thăng cấp khi **Tỷ lệ thành công (Success Rate) $\ge 90\%$** trong 100 episodes gần nhất:

1. **Giai đoạn 1: Hành lang trống (Clear Corridor)**
   - Không có vật cản. Mục tiêu cách $2\text{m} \to 8\text{m}$.
   - Mục đích: Học tăng tốc thẳng mượt, phanh hãm đúng điểm khi tới đích.
2. **Giai đoạn 2: Vật cản tĩnh đơn lẻ (Single Obstacle)**
   - Đặt 1 hình trụ bán kính $0.15\text{ m} - 0.30\text{ m}$ nằm chính giữa đường nối từ xe tới đích.
   - Mục đích: Học bẻ lái sớm trước $1.0\text{m}$, ôm cua mềm lách qua rồi lấy lại hướng đi.
3. **Giai đoạn 3: Hẻm hẹp & Góc vuông 90° (Narrow Passage & Corner)**
   - Bố trí 2 bức tường tạo thành hẻm rộng $0.70\text{ m}$ (xe rộng $0.40\text{m}$) kèm một góc cua vuông.
   - Mục đích: Học căn giữa tâm đường hẹp, không để đuôi xe quẹt tường khi đánh lái.
4. **Giai đoạn 4: Mê cung chướng ngại vật (Cluttered Slalom)**
   - Rải ngẫu nhiên 6–10 hình trụ trong phòng $10\text{m} \times 10\text{m}$.
   - Mục đích: Học kỹ năng luồn lách slalom liên tục nhiều vật cản phức tạp.
5. **Giai đoạn 5: Bẫy ngõ cụt túi chữ U (U-Pocket Dead-end Trap)**
   - Robot bị đặt đối diện hoặc đi vào một ngõ cụt dạng chữ U có chiều sâu $1.5\text{m}$, rộng $1.2\text{m}$, đích nằm bên ngoài bẫy.
   - Mục đích: Học nhận diện ngõ cụt từ LiDAR, tự động lùi ra ngoài hoặc quay 180° để thoát bẫy thay vì đâm đầu vào đáy chữ U.
6. **Giai đoạn 6: Vật cản động (Dynamic Obstacles - Sim-to-Real Challenge)**
   - Thêm 2–3 vật cản hình tròn di chuyển với tốc độ người đi bộ chậm ($0.15 - 0.25\text{ m/s}$) cắt ngang đường.
   - Mục đích: Học phản xạ nhường đường hoặc lùi/lách linh hoạt theo thời gian thực.

---

## 7. KIẾN TRÚC MẠNG ACTOR-CRITIC (PPO ARCHITECTURE)

Thiết kế mạng nhẹ, tối ưu hóa suy luận CPU trên Raspberry Pi 4:
```text
State Input: (Batch, 365)
  │
  ├──► [0:360] LiDAR Rays (Batch, 1, 360)
  │        ▼
  │     Conv1D(1 -> 16, kernel=5, stride=2) + ReLU
  │        ▼
  │     Conv1D(16 -> 32, kernel=3, stride=2) + ReLU
  │        ▼
  │     AdaptiveAvgPool1D(16) -> Flatten -> (Batch, 512)
  │        ▼
  │     Linear(512 -> 128) + LayerNorm + ReLU (LiDAR Feature)
  │
  └──► [360:365] Target & Velocity Vector (Batch, 5)
           ▼
        Linear(5 -> 32) + ReLU (Goal Feature)
           ▼
     Concat([LiDAR Feature, Goal Feature]) -> (Batch, 160)
           │
           ├───────────────────────────────┐
           ▼                               ▼
      Actor Head                      Critic Head
      Linear(160 -> 128) + ReLU      Linear(160 -> 128) + ReLU
      Linear(128 -> 64)  + ReLU      Linear(128 -> 64)  + ReLU
           ▼                               ▼
      Mean: Linear(64 -> 2)          Value V(s): Linear(64 -> 1)
      Log-Std: Parameter (2,)
           ▼
      Squashed Gaussian Policy
      Output: [v_cmd, omega_cmd]
```

### Siêu tham số huấn luyện (PPO Hyperparameters):
- **Optimizer**: AdamW, Learning Rate $= 3 \times 10^{-4}$ (có Linear Cosine Annealing xuống $1 \times 10^{-5}$).
- **Rollout Steps per Iteration**: 2048 steps.
- **Mini-batch Size**: 128 hoặc 256.
- **PPO Epochs**: 10 epochs mỗi lần update.
- **Discount Factor ($\gamma$)**: 0.99.
- **GAE Parameter ($\lambda$)**: 0.95.
- **Clip Range ($\epsilon$)**: 0.2.
- **Entropy Coefficient**: 0.01 (khuyến khích thăm dò các hướng né mới).
- **Max Grad Norm**: 0.5.

---

## 8. ĐẶC TẢ XUẤT XƯỞNG & ĐÓNG GÓI ONNX (EXPORT SPECIFICATION)

1. **Xuất mô hình ONNX**:
   - Chỉ xuất nhánh **Actor (Mean Policy)** sang `exported/local_planner.onnx`.
   - Bỏ qua Critic Head và Stochastic Sampling để đảm bảo hành vi suy luận xác định (Deterministic Inference) an toàn trên xe thật.
   - Input Tensor: `lidar_and_goal_state` kiểu float32 kích thước `[1, 365]`.
   - Output Tensor: `cmd_vel` kiểu float32 kích thước `[1, 2]` đại diện cho $[v, \omega]$.
   - ONNX Opset: 14.
2. **Kiểm tra độ trễ (Latency Benchmark)**:
   - Chạy 1,000 lần suy luận liên tiếp bằng `onnxruntime.InferenceSession` với CPU execution provider.
   - Độ trễ P99 phải đạt $< 2.0\text{ ms}$ (chuẩn an toàn cho chu kỳ điều khiển $10\text{ Hz} = 100\text{ ms}$).
3. **Manifest Signature**:
   - Tự động sinh `exported/manifest.json` chứa:
     - `model_name`: `"agv_local_planner_v1"`
     - `sha256`: Hash toàn vẹn file ONNX
     - `date`: Timestamp xuất xưởng
     - `success_rate`: Tỷ lệ thành công qua 100 test seeds
     - `input_shape`: `[1, 365]`
     - `output_shape`: `[1, 2]`
     - `safety_boundary_min_dist`: $0.18\text{ m}$

---

## 9. QUY TRÌNH THỰC THI CHO AGENT (STEP-BY-STEP INSTRUCTIONS)

1. **Bước 1**: Đọc bản đồ thư mục trong `ai_local_planner/README.md`.
2. **Bước 2**: Triển khai `ai_local_planner/environments/agv_motion_env.py` và `scenarios.py` có đầy đủ 5 cơ chế Sim-to-Real Domain Randomization.
3. **Bước 3**: Triển khai mạng Actor-Critic trong `ai_local_planner/models/actor_critic.py` và thuật toán PPO trong `ai_local_planner/trainers/ppo_agent.py`.
4. **Bước 4**: Viết và chạy bộ Unit Tests trong `ai_local_planner/tests/` để xác nhận mọi phép tính kinematic và tensor shape đều chính xác 100%.
5. **Bước 5**: Chạy thử nghiệm 2,000 steps cục bộ để kiểm tra log, sau đó đóng gói kịch bản để nạp lên Kaggle GPU cho huấn luyện quy mô lớn (5 - 10 triệu steps).
6. **Bước 6**: Sau khi huấn luyện đạt tỷ lệ thành công $> 95\%$, chạy `export_onnx.py` để xuất mô hình sang `exported/local_planner.onnx` và nghiệm thu độ trễ.
