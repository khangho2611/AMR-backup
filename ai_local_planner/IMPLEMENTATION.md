# AI 1 PPO Local Motion Planner — vận hành và kiểm chứng

## Trạng thái hiện tại — 17/10/2026

**Ứng viên mô phỏng 6 cấp (EXPERIMENTAL):**
`exported/locked_scene_margin070_experimental/package.json`. Hệ thống dùng
CNN phân loại scene từ 365 quan sát, hiệu chuẩn 5 chu kỳ đứng yên rồi khóa
chuyên gia đến hết episode; các file ONNX tách rời chạy qua Python supervisor.
Các thành phần: PPO Level 1–2, Behavioral Cloning/DAgger Level 3 và 5,
LiDAR reactive gap Level 4 (margin 0.12 m) và 6 (margin 0.70 m).
**Không được gọi đây là một Actor-Critic PPO duy nhất học xong 6 cấp.**

Đánh giá ONNX trên 100 episode **mỗi level**, có noise/dropout/slip/jitter,
UART delay 100 ms và random seed chưa dùng train, tối đa 600 bước/episode:

| Level | Seed | Thành công | Va chạm | Timeout |
|---|---|---:|---:|---:|
| 1 | 2001000–2001099 | 100/100 | 0 | 0 |
| 2 | 2002000–2002099 | 100/100 | 0 | 0 |
| 3 | 2003000–2003099 | 100/100 | 0 | 0 |
| 4 | 2004000–2004099 | 99/100 | 0 | 1 |
| 5 | 2005000–2005099 | 100/100 | 0 | 0 |
| 6 | 2006000–2006099 | 100/100 | 0 | 0 |

`logs/locked_margin070_onnx_acceptance_20261017.json`: **PASS trên bộ 600
episode này** với ngưỡng success từ 90–99% theo level và collision tối đa 2%.
Đây là acceptance đối với sáu *họ bản đồ trong simulator*, không chứng minh
generalization sang tất cả địa hình hoặc điều khiển an toàn trên phần cứng.

**Lặp lại độc lập trên 600 episode mới** (seed 2401000..2406099 theo level):
Level 1: **100/100**, Level 2: **99/100** (1 va chạm seed `2402016`),
Level 3: **100/100**, Level 4: **99/100** (1 timeout seed `2404091`),
Level 5: **100/100**, Level 6: **100/100**. File
`logs/locked_margin070_onnx_independent_acceptance_20261017.json`:
**PASS lần thứ hai**, cùng package, không chỉnh lại trọng số hoặc margin.
Tổng 1.200 episode: **1.197 thành công, 1 va chạm và 2 timeout**.

Kiểm tra Level 3 **OOD**, thay đổi width 0.58–0.82 m, vị trí cua, tâm và góc
khởi đầu: 99/100 thành công, 1/100 va chạm (seed `2100099`, width 0.5918 m).
Log `logs/locked_margin070_level3_ood100.json`: còn lỗi tại hẻm rất hẹp.

**Level 6 OOD nghiêm ngặt hơn:** thêm bộ kiểm thử
`scripts/evaluate_dynamic_robustness.py`: 2–4 vật cản di chuyển, tốc độ cắt
ngang 0.25–0.55 m/s (cao hơn 0.15–0.25 m/s trong curriculum), jitter vị trí,
góc đầu xe và goal. Trên 100 seed `2906000..2906099`, cấu hình **0.70 m
chỉ thành công 73/100, va chạm 27/100**; classifier chọn đúng Level 6 cả
100 episode. File `logs/locked_margin070_level6_dynamic_ood100.json`.
Tăng inflation margin lên 0.95 m trong một gói thử nghiệm riêng
`exported/locked_scene_margin095_experimental/package.json` chỉ đạt
**75/100 success, 25 va chạm** trên cùng tập; xem
`logs/locked_margin095_level6_dynamic_ood100.json`. Trên bộ chuẩn Level 6
khác (100 seed `3106000..3106099`), margin 0.95 m vẫn đạt 100/100;
file `logs/locked_margin095_level6_independent100.json`.
Vì vậy cấu hình 0.95 m
**không khắc phục được** thất bại ngoài phân phối và chưa được thay thế gói
0.70 m đã vượt fixed-curriculum gate. Cần perception đa frame để ước lượng
vận tốc tương đối và giám sát an toàn độc lập trước khi đánh giá robot thật.

**Thử nghiệm PPO thuần Level 3, tiếp nối BC/DAgger:** chạy 4.096 bước PPO
với action anchor hệ số 20 và learning rate `1e-5`; checkpoint riêng
`checkpoints/ppo_level3_anchored_probe_20261017/best_level_3.pth`.
Đánh giá deterministic 100 seed độc lập mỗi cấp (`3001000`, `3002000`,
`3003000`): Level 1 **89/100**, 11 timeout; Level 2 **99/100**, 1 va chạm;
Level 3 **100/100**. File `logs/ppo_level3_probe_gate_20261017.json`
**FAIL** vì quên Level 1 (yêu cầu >=99/100). Chỉ số Level 3 trong lúc train
cũng đạt 100/100 trước và sau PPO trên 100 seed `2803000..2803099`, nhưng
đó không chứng minh PPO học kỹ năng mới. Checkpoint này giữ là thí nghiệm,
**không được thay thế ONNX tham chiếu hoặc gói hybrid**.

Benchmark Windows CPU, 1.000 lần/model, 100 warmup:
PPO nhánh 1 p99 1.002 ms; L2 0.749 ms; L3 0.701 ms; L4 1.261 ms;
L5 0.930 ms; L6 1.361 ms; classifier 0.904 ms.
Log `logs/locked_margin070_windows_benchmark.json`. Các số này **chỉ đo
inference ONNX trên Windows**, chưa gồm LiDAR preprocessing, supervisor,
UART hay Pi 4. **Pi 4 p99 < 2ms chưa được xác nhận**.
Đặc biệt, **max latency của riêng ONNX Level 6 là 3.2859 ms**, vượt yêu cầu
nghiêm ngặt <2 ms cho mọi lần inference ngay trên host Windows; đạt p99
không tương đương bảo đảm worst-case latency.
Manifest có SHA256 riêng cho cả sáu ONNX, `trained_by_single_ppo=false`,
`real_robot_approved=false`, `pi4_latency_verified=false`.

Chạy lần lượt Level 1→6 từ thư mục gốc repo:

```powershell
1..6 | ForEach-Object {
  $lv = $_
  python -m ai_local_planner.scripts.evaluate_locked_scene_onnx `
    --package ai_local_planner/exported/locked_scene_margin070_experimental/package.json `
    --level $lv --episodes 100 --seed (2600000 + $lv * 1000) `
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

**Phần chưa đạt nguyên bản yêu cầu:** huấn luyện một mạng PPO xuyên suốt sáu
level với gate trên held-out seed; kiểm định đa hình học, vật cản động đa
phân phối; benchmark end-to-end trên Pi 4; và tích hợp E-stop/STM32 trên xe.
Các phần 4–6 của bản thí nghiệm hiện dùng chuyên gia BC hoặc thuật toán hình
học. Các kết quả cũ phía dưới ghi lại quá trình thử nghiệm, không phải
trạng thái ứng viên mới nhất.

## 1. Cài đặt và thực thi (từ thư mục gốc repository)

```powershell
python -m pip install -r ai_local_planner/requirements.txt
python -m pytest ai_local_planner/tests -q

# Huấn luyện PC/GPU: PPO 5 triệu time steps, tự chuyển cấp nếu >=90/100 thành công.
python -m ai_local_planner.scripts.run_train --steps 5000000 --device auto

# Đánh giá checkpoint trên 100 episodes có domain randomization.
python -m ai_local_planner.scripts.evaluate_policy --checkpoint ai_local_planner/checkpoints/latest_model.pth --level 1 --episodes 100

# Export sau khi đánh giá chất lượng mô hình.
python -m ai_local_planner.scripts.export_onnx --checkpoint ai_local_planner/checkpoints/latest_model.pth

# Chạy benchmark **trực tiếp trên Raspberry Pi 4**, không lấy thời gian PC thay thế.
python -m ai_local_planner.scripts.benchmark_latency --model ai_local_planner/exported/local_planner.onnx
```

`exported/local_planner.onnx` hiện được xuất từ checkpoint PPO Level 2 đã
kiểm định độc lập (xem mục 6). Đây vẫn là **mô hình nghiên cứu mô phỏng**;
không kết nối thẳng vào bộ lái xe trước khi kiểm định phần cứng và Level 3–6.

## 2. Interface cho mô phỏng và inference

- `AGVMotionEnv(level=1..6, randomize=True, max_steps=600)` có API `reset(seed=...)` và
  `step(action)` của Gymnasium. Action là `float32[2]` **normalized [-1,1]**.
- Observation là `float32[365]`, trong đó `[0:360]` là 360 ray counterclockwise
  từ phương trước của xe, `(distance_m - .12)/11.88` kẹp vào `[0,1]`; `[360]` là
  `min(goal_distance_m/10, 1)`; `[361:363]` là `sin,cos` lỗi hướng tới goal;
  `[363:365]` là `v/0.35`, `omega/1.5` được giới hạn vào miền observation.
- ONNX mean policy có input `lidar_and_goal_state` `[N,365]`, output `cmd_vel`
  `[N,2]` **vận tốc vật lý** `[v m/s, omega rad/s]`. Không scale đầu ra thêm lần nữa.
- `runtime.build_observation(...)` xây input từ dữ liệu cảm biến thực và odometry.
  `LocalPlannerRuntime(...).predict_from_sensors(...)` áp giới hạn vận tốc, gia tốc
  (`0.5 m/s²`, `2.0 rad/s²`) và stop ngưỡng phía trước `< 0.46 m`. Lớp này chưa tích hợp vào
  đường điều khiển động cơ trong `agv_unified_brain.py`.

## 3. Mô phỏng và Sim-to-Real

| Thành phần | Cách thực thi |
|---|---|
| Kinematics | Differential drive, wheel base `0.28m`, bán kính va chạm `0.20m`, midpoint integration `dt=.1s`. |
| LiDAR | Analytic ray/line-segment và ray/circle intersection, 360 tia, 0.12–12m. |
| Nhiễu | Sigma Gaussian 0.03–0.05m / episode; dropout 5% về min/max mỗi scan. |
| UART | FIFO 1-step: action ở t chỉ được áp ở t+1. |
| Bánh xe | Sai lệch hiệu suất từng bánh cố định mỗi episode, độ lớn 5–10%, dấu ngẫu nhiên. |
| Obstacle jitter | Vật cản hình trụ lệch tối đa ±2cm so với vị trí gốc mỗi bước. |
| Reward | Progress +15Δd; goal +100; collision -50; clearance, smoothness, heading và time penalty. |
| 6 levels | Corridor, circle, L-corridor 0.7m, clutter 6–10 circles, U-pocket 1.2m, 2–3 moving circles. |
| Curriculum | `90%` của **đủ 100 episode hoàn tất cùng level** để mở cấp tiếp theo. |

**Ràng buộc Level 5:** action v cố định `[0, .35]m/s`, do đó không thể lùi.
Kịch bản U cho phép quay tại chỗ rồi tiến ra. Nếu robot vật lý cần lùi,
phải thay đổi contract action, sinh lại policy và huấn luyện lại.

## 4. Những kiểm chứng đã thực hiện ngày 16/10/2026

- Smoke PPO: 4.096 bước, 15 episodes hoàn tất, **Level 1**, checkpoint
  `checkpoints/smoke_20261016_v2/latest_model.pth`.
- Deterministic mean policy, 20 episode độc lập với randomization (seed 1000..1019):
  **success 0%, collision 100%**. Kết quả nằm trong `logs/eval_smoke_level1_20261016.json`.
