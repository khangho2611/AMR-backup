# MASTER PROMPT CHO CODEX: THỰC THI 3 GIAI ĐOẠN (A, B, C) ĐỂ CÁN ĐÍCH MÔ HÌNH ĐƠN LEVEL 1–5

> **Mục tiêu tối thượng**: Hoàn tất **MỘT MÔ HÌNH ACTOR-CRITIC DUY NHẤT** vượt qua bài kiểm định độc lập **Acceptance Gate cho toàn bộ 5 Levels (L1 $\rightarrow$ L5)** với $100$ episodes/level bật đầy đủ Sim-to-Real Domain Randomization, sau đó xuất xưởng chính thức file `local_planner_single_actor_l1_l5.onnx`.

---

## BƯỚC 0: CHỐT GIT BẢO VỆ THÀNH QUẢ HIỆN TẠI (BẮT BUỘC)
Trước khi chỉnh sửa code, hãy commit trạng thái hiện tại (58/58 tests PASS, Level 1, 3, 5 đạt 100%):
```powershell
git add ai_local_planner/
git commit -m "feat(ai1): checkpoint with L1=100%, L3=100%, L5=100% in single actor; 58 tests pass"
```

---

## GIAI ĐOẠN A: KHÔI PHỤC LEVEL 2 (MỤC TIÊU: $\ge 98\%$ THÀNH CÔNG, $\le 2\%$ VA CHẠM)

### 1. Phân tích nguyên nhân
Khi tối ưu đồng thời Level 4 và 5, mạng bị nhạy cảm quá mức với vật cản xa, dẫn đến việc đổi lái sớm hoặc giật hướng khi tiếp cận vật cản đơn ở Level 2, gây ra 9 va chạm trên 100 episodes kiểm định.

### 2. Kế hoạch triển khai trong `ai_local_planner/scripts/repair_retention.py`
1. **Khai thác chính xác 9 seed thất bại**:
   Chạy riêng 9 seed va chạm của Level 2 (`collision_seeds` từ lần đánh giá trước) với Teacher Level 2 ONNX để thu thập các frame mà hành động của Student lệch lớn so với Teacher: $|a_{student} - a_{teacher}| > 0.15$.
2. **Nâng trọng số an toàn cho Level 2 (`level2_safety_weights`)**:
   Tăng trọng số mất mát (Sample Weight) lên **5.0x** cho các mẫu trong vùng khoảng cách $0.8\text{m} \le d \le 2.2\text{m}$ (vùng quyết định quỹ đạo ôm cua vòng tránh).
3. **Cân bằng Replay bảo toàn L1, L3, L5**:
   - Replay ngân sách: Level 1 (15 eps), Level 2 (40 eps - tăng cường), Level 3 (20 eps), Level 5 (20 eps).
   - Tối ưu với learning rate nhỏ $1.2 \times 10^{-5}$ trong 4–6 epochs.
4. **Kiểm tra chốt chặn Giai đoạn A**:
   Đánh giá lại 100 seeds Level 2 (`seed 5002000`). Bắt buộc Level 2 phải phục hồi về $\ge 98\%$ thành công và $\le 2\%$ va chạm, đồng thời kiểm tra lại Level 1, 3, 5 vẫn giữ $\ge 98\%$.

---

## GIAI ĐOẠN B: ĐỘT PHÁ LEVEL 4 (MỤC TIÊU: $\ge 90\%$ THÀNH CÔNG, $\le 2\%$ VA CHẠM)

### 1. Phân tích nguyên nhân 44 va chạm
Trong bài toán Slalom mê cung (6–10 vật cản), chỉ cần lệch nhẹ quỹ đạo ở vật cản thứ nhất, xe bị rơi vào trạng thái lệch phân phối (Covariate Shift). Student không biết cách "tự cứu nguy" khi đã ở cự ly sát vách $\rightarrow$ sai số tích lũy làm xe đâm vào vật cản thứ hai hoặc thứ ba.

