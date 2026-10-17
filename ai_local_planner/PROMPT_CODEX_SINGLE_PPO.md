# PROMPT DÀNH CHO CODEX: CHINH PHỤC CÁC CẤP ĐỘ 3, 4, 5 BẰNG MỘT MÔ HÌNH PPO ACTOR-CRITIC DUY NHẤT

> **Mục tiêu của nhiệm vụ**: Huấn luyện thành công **MỘT MÔ HÌNH PPO ACTOR-CRITIC DUY NHẤT** (Single Policy Neural Network, input `[N, 365]`, output `[N, 2]`) vượt qua toàn bộ các kịch bản từ Level 1 đến Level 5 (và mở rộng Level 6), vượt qua bài kiểm định độc lập **Acceptance Gate** (100 episodes/level có đầy đủ Sim-to-Real Domain Randomization), không bị quên bài cũ (Catastrophic Forgetting) và xuất xưởng ra file ONNX duy nhất.

---

## 1. BỐI CẢNH VÀ NGUYÊN NHÂN NGHẼN KỸ THUẬT

1. **Thực trạng**:
   - Gói nhiều chuyên gia (`local_planner_six_scene_experimental.onnx`) đã đạt $1.197 / 1.200$ episodes ($99.75\%$), nhưng là tổ hợp gồm bộ phân loại và 5 controller chuyên biệt, chưa phải một mô hình PPO duy nhất.
   - Khi cố gắng train PPO tuần tự hoặc distill vào một mạng đơn trước đây:
     - Level 1 & 2 đạt chuẩn ($\ge 99\%$ và $\ge 98\%$).
     - Nhưng bị chặn tại Level 3 (Hẻm hẹp 0.7m, cua 90°): Nếu học Level 3 thì Level 1 tụt xuống $84\%$ và Level 2 tụt xuống $92\%$, dẫn đến bị Gate chặn không cho lên Level 4 & 5.
2. **Hai nguyên nhân cốt lõi**:
   - **Cổ chai độ phân giải LiDAR**: Mạng `ActorCritic` trong `ai_local_planner/models/actor_critic.py` dùng `AvgPool1d(9, 9)` gộp 360 tia xuống còn 10 cung (mỗi cung $36^\circ$). Ở hẻm $0.7\text{m}$ (khoảng hở mỗi bên chỉ $15\text{cm}$), việc gộp $36^\circ$ làm mất hoàn toàn hình học chi tiết của vách tường và góc cua vuông. Tầng bottleneck chỉ có 64 chiều, không đủ dung lượng cho 6 bối cảnh khác nhau.
   - **Neo tham chiếu bị lệch nhãn**: Khi chạy PPO Level 3, script truyền `--reference-checkpoint` là checkpoint chỉ chuyên cho Level 3 (bản thân nó chỉ đạt $84\%$ L1 và $92\%$ L2). Khi rehearsal ôn bài L1 và L2, hàm mất mát neo `reference_coef * bc_loss` lại ép mô hình khớp với nhãn sai, gây thoái hóa kỹ năng cũ.

---

## 2. NHIỆM VỤ CỤ THỂ CHO CODEX

### Bước 1: Nâng cấp mạng ActorCritic trong `ai_local_planner/models/actor_critic.py`
1. Giữ nguyên Input Contract `obs[N, 365]` và Output Contract `cmd_vel[N, 2]` (`v` trong $[0, 0.35]\text{ m/s}$, `w` trong $[-1.5, 1.5]\text{ rad/s}$).
2. Cải tiến nhánh `lidar_net`:
   - Giảm stride hoặc kernel pooling để giữ lại ít nhất **30 cung không gian** ($12^\circ$/cung) thay vì 10 cung, giúp bảo toàn chi tiết khoảng hở $15\text{cm}$ ở hẻm hẹp.
   - Ví dụ:
     ```python
     self.lidar_net = nn.Sequential(
         nn.Conv1d(1, 16, 7, padding=3, padding_mode="circular"), nn.ReLU(),
         nn.Conv1d(16, 32, 5, stride=2, padding=2), nn.ReLU(),
         nn.Conv1d(32, 32, 5, stride=2, padding=2), nn.ReLU(),
         # 360 -> 180 -> 90 -> 30 sectors (mỗi sector 12 độ)
         nn.AvgPool1d(kernel_size=3, stride=3), nn.Flatten(),
         nn.Linear(32 * 30, 128), nn.ReLU(),
     )
     ```