- ONNX Opset 14: sai số lớn nhất so với PyTorch `2.384185791015625e-07` trên 32 mẫu,
  được xác minh bởi ONNX Runtime CPU.
- CPU Windows x86-64: benchmark 1.000 lần, 100 warmup: **p99 0.422 ms**.
  File: `logs/benchmark_windows_cpu_20261016.json`. Đây **không** phải số đo Pi 4.
- `exported/local_planner.json`: SHA256 và metadata; `real_robot_approved: false`,
  `pi4_latency_verified: false`.

## 5. Điều kiện kiểm định để chạy trên xe thật

1. Tiếp tục train tới mức success rate >=90% **trên 100 episodes ở từng level**,
   đo lại trên seed chưa dùng train, cả trường hợp randomization on/off. Báo cáo
   collision rate và quãng đường / độ giật lái cho từng scenario.
2. Benchmark ONNX `p99<2ms` trên **Raspberry Pi 4 CPU** ở môi trường chạy thực,
   đo cả pre-processing và vận chuyển UART cho latency vòng điều khiển 100ms.
3. Kiểm tra thực tế C1 trả tia theo thứ tự nào, offset lắp đặt, góc 0°,
   điều kiện `None`/invalid scan, đồng bộ 10Hz và odometry bánh xe.
4. Giữ E-stop phần cứng và quản lý vòng điều khiển độc lập. Ngưỡng dừng
   software hiện là **46 cm**; vẫn cần kiểm định theo vị trí LiDAR, footprint,
   độ trễ truyền thông và quãng phanh thực tế trước khi di chuyển.
5. Mô hình hiện nhận một scan LiDAR đơn (không có lịch sử); Level 6 mô phỏng
   vật thể động nhưng chưa quan sát trực tiếp vận tốc của vật thể.

Smoke model chỉ có giá trị minh chứng tính chạy được của pipeline, **chưa được
chứng nhận đủ điều kiện điều khiển AGV**. Bản ONNX mới hơn cũng chưa được cấp
phép triển khai thực tế.

## 6. Huấn luyện và đánh giá Level 2 (16/10/2026)

Khởi tạo bằng teacher hình học Level 2 và mixed Behavioral Cloning Level 1–2.
Teacher chỉ dùng vị trí thực của vật cản trong giai đoạn sinh nhãn **offline**;
policy triển khai nhận đúng observation 365 chiều (LiDAR + goal + odometry).

| Model | Tập đánh giá | Level 1 | Level 2 | Ghi chú |
|---|---|---:|---:|---|
| Mixed BC | 100 tập, seed 200000..200099 | 100% | 99% | Baseline trước PPO |
| PPO không neo, 10.240 steps | 100 tập, seed 110000..110099 | — | 72% | Catastrophic forgetting |
| PPO không neo, 20.000 steps | 100 tập, seed 110000..110099 | — | 11% | Không chọn để export |
| PPO **có neo BC**, 10.000 steps | 100 tập, seed 110000..110099 | — | **100%** | Best validation checkpoint |
| Mixed BC | **final test** 200 tập, seed 300000..300199 | — | 98% (196/200) | 4 va chạm |
| PPO **có neo BC**, 10.000 steps | **final test** 200 tập, seed 300000..300199 | **100% (200/200)** | **99% (198/200)** | Level 2 có 2 va chạm, không timeout |

Hai va chạm cuối cùng của PPO Level 2 ở seed `300056` và `300099`.
Tỷ lệ 99% vs 98% trên 200 episode chỉ là cải thiện quan sát được; chưa đủ
bằng chứng thống kê để kết luận PPO có neo tốt hơn BC trên toàn bộ phân phối.
Đánh giá giữ domain randomization bật, hành vi mean policy deterministic,
không dùng seed final test để chỉnh hyperparameter.

Checkpoint được chọn:
`checkpoints/ppo_level2_anchored_20261016/best_level_2.pth`.
PPO được giữ gần BC bằng MSE của deterministic action từ hai actor trên
cùng rollout states (`--reference-checkpoint`, `--reference-coef 10`),
với LR `2e-5`, 2 epochs/update, KL guard `0.02`, giới hạn curriculum `--max-level 2`.
Lựa chọn `--early-stop-success-floor 0.90` dừng thử nghiệm khi held-out success
dưới ngưỡng, đồng thời bảo toàn `best_level_2.pth`.

Đóng gói ONNX: `exported/local_planner.onnx`, opset 14, input `[N,365]`,
output vật lý `[N,2]`. Parity PyTorch/ONNX:
**max absolute error = 6.556510925292969e-07**; kiểm tra SHA256 ở
`exported/local_planner.json`. Benchmark Windows AMD64: **p99 0.43928ms**
(1.000 inferences, 100 warmup), xem `logs/benchmark_ppo_level2_windows_20261016.json`.
**Chưa benchmark trên Raspberry Pi 4.**

Để tái tạo thử nghiệm fine-tuning, chạy từ root của repository:

```powershell
python -m ai_local_planner.scripts.run_train `
  --resume ai_local_planner/checkpoints/expert_level2_mixed_20261016.pth `
  --reference-checkpoint ai_local_planner/checkpoints/expert_level2_mixed_20261016.pth `
  --reference-coef 10 --steps 10000 --rollout-steps 1024 `
  --epochs 2 --batch-size 128 --learning-rate 0.00002 --seed 55231 `
  --device cpu --max-level 2 --eval-on-start --eval-every 5000 `
  --eval-episodes 100 --eval-seed 110000 --early-stop-success-floor 0.90 `
  --save-every 5000 --output-dir ai_local_planner/checkpoints/ppo_level2_anchored_20261016

python -m ai_local_planner.scripts.export_onnx `
  --checkpoint ai_local_planner/checkpoints/ppo_level2_anchored_20261016/best_level_2.pth `
  --output ai_local_planner/exported/local_planner.onnx
```

**Giới hạn nghiệm thu:** chưa đạt Level 3–6, chưa xác minh quãng phanh/footprint
ngoài đời, góc LiDAR C1 gắn thực tế, chu kỳ 10Hz end-to-end hoặc Pi4 p99<2ms.
Ngưỡng dừng software ban đầu `0.18m` đã tăng thành `0.46m`; vẫn cần kiểm định
phải hiệu chỉnh trước mọi lệnh điều khiển động cơ thật.

## 7. Kết quả ONNX closed-loop và thí nghiệm Level 3 (16/10/2026)

**Parity closed-loop Level 2** trên cùng 100 seed `300000..300099` với randomization:
PyTorch và ONNX đều đạt **98/100**, va chạm đúng `300056, 300099`, không timeout;
số bước trung bình đều là **227.4**. Đầu ra ONNX là vận tốc vật lý `[v, w]`,
phải đổi sang action chuẩn hóa trước khi nạp vào `AGVMotionEnv.step()`.
File: `logs/onnx_closed_loop_level2_20261016.json` và
`logs/pytorch_onnx_parity_seed300000_100.json`.

**Phân tích 2 va chạm Level 2:** Khi vùng trống giảm về khoảng `0.35m`,
vận tốc thực vẫn ở khoảng `0.33m/s`, robot tiếp tục đi gần tối đa vào vật cản.
Trace: `logs/level2_collision_diagnostics_20261016.json` từ
`scripts/diagnose_failures.py`. Đây là bằng chứng lỗi tránh vật cản trong mô
phỏng, chưa chứng minh ngưỡng dừng của robot ngoài đời là đủ an toàn.

**Level 3 (hành lang L rộng 0.7m):**

| Thành phần | Tập đánh giá | Success | Collision | Timeout |
|---|---:|---:|---:|---:|
| PPO Level 2 ban đầu | 10 seed `410000..410009` | 0/10 | 10/10 | 0 |
| Teacher dùng waypoint hình học | 100 seed `420000..420099` | 100/100 | 0 | 0 |
| BC hỗn hợp Levels 1–3 | Level 1, 30 seed `500000..500029` | 30/30 | 0 | 0 |
| BC hỗn hợp Levels 1–3 | Level 2, 30 seed `500000..500029` | 21/30 | 0 | 9/30 |
| BC hỗn hợp Levels 1–3 | Level 3, 30 seed `510000..510029` | 0/30 | 30/30 | 0 |

BC Level 3 học từ `58,058` mẫu, khởi tạo bằng PPO Level 2 và train 12 epoch;
checkpoint thử nghiệm `checkpoints/bc_level3_multilevel_20261016.pth`.
`validation_mse=0.01115` của thử nghiệm này được tính bằng chia ngẫu nhiên
**theo frame**, do đó có rò rỉ tương quan giữa frame của cùng episode.
Không được dùng MSE này để khẳng định khả năng tổng quát hóa. Mã BC hiện hành
đã đổi sang **chia validation theo episode** cho các thử nghiệm tiếp theo.
Trace Level 3 (`logs/bc_level3_failure_trace_20261016.json`) cho thấy policy
quay sai chiều khi tới cua và đâm vào tường; phải thu thập trạng thái lệch
quỹ đạo để huấn luyện DAgger.

Đã bổ sung DAgger và reference on-policy replay vào
`scripts/pretrain_obstacle_expert.py`:

- `--dagger-episodes`: chạy policy mới tại Level 3 và lấy nhãn chuyên gia trên
  chính các trạng thái mà policy gặp (chuyên gia chỉ dùng privileged pose offline).
- `--reference-checkpoint` + `--reference-replay-episodes`: chạy policy Level 2
  đã kiểm chứng tại Level 1 và 2 để tạo dữ liệu giữ kỹ năng cũ.
- Chia validation theo **nguyên episode**, tránh frame liền kề nằm ở hai tập.

Thử nghiệm DAgger + replay đã hoàn tất, tạo checkpoint
`checkpoints/bc_level3_dagger_replay_20261016.pth` (60.002 mẫu;
validation theo episode: MSE `0.00669`). Lệnh tái tạo:

```powershell
python -m ai_local_planner.scripts.pretrain_obstacle_expert `
  --resume ai_local_planner/checkpoints/bc_level3_multilevel_20261016.pth `
  --reference-checkpoint ai_local_planner/checkpoints/ppo_level2_anchored_20261016/best_level_2.pth `
  --output ai_local_planner/checkpoints/bc_level3_dagger_replay_20261016.pth `
  --level1-episodes 0 --level2-episodes 0 --level3-episodes 100 `
  --reference-replay-episodes 50 --dagger-episodes 120 `
  --epochs 14 --batch-size 256 --learning-rate 0.00005 --seed 71717 --device cpu
```

**Kết quả kiểm tra deterministic closed-loop (17/10/2026):** 100 seed mới
`620000..620099`, bật domain randomization, tối đa 600 bước/episode:

| Checkpoint | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| PPO Level 2 tham chiếu | 100/100 success | 100/100 success | chưa đánh giá trong loạt này |
| BC + DAgger + replay | 86/100 success, 14 timeout | 92/100 success, 8 timeout | **100/100 success, 0 collision** |

BC + DAgger thành công với hình học Level 3 hiện tại, nhưng **chưa được chấp
nhận để thay thế mô hình** vì regression Levels 1–2. Trace:
`logs/dagger_level1_timeout_20261017.json`,
`logs/dagger_level2_timeout_20261017.json`. Các timeout chủ yếu do giảm tốc
hoặc quay sai hướng, không phải do va chạm. Dữ liệu chi tiết trong các file
`logs/dagger_eval_level{1,2,3}_20261017.json`.

Đã thêm `scripts/acceptance_gate.py`: bắt buộc >=100 episodes randomized cho
ba level; Level 1 success >=99%, Level 2 >=98%, Level 3 >=90%; collision <=2%
ở mỗi level. Chạy:

```powershell
python -m ai_local_planner.scripts.acceptance_gate `
  --level1 ai_local_planner/logs/dagger_eval_level1_20261017.json `
  --level2 ai_local_planner/logs/dagger_eval_level2_20261017.json `
  --level3 ai_local_planner/logs/dagger_eval_level3_20261017.json `
  --output ai_local_planner/logs/dagger_simulation_gate_20261017.json
