# Lệnh chạy AI1 Local Planner (Windows PowerShell, từ gốc repository)

Thông số và kết quả: [../IMPLEMENTATION.md](../IMPLEMENTATION.md).

## PPO *một* mạng 30-sector, Level 1→5 (17/10/2026)

Kiến trúc mới giữ `[N,365] -> [N,2]`: Conv1D LiDAR chia 30 cung, fusion
128-D, MeanPolicy đưa ra `v` [0,0.35] m/s và `w` [-1.5,1.5] rad/s.
Giữ lại checkpoint cũ (10 cung): `--init-from` chuyển trọng số gần như
chính xác về hành vi cũ trước khi PPO cập nhật, reset optimizer, bắt đầu
từ Level 1 và step 0. `--resume` tiếp tục đúng step/level đã lưu.

Teacher mặc định (nếu gói có sẵn) là
`exported/locked_scene_margin070_experimental/package.json`. Đây là
**nhiều chuyên gia chỉ dùng lúc huấn luyện**, không nằm trong ONNX student.
Nhãn được lấy từ expert *theo level thật của mỗi transition* kể cả rehearsal,
không dùng nhãn từ bộ phân loại scene đang calibration. Teacher không hoàn hảo,
và tối ưu PPO với MSE imitation vẫn có thể gây xung đột gradient.

```powershell
python -m pytest ai_local_planner/tests -q

python -m ai_local_planner.scripts.run_train `
  --init-from ai_local_planner/checkpoints/ppo_level2_anchored_20261016/best_level_2.pth `
  --reference-package ai_local_planner/exported/locked_scene_margin070_experimental/package.json `
  --steps 200000 --rollout-steps 1024 --epochs 2 --batch-size 256 `
  --learning-rate 0.00002 --device cpu --level 1 --max-level 5 `
  --rehearsal-prob 0.35 --retention-eval --eval-every 5000 `
  --eval-episodes 100 --eval-seed 4000000 `
  --output-dir ai_local_planner/checkpoints/single_ppo_curriculum_20261017
```

Trình tự bắt buộc: L1 >=99%, L2 >=98%, L3–5 >=90% thành công,
va chạm <=2% tại *từng* level trên 100 episode ngẫu nhiên, và các level
cũ được đánh giá lại mỗi lần xét thăng cấp. `best_model.pth` có thể lưu
ở một level trước; **chỉ checkpoint đạt cả L1–L5 mới đủ điều kiện export
tên sản phẩm**. Khi qua gate, đánh giá ONNX với **seed độc lập**:

Nếu huấn luyện bị ngắt, dùng `--resume` với checkpoint đã lưu. Với lượt
2026-10-17 dừng ở 30.720 bước, checkpoint có thể resume là
`checkpoints/single_ppo_curriculum_20261017/best_level_3.pth` (25.600 bước).
Nên dùng **output-dir mới** cho lượt resume để không trộn lịch sử episode
không thuộc checkpoint (checkpoint định kỳ mới mặc định mỗi 10.000 bước):

```powershell
python -m ai_local_planner.scripts.run_train `
  --resume ai_local_planner/checkpoints/single_ppo_curriculum_20261017/best_level_3.pth `
  --steps 200000 --rollout-steps 1024 --epochs 2 --batch-size 256 `
  --learning-rate 0.00002 --device cpu --max-level 5 `
  --rehearsal-prob 0.35 --retention-eval --eval-every 5000 `
  --eval-episodes 100 --eval-seed 4000000 `
  --output-dir ai_local_planner/checkpoints/single_ppo_curriculum_resume_20261017
```

```powershell
python -m ai_local_planner.scripts.export_onnx `
  --checkpoint ai_local_planner/checkpoints/single_ppo_curriculum_20261017/best_model.pth `
  --output ai_local_planner/exported/local_planner_single_ppo.onnx

python -m ai_local_planner.scripts.evaluate_single_six `
  --onnx ai_local_planner/exported/local_planner_single_ppo.onnx `
  --max-level 5 --episodes 100 --seed-base 5100000 `
  --output ai_local_planner/logs/single_ppo_final_holdout.json

python -m ai_local_planner.scripts.benchmark_latency `
  --model ai_local_planner/exported/local_planner_single_ppo.onnx `
  --iterations 1000 --output ai_local_planner/logs/single_ppo_host_latency.json
```

`evaluate_single_six --max-level 5` đánh giá một actor duy nhất, dùng
gate đủ 5 level. Chỉ nên phát hành sau khi cả gate training **và** gate
ONNX seed độc lập đều PASS. Benchmark Windows không chứng minh <2ms trên Pi4.

## 1. Huấn luyện PPO tuần tự Level 1 → 6

```powershell
python -m pip install -r ai_local_planner/requirements.txt
python -m pytest ai_local_planner/tests -q
python -m ai_local_planner.scripts.run_train --steps 5000000 `
  --device auto --level 1 --max-level 6 --eval-episodes 100 `
  --eval-every 25000 --retention-eval --rehearsal-prob 0.25 `
  --output-dir ai_local_planner/checkpoints/ppo_six_level