### 2. Kế hoạch triển khai: Kỹ thuật DAgger Tiêm nhiễu Phục hồi (Perturbation DAgger)
1. **Tiêm nhiễu góc lái chủ động (Noise Injection during Data Collection)**:
   - Trong quá trình thu thập DAgger Level 4, tại $15\%$ số bước ngẫu nhiên, cộng thêm một độ lệch lái nhỏ $\delta \omega \sim \mathcal{U}(-0.3, 0.3)\text{ rad/s}$ vào lệnh điều khiển của xe.
   - Khi xe bị cưỡng bức lệch vào thế hiểm sát vật cản ($0.25\text{m} \le d \le 0.45\text{m}$), **Teacher Level 4 ONNX sẽ cung cấp nhãn bẻ lái và hãm tốc chuẩn xác để thoát hiểm**.
   - Nhờ đó, mạng Student sẽ học được hành vi phục hồi (Recovery Behavior) thay vì hoảng loạn khi đi lệch tâm.
2. **Mở rộng biên nở an toàn (Inflation Clearance)**:
   - Tăng trọng số phạt cho các trạng thái có $d_{lidar\_min} < 0.45\text{m}$ với hệ số 4.0x. Ép xe phải chọn đường phân giác rộng rãi giữa hai vật cản thay vì lách sát sườn.
3. **Ngân sách thu thập Level 4**:
   - Thu thập 50 episodes DAgger tiêm nhiễu kết hợp nhãn từ Teacher Level 4 ONNX.
   - Huấn luyện kết hợp cùng Replay L1, L2, L3, L5 để giữ toàn bộ các bài toán khác.

---

## GIAI ĐOẠN C: TỔNG HỢP VÀ NGHIỆM THU ĐẦU CUỐI (END-TO-END ACCEPTANCE)

### 1. Chạy Acceptance Gate toàn diện 5 Levels (100 episodes mỗi level)
Chạy script kiểm định độc lập với 100 seeds chưa từng thấy cho từng cấp độ:
- **Level 1**: Thành công $\ge 99\%$, Va chạm $\le 2\%$
- **Level 2**: Thành công $\ge 98\%$, Va chạm $\le 2\%$
- **Level 3**: Thành công $\ge 90\%$, Va chạm $\le 2\%$
- **Level 4**: Thành công $\ge 90\%$, Va chạm $\le 2\%$
- **Level 5**: Thành công $\ge 90\%$, Va chạm $\le 2\%$

Lưu kết quả ra file: `ai_local_planner/logs/single_actor_l1_to_l5_final_acceptance.json`.

### 2. Xuất xưởng ONNX và Benchmark
Khi và chỉ khi Gate báo **PASS** trên cả 5 levels:
1. Xuất mô hình sang:
   `ai_local_planner/exported/local_planner_single_actor_l1_l5.onnx`
2. Chạy benchmark đo độ trễ suy luận CPU bằng `benchmark_latency.py`, ghi nhận $P99 < 2.0\text{ ms}$.
3. Cập nhật bảng tổng kết nghiệm thu cuối cùng vào `ai_local_planner/IMPLEMENTATION.md`.

---

## LỆNH THỰC THI MẪU

```powershell
# 1. Chạy script tối ưu khôi phục L2 và đột phá L4
python -m ai_local_planner.scripts.repair_retention `
  --resume ai_local_planner/checkpoints/retention_level2_diverse_20261017/retention_candidate.pth `
  --output-dir ai_local_planner/checkpoints/single_model_l1_l5_final_20261018 `
  --level2-weight 5.0 --level4-weight 4.0 --perturbation-prob 0.15 `
  --epochs 6 --learning-rate 0.000012 --device cpu

# 2. Đánh giá Acceptance Gate độc lập
python -m ai_local_planner.scripts.acceptance_gate `
  --level1 ai_local_planner/logs/final_eval_l1.json `
  --level2 ai_local_planner/logs/final_eval_l2.json `
  --level3 ai_local_planner/logs/final_eval_l3.json `
  --level4 ai_local_planner/logs/final_eval_l4.json `
  --level5 ai_local_planner/logs/final_eval_l5.json `
  --output ai_local_planner/logs/single_actor_l1_to_l5_final_acceptance.json

# 3. Export ONNX chính thức khi PASS
python -m ai_local_planner.scripts.export_onnx `
  --checkpoint ai_local_planner/checkpoints/single_model_l1_l5_final_20261018/retention_candidate.pth `
  --output ai_local_planner/exported/local_planner_single_actor_l1_l5.onnx
```