```

Gate hiện báo **FAIL**, đúng với regression. Gate chỉ xét mô phỏng cố định
Level 1–3, không thay cho nghiệm thu phần cứng, các địa hình chưa thấy hoặc
benchmark Pi 4. Giữ nguyên `exported/local_planner.onnx` và checkpoint PPO
Level 2 đã xác minh cho tới khi ứng viên mới đạt gate.

### Thí nghiệm cân bằng lại replay (17/10/2026)

Huấn luyện tiếp từ `bc_level3_dagger_replay_20261016.pth` với 110 reference
episodes mỗi Level 1–2, 40 expert episodes Level 3 và 40 DAgger episodes;
7 epoch, learning rate `1e-5`, tổng 66.679 samples. Checkpoint thử nghiệm:
`checkpoints/bc_level3_rebalanced_20261017.pth`.

Đánh giá 100 seed `630000..630099`, domain randomization bật:

| Level | Thành công | Va chạm | Timeout |
|---|---:|---:|---:|
| 1 | 100/100 | 0 | 0 |
| 2 | 99/100 | 1/100 (seed `630044`) | 0 |
| 3 | **0/100** | **100/100** | 0 |

Loạt này **không được chấp nhận**: hồi phục Levels 1–2 nhưng làm mất hoàn toàn
năng lực cua góc hẹp Level 3. `validation_mse=0.1153` đồng thời cho thấy độ
lệch nhãn lớn. Dữ liệu: `logs/rebalanced_eval_level{1,2,3}_20261017.json`.
Đây là dấu hiệu tương tác giữa các tác vụ và/hoặc nhãn expert thiếu nhất quán
với thông tin observation; cần thử objective chống quên hoặc chuyển hướng
kiến trúc trước khi huấn luyện lại. Không thay thế checkpoint PPO gốc hay
model ONNX đã kiểm chứng.

## 8. Thử nghiệm kết hợp 2 policy theo LiDAR (17/10/2026)

Do một mạng BC bị **catastrophic forgetting** giữa Levels 1–2 và Level 3,
thử nghiệm một bộ định tuyến heuristic dùng **duy nhất observation 365-D**:
đếm số tia LiDAR dưới 0.72m ở mỗi phía, trong hai cung `55:125` và
`235:305`. Nếu **cả hai bên** có >=18 tia gần, dùng policy Level 3 DAgger;
các trạng thái còn lại dùng PPO Level 2 đã xác minh. Mô hình định tuyến
được thực hiện bằng `models/hybrid_policy.py`; mã đánh giá bằng
`scripts/evaluate_hybrid.py`. Đây là ensemble chuyên gia (mỗi nhánh đã học
trước), **chưa phải một actor PPO duy nhất**, và bộ nhận diện hành lang hiện
còn là heuristic.

**Kết quả mô phỏng 100 seed mới `660000..660099`:**

| Policy / backend | Level 1 | Level 2 | Level 3 |
|---|---:|---:|---:|
| Router PyTorch | **100/100** | **100/100** | **100/100** |
| Router ONNXRuntime CPU | **100/100** | **100/100** | **100/100** |

Mọi episode đều bật noise/dropout/slip/jitter và trễ lệnh 100ms, không va chạm
hay timeout trong 300 episode. Logs:
`logs/hybrid_eval_level{1,2,3}_20261017.json` và
`logs/hybrid_onnx_eval_level{1,2,3}_20261017.json`.
`logs/hybrid_onnx_simulation_gate_20261017.json` xác nhận **PASS** theo
ngưỡng nghiệm thu mô phỏng Levels 1–3. Các Level 4–6 chưa được nghiệm thu.

ONNX experimental xuất tại `exported/local_planner_hybrid_experimental.onnx`
(opset 14), manifest cùng tên `.json`. Sai số tối đa PyTorch/ONNX trong
64 observation thử nghiệm (bao gồm hai nhánh và ngưỡng chuyển nhánh)
`1.13249e-6`. Benchmark Windows AMD64: **p99=0.60803ms** (1.000 lần suy luận,
100 warmup); chi tiết `logs/hybrid_windows_benchmark_20261017.json`.
**Chưa đo trên Raspberry Pi 4**: ONNX có hai mạng Conv1D nên p99 Windows không
chứng minh đáp ứng <2ms trên Pi. `real_robot_approved=false`.

Stress test biến thiên hình học hành lang:

| Điều kiện Level 3 chưa có trong training | Success | Collision |
|---|---:|---:|
| Chỉ đổi width 0.62–0.80m (100 seed `670000..670099`) | 100/100 | 0 |
| Width 0.58–0.82m, dịch góc cua ±0.30m, tâm ±0.12m, yaw đầu ±0.12rad (100 seed `680000..680099`) | **97/100** | **3/100** |

Ba thất bại ở widths 0.5835m, 0.5996m, 0.5970m (seeds `680035`, `680045`,
`680065`); log và bộ kiểm thử tái lập bằng
`scripts/evaluate_corridor_robustness.py` và
`logs/hybrid_level3_shift_ood_reproduced_20261017.json`.
Vì vậy **chưa đạt ngưỡng va chạm <=2% trên stress test khắc nghiệt**; cần
huấn luyện/kiểm chứng thêm khi độ rộng thực tế có thể dưới 0.62m.

Tái xuất model thử nghiệm (chạy từ repository root):

```powershell
python -m ai_local_planner.scripts.export_hybrid_onnx `
  --reference ai_local_planner/checkpoints/ppo_level2_anchored_20261016/best_level_2.pth `
  --specialist ai_local_planner/checkpoints/bc_level3_dagger_replay_20261016.pth `
  --output ai_local_planner/exported/local_planner_hybrid_experimental.onnx
```

**Trước khi chạy phần cứng:** cần thiết kế lại independent E-stop với bán kính
xe 0.20m, độ trễ UART 100ms, phanh 0.5m/s² và false returns LiDAR. Ngưỡng
runtime hiện dùng 0.46m, vẫn chưa được xác nhận an toàn thực tế; chỉ được dùng
model sau khi có nghiệm thu watchdog/footprint, cấu hình LiDAR thực tế, và
benchmark p99 trên Pi4. Bản `exported/local_planner.onnx` gốc được giữ nguyên.

### Baseline chưa huấn luyện Levels 4–6

ONNX hybrid hiện chỉ mới học thành phần Levels 1–3. Chạy 30 seed độc lập
`690000..690029` để biết mức độ còn thiếu trước khi lên curriculum:

| Level | Success | Collision | Timeout |
|---|---:|---:|---:|
| 4 – Cluttered slalom | 9/30 (30.0%) | 21/30 (70.0%) | 0 |
| 5 – U-pocket dead end | 2/30 (6.7%) | 0 | 28/30 (93.3%) |
| 6 – Dynamic obstacles | 22/30 (73.3%) | 8/30 (26.7%) | 0 |

Log tại `logs/hybrid_onnx_baseline_level{4,5,6}_20261017.json`.
Đây là chỉ số **baseline**, hoàn toàn chưa đủ để chứng nhận Levels 4–6.
Cần xây dựng expert/curriculum bổ sung và đánh giá lại trên seed độc lập.

## 9. Thử nghiệm ONNX đủ sáu kịch bản và stress test (17/10/2026)

Gói `exported/locked_scene_margin070_experimental/package.json` giữ nguyên
observation 365-D, 2 action liên tục, ONNX opset 14 nhưng là **scene classifier
và nhiều expert**, khóa nhánh sau 5 frame đứng yên; không phải một actor PPO
duy nhất được huấn luyện xuyên suốt sáu level.

Hai loạt đánh giá 100 episode/level độc lập, domain randomization bật:

| Loạt seed | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---:|---:|---:|---:|---:|---:|
| 2001000..2006099, theo level | 100 | 100 | 100 | 99 | 100 | 100 |
| 2401000..2406099, theo level | 100 | 99 | 100 | 99 | 100 | 100 |

Tổng **1.197/1.200 thành công**, một collision và hai timeout. Cả hai gate
kiểm tra riêng đều PASS: `logs/locked_margin070_onnx_acceptance_20261017.json`
và `logs/locked_margin070_onnx_independent_acceptance_20261017.json`.
Đây chỉ là kết quả trên **họ hình học bản đồ mô phỏng cố định**.

- Level 3 dịch chuyển hành lang: `99/100`, một va chạm;
  `logs/locked_margin070_level3_ood100.json`.
- Level 6 OOD gồm 2–4 vật thể chuyển động nhanh hơn: **73/100 thành công,
  27 va chạm**; `logs/locked_margin070_level6_dynamic_ood100.json`.
- Biến thể tăng biên bù vật cản lên 0.95m chỉ đạt **75/100** trên Level 6 OOD;
  `logs/locked_margin095_level6_dynamic_ood100.json`. Chưa thể giải quyết
  thiếu sót này bằng tăng margin đơn thuần.

Benchmark ONNX Windows, 1.000 inference/model:
p99 dao động **0.701–1.361 ms** với 6 nhánh actor; classifier p99
**0.904 ms**. Chi tiết `logs/locked_margin070_windows_benchmark.json`.
Không cộng các số p99 riêng thành số latency end-to-end; thời gian chạy trên
Raspberry Pi 4 **chưa được đo**, do đó không xác nhận yêu cầu `<2ms` trên Pi.

## 10. PPO tuần tự có rehearsal và chống quên (17/10/2026)

Đường huấn luyện một PPO (`scripts/run_train.py`) hỗ trợ `--rehearsal-prob`
để bổ sung episode từ level trước; mặc định `--retention-eval` kiểm tra đầy đủ
các level 1..N trên 100 episode/level trước khi cấp phép thăng cấp N→N+1.
Gate: Level 1 >=99%, Level 2 >=98%, Level 3–6 >=90% thành công; tất cả phải
<=2% collision; đủ 100 episode randomization cho từng level. Gate được dùng
cả cho lưu `best_model.pth`. Checkpoint `best_level_N.pth` chỉ là ứng viên
theo level, **có thể làm suy giảm level cũ**. `success_rate_100` trong CSV
được tính riêng theo level, tránh trộn thống kê rehearsal.

Checkpoint PPO Level 3 thử nghiệm
`checkpoints/ppo_level3_anchored_probe_20261017/best_level_3.pth`
đạt Level 3 100/100 nhưng dưới ngưỡng giữ kỹ năng cũ.
Một lượt đánh giá độc lập khác tại seed 3203000 cho Level 3 100/100,
Level 1 92/100 và Level 2 95/100; gate **FAIL** và không sinh
`best_model.pth` trong
`checkpoints/ppo_level3_retention_guard_smoke_20261017/`.
Chưa có checkpoint **một PPO duy nhất** qua đủ sáu cấp và chưa được phép
xuất một ONNX duy nhất với nhãn sẵn sàng triển khai.

Thêm `scripts/distill_locked_experts.py`: thu thập teacher rollouts và
DAgger theo trình tự 1→6, lấy nhãn từ expert ONNX ứng với cấp đang huấn luyện.
Student là **một** `ActorCritic` chỉ nhận observation 365 chiều; tập replay
được cân bằng theo cấp và chia train/validation theo **episode**, tránh
rò rỉ frame kề nhau. Mỗi giai đoạn tạo `candidate_level_N.pth` và
`distillation_report.json`. Đây là bước **behavioral cloning để khởi tạo**,
không thay cho PPO, không chứng minh vận hành được. Tùy chọn
`--curriculum-warmstart-dir` trong `run_train.py` chỉ nạp candidate cấp N
khi cấp N-1 đã vượt acceptance gate, sau đó tiếp tục PPO và kiểm tra lại
tất cả cấp trước.

### Thử nghiệm distillation sáu giai đoạn (17/10/2026)

