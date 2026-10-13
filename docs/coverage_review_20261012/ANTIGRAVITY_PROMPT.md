# Giao việc cho Antigravity: sửa và chứng minh Coverage trainer V2

Bạn là implementation agent. Codex là reviewer độc lập. Làm việc tại:

`D:\HoMinhKhang\PROJECT\GITHUB_PROJECT\CODE XE TU HANH`

Mục tiêu: sửa `train_coverage_20000.py` và `run_train_20000.bat` để huấn luyện coverage policy reproducible, có đánh giá đúng và xuất model ONNX đã kiểm chứng vào `models/coverage_model.onnx`. Làm đến kết quả kiểm chứng được; không kết luận dựa vào việc script chạy hết hoặc export được.

## 1. Đọc bằng chứng trước khi sửa

Đọc `docs/coverage_review_20261012/REVIEW.md`, `audit_current.json`, `golden_reference.py` và code hiện hành. Các line number/hash trong review là snapshot: đối chiếu code mới nhất trước khi hành động. Không sửa evidence của reviewer để làm kết quả trông tốt hơn. Ghi kết quả mới ở `models/runs/<run_id>/`.

Xác nhận và tái hiện lỗi `covered_count <= steps + 1`, `max_steps=350`, trong khi map có ít nhất 788 free cell theo generator gốc. Đây là blocker: không thể đạt 95%. Audit greedy hiện tại được ~40,05%, 0/100 màn đạt 95%, 100/100 hết budget. Mô hình hiện tại có một input 2×9×9, chưa có frontier vector. ONNX hiện tại đã tự chứa trọng số; không mặc định `.data` là dependency.

Phạm vi sửa: trainer, BAT, tests/eval/benchmark thuần offline và artifact trong models. Giữ nguyên công việc của người khác, không reset/clean. Không điều khiển robot, sửa firmware/ROS controller hoặc bật chế độ bỏ safety. Sao lưu model hiện có vào run riêng trước khi thay artifact. Không tạo training dài ngay khi chưa qua unit tests và smoke.

## 2. Chốt hợp đồng môi trường và thuật toán trong manifest

Ưu tiên Double DQN để giữ 4 action và dễ đối chiếu code cũ. Không trộn PPO update với DQN replay. Nếu thay thuật toán, phải có lý do đo được và triển khai đúng toàn bộ hợp đồng của thuật toán đó.

Tách rõ hai chế độ:

- Point-grid/known-map là baseline kiểm lỗi thuật toán, không đủ nghiệm thu triển khai.
- Robot footprint/observed-map mô phỏng tín hiệu có trên Pi; policy, frontier và action mask chỉ đọc bản đồ đã quan sát. Ground truth chỉ dùng mô phỏng cảm biến/collision và evaluator. Ghi rõ mode trong checkpoint và metadata ONNX.

Mỗi episode: map và start hợp lệ, có seed; xác định reachable component sau inflation. Phân biệt occupancy-free, vùng robot-center-reachable và diện tích công tác serviceable. Báo cáo cả diện tích bị loại vì không thể tiếp cận. Tool footprint quét thực sự mới tăng coverage; LiDAR nhìn thấy không được coi là đã dọn. Tạm thiếu số đo footprint thì dùng tham số cấu hình được gắn nhãn giả định, đánh dấu hardware gate BLOCKED, không giả số đo.

Point-grid budget mặc định theo N_reachable, ví dụ 4*N thay cho hằng 350; kiểm tra DFS spanning-tree baseline phủ hết trong ≤2*(N−1) bước trên đồ thị liên thông 4-neighbor. Với quay/đi có thời lượng, đổi budget theo thời gian baseline và mô tả units. Giữ 32×32, 5cm/cell cho cấu hình mặc định; hỗ trợ bản đồ đánh giá lớn hơn qua crop input cố định.

`step` trả `obs,reward,terminated,truncated,info`. Hoàn thành là terminal; giới hạn collector là truncation. Nếu định nghĩa deadline là terminal của nhiệm vụ, thêm time-to-go vào observation và giải thích. Mọi nhánh kể cả blocked/no-op đều tăng step/time và kiểm tra budget chung. Tách lý do kết thúc: success, collision/failure, time_limit, no_progress, invalid_map.

## 3. Guidance và observation

Chọn mục tiêu free/reachable bằng geodesic BFS/Dijkstra trên costmap an toàn. Không trỏ thẳng Euclid tới centroid có thể nằm trong tường. Hướng đưa vào mạng là first segment/lookahead của đường hợp lệ; thêm distance chuẩn hóa và has_target. Có deterministic tie-break và goal hysteresis; đổi goal khi goal đã phủ, mất reachability hoặc hết thời hạn, không dao động vô hạn.

Tách exploration frontier (known/unknown) và coverage target (chưa quét). Không có coverage target nhưng còn exploration frontier thì chưa phải success. Không có goal hợp lệ phải STOP/replan hoặc failure có lý do; không chia vector zero hoặc phát NaN. Distance/scalars chỉ dùng thông tin khả dụng khi deploy, không đọc oracle.