3. Mở rộng tầng `fusion` từ 64 chiều lên **128 chiều** (`Linear(160, 128) -> ReLU -> Linear(128, 128) -> ReLU`), sau đó đưa vào `actor = nn.Linear(128, 2)` và `critic = nn.Linear(128, 1)`.
4. Đảm bảo mô hình tương thích hoàn toàn với PyTorch forward pass, `MeanPolicy` và ONNX Opset 14.

### Bước 2: Nâng cấp Neo tham chiếu trong `ai_local_planner/trainers/ppo_agent.py`
1. Thay vì chỉ nhận một file `.pth` đơn lẻ, cho phép `set_reference_policy` có thể nhận một **Teacher Policy tổng thể** (hoặc một Callable nhận `obs` và trả về `target_action`).
2. Tích hợp giáo viên toàn diện `LockedSceneONNXAgent` (vốn đã đạt $99.75\%$ trên cả 6 level từ file `ai_local_planner/exported/locked_scene_margin070_experimental/package.json`) làm nguồn sinh nhãn chuẩn cho hàm mất mát neo `bc_loss`:
   $$\mathcal{L} = \mathcal{L}_{PPO} + c_{ref} \cdot \text{MSE}(a_{student}, a_{teacher})$$
3. Nhờ đó, dù Rehearsal bốc trúng episode ở Level 1, 2, 3, 4 hay 5, Teacher đều cung cấp nhãn tối ưu 100%, **hoàn toàn triệt tiêu xung đột gradient!**

### Bước 3: Huấn luyện tuần tự với Rehearsal và Chốt chặn Gate
1. Chạy huấn luyện PPO từ Level 1 đến Level 5 bằng `ai_local_planner/scripts/run_train.py` với cấu hình:
   - `--rehearsal-prob 0.35`: 35% số episode trong quá trình học dành để ôn tập ngẫu nhiên các level trước đó.
   - `--retention-eval`: Bắt buộc kiểm tra toàn diện 100 episode cho từng level cũ trước khi cho phép thăng cấp.
   - `--epochs 2`, `--batch-size 256`, `--learning-rate 0.00002`.
2. Tiêu chuẩn Acceptance Gate nghiêm ngặt (không hạ chuẩn):
   - Level 1: Thành công $\ge 99\%$, Va chạm $\le 2\%$.
   - Level 2: Thành công $\ge 98\%$, Va chạm $\le 2\%$.
   - Level 3: Thành công $\ge 90\%$, Va chạm $\le 2\%$.
   - Level 4: Thành công $\ge 90\%$, Va chạm $\le 2\%$.
   - Level 5: Thành công $\ge 90\%$, Va chạm $\le 2\%$.
3. Tự động lưu `best_model.pth` khi vượt qua Gate và bảo toàn kỹ năng cũ.

### Bước 4: Đóng gói ONNX và Đánh giá Nghiệm thu
1. Xuất mô hình tốt nhất sang:
   `ai_local_planner/exported/local_planner_single_ppo.onnx`
2. Chạy đánh giá độc lập 100 seeds/level bằng `ai_local_planner/scripts/evaluate_onnx.py`.
3. Đo đạc độ trễ CPU (Inference Latency) bằng `benchmark_latency.py`, xác nhận $P99 < 2.0\text{ ms}$.
4. Cập nhật kết quả nghiệm thu vào `ai_local_planner/IMPLEMENTATION.md`.

---

## 3. LỆNH THỰC THI THAM KHẢO

```powershell
# 1. Kiểm tra Unit Tests trước khi sửa đổi
python -m pytest ai_local_planner/tests -q

# 2. Chạy huấn luyện tuần tự PPO từ Level 1 đến Level 5 với Rehearsal & Teacher Anchor
python -m ai_local_planner.scripts.run_train `
  --steps 200000 --rollout-steps 1024 --epochs 2 --batch-size 256 `
  --learning-rate 0.00002 --device cpu --max-level 5 `
  --rehearsal-prob 0.35 --retention-eval `
  --eval-every 5000 --eval-episodes 100 --eval-seed 4000000 `
  --output-dir ai_local_planner/checkpoints/single_ppo_curriculum_20261017

# 3. Export sang ONNX duy nhất
python -m ai_local_planner.scripts.export_onnx `
  --checkpoint ai_local_planner/checkpoints/single_ppo_curriculum_20261017/best_model.pth `
  --output ai_local_planner/exported/local_planner_single_ppo.onnx

# 4. Kiểm tra độ trễ CPU P99 < 2ms
python -m ai_local_planner.scripts.benchmark_latency `
  --model ai_local_planner/exported/local_planner_single_ppo.onnx
```