Khởi tạo từ PPO Level 2; tại mỗi level 1→6 thu 12 episode teacher, 6 episode
DAgger, tối đa 3.500 frame/level, 3 epoch; domain randomization bật. Teacher
thành công `12/12` tại từng level gốc, nhưng **một student duy nhất** không
giữ được mọi kỹ năng. Checkpoint cuối:
`checkpoints/distill_six_stage_probe_20261017/candidate_level_6.pth`.

ONNX experimental `exported/local_planner_six_stage_bc_experimental.onnx`
(opset 14, input `[N,365]`, output `[N,2]`), sai số PyTorch/ORT tối đa
`7.15e-7` trên 32 mẫu; benchmark Windows AMD64 1000 lần p99 `0.1071ms`,
**không đại diện Pi4**. Đánh giá ONNX closed-loop trên **100 seed/level**:

| Level | Success | Collision | Gate |
|---|---:|---:|---|
| 1 | 100% | 0% | PASS |
| 2 | 42% | 58% | FAIL |
| 3 | 0% | 100% | FAIL |
| 4 | 45% | 55% | FAIL |
| 5 | 100% | 0% | PASS |
| 6 | 74% | 26% | FAIL |

Tổng `361/600`, gate sáu cấp **FAIL**. Kết quả đầy đủ:
`logs/single_six_stage_bc_onnx_gate_20261017.json`, benchmark
`logs/single_six_stage_bc_windows_latency_20261017.json`. Tất cả output đều
đánh dấu **experimental**; không thay thế `exported/local_planner.onnx`
hay gói hybrid đã đạt gate mô phỏng cố định. Loss MSE thấp trên tập validation
không bảo đảm điều khiển vòng kín thành công; cần nghiên cứu kiến trúc thích ứng
theo ngữ cảnh, giảm xung đột nhãn và cải thiện tổng quát hóa trước khi chọn PPO
duy nhất làm bộ điều khiển xe thật.

**Thử nghiệm PPO warm-start có gate thực (2.048→8.192 steps):** khởi tạo
`candidate_level_1.pth`, qua gate Level 1 `100/100` tại step 2.048;
chuyển đúng tuần tự sang candidate Level 2, qua gate Level 2 `99/100`
và giữ Level 1 `100/100` tại step 4.096. Sau đó nạp candidate Level 3,
chạy PPO + rehearsal tới 8.192 steps; Level 3 vẫn `0/100` và `100/100`
collision, trong khi Levels 1–2 giữ `100/100`. Vì vậy **không lên Level 4**.
Log checkpoint tại `checkpoints/ppo_six_stage_warmstart_smoke_20261017/`.
`best_model.pth` trong thư mục này chỉ đủ gate Levels 1–2; `latest_model.pth`
thuộc Level 3 chưa được chấp nhận. Thử nghiệm không chứng minh hội tụ PPO
hoàn chỉnh sau ngân sách lớn hơn.

Một thử nghiệm PPO Level 3 có neo và rehearsal 2.048 bước từ checkpoint
Level 3 tốt hơn cho hình học cua đạt L3 `100/100`, nhưng L1 `84/100`,
L2 `92/100` nên vẫn FAIL retention; log
`checkpoints/ppo_level3_rehearsal_smoke_20261017/evaluations.jsonl`.

## 11. Thí nghiệm kiến trúc 30 cung và teacher anchor đúng level (17/10/2026)

- `models/actor_critic.py`: `AvgPool1d(3,3)` trên feature map LiDAR 90
  vị trí tạo **30 cung**; `Linear(960,128)`, fusion
  `Linear(160,128)->ReLU->Linear(128,128)->ReLU` và actor/critic 128-D.
  `MeanPolicy` giữ nguyên ONNX opset14 và contract 365->2.
- Cho phép load checkpoint 10 cung bằng phép nhúng trọng số sang 30 cung;
  lớp đầu lấy trung bình ba cung liên tiếp (chia 3), 64 latent cũ nằm trong
  64 kênh đầu; head khởi tạo không phụ thuộc 64 kênh mới. So sánh parity
  giữa legacy và migrated có kiểm thử. Adam được làm mới khi upgrade.
- `PPOAgent.set_reference_policy(package.json, coef)` khởi tạo các chuyên gia
  ONNX của `LockedSceneONNXAgent`. Mỗi transition chứa một nhãn chuẩn hóa
  `[a_v,a_w]` từ chuyên gia khớp `env.level`, lưu cùng rollout để tránh
  nhầm nhãn khi minibatch PPO trộn Level 1–5. Teacher chỉ tham gia offline:
  **mô hình student ONNX không chứa router, level ID hay teacher**.
  Kết quả 1197/1200 trước đây là **ensemble, không phải teacher tối ưu 100%**;
  imitation loss vẫn có thể xung đột với PPO gradient.
- `run_train.py` mặc định dùng package teacher khi file tồn tại, hỗ trợ
  `--init-from` warm-start weights và `--reference-package`; rehearsal 35%,
  retention 100 episodes/level; `best_model.pth` chỉ được lưu khi đã qua gate
  level hiện tại và toàn bộ level cũ. Export có tên
  `local_planner_single_ppo.onnx` từ chối checkpoint chưa có bằng chứng qua
  tất cả gate Level 1–5; lệnh có trong `scripts/README.md`.
- `acceptance_gate.py` và `evaluate_single_six.py` hỗ trợ xét chính xác
  5 level ngoài 3/6 level cũ, seed ONNX độc lập so với seed training.

**Kết quả xác thực mã:** 44 pytest PASS; smoke test ONNX opset14,
PyTorch/ORT parity và kiểm tra không được export model sản phẩm khi thiếu gate.

**Lượt PPO 200.000 bước đang được kiểm định:**
`checkpoints/single_ppo_curriculum_20261017/`, warm-start trọng số
`ppo_level2_anchored_20261016/best_level_2.pth`, train lại từ Level 1,
teacher package `locked_scene_margin070_experimental` và seed gate 4000000.
Kết quả gate tính từ `evaluations.jsonl` (100 episodes/level, randomization):

| Training step | Level | Success | Collision | Retention | Verdict |
|---:|---:|---:|---:|---|---|
| 5.120 | 1 | 100/100 | 0/100 | n/a | PASS, lên L2 |
| 10.240 | 2 | 99/100 | 1/100 | L1 = 100/100 | PASS, lên L3 |
| 15.360 | 3 | 0/100 | 100/100 | FAIL | FAIL, ở lại L3 |
| 20.480 | 3 | 0/100 | 100/100 | FAIL | FAIL, ở lại L3 |
| 25.600 | 3 | 0/100 | 100/100 | L1,L2 PASS | FAIL, ở lại L3 |

Lượt train có ngân sách cấu hình 200.000 bước; bảng là **số liệu đo được
tới 25.600 bước**, không phải dự đoán kết quả cuối cùng. Chưa có bằng chứng
Level 3–5 đạt ngưỡng; không được coi đây là nghiệm thu cuối, và chưa xác nhận
latency Raspberry Pi 4 <2ms hay độ an toàn robot thật.

Lượt này đã được ngắt ở **30.720 bước / 200.000 bước** sau khi Level 3 vẫn
không đạt gate. Checkpoint có thể resume gần nhất:
`checkpoints/single_ppo_curriculum_20261017/best_level_3.pth`
(25.600 bước, Level 3; ứng viên FAIL gate). `best_model.pth` ở 10.240 bước
chỉ qua Level 1+2. Gọi export tên sản phẩm bằng checkpoint này nhận
`ValueError: Official single PPO export requires passing the full randomized
100-episode L1-L5 checkpoint gate with 30-sector architecture`, nên
**không có** `exported/local_planner_single_ppo.onnx`; không có benchmark
hay đánh giá ONNX nghiệm thu để công bố. Lệnh resume với output-dir mới
nằm trong `scripts/README.md`. Pytest sau cập nhật cuối: **44 PASS**.

### Thử nghiệm mở rộng một ActorCritic từ Level 1–3 lên Level 1–5 (17/10/2026)

`scripts/repair_retention.py --max-level 5` nay hỗ trợ teacher/DAgger cho cả
năm level, `--episode-budgets 15 25 25 40 35` (tổng số episode thu thập mỗi
level, chia gần đều teacher và student), replay imitation giữ kỹ năng L1–L3,
trọng số 3× cho vật cản gần ở L4 và trạng thái kẹt chữ U ở L5. Các teacher
checkpoint 10-cung được nạp bằng `PPOAgent.initialize_from` để nhúng trọng số
sang mạng 30-cung; có thể thay bằng specialist ONNX đã kiểm tra SHA. Mọi
student vẫn nhận `[N,365]` và xuất action chuẩn hóa `[N,2]` qua **một**
`ActorCritic`; đây là **DAgger/behavioral cloning fine-tune**, không phải
minh chứng một lượt PPO mới đã hội tụ.

- Baseline không bị ghi đè:
  `checkpoints/retention_level2_diverse_20261017/retention_candidate.pth`.
  Báo cáo có trước `logs/diverse_heldout_20261017_gate_l1_l3.json` đạt
  L1=100/100, L2=99/100, L3=99/100 trên **seed của lần trước**.
- Vòng thử với teacher `.pth` gốc L4 chỉ thành công 16/20 episode thu thập
  (80%), trong khi specialist `locked_scene_margin070_experimental/`
  `gap_level4_margin012.onnx` đạt 20/20 trên cùng seed; specialist Level 5
  `bc_level5.onnx` cũng đạt 20/20. Lượt thử teacher `.pth` đã dừng sớm khi
  pilot Level 2 giảm còn 6/15, không có gate nghiệm thu.
- Vòng chạy hoàn chỉnh 6 epochs, LR=4e-6, 90 updates/epoch, batch=128,
  rehearsal loss L1–L3 nhân 6, nguồn teacher ONNX kể trên: lưu tại
  `checkpoints/retention_l1_l5_strong_teachers_20261017/`.
  Model được chọn theo **pilot 15 episode/level** là `candidate_epoch_1.pth`,
  sau đó kiểm định 100 episode/level bằng seed bắt đầu lần lượt
  8301000, 8302000, 8303000, 8304000, 8305000.

| Level | Thành công / 100 | Va chạm / 100 | Gate |
|---|---:|---:|---|
| 1 | 100 | 0 | PASS |
| 2 | 91 | 9 | FAIL (yêu cầu >=98, va chạm <=2) |
| 3 | 100 | 0 | PASS |
| 4 | 56 | 44 | FAIL (yêu cầu >=90, va chạm <=2) |
| 5 | 100 | 0 | PASS |

Nguồn số liệu: `checkpoints/retention_l1_l5_strong_teachers_20261017/retention_report.json`;
log huấn luyện `logs/retention_l1_l5_strong_teachers_20261017_train.log`.
`all_gates_passed=false`, nên checkpoint `retention_candidate.pth` được đánh
dấu `independently_gated=false`, `eligible_for_real_robot=false`.

**Kết luận nghiệm thu:** chưa có **một** ActorCritic vượt gate 5 level.
`export_onnx.py` từ chối tên sản phẩm
`exported/local_planner_single_actor_l1_l5.onnx` nếu thiếu báo cáo gate 100
episode/level của chính checkpoint được xuất. Không xuất ONNX chính thức,
không chạy benchmark P99 cho bản chưa đạt; đặc biệt chưa có kết quả Pi 4.
Việc Level 5 đạt 100% nhưng Level 2 suy giảm 9% và Level 4 mới đạt 56%
cho thấy cần nghiên cứu chống quên kỹ năng theo trạng thái và tăng khả năng
phân biệt hành vi slalom của actor, thay vì chọn mô hình theo MSE offline.
Sau cập nhật: **58 pytest PASS**; thử xuất ONNX chính thức trực tiếp từ
checkpoint không đạt gate đã bị chặn bằng `ValueError`, không tạo file ONNX.

