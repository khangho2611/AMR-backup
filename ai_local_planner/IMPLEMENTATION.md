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
