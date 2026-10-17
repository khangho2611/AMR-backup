# MASTER PROMPT: MỞ RỘNG MÔ HÌNH ĐƠN CHINH PHỤC TOÀN DIỆN LEVEL 4 VÀ LEVEL 5 (HOÀN TẤT BỘ LÕI AI 1)

> **Cột mốc đã đạt được vừa qua**:
> Checkpoint `ai_local_planner/checkpoints/retention_level2_diverse_20261017/retention_candidate.pth` đã chính thức **VƯỢT QUA SIMULATION ACCEPTANCE GATE CHO CẢ 3 LEVEL ĐẦU TIÊN**:
> - **Level 1**: **100/100 (100.0%)**, 0% va chạm (Gate pass).
> - **Level 2**: **99/100 (99.0%)**, 1% va chạm (Gate pass).
> - **Level 3**: **99/100 (99.0%)**, 1% va chạm (Gate pass).
> File kiểm định độc lập: `ai_local_planner/logs/diverse_heldout_20261017_gate_l1_l3.json` (`simulation_gate_passed: true`).

---

## 1. MỤC TIÊU CỦA PHIÊN TIẾP THEO

Sử dụng chính xác phương pháp **Retention Repair & DAgger Rehearsal** thành công vừa rồi để mở rộng checkpoint hiện tại (`retention_candidate.pth`) sang **Level 4 (Mê cung 6–10 vật cản Slalom)** và **Level 5 (Bẫy chữ U ngõ cụt)**.

### Mục tiêu nghiệm thu (Acceptance Criteria):
Mô hình đơn (Single Actor-Critic) phải đồng thời vượt qua bài kiểm định 100 seeds độc lập có Sim-to-Real Domain Randomization trên **cả 5 cấp độ (Levels 1 $\rightarrow$ 5)**:
- **Level 1**: $\ge 99\%$ success, $\le 2\%$ collision.
- **Level 2**: $\ge 98\%$ success, $\le 2\%$ collision.
- **Level 3**: $\ge 90\%$ success, $\le 2\%$ collision.
- **Level 4**: $\ge 90\%$ success, $\le 2\%$ collision (hiện đang đạt 61%).
- **Level 5**: $\ge 90\%$ success, $\le 2\%$ collision (hiện đang bị 100% timeout do kẹt trong túi).

---

## 2. NGUYÊN NHÂN VÀ CÁCH GIẢI QUYẾT CHO LEVEL 4 VÀ LEVEL 5

### A. Level 5 (Bẫy chữ U ngõ cụt)
- **Hiện trạng**: Đạt $0\%$ success, $0\%$ collision, nhưng **$100\%$ timeout** (xe đi vào ngõ cụt, thấy vách chắn trước mặt thì đứng yên hoặc xoay nhẹ, không quay đầu $180^\circ$ để thoát ra).
- **Giải pháp**:
  - Đã có sẵn chuyên gia Level 5: `ai_local_planner/checkpoints/level5_bc_reactive_experimental.pth` (đã đạt $100\%$ trên Level 5).
  - Thu thập DAgger rollouts tại Level 5 với nhãn từ chuyên gia này: Ép mạng nơ-ron học kỹ năng quay tại chỗ $180^\circ$ khi phía trước là ngõ cụt chữ U ($d_{front} < 0.6\text{m}$, sườn trái và sườn phải đều bị chặn).

### B. Level 4 (Mê cung rải rác Slalom)
- **Hiện trạng**: Đạt $61\%$ success, $38\%$ collision (xe luồn lách được nhưng hay bị liếm vách khi cua gắt giữa hai vật cản gần nhau).
- **Giải pháp**:
  - Đã có sẵn chuyên gia Level 4: `ai_local_planner/checkpoints/level4_dagger_reactive_experimental.pth` (đạt $91\% - 96.7\%$).
  - Bổ sung hàm trọng số an toàn `level4_safety_weights` (tương tự như Codex đã làm cho Level 2 trong `repair_retention.py`): Tăng trọng số phạt (sample weight 3x) cho các mẫu có khoảng cách vật cản gần ($d < 0.5\text{m}$) để xe ôm cua rộng hơn.