### Thí nghiệm DAgger hai giai đoạn L2→L4 (18/10/2026)

- Mã mới: `scripts/repair_stages_l2_l4.py`, gọi bằng
  `scripts/repair_retention.py --resume ... --level2-weight 5.0
  --level4-weight 4.0 --perturbation-prob 0.15 --epochs 6
  --learning-rate 0.000012 --device cpu`. Đây là **DAgger/BC**;
  không được gọi là lượt PPO huấn luyện mới.
- Baseline L1–L5 trước sửa:
  `checkpoints/retention_l1_l5_strong_teachers_20261017/retention_candidate.pth`.
  Checkpoint L1–L3 đã qua gate trước đây dùng làm teacher bảo toàn L1/L3.
- Stage A: 40 episode L2 trên seed mới + 9 failure seed phát hiện từ lần
  kiểm thử trước; tăng sample weight 5× trong vùng tiếp cận 0,8–2,2m
  hoặc khi chênh hành động teacher/student >0,15. Replay L1 15, L3 20,
  L5 20 episodes. **Gate riêng Stage A: PASS**, 100 episode/level
  (đều bật domain randomization):

  | Level | Thành công | Va chạm | Kết quả |
  |---|---:|---:|---|
  | 1 | 100/100 | 0/100 | PASS |
  | 2 | 99/100 | 1/100 | PASS |
  | 3 | 99/100 | 1/100 | PASS |
  | 5 | 100/100 | 0/100 | PASS |

  Báo cáo `checkpoints/single_model_l1_l5_final_20261018/stage_A_gate.json`.
- Stage B: thu 50 episode DAgger Level 4, nhiễu góc lái ±0,3 rad/s tại
  15% bước, tăng sample weight 4× tại vật cản dưới 0,45m và replay
  L1–L3/L5. Trên tập thu thập L4, **99,13%** frame có chênh hành động
  giữa student và teacher >0,15. Đây là dấu hiệu xung đột hành vi mạnh.
- Chọn epoch tốt nhất bằng pilot **15 episode/level**, sau đó đánh giá
  **100 episode độc lập/level** tại seed 9401000–9405000:

  | Level | Thành công | Va chạm | Kết quả |
  |---|---:|---:|---|
  | 1 | 100/100 | 0/100 | PASS |
  | 2 | 56/100 | 44/100 | FAIL |
  | 3 | 97/100 | 3/100 | FAIL do va chạm >2% |
  | 4 | 59/100 | 40/100 | FAIL |
  | 5 | 100/100 | 0/100 | PASS |

  File lưu trữ `logs/first_attempt_dagger_20261018/single_actor_l1_to_l5_final_acceptance.json`,
  cùng `logs/first_attempt_dagger_20261018/final_eval_l1.json`…`final_eval_l5.json`;
  ứng viên được lưu
  `checkpoints/single_model_l1_l5_final_20261018/retention_candidate.pth`.
  Gate kết luận `simulation_gate_passed=false` và metadata
  `independently_gated=false`; **không xuất ONNX chính thức**.
- Teacher ONNX Level 4 (`gap_level4_margin012.onnx`) được kiểm tra trên
  100 seed khác: thành công **99/100**, va chạm **0/100**, timeout 1/100.
  Khoảng cách teacher–student hiện tại là vấn đề chưng cất đa nhiệm và
  bảo toàn kỹ năng, chưa có bằng chứng nghiệm thu Level 4 của single actor.
- Lượt khắc phục tiếp theo dùng **projection of conflicting gradients**:
  khi gradient L4 ngược hướng gradient của L1/L2/L3/L5, loại bỏ thành phần
  gây tăng loss cũ ở xấp xỉ bậc một (bật `--gradient-surgery`). Trong 6 epoch
  Stage B có **84–90/90 cập nhật mỗi epoch** bị xung đột. Kết quả gate mới
  trên 100 episode/level, seed 10301000–10305000:

  | Level | Thành công | Va chạm | Kết quả |
  |---|---:|---:|---|
  | 1 | 100/100 | 0/100 | PASS |
  | 2 | 98/100 | 2/100 | PASS |
  | 3 | 99/100 | 1/100 | PASS |
  | 4 | 53/100 | 43/100 (4 timeout) | FAIL |
  | 5 | 100/100 | 0/100 | PASS |

  Checkpoint `checkpoints/single_model_l1_l5_pcgrad_20261018/retention_candidate.pth`;
  báo cáo `logs/pcgrad_dagger_20261018/`. Gate chạy lại bằng
  `scripts/acceptance_gate.py` trả **exit code 1** như kỳ vọng; file
  `logs/single_actor_l1_to_l5_final_acceptance.json` hiện phản ánh lượt
  PCGrad. Trộn tuyến tính trọng số A→B ở α=0..1 trên pilot 15 episode/level
  cũng không phục hồi Level 4; kết quả lưu `interpolation_pilot.json`.
- **Đến cuối ngày 18/10/2026: 64/64 pytest PASS.** Hiện chỉ có
  checkpoint thử nghiệm; do Level 4 chưa đạt, file sản phẩm
  `exported/local_planner_single_actor_l1_l5.onnx` **chưa được tạo**, chưa
  benchmark p99, chưa xác minh phần cứng Raspberry Pi 4. Không công bố
  thuật toán đã nghiệm thu hay triển khai lên AGV thật.

### Sửa Stage B: tiếp cận slalom sớm và rollout hỗn hợp (18/10/2026)

`scripts/repair_stages_l2_l4.py` hiện tính khoảng cách LiDAR robust theo
phân vị 15% trên dải ±60°; mẫu Level 4 được tăng trọng số 5× khi cách vật
cản 0,5–2,2 m, 6× khi dưới 0,5 m, và thêm 5× khi độ lệch action teacher–student
vượt 0,15. Rollout DAgger thi hành lệnh teacher với xác suất 0,5 hoặc khi
student có nguy cơ đâm ở cự ly <1 m; phần còn lại là lệnh student với xác suất
15% nhiễu lái ±0,3 rad/s. Loss phạt quá tốc gấp 3 lần khi teacher ra lệnh
chạy chậm. Các hành động luôn được chặn trong [-1,1].

Trên 50 episode thu thập Level 4, rollout **có teacher hỗ trợ** đạt 50/50,
không va chạm (15.497 frame; teacher thi hành 56,72% số bước). Đây là số liệu
thu thập demonstration, **không phải** kết quả tự lái của student.

Lượt thứ nhất dùng `--stage-b-only`, 6 epoch, LR=1,5e-5, 90 update/epoch,
`--old-loss-threshold 0.015`, projection-relaxation=0.5. Không có cập nhật
gradient nào thực sự kích hoạt phép chiếu (`gradient_conflict_updates=0`
ở cả 6 epoch); fine-tune làm suy giảm nặng L2/L3. Nghiệm thu độc lập đủ
100 seed/level (domain randomization bật, seed bắt đầu 10601000–10605000):

| Level | Thành công / 100 | Va chạm / 100 | Timeout / 100 | Gate |
|---|---:|---:|---:|---|
| 1 | 100 | 0 | 0 | PASS |
| 2 | 78 | 22 | 0 | FAIL |
| 3 | 71 | 29 | 0 | FAIL |
| 4 | 64 | 32 | 4 | FAIL |
| 5 | 100 | 0 | 0 | PASS |

Checkpoint thử nghiệm:
`checkpoints/single_model_l1_l5_slalom_resolved_20261018/retention_candidate.pth`.
Log được bảo toàn trong `logs/slalom_recovery_unprojected_20261018/`;
`simulation_gate_passed=false` và checkpoint không được cấp phép xuất ONNX.
Kết quả ở seed khác so với baseline không đủ để khẳng định mức cải thiện
nhân quả theo cặp. Vì vậy, ngưỡng chiếu gradient mặc định của runner được
đổi sang `0.0` để bảo vệ retention khi phát hiện gradient xung đột; tham số
CLI vẫn cho phép thử ngưỡng khác có chủ đích.

Sau thay đổi, **67/67 pytest PASS**. Chưa có minh chứng Gate L1–L5 toàn bộ
PASS và chưa có benchmark Raspberry Pi 4; không được xuất sản phẩm chính thức.

### Kiểm định gradient projection có ràng buộc (18/10/2026)

Chạy lại Stage B từ checkpoint PCGrad với `--old-loss-threshold 0`
và `--gradient-projection-relaxation .5`. Phép chiếu phát hiện gradient
xung đột trong **90/90** cập nhật tại **mỗi** trong 6 epoch. Epoch 2 có
pilot tốt nhất nhưng Gate cuối cùng (100 episode/level, randomization bật,
seed bắt đầu 10901000–10905000) vẫn **FAIL**:

| Level | Thành công / 100 | Va chạm / 100 | Timeout / 100 | Gate |
|---|---:|---:|---:|---|
| 1 | 100 | 0 | 0 | PASS |
| 2 | 89 | 11 | 0 | FAIL |
| 3 | 81 | 19 | 0 | FAIL |
| 4 | 53 | 37 | 10 | FAIL |
| 5 | 100 | 0 | 0 | PASS |

Checkpoint: `checkpoints/single_model_l1_l5_constrained_slalom_20261018/retention_candidate.pth`.
Báo cáo, seed thất bại và metadata đã được **sao lưu riêng** tại
`logs/slalom_recovery_constrained_20261018/`. DAgger thu 50/50 episode L4
thành công **có teacher can thiệp trong 56,72% bước**, do đó không thể dùng
để khẳng định student độc lập thành công. Ở các frame L4 có **92,25%**
trường hợp hành động teacher–student chênh >0,15. Không hạ chuẩn Gate.

### Thử nghiệm tiếp: một ActorCritic có hiệu chỉnh theo quan sát

`models/actor_critic.py` bổ sung `ContextualResidualActorCritic` gồm backbone
ActorCritic gốc và **một** nhánh hiệu chỉnh actor sử dụng 365 giá trị quan sát,
được điều tiết bởi ngữ cảnh hình học LiDAR (phân loại nhận diện ngữ cảnh chỉ
được giám sát qua kịch bản mô phỏng lúc huấn luyện). **Không có ID level hoặc
teacher policy lúc chạy suy luận.** Các tham số actor cũ bị khóa, chỉ học
correction bằng DAgger Level 4 và rehearsal bảo toàn L1/L2/L3/L5. Đây là
**kiến trúc thử nghiệm có classifier ngữ cảnh bên trong**, không phải PPO vừa
được huấn luyện hội tụ và chưa có bằng chứng tổng quát hóa bản đồ lạ.

Trên 15 episode/level chẩn đoán, xác suất classifier nhận nhầm L4 khi đang ở
Level 1/2/3/5 (>0,5) đều bằng 0 trong mẫu; với Level 4 teacher rollout,
82,99% frame có xác suất nhận diện L4 >0,5. Đây là pilot chẩn đoán, không
phải xác nhận triển khai. Quy trình huấn luyện độc lập nằm trong
`scripts/train_context_residual.py` và chỉ nâng metadata `independently_gated`
thành true khi 100 episode/level vượt mọi ngưỡng thành công và va chạm.

**Kết quả thực nghiệm actor có ngữ cảnh, chưa được nghiệm thu:**

1. `checkpoints/single_actor_context_residual_20261018/`: 3 vòng DAgger
   Level 4 (50/70/90 episode, 500 update/vòng); pilot tốt nhất Level 4
   **13/15**. Gate độc lập 100 episode/level, seed 12501000–12505000:
   L1 **100/100** (0 va chạm), L2 **96/100** (4), L3 **100/100** (0),
   L4 **71/100** (29), L5 **100/100** (0). **FAIL**.