Baseline tối giản 2×9×9 + [dx,dy] là ablation, không tuyên bố đủ Markov. Bản mở rộng khuyến nghị 3 map channels + 8 scalar như REVIEW; hướng heading và map patch cùng frame. Ghi chính xác axis xy/row-column, thứ tự action, yaw, chuẩn hóa, channel semantics, padding, shape và dtype vào metadata. Có test yaw 90°, map origin quay/dịch và chưa thấy toàn map. Nếu vẫn có state aliasing, báo rõ và ablate coarse global map/recurrent input, không thêm chi phí âm thầm.

## 4. Reward và vòng học

Dùng `golden_reference.py` làm kernel tham khảo, không copy coi là chương trình hoàn chỉnh. Reward mới phủ làm tín hiệu chính; phạt overlap nhỏ vì hành lang nối phòng cần đi lại. Phạt thời gian/quay có units; success chỉ trả một lần. Potential shaping là `beta*(discount*Phi(next)-Phi(current))`, có Phi terminal=0, không đặt Phi=0 ở collector truncation. Nếu option có thời lượng khác nhau, dùng cùng discount-duration trong shaping và TD target. Goal thay đổi phải được phản ánh nhất quán trong state/Phi.

Không thưởng đi thẳng vô điều kiện hoặc phạt U-turn đến mức agent không quay đầu. Nếu muốn zíc-zắc, so với boustrophedon/STC baseline; có thể thêm demonstration hoặc total-variation reward dưới ablation. Không cam kết một reward “tối ưu” hoặc tuyệt đối không đâm tường.

Mask action không hợp lệ ở cả epsilon sampling, greedy selection và lựa chọn next action trong Double DQN target. Online net chọn action, target net đánh giá. All-false mask và nonfinite output trả STOP/replan cho caller; training phải định nghĩa transition tương ứng, không argmax mặc định=0 và không tính 0*(-inf). Policy đề xuất blocked action trong simulator có thể giữ pose và bị phạt; contact vật lý vẫn là failure được safety xử lý.

Replay lưu final next observation, mask/scalars và terminated/truncated đúng, không lưu nhầm reset observation. Huber loss, finite loss/Q checks, gradient clipping, replay warmup và target sync theo global env/optimizer steps. Log epsilon theo global steps, gamma, update count và replay sampling ratio. Thử gamma .99/.995/.999 trên validation thay vì giữ .95 không đánh giá. Chọn giới hạn Q/reward scale từ dữ liệu; không coi số Q lớn tự nó là divergence.

Train frequency configurable, ví dụ 4/16/32. Profile env, guidance, replay conversion, inference, backward; thử thread count 1/2/4. So sánh chất lượng ở cùng env-step budget và cả cùng wall-clock budget. Một update/episode dài không tương đương mỗi 16 bước. Không hứa 20.000 episode/5–8 phút nếu chưa có đo thực tế.

Seed Python/NumPy/Torch/env; tách RNG train/eval để đánh giá không làm đổi trình tự train. Checkpoint resume gồm net/target/optimizer/RNG/counters/config và replay, hoặc công bố rõ warm restart nếu không khôi phục replay. Import module không train, không load hardware, không bắt buộc stdout.reconfigure.

## 5. Mạng và export

Mạng đề xuất: map Conv→8→16(stride2)→FC64, vector→16, concat→FC64→4; ReLU, không cần BatchNorm/Dropout. Reference default 32.644 params. Giữ output 4 Q-values thô; safety/action mask nằm trong consumer theo cùng contract.

Xuất candidate vào run directory trước, FP32, batch=1, named inputs/outputs, opset18 nếu runtime mục tiêu hỗ trợ. `dynamo=False` có thể dùng với phiên bản PyTorch phù hợp nhưng không phải tiêu chí chứng nhận. Có `model.eval()` và inference parity với đúng preprocessing.

Kiểm tra ONNX checker; không external initializer/tensor dependency; load bằng bytes trong thư mục không có `.data`; chạy nhiều observation thực tế và edge cases, không chỉ random normal. Quy định tolerance FP32 trước, gợi ý atol=1e-4, rtol=1e-4 rồi điều tra sai khác vượt ngưỡng. Báo cáo Q error và argmax mismatch; tách tie gần bằng nhau. Đánh giá rollout ONNX độc lập cùng map/start/mask, không chỉ so output trên rollout PyTorch.

Ghi metadata vào chính ONNX: contract version, channels/scalars/actions/frame/units, preprocessing, resolution, mode, checkpoint hash/run id. Manifest/checkpoint/test JSON là artifact đào tạo riêng; yêu cầu một file model triển khai không cấm có chúng.

Chỉ promote candidate đã qua software gates sang `models/coverage_model.onnx`, dùng ghi tạm/atomic replace. Checkpoint chưa đạt vẫn giữ trong run để phân tích. Dưới 1.000.000 byte là gate model size. Benchmark Pi 4 CPUExecutionProvider batch1, warmup≥100, đo≥1000, p50/p95/p99, versions/threads/temperature/tải hệ thống. Mốc <5ms lấy p95 inference làm mục tiêu; đo pipeline preprocessing+guidance+inference riêng. Nếu không có Pi thì gate này NOT_RUN, không thay bằng PC latency.