```

`run_train.py` chỉ tăng cấp sau đánh giá >=90% success trên 100 episode
độc lập và xác nhận các level trước vẫn vượt ngưỡng hồi quy
(L1 >=99%, L2 >=98%, L3–6 >=90%, collision <=2%). Dữ liệu rehearsal chọn
level đã qua với xác suất 25% theo episode để giảm catastrophic forgetting.
Lưu `best_level_N.pth` (ứng viên theo level), `best_model.pth` (chỉ khi cả
level hiện tại và level trước qua gate), `latest_model.pth`, `evaluations.jsonl`.
Ngân sách 5 triệu bước không bảo đảm sẽ vượt gate hoặc tới Level 6.

**Warm-start tùy chọn từ chuyên gia đã có, theo đúng thứ tự 1→6:**

```powershell
python -m ai_local_planner.scripts.distill_locked_experts `
  --package ai_local_planner/exported/locked_scene_margin070_experimental/package.json `
  --resume ai_local_planner/checkpoints/ppo_level2_anchored_20261016/best_level_2.pth `
  --episodes-per-level 40 --dagger-episodes 20 --epochs-per-level 12 `
  --output-dir ai_local_planner/checkpoints/distill_six_stage

python -m ai_local_planner.scripts.run_train `
  --resume ai_local_planner/checkpoints/distill_six_stage/candidate_level_1.pth `
  --curriculum-warmstart-dir ai_local_planner/checkpoints/distill_six_stage `
  --steps 5000000 --max-level 6 --eval-episodes 100 --eval-every 25000 `
  --retention-eval --rehearsal-prob 0.25 `
  --output-dir ai_local_planner/checkpoints/ppo_six_level_from_warmstart
```

Giai đoạn distillation huấn luyện offline **một ActorCritic** để bắt chước
chuyên gia theo từng level, có DAgger và chia validation theo episode; nó là
**behavioral cloning, chưa phải PPO**. Các checkpoint `candidate_level_N.pth`
chỉ là warm-start. Trong lượt PPO, checkpoint N được nạp **sau khi** level N-1
qua retention gate; nếu mất năng lực cũ thì không thể tiếp tục thăng cấp.
Không tự triển khai bản candidate lên AGV.

Kiểm định một ONNX student sáu cấp (phân biệt rõ với gói nhiều expert):

```powershell
python -m ai_local_planner.scripts.export_onnx `
  --checkpoint ai_local_planner/checkpoints/distill_six_stage/candidate_level_6.pth `
  --output ai_local_planner/exported/local_planner_single_candidate.onnx

python -m ai_local_planner.scripts.evaluate_single_six `
  --onnx ai_local_planner/exported/local_planner_single_candidate.onnx `
  --episodes 100 --seed-base 3500000 `
  --output ai_local_planner/logs/single_candidate_six_gate.json

python -m ai_local_planner.scripts.benchmark_latency `
  --model ai_local_planner/exported/local_planner_single_candidate.onnx `
  --iterations 1000 --output ai_local_planner/logs/single_candidate_cpu_bench.json
```

**Lượt probe 12 teacher + 6 DAgger episode/level, 3 epoch/level** đã chạy;
single-ONNX student `local_planner_six_stage_bc_experimental.onnx` đạt lần lượt
100%, 42%, 0%, 45%, 100%, 74% success trên 100 episode/level: **FAIL**.
Không được coi candidate offline là bộ điều khiển đã nghiệm thu.

## 2. Đánh giá gói hybrid ONNX sáu cấp

Ứng viên: `exported/locked_scene_margin070_experimental/package.json`,
gồm PPO Level 1–2, BC/DAgger Level 3 và 5, reactive gap Level 4 và 6,
cùng classifier 6 scene. Có 5 bước calibration rồi khóa nhánh theo episode.
**Chưa phải PPO Actor-Critic duy nhất trên 6 cấp**.

```powershell
1..6 | ForEach-Object {
  $lv = $_
  python -m ai_local_planner.scripts.evaluate_locked_scene_onnx `
    --package ai_local_planner/exported/locked_scene_margin070_experimental/package.json `
    --level $lv --episodes 100 --seed (2600000+$lv*1000) `
    --output "ai_local_planner/logs/locked_scene_level${lv}_replication.json"
}
$gate = @()
1..6 | ForEach-Object {
  $gate += "--level$_"
  $gate += "ai_local_planner/logs/locked_scene_level${_}_replication.json"
}
python -m ai_local_planner.scripts.acceptance_gate @gate `
  --output ai_local_planner/logs/locked_scene_replication_gate.json
```

## 3. Stress test, benchmark và phần cứng

```powershell
python -m ai_local_planner.scripts.evaluate_corridor_robustness `
  --package ai_local_planner/exported/locked_scene_margin070_experimental/package.json `
  --episodes 100 --seed 2700000 `
  --output ai_local_planner/logs/locked_scene_level3_ood_replication.json

python -m ai_local_planner.scripts.benchmark_locked_scene_onnx `
  --package ai_local_planner/exported/locked_scene_margin070_experimental/package.json `
  --iterations 1000 --output ai_local_planner/logs/locked_scene_host_benchmark.json

# Test vật cản động ngoài phân phối (Level 6), KHÔNG tính vào gate tiêu chuẩn
python -m ai_local_planner.scripts.evaluate_dynamic_robustness `
  --package ai_local_planner/exported/locked_scene_margin070_experimental/package.json `
  --episodes 100 --seed 2906000 --speed-min 0.25 --speed-max 0.55 `
  --output ai_local_planner/logs/locked_scene_level6_dynamic_ood.json
```

Benchmark Windows chỉ phản ánh Windows. Pi 4 phải kiểm tra ONNXRuntime,
thời gian xử lý scan LiDAR/odometry, UART và watchdog thực tế. Vẫn bắt buộc
E-stop phần cứng độc lập; chưa cho phép đấu trực tiếp vào driver động cơ.