2. `checkpoints/single_actor_conservative_dagger_20261018/`: tiếp tục từ
   round-3 checkpoint, thử cổng ngữ cảnh nghiêm ngặt hơn và Level 4 DAgger
   dùng hành động student nhiều hơn để thu dữ liệu sát rủi ro
   (90/110 episode, 650 update/vòng). Gate độc lập 100 episode/level,
   seed 13101000–13105000: L1 **100/100** (0 va chạm),
   L2 **98/100** (2), L3 **99/100** (1), L4 **73/100** (27),
   L5 **100/100** (0). **FAIL do Level 4**. Mọi kết quả Gate và seed
   được lưu riêng cùng checkpoint trong thư mục tương ứng; kiểm thử **73/73 PASS**.

Chỉ bản **thử nghiệm** đã xuất tại
`checkpoints/single_actor_conservative_dagger_20261018/experimental_contextual.onnx`
(ONNX Opset 14; sai số xuất PyTorch→ONNX lớn nhất **8,94e-7**).
Benchmark ONNX Runtime CPU trên **Windows 11 AMD64**: 1500 suy luận,
P99 **0,487 ms**; số này **không xác nhận** Raspberry Pi 4 P99 < 2 ms.
Thử xuất chính thức `exported/local_planner_single_actor_l1_l5.onnx`
đã bị chặn đúng bởi Acceptance Gate do L4 còn 27% va chạm;
**không tạo file chính thức và không phê duyệt chạy AGV thật**.

### Hai lượt phục hồi bổ sung: khoảng hở bên hông và hiệu chỉnh context (18/10/2026)

Sau khi phân tích 12 seed va chạm độc lập Level 4, phát hiện nhiều thời điểm
xe **thiếu góc quay** khi khoảng hở phía trước còn lớn nhưng vật cản bên hông
chỉ cách tâm xe khoảng 0,25–0,30 m. Bổ sung `level4_side_distance` (phân vị
15% của hai cung LiDAR bên) và trọng số nguy hiểm bên hông trong
`scripts/repair_stages_l2_l4.py`; bổ sung hình phạt hướng quay lớn khi teacher
yêu cầu và bộ hiệu chỉnh classifier theo mẫu DAgger + replay vào
`scripts/train_context_residual.py`. Có kiểm thử hồi quy cho cả hai tính năng.

**Gate độc lập, mỗi level 100 episode, đầy đủ domain randomization:**

| Checkpoint thử nghiệm | L1 thành công / va chạm | L2 | L3 | L4 | L5 | Gate |
|---|---|---|---|---|---|---|
| `single_actor_conservative_dagger_20261018` (trước sửa) | 100% / 0% | 98% / 2% | 99% / 1% | 73% / 27% | 100% / 0% | **FAIL** |
| `single_actor_lateral_recovery_20261018` | 100% / 0% | 95% / 5% | 100% / 0% | 75% / 25% | 100% / 0% | **FAIL** |
| `single_actor_context_calibrated_20261018` | 100% / 0% | 97% / 3% | 98% / 2% | 67% / 33% | 100% / 0% | **FAIL** |

Seed độc lập lần lượt bắt đầu ở 13101000–13105000, 14601000–14605000,
15601000–15605000; kết quả và danh sách seed va chạm lưu trong từng thư mục
checkpoint dưới `single_actor_l1_to_l5_final_acceptance.json` và
`final_eval_l1.json` ... `final_eval_l5.json`. So sánh giữa các dòng là
**tham khảo** vì seed khác nhau, không phải đánh giá cải thiện nhân quả ghép cặp.
Với teacher hỗ trợ 36,37% đến 57,03% số bước DAgger, thành công khi thu thập
demonstration **không tương đương** khả năng tự lái của student.

Phép hiệu chỉnh ngữ cảnh có mục tiêu CE giám sát (nhãn level ở **train only**),
không thay đổi hợp đồng đầu vào `[N,365]`/đầu ra `[N,2]` lúc suy luận;
nhưng làm giảm thành công L4 và chưa giải quyết biến thiên chính sách trên
trạng thái khó. Cả hai lượt đều là DAgger/BC, **không phải PPO mới hội tụ**.
Kiểm thử cuối: **75/75 pytest PASS**. Chưa có mô hình đơn nào đạt đủ
Acceptance Gate L1–L5; tệp phát hành
`exported/local_planner_single_actor_l1_l5.onnx` **không tồn tại**.
Benchmark Pi 4 cũng **chưa được đo**. Cấm xem hai checkpoint thử nghiệm là
phiên bản chính thức để chạy AGV thật.

### Thử nghiệm min/avg LiDAR + Flank Rescue DAgger ba vòng (18/10/2026)

Triển khai `DirectionalContextualResidualActorCritic` theo hợp đồng
`[N,365] -> [N,2]`, với nhánh hiệu chỉnh dùng 72 min-pooled + 72
avg-pooled + 6 khoảng hở định hướng + 128 đặc trưng fusion + 5
biến goal/vận tốc, MLP `283 -> 256 -> 128 -> 2`. Trọng số residual
checkpoint cũ được nhúng vào tầng mới mà giữ nguyên hành động tại lúc
khởi tạo (kiểm chứng trong pytest). Mạng có **một** đầu ra hành động,
không có Teacher hoặc nhãn level bên ngoài ở thời điểm inference.

`repair_stages_l2_l4.py` đã bổ sung nhánh Teacher rescue cả khi phía
trước thoáng nhưng bên sườn `<0.55m`, loss phạt thiếu góc quay so với
Teacher và phạt tiến quá nhanh khi bên sườn `<0.40m`; giữ nguyên hành
vi cũ cho các call không bật tùy chọn. `train_context_residual.py` có
các flag `--directional-pool --directional-loss --flank-rescue`.
**79/79 pytest PASS**; `git diff --check` không có lỗi khoảng trắng.

Chạy chính xác 3 vòng DAgger Level 4 (60/80/100 episode, 600 update/vòng,
batch 256, learning rate 0.00025) và replay 10 episode mỗi level
L1/L2/L3/L5 từ checkpoint bảo toàn. Kết quả pilot trên 15 episode/level:

| Vòng | L2 pilot thành công | L4 pilot thành công | Chọn |
|---|---:|---:|---|
| 1 | 14/15 | 13/15 | **Có** |
| 2 | 14/15 | 13/15 | Không |
| 3 | 15/15 | 8/15 | Không |

DAgger Level 4 có Teacher can thiệp **62.94%, 54.38%, 45.25%** số
bước tương ứng ba vòng. Tỷ lệ hoàn tất episode lúc thu thập không
được xem là kết quả tự lái Student. Đây là huấn luyện **DAgger/BC
residual** trên backbone PPO đóng băng, **không phải PPO vừa hội tụ**.

**Acceptance Gate độc lập:** 100 episode/level, domain randomization bật,
seed bắt đầu từ **16001000, 16002000, 16003000, 16004000, 16005000**.

| Level | Thành công | Va chạm | Timeout | Điều kiện | Kết quả |
|---|---:|---:|---:|---|---|
| 1 | 100/100 | 0/100 | 0 | Thành công >=99%, va chạm <=2% | PASS |
| 2 | 93/100 | 7/100 | 0 | Thành công >=98%, va chạm <=2% | **FAIL** |
| 3 | 100/100 | 0/100 | 0 | Thành công >=90%, va chạm <=2% | PASS |
| 4 | 87/100 | 13/100 | 0 | Thành công >=90%, va chạm <=2% | **FAIL** |
| 5 | 100/100 | 0/100 | 0 | Thành công >=90%, va chạm <=2% | PASS |

**TOÀN BỘ GATE: FAIL.** Mô hình thử nghiệm được giữ lại:
`checkpoints/single_actor_slalom_master_20261018/retention_candidate.pth`
(SHA256 `66ce572e44c2f7a9be5ce0e0a04d057d57da28b0e7a69e88dd0d7754d8721909`).
Bằng chứng: cùng thư mục có `training_trials.json`, 5 file
`final_eval_l*.json`, `retention_report.json` và
`single_actor_l1_to_l5_final_acceptance.json`; bản Gate kết hợp cũng
được ghi vào `logs/single_actor_l1_to_l5_final_acceptance.json`
(bản log cũ được lưu tại hậu tố `_previous_20261018.json`).

Chẩn đoán **13/13 seed va chạm** tại
`checkpoints/single_actor_slalom_master_20261018/l4_collision_diagnostics.json`:
trung bình 15 bước cuối có vận tốc tiến thực `0.232m/s`, khoảng hở
trước `1.535m`, khoảng hở xuyên tâm `0.308m`, xác suất nhận diện ngữ
cảnh L4 `0.769`, hệ số gain residual `0.999`, sai lệch hành động
teacher/student chuẩn hóa `0.891`. Cổng ngữ cảnh có kích hoạt mạnh
nhưng policy vẫn quay/phanh chưa đủ trên các trạng thái sát sườn;
min-pooling riêng lẻ cũng nhạy với ray dropout nên cần kiểm chứng
thêm bằng dữ liệu thất bại và đặc trưng hình học robust.

Các checkpoint trước đó được đánh giá trên **bộ seed khác**, nên không
được khẳng định mức tăng L4 từ 73% lên 87% là cải thiện nhân quả theo
cặp. Seed Gate 1600xxxx chỉ phục vụ nghiệm thu này; mọi lần hiệu
chỉnh mới phải dùng seed train/pilot/gate **mới, tách biệt**.

**Không xuất** `exported/local_planner_single_actor_l1_l5.onnx`
khi Gate còn FAIL. Do chưa có ONNX đủ điều kiện, chưa benchmark độ trễ
P99 của phiên bản này. Mốc P99 Windows 0.487ms chỉ thuộc mô hình
thử nghiệm cũ; Raspberry Pi 4 và AGV vật lý chưa được xác nhận.

### Tinh chỉnh phanh sườn L4 và replay Teacher L2 (18/10/2026)

`scripts/repair_stages_l2_l4.py` nay phạt vượt vận tốc bò khi khoảng hở
sườn `<0.45m`: `3*mean(risk*relu(v_norm+0.6)^2)`, tương ứng
`v_norm<=-0.6` hoặc `v<=0.07m/s`. `train_context_residual.py` đã thay
nhãn replay L2 bằng chuyên gia `exported/locked_scene_margin070_experimental/ppo_levels12.onnx`
trên chính các trạng thái Student đã đi qua, 40 episode và hệ số replay L2
`2.0`; L1/L3/L5 giữ retention-reference. Đây là **DAgger/BC trên residual
ActorCritic**, không phải huấn luyện PPO mới. Kiểm thử: **81/81 PASS**.

Chạy ba vòng DAgger L4 (60/80/100 episode; 600 update/vòng;
`batch_size=256`, `learning_rate=0.00015`). Teacher can thiệp lần lượt
61.87%, 54.23%, 44.03% số bước. Pilot tự lái 30 episode/level cho L4
17/30, 14/30, 23/30 và L2 29/30, 29/30, 30/30; chọn vòng 3. Thành
công khi có Teacher hỗ trợ thu thập không phải kết quả tự lái Student.

**Acceptance Gate độc lập (domain randomization bật; 100 episode/level):**
seed đầu tiên theo cấp lần lượt `17201000`, `17202000`, `17203000`,
`17204000`, `17205000`. Các seed này không tham gia train/pilot.

| Level | Thành công | Va chạm | Timeout | Gate |
|---|---:|---:|---:|---|
| L1 | 100/100 | 0/100 | 0/100 | PASS |
| L2 | 99/100 | 1/100 | 0/100 | PASS |
| L3 | 100/100 | 0/100 | 0/100 | PASS |
| L4 | 76/100 | 19/100 | 5/100 | **FAIL** |
| L5 | 100/100 | 0/100 | 0/100 | PASS |