## 6. CLI và BAT

Giữ `python train_coverage_20000.py 20000` tương thích. Bổ sung CLI rõ ràng cho smoke, eval-only, seed, output directory, resume, train frequency, thread count. Dùng argparse, sai tham số exit khác 0. Đường dẫn mặc định bám `Path(__file__).resolve().parent`, không bám cwd.

BAT `cd /d "%~dp0"`, dùng Python/venv cấu hình rõ, quote path, kiểm tra errorlevel ngay sau Python và truyền đúng exit code. Chỉ in thành công khi trainer báo đủ gate; Ctrl+C lưu checkpoint incomplete và trả trạng thái riêng (ví dụ 130), không in đã hoàn tất 20.000 episode hay ghi đè accepted model. Thiếu dependency/export/parity lỗi phải fail rõ. Ghi command line + package versions vào run manifest.

## 7. Gate kiểm thử, chạy theo thứ tự

**G1 — correctness offline:** test empty room, corridor, cul-de-sac/U-shape, hai phòng nối cửa, disconnected island, chỉ 1 ô reachable, unknown không có frontier, all-false mask, map lỗi, nonfinite input. Test coverage monotonic/no reward twice, mẫu số reachable, swept footprint đi và quay, collision không tăng coverage, mọi nhánh hết budget, target reachable và deterministic, truncation bootstrap/terminal no bootstrap, invalid action không lọt Bellman argmax, train/eval split và import side effects. Có test tái hiện lỗi cũ rồi mới kiểm tra sửa. Không đặt seed để che lỗi.

**G2 — smoke/export:** chạy ngắn khoảng 10 episode trong output riêng; kiểm tra replay/gradient/checkpoint/resume, test ONNX/parity, CLI invalid args, BAT từ cwd khác/path có dấu cách, Ctrl+C và export failure không ghi đè accepted model. Báo exact commands và exit codes.

**G3 — pilot và đánh giá:** pilot có log throughput/progress, kiểm tra reward exploitation, loop và memory. Ít nhất 100 map validation cố định; có baseline random-masked, nearest-uncovered BFS và boustrophedon/STC khả thi. Cùng budget, map/start và metric. Baseline dùng oracle map phải gắn nhãn riêng, không so nó như có cùng information budget với observed-map policy. Tách policy thuần, policy+mask và policy+fallback; báo intervention rate, tránh gọi thành tích planner là thành tích mạng.

**G4 — full run:** khi G1/G2 qua và pilot không có lỗi cấu trúc, chạy đủ 20.000 episode, ghi cả số episode thực hoàn tất và global env steps. 20.000 episode không tự chứng minh 20.000 geometry khác nhau; lưu seed và hash map, báo unique count nếu yêu cầu unique. Chọn checkpoint bằng validation, không dùng test để tuning. Đánh giá cuối trên ≥500 map test seeds tách biệt, đa dạng hình học và kích thước, epsilon=0, thêm rollout ONNX độc lập. Khi cần kết luận ổn định qua seed, dùng ≥3 train seeds; một run chỉ là bằng chứng cho một seed.

Gate chất lượng đề xuất cho simulator đã chốt: mean coverage≥95% và ít nhất 95% test episode đạt coverage≥95%; đồng thời báo exact-completion=100% rate, p5/median/worst coverage, collision episode rate, blocked proposals, overlap ratio, số lần quay, thời gian quét, timeout/no-progress rate, fallback rate. Báo mean/CI và tất cả seed, không chỉ ảnh tốt. Zero observed collision trên test không phải bảo đảm tuyệt đối. Tính completeness trên cùng serviceable-area definition đã công bố.

**G5 — deployment chưa thể gộp vào G4:** ONNX dưới 1MB, Pi latency thực, adapter contract, sensor/TF stale handling, STOP/watchdog, timeout, rollback, footprint/braking measurements và sim-to-real scenarios. Không tự chạy xe thật. `twist_centres` hiện có max_w=1.5 trong một số nhánh, khác 3.194; phải báo integration issue, không bypass guard trong task trainer.

## 8. Bàn giao cho reviewer

Tạo `models/runs/<run_id>/acceptance_report.md` cùng manifest, metrics JSON/CSV, failures/traces, learning curves, selected checkpoint, ONNX candidate và SHA256. Báo bảng PASS/FAIL/NOT_RUN/BLOCKED cho từng gate; nguyên nhân cụ thể, command tái hiện và files đã sửa. Lưu diff hoặc bản snapshot code gắn run hash. Với hyperparameter chưa đạt, giữ checkpoint và báo thật, không hạ gate hoặc sửa evaluator để pass.

Sau phần implementation, unit tests, pilot và full-run evidence, để Codex review độc lập. Không viết “sẵn sàng 100% lên Raspberry Pi” chỉ vì ONNX load được. Không thay đổi controller hay chạy robot trong task này.