---

## 3. CÁC BƯỚC THỰC HIỆN CỤ THỂ CHO CODEX

### Bước 1: Mở rộng `ai_local_planner/scripts/repair_retention.py` lên 5 Levels
1. Nạp checkpoint nền tảng đã qua gate L1–L3:
   `ai_local_planner/checkpoints/retention_level2_diverse_20261017/retention_candidate.pth`
2. Cấu hình chuyên gia làm nguồn nhãn (Teacher oracles):
   - Level 1 & 2: Dùng chính student hiện tại (hoặc PPO L1-2 đã nghiệm thu).
   - Level 3: Dùng nhãn ôm cua giảm tốc từ Level 3 DAgger (`retention_candidate.pth`).
   - Level 4: Dùng nhãn từ `ai_local_planner/checkpoints/level4_dagger_reactive_experimental.pth`.
   - Level 5: Dùng nhãn từ `ai_local_planner/checkpoints/level5_bc_reactive_experimental.pth`.
3. Thu thập dữ liệu DAgger & Replay:
   - Level 1: 15 episodes (giữ bài thẳng)
   - Level 2: 25 episodes (giữ bài né vật cản tĩnh)
   - Level 3: 25 episodes (giữ bài cua hãm tốc hẻm hẹp)
   - Level 4: 40 episodes (học luồn lách slalom)
   - Level 5: 35 episodes (học quay đầu thoát ngõ cụt chữ U)
4. Huấn luyện đa nhiệm cân bằng (Multi-task balanced sampling) trong 5–8 epochs với learning rate nhỏ ($1 \times 10^{-5}$ đến $2 \times 10^{-5}$) để bảo toàn tối đa trọng số L1–L3.

### Bước 2: Kiểm định vòng kín độc lập (Held-out Acceptance Evaluation)
Chạy script kiểm định độc lập trên 100 seeds chưa từng thấy cho từng level từ 1 đến 5:
- Level 1: seeds `5001000..5001099`
- Level 2: seeds `5002000..5002099`
- Level 3: seeds `5003000..5003099`
- Level 4: seeds `5004000..5004099`
- Level 5: seeds `5005000..5005099`
Lưu kết quả ra file: `ai_local_planner/logs/single_model_l1_to_l5_gate.json`.

### Bước 3: Đóng gói ONNX và Đo đạc
1. Xuất mô hình hoàn chỉnh sang:
   `ai_local_planner/exported/local_planner_single_actor_l1_l5.onnx`
2. Đo độ trễ suy luận CPU bằng `benchmark_latency.py`, xác nhận $P99 < 2.0\text{ ms}$.
3. Cập nhật báo cáo nghiệm thu vào `ai_local_planner/IMPLEMENTATION.md`.

---

## 4. LỆNH THỰC THI DỰ KIẾN

```powershell
# Chạy repair retention mở rộng lên Level 4 và 5
python -m ai_local_planner.scripts.repair_retention `
  --resume ai_local_planner/checkpoints/retention_level2_diverse_20261017/retention_candidate.pth `
  --output-dir ai_local_planner/checkpoints/single_model_l1_to_l5_20261017 `
  --epochs 6 --learning-rate 0.000015 --device cpu

# Chạy Acceptance Gate toàn diện cho Levels 1 -> 5
python -m ai_local_planner.scripts.acceptance_gate `
  --level1 ai_local_planner/logs/single_l1.json `
  --level2 ai_local_planner/logs/single_l2.json `
  --level3 ai_local_planner/logs/single_l3.json `
  --level4 ai_local_planner/logs/single_l4.json `
  --level5 ai_local_planner/logs/single_l5.json `
  --output ai_local_planner/logs/single_model_l1_to_l5_gate.json
```