**Gate tổng hợp: FAIL**. Checkpoint:
`checkpoints/single_actor_creep_l2_teacher_20261018/retention_candidate.pth`,
SHA256 `47650304988BD5C7E04DCEC7ACD2E570D56045044938D00BA0DA5C22ACCAB4CC`.
Trong thư mục này có `training_trials.json`, `final_eval_l1.json` đến
`final_eval_l5.json`, `retention_report.json`,
`single_actor_l1_to_l5_final_acceptance.json` và các checkpoint từng
vòng. Gate kết hợp mới được lưu tại
`logs/single_actor_l1_to_l5_final_acceptance.json`; gate trước được
giữ tại `logs/single_actor_l1_to_l5_final_acceptance_before_creep_20261018.json`.

Đánh giá bổ sung **chỉ trên seed phát triển**: Nội suy residual trọng số
alpha `[0, .25, .5, .75, 1]` trên 30 episode L2/L4 với seed
`17402xxx` và `17404xxx` cho L4 cao nhất **25/30 thành công,
5/30 va chạm** (alpha `.5`); L2 đều **28/30**.
Chi tiết trong `blend_pilot_l2_l4.json`. Kiểm tra thêm chính sách có
giới hạn trực tiếp `v_norm<=-0.6` khi sườn `<.45m` trên seed
`1760xxxx`: checkpoint gốc L4 **26/30, 4 va chạm**; checkpoint mới L4
**19/30, 9 va chạm, 2 timeout**. Chi tiết `flank_clamp_pilot.json`.
Các phép thử này không thay thế Gate và không được dùng để chọn theo
seed kiểm định cuối.

Nhận định: phạt vận tốc sát sườn làm giảm tốc nhưng chưa sửa đủ
góc quay và quỹ đạo phục hồi. Nhãn Teacher tại nhiều trạng thái gần
sườn vẫn có tốc độ cao, có khả năng xung đột với loss phạt tốc độ.
Đây là giả thuyết cần thí nghiệm nhân quả tiếp theo.
**Không xuất** `exported/local_planner_single_actor_l1_l5.onnx` khi
L4 còn dưới 90% thành công và vượt 2% va chạm. Chưa có benchmark P99
cho ONNX mới, chưa đo latency trên Raspberry Pi 4 và không phê duyệt
chạy trên AGV vật lý.

### Thí nghiệm tiếp diễn: hiệu chỉnh ngữ cảnh và DAgger ít can thiệp (18/10/2026)

**Bản đối chứng giữ lại:**
`checkpoints/single_actor_context_recalibration_20261018/retention_candidate.pth`
(SHA256 `A2F3C23813B4099DFA497ADC26313CEB19908154ABB109F5720AF74434766CAC`).
Gate độc lập 100 seed/level, có randomization, seed L1–L5 lần lượt
`18801000`, `18802000`, `18803000`, `18804000`, `18805000`:

| Level | Thành công | Va chạm | Timeout | Gate |
|---|---:|---:|---:|---|
| 1 | 100/100 | 0/100 | 0/100 | PASS |
| 2 | 98/100 | 2/100 | 0/100 | PASS |
| 3 | 100/100 | 0/100 | 0/100 | PASS |
| 4 | 89/100 | 10/100 | 1/100 | **FAIL** |
| 5 | 100/100 | 0/100 | 0/100 | PASS |

**Thí nghiệm A – quét bias bộ phân loại ngữ cảnh L4:** thêm tiện ích
`scripts/calibrate_l4_context.py`. Tại 30 seed phát triển cho mỗi L2,
L4 (seed `19202000` và `19204000`), thử shift `[-0.75, -0.35, 0,
0.35, 0.75, 1.25, 2]` trên logit L4 với cùng checkpoint nguồn.
**Cả bảy giá trị đều cho L2 29/30 (1 va chạm), L4 29/30
(0 va chạm, 1 timeout), score 2.5333**. Không có cải thiện quan sát được
so với shift=0 trên các seed này; sau thử nghiệm, code ưu tiên shift=0
khi đồng điểm, trong khi run trước khi sửa đã ghi shift=-0.75 trong
`checkpoints/single_actor_l4_bias_sweep_20261018/calibration_summary.json`.
Checkpoint thử nghiệm từ run đó chưa qua Gate, tuyệt đối không sử dụng
như bản chính thức. L1/L3/L5 trong tập phát triển đều 30/30.

**Thí nghiệm B – DAgger phục hồi L4 có ít Teacher can thiệp:** bắt đầu
từ checkpoint đối chứng, thu thập 75 episode L4 / 22.337 frame, rollout
Teacher 11.3% bước, tiêm nhiễu lái 15%, risk override 15%, cập nhật
residual 300 lần với lr `0.00005`, replay L2 do chuyên gia gắn nhãn
40 episode (`weight=2`), replay L1/L3/L5 10 episode/level. Trong tập
thu thập có Teacher hỗ trợ: L4 72/75 thành công; **đây không phải
hiệu năng tự lái**. Pilot Student 30 episode/level: L2 28/30 (2 va chạm),
L4 26/30 (1 va chạm, 3 timeout).

Gate độc lập 100 seed/level, seed `19601000` tới `19605000`:

| Level | Thành công | Va chạm | Timeout | Gate |
|---|---:|---:|---:|---|
| 1 | 100/100 | 0/100 | 0/100 | PASS |
| 2 | 97/100 | 3/100 | 0/100 | **FAIL** |
| 3 | 99/100 | 1/100 | 0/100 | PASS |
| 4 | 85/100 | 4/100 | 11/100 | **FAIL** |
| 5 | 100/100 | 0/100 | 0/100 | PASS |

**Gate tổng thể: FAIL.** Bản thử nghiệm được lưu độc lập tại
`checkpoints/single_actor_offpolicy_recovery_20261018/retention_candidate.pth`
(SHA256 `39EBB1FB0FE4B1A63C8CDD9CBF36E3634347007C8482DAACE1F94C5E5D0FBD43`).
Cùng thư mục lưu đầy đủ `final_eval_l1.json` đến `final_eval_l5.json`,
`retention_report.json` và `single_actor_l1_to_l5_final_acceptance.json`.
Kết quả cho thấy giảm can thiệp trong giai đoạn DAgger chưa đủ: lỗi
L4 dịch sang timeout đáng kể và L2 bị suy giảm. Vì bộ seed hai Gate
khác nhau, không diễn giải chênh lệch tỷ lệ thành công như hiệu ứng nhân quả.

Kiểm thử nguồn: **83/83 pytest PASS** trước đợt DAgger. Chưa có chính
sách đơn L1–L5 vượt Gate. **Không xuất**
`exported/local_planner_single_actor_l1_l5.onnx`, không gắn nhãn
`independently_gated=true` và chưa có kết quả benchmark P99 cho bản này.
Hạn chế mô phỏng: bộ kịch bản hình học cố định và randomization chưa
chứng minh an toàn hoặc độ trễ trên Raspberry Pi 4 / AGV thực.

### Audit độc lập Subagent 4: code review, release gate và an toàn AGV (18/10/2026)

Bằng chứng đầy đủ, mức độ nghiêm trọng và vị trí source được lưu riêng tại
`logs/fast_gate_code_review_20261018.md`. Đã đọc diff tracked và source
untracked `scripts/train_context_residual.py`, `scripts/repair_stages_l2_l4.py`,
`scripts/run_fast_gate.py` (mới do Main thêm); **không sửa các source/checkpoint
của agent khác**. `ocr review --audience agent --background "AGV L1-L5 single
ActorCritic, 365/2, randomized acceptance and no release on FAIL"` được gọi
trực tiếp nhưng **exit code 1** vì chưa cấu hình LLM endpoint
(`no valid LLM endpoint configured`); do đó kết luận dưới đây là **manual
review**, không phải kết quả OCR tự động. Kiểm thử độc lập
`python -m pytest ai_local_planner/tests -q`: **83 passed**; `git diff --check`
không phát hiện lỗi whitespace (chỉ cảnh báo quy đổi LF/CRLF của Git).

- **CRITICAL / hardware safety design**: yêu cầu STM32 hard E-stop **0,18 m**
  trong `PROMPT_SUBAGENTS_FAST_RELEASE.md` nằm **bên trong bán kính thân xe
  R=0,20 m**, không thể coi là cự ly phanh an toàn. Nếu LiDAR được quy về
  tâm robot, dừng khi d=0,18 m là muộn hơn ngưỡng va chạm. Với v=0,35 m/s,
  trễ 0,1 s và giảm tốc 0,5 m/s², khoảng cách tối thiểu xấp xỉ
  `0,20 + 0,35*0,1 + 0,35²/(2*0,5) = 0,3575 m`, **chưa** tính sai số LiDAR,
  trễ bổ sung và biên dự phòng. Đây là **lỗi trong đề xuất ngưỡng**, không
  phải bằng chứng firmware STM32 hiện tại đã cấu hình 0,18 m. Software
  `CommandSafetyFilter` hiện đặt 0,46 m phía trước và 0,25 m toàn vòng,
  nhưng không thay thế STM32 watchdog/hard E-stop độc lập. Phải thống nhất
  phép đo LiDAR từ tâm/sensor và `clearance` từ mép thân xe: nếu sensor ở
  tâm, `hull_clearance ≈ raw_range - 0,20 m` (cần hiệu chỉnh extrinsic thực).
- **HIGH / fail-closed release**: `scripts/run_fast_gate.py:60-76` gắn
  `independently_gated=true`, ghi đè checkpoint và xuất **ONNX chính thức
  trước khi** kiểm tra P99; khi `target_p99_below_2ms=false`, CLI trả thất
  bại nhưng ONNX và metadata promoted đã tồn tại. Cần benchmark bản
  ứng viên ở đường dẫn tạm, xác thực đầy đủ rồi mới phát hành atomic.
- **HIGH / artifact integrity**: `run_fast_gate.py:29,60-68` ghi
  `evaluated_checkpoint_sha256` từ hash **trước** lần `torch.save` thay
  metadata; checkpoint sau gate có bytes/hash khác. Trong khi đó
  `export_onnx.py:38-55` chỉ đối chiếu đường dẫn và tỉ lệ, **không** kiểm
  tra hash của tensor/trọng số đã nghiệm thu. Cần neo hash bất biến của
  weights và xác minh ngay trước export; tránh ghi đè checkpoint được gate.
- **MEDIUM / independent seeds**: `run_fast_gate.py:20-33` nhận `--seed`
  tùy ý mà không kiểm tra giao nhau với seed training/pilot ghi trong
  `provenance.json`/`training_metrics.json`; tính độc lập hiện phụ thuộc
  quy trình vận hành. Các seed mặc định **của lần train quan sát được**
  (training L4 `22500000..22500039`, pilot base `22400000`) khác seed
  gate mặc định, nhưng runner cần fail-closed nếu người gọi đổi seed.
- **MEDIUM / benchmark scope**: `benchmark_latency.py:13-39` đo 1.000
  lần gọi ONNX Runtime trên **một** quan sát giả định cố định của host;
  P99 này chỉ là latency ONNX CPU host, chưa bao gồm tiền xử lý LiDAR,
  safety guard, độ trễ truyền thông hay xác minh **Raspberry Pi 4**.
  Manifest vẫn đánh dấu `pi4_latency_verified=false`.

Đối chứng gần nhất trong `logs/single_actor_l1_to_l5_final_acceptance.json`
vẫn ghi `simulation_gate_passed=false` (L4: 76/100 thành công,
19/100 va chạm, 5/100 timeout). Ở thời điểm audit, thí nghiệm micro-DAgger
mới tại `checkpoints/single_actor_fast_gate_pass_20261018/` đã **hoàn thành
train 180 updates** theo `training_metrics.json` và có pilot **20 seed/level**
(L2 19/20, va chạm 1/20; L4 19/20, va chạm 1/20); `outcome.json` ghi
`independently_gated=false`, `independent_gate_run=false`,
`official_onnx_exported=false`. **Chưa có bằng chứng Acceptance Gate độc
lập 100 seed/level PASS cho ứng viên mới**; chưa đo P99 của ONNX mới.
Tiếp tục yêu cầu Gate **L1–L5 đồng thời** đạt ngưỡng thành công và va
chạm, domain randomization bật, seed độc lập, hash checkpoint nhất quán,
trước bất kỳ phát hành chính thức nào. **Tuyệt đối chưa chạy AGV thật**:
phải qua jack-up bench test, xác minh LiDAR/extrinsic/fail-safe sớm và
kiểm tra STM32 hardware E-stop độc lập ở ngưỡng được tính lại theo thân xe,
trễ và quãng phanh; sau đó mới thử nghiệm có kiểm soát.

