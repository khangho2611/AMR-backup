# TÀI LIỆU PROMPT TIÊU CHUẨN: HUẤN LUYỆN AI 1 (LOCAL MOTION PLANNER)

Tài liệu này được đồng bộ và trích dẫn trực tiếp từ thư mục mã nguồn cốt lõi:
👉 [ai_local_planner/PROMPT_TRAIN_AI1_PPO.md](file:///d:/HoMinhKhang/PROJECT/GITHUB_PROJECT/CODE%20XE%20TU%20HANH/ai_local_planner/PROMPT_TRAIN_AI1_PPO.md)

👉 [Bản đồ trích dẫn thư mục ai_local_planner/README.md](file:///d:/HoMinhKhang/PROJECT/GITHUB_PROJECT/CODE%20XE%20TU%20HANH/ai_local_planner/README.md)

---

## TỔNG QUAN NHANH (QUICK SPECIFICATION)

- **Mục tiêu**: Điều hướng cục bộ thời gian thực (Local Motion Planning) & Tránh chướng ngại vật phản xạ (Reactive Obstacle Avoidance).
- **Thuật toán**: PPO (Proximal Policy Optimization) liên tục (Continuous Actor-Critic).
- **Đầu vào (Observation - 365D float32)**:
  - 360 tia khoảng cách LiDAR chuẩn hóa $[0, 1]$.
  - Khoảng cách đến đích waypoint: $\min(d_{goal} / 10.0, 1.0)$.
  - Hướng đến đích: $[\sin(\Delta\theta), \cos(\Delta\theta)]$.
  - Vận tốc hiện tại: $[v / v_{max}, \omega / \omega_{max}]$.
- **Đầu ra (Action - 2D float32)**:
  - Vận tốc dài $v \in [0.0, 0.35]\text{ m/s}$.
  - Vận tốc góc $\omega \in [-1.5, 1.5]\text{ rad/s}$.
- **Sim-to-Real Domain Randomization**:
  - Nhiễu Gaussian LiDAR $\pm 3\text{cm} \to \pm 5\text{cm}$.
  - $5\%$ Dropout / Tia lỗi quang học.
  - Trễ truyền thông UART $40\text{ms} - 100\text{ms}$ (1-2 steps buffer).
  - Lực kéo động cơ lệch $\pm 5\% - 10\%$.
- **Giới hạn an toàn phần cứng**: Phanh khẩn cấp bất biến nếu cự ly LiDAR $< 0.18\text{m}$.
- **Chuẩn đóng gói**: `local_planner.onnx` (Opset 14, latency CPU $< 2.0\text{ms}$).