### Kết quả cuối cùng của đợt Micro-DAgger 1 vòng (18/10/2026)

Checkpoint được đánh giá: `checkpoints/single_actor_fast_gate_pass_20261018/retention_candidate.pth`,
SHA256 `781152955c4ceb8e040bc8569cf6669ea5fb57bace69739ebc9cb2f573e917e2`.
Một vòng DAgger/behavior cloning (**180 optimizer updates, LR=3e-5; không
phải cập nhật PPO**); replay 40 episodes L2 bằng `ppo_levels12.onnx`
(weight=2.0), 10 episodes cho từng L1/L3/L5. Dữ liệu replay L1/L3/L5
trong lần chạy thực tế lấy nhãn từ checkpoint PCGrad cũ, **khác baseline
recalibration được yêu cầu**; runner đã được chỉnh default cho lần chạy
tương lai, tuyệt đối không mô tả lần chạy này là đúng cấu hình baseline.
Chi tiết audit tại `checkpoints/single_actor_fast_gate_pass_20261018/replay_reference_deviation.json`.

Acceptance Gate độc lập 100 episodes/level, bật Domain Randomization,
seed khởi đầu cho từng level `20101000`, `20102000`, `20103000`,
`20104000`, `20105000`:

| Level | Thành công | Va chạm | Timeout | Gate |
| --- | ---: | ---: | ---: | --- |
| L1 | 100/100 | 0/100 | 0/100 | PASS |
| L2 | 98/100 | 2/100 | 0/100 | PASS |
| L3 | 100/100 | 0/100 | 0/100 | PASS |
| L4 | 90/100 | **9/100** | 1/100 | **FAIL** |
| L5 | 100/100 | 0/100 | 0/100 | PASS |

**KẾT LUẬN GATE: FAIL.** L4 đã chạm ngưỡng success 90% nhưng collision
9% > mức cho phép 2%. Log gốc:
`checkpoints/single_actor_fast_gate_pass_20261018/single_actor_l1_to_l5_final_acceptance.json`
và các `final_eval_l1.json` ... `final_eval_l5.json`.
Checkpoint ứng viên đã đối chiếu SHA và vẫn giữ `independently_gated=false`.
Không có ONNX chính thức `exported/local_planner_single_actor_l1_l5.onnx`
và không có phép đo P99 của ONNX chính thức vì Gate không đạt.

Sau audit, `scripts/run_fast_gate.py` đã bổ sung kiểm tra provenance của
seed, kiểm tra checkpoint bất biến giữa mỗi level, staging riêng cho ONNX,
chỉ promote sau khi P99 CPU đạt; `scripts/export_onnx.py` kiểm tra digest
trọng số model khớp giữa checkpoint và báo cáo trước khi xuất chính thức.
Đây là sửa lỗi quy trình phát hành cho những lần chạy tiếp theo, không
biến kết quả Gate hiện tại thành PASS. Mô hình chưa được nghiệm thu cho
Raspberry Pi 4 hoặc AGV thật; hard E-stop STM32 phải thiết kế theo
quãng dừng thực, với lưu ý ngưỡng LiDAR 0.18 m từ tâm **không đủ** khi
bán kính thân xe 0.20 m.

Kiểm thử sau các sửa đổi: **86/86 pytest PASS** trên toàn bộ
`ai_local_planner/tests`; sau điều chỉnh kiểm tra seed, bộ test tập trung
export/release chạy tiếp **7/7 PASS**.

### Đánh giá bổ sung Subagent 4 — zero-collision micro-DAgger / gate / E-stop (18/10/2026)

Báo cáo có vị trí source, rủi ro và bằng chứng tại
`logs/zero_collision_code_review_20261018.md` (manual review). Đã thực chạy
`python -m pytest ai_local_planner/tests -q`: **86 passed, exit 0**;
`git diff --check`: **exit 0**, chỉ có cảnh báo LF/CRLF. Đã thử OCR trực tiếp
nhưng CLI **exit 1** vì `no valid LLM endpoint configured`; vì vậy không có
kết quả OCR tự động và không khẳng định đã kiểm định bằng OCR.

Đã tự đối chiếu lại 5 báo cáo nghiệm thu **hiện có** của checkpoint
`single_actor_fast_gate_pass_20261018` bằng `acceptance_gate.assess`:
L1 `100/100, collision 0`, L2 `98/100, collision 2`,
L3 `100/100, collision 0`, L4 `90/100, collision 9`,
L5 `100/100, collision 0`. **Gate tổng: FAIL vì L4 collision 9% > 2%**.
Tại thời điểm review, thư mục `checkpoints/single_actor_zero_collision_20261018/`
**chưa có**, nên `run_fast_micro_dagger.py` mới chỉ được review source;
không công bố train/pilot/independent gate đã chạy. ONNX chính thức
`exported/local_planner_single_actor_l1_l5.onnx` **không tồn tại**.

**Yêu cầu thiết kế về E-stop STM32:** ngưỡng tối thiểu **0,41 m đo từ LiDAR
ở tâm robot** đã được nêu trong `PROMPT_L4_COLLISION_COMPRESSION.md`, với
bán kính vỏ xe danh định `0,20 m` (clearance hình học danh định `0,21 m`).
Ngưỡng này **chỉ là mục tiêu thiết kế, CHƯA PHẢI nghiệm thu phần cứng**.
Phép tính minh họa `0,20 + 0,35×0,10 + 0,35²/(2×0,50) = 0,3575 m`
chưa bao gồm sai số và độ trễ đo thực tế; không được tuyên bố phần dư
`0,0525 m` là biên an toàn đã đo. Các tài liệu cũ vẫn đề cập **0,18 m**,
không được sử dụng làm mức dừng thực tế từ tâm cho xe bán kính 0,20 m.
Chưa có bằng chứng xác minh **firmware STM32 thực được nạp, wiring E-stop,
liên động watchdog/fail-safe, vị trí thực LiDAR, đo quãng phanh và thử nghiệm
treo bánh (jack-up bench test)**; do đó **không ký xác nhận E-stop hay cho
phép chạy xe thật**.

Review ghi nhận việc `run_fast_gate.py` đã triển khai staging, hash trọng số,
kiểm tra seed theo provenance và benchmark trước promotion; tuy nhiên hai
lệnh `os.replace` cho ONNX/manifest **không tạo giao dịch atomic của cả cặp**
(runtime dùng SHA để fail-closed khi lệch cặp). P99 là CPU host, chưa đo
Raspberry Pi 4 hoặc pipeline LiDAR → UART → motor. Không sửa source,
checkpoint, kết quả gate hay log của agent khác trong lượt đánh giá này.
### Kết quả chốt đợt Zero-Collision Micro-DAgger / Independent Gate (18/10/2026)

**Trạng thái phát hành: BLOCKED / SIMULATION_GATE_FAILED.** Đoạn này cập nhật
và thay thế các ghi chú trạng thái *trước khi chạy* nằm ở phần audit phía trên.
Không có file ONNX chính thức `exported/local_planner_single_actor_l1_l5.onnx`.

- Base: `checkpoints/single_actor_fast_gate_pass_20261018/retention_candidate.pth`
  (SHA256 `781152955c4ceb8e040bc8569cf6669ea5fb57bace69739ebc9cb2f573e917e2`).
- Candidate sau **một** Micro-DAgger BC 150 updates, LR 0.00002:
  `checkpoints/single_actor_zero_collision_20261018/retention_candidate.pth`
  (SHA256 `25af1efa24c00977ad6c270613e62142b4aeabd0c31bf2d8d16b2de1f5a2d29d`).
  Replay: 40 episodes L2 với teacher `ppo_levels12.onnx`/weight 2.0,
  10 episodes mỗi L1/L3/L5; 40 episodes L4 DAgger mixed rollout.
  Mixed rollout 40/40 thành công là kết quả **có Teacher can thiệp**, không
  phải kết quả student-only; pilot student-only ban đầu L3 0/20 vì flank gate
  kích hoạt sai trong hành lang hai vách.
- Sửa `DirectionalContextualResidualActorCritic.effective_context_gain()`:
  giữ gain theo flank khi **chỉ một sườn** áp sát và phía trước thoáng;
  tắt phần gain cưỡng bức khi L3 có hai vách gần hoặc đang tiếp cận cua.
  Sau sửa, pilot L3 20/20, L4 19/20 (L4 vẫn 1/20 collision).
  Sửa `model_fingerprint()` cho 0-D int64 version buffers để Gate có thể
  xác minh SHA trọng số mà không lỗi PyTorch `.view(uint8)`.
- Pytest toàn bộ sau thay đổi: **97/97 PASS**. Bộ seed nghiệm thu **mới**:
  `--seed 22700000 --episodes 100`, mỗi level 100 episodes có đầy đủ domain
  randomization, không giao với seed train/pilot trong `provenance.json`.

| Level | Success / 100 | Collision / 100 | Timeout / 100 | Gate |
|---|---:|---:|---:|---|
| L1 | 100 | 0 | 0 | PASS |
| L2 | 97 | **3** | 0 | **FAIL** (cần >=98, collision <=2) |
| L3 | 100 | 0 | 0 | PASS |
| L4 | **89** | **11** | 0 | **FAIL** (cần >=90, collision <=2) |
| L5 | 100 | 0 | 0 | PASS |

Log có thể tái lập tại
`checkpoints/single_actor_zero_collision_20261018/single_actor_l1_to_l5_final_acceptance.json`,
`retention_report.json`, `final_eval_l{1..5}.json`, `execution.log`,
`pilot_report.json`, `provenance.json`. Candidate mới không đạt chuẩn an toàn
L2/L4 và L4 còn thoái hóa so với base (9 -> 11 collision/100, ở *hai* tập
seed kiểm định khác nhau nên không kết luận được ý nghĩa thống kê). Giữ base
nguyên vẹn; **không** gắn metadata `independently_gated=true`, **không** xuất
ONNX chính thức và **không** chạy benchmark P99 trên artifact chính thức.

**An toàn thực:** `robot_stm32_f103/src/main.cpp` trong workspace hiện chứa
`PIN_*` ESP32 và log "ESP32 Robot Ready", đồng thời có command watchdog nhưng
chưa có kênh đo LiDAR/range độc lập đi tới vi điều khiển này. Không có bằng chứng
cài đặt và test hard E-stop ở khoảng cách từ tâm LiDAR >=0.41 m trên STM32 thật.
Không cấp hardware sign-off. Trước khi đặt bánh xuống sàn bắt buộc xác minh
phần cứng E-stop độc lập, liên động/mất tín hiệu, quãng dừng đo thực nghiệm,
và jack-up test. ONNX/P99 trên Raspberry Pi 4 chưa được xác thực.

### Independent final release attempt (18/10/2026)

- Held-out final seed base: `27000000`, 100 episodes/level, domain randomization.
- Five-level simulation gate: **FAIL**.
| Level | Success | Collision | Timeout | Gate |
| --- | ---: | ---: | ---: | --- |
| 1 | 100% | 0% | 0% | PASS |
| 2 | 97% | 3% | 0% | FAIL |
| 3 | 73% | 27% | 0% | FAIL |
| 4 | 86% | 13% | 1% | FAIL |
| 5 | 100% | 0% | 0% | PASS |
- Official ONNX withheld due to failed simulation or CPU gate.
- Real Pi4 CPU P99, STM32 independent E-stop and jack-up test unverified.
