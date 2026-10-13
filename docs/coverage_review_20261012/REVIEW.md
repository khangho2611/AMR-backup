# Giám sát Coverage DRL — 12/10/2026

## Kết luận

Chưa chấp nhận V2 theo mô tả để train dài hoặc đưa lên xe. Hướng frontier + mạng nhỏ có ích, nhưng giới hạn bước, định nghĩa coverage, thông tin quan sát và hợp đồng điều khiển phải sửa trước. Không có reward nào tự bảo đảm tuyệt đối không va chạm. Không có bộ hệ số reward tối ưu chung cho mọi bản đồ.

Đã đọc trực tiếp `train_coverage_20000.py`, `run_train_20000.bat`, kiểm tra model hiện có và các điểm tích hợp liên quan. Không sửa trainer, BAT, model hay điều khiển xe. Báo cáo là review bản trên đĩa được định danh bằng SHA256 trong `audit_current.json`, không suy đoán trạng thái Antigravity từ ảnh.

## Bằng chứng thực nghiệm hiện tại

Lệnh từ thư mục gốc: `python docs/coverage_review_20261012/audit_current.py`.

100 seed cố định 10000–10099; epsilon=0; dùng PyTorch chọn action trong đúng môi trường V1. Không có lịch sử seed train nên không tuyên bố đây là tập test chưa từng thấy.

| Chỉ số | Kết quả |
|---|---:|
| Coverage trung bình | 40,0539% |
| Median / min / max | 40,5373% / 22,5386% / 42,1875% |
| Số màn đạt ít nhất 95% | 0/100 |
| Màn va chạm | 0/100 |
| Số bước trung bình | 350 |
| Baseline đi BFS tới ô chưa phủ gần nhất, cùng 350 bước | 40,6731% |
| Bản đồ bị tách thành phần liên thông trong mẫu | 0/100 |
| Số tham số model hiện tại | 171.156 |
| Kích thước ONNX | 685.973 byte |
| Tensor external trong graph | 0 |

ONNX load trực tiếp từ bytes thành công: file `.onnx.data` nằm cạnh không cần cho model được kiểm tra. Không xóa file đó vì có thể là artifact cũ cần giữ.

So sánh 35.000 observation dọc rollout: sai số tuyệt đối Q lớn nhất 6,58e-5; 1 lần argmax khác nhau. Tại seed 10031, bước 176, PyTorch có hai action cùng Q=171,4699097; ONNX làm lệch thứ tự do số học float. Đây là tie sensitivity, chưa phải bằng chứng export sai. Kiểm tra `rtol=1e-4, atol=1e-5` trượt 14 observation; nghiệm thu mới phải quy định tolerance trước và phân tích tie, không chỉ kiểm tra shape. Cần đánh giá rollout ONNX độc lập sau khi sửa; audit hiện tại không làm việc đó.

Benchmark cuối trên PC, CPUExecutionProvider một thread, batch=1, warmup 100 rồi 1.000 lượt: p50≈0,035 ms, p95≈0,052 ms, p99≈0,096 ms. Chỉ đo `session.run`, không gồm SLAM, frontier, preprocessing hoặc safety. Kết quả thay đổi theo tải máy và không phải tốc độ Pi 4.

## Các lỗi và thiếu sót theo mã nguồn

1. **P0 — Mục tiêu bất khả thi do horizon.** Dòng 92–100 chỉ tăng coverage một ô/lần di chuyển và dừng ở 350. `covered_count <= 1 + steps`. Với 800 ô: tối đa 43,875%; cần ít nhất 759 bước để đạt 95%, 799 để phủ hết, chưa kể đi lại. Với generator hiện tại còn chặt hơn: nội thất 900 ô, nhiều nhất 7×16=112 ô vật cản, nên ít nhất 788 ô free; trần coverage toàn generator là 351/788≈44,54%. Bỏ collision termination vẫn không sửa được điều này.
2. **P1 — Chạm tường kết thúc thật.** Dòng 83–86 xác nhận chẩn đoán. Đây là một lựa chọn MDP hợp lệ nếu collision là failure, không phải lỗi DRL phổ quát. Trong giai đoạn epsilon cao nó làm episode ngắn; nhưng không giải thích tất cả stagnation, nhất là đánh giá greedy hiện tại không va chạm.
3. **P1 — Local observation không đủ Markov.** Dòng 65–73 chỉ có 2×9×9, chưa có frontier. Hai lịch sử coverage khác nhau có thể cho cùng observation nhưng cần action khác nhau. Thêm hai scalar cũng không tự biến thành MDP đầy đủ. Môi trường đầy đủ có thể Markov trong khi đầu vào policy chỉ là quan sát của POMDP.
4. **P1 — Gộp termination với truncation.** Dòng 100 và 179–196 coi timeout như terminal và bỏ bootstrap. Nếu 350 chỉ là giới hạn collector, phải tách `terminated`, `truncated` và bootstrap từ final observation khi truncated. Nếu thời hạn thực sự thuộc nhiệm vụ thì biểu diễn thời gian còn lại trong state/observation. Xem [Gymnasium: Handling Time Limits](https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/).
5. **P1 — Robot một ô, không footprint.** Dòng 75–95 chỉ kiểm tra ô đích. Không mô phỏng quay, quét thân xe, clearance, braking hoặc vùng công tác. Robot thật không phải điểm. Occupancy-free, robot-center-reachable và serviceable floor area là ba tập khác nhau; báo cáo mẫu số rõ ràng, không inflate rồi âm thầm gọi đó là toàn bộ sàn.
6. **P1 — Chưa có đánh giá model để chọn checkpoint.** Dòng 213–231 chỉ log train rolling mean khi epsilon còn hoạt động. Không có validation/test tách biệt, seed reproducible, baseline hoặc acceptance gate.
7. **P1 — Export được báo thành công quá mức.** Dòng 268–277 chỉ thử input ngẫu nhiên, xem shape, rồi in “sẵn sàng 100%”; bắt exception và không trả lỗi. BAT vẫn in hoàn tất kể cả Python lỗi. Ctrl+C cũng có thể ghi đè model tốt bằng model chưa học xong.
8. **P2 — Lịch train theo episode không ổn định.** Dòng 183 dùng bộ đếm episode-local; episode ngắn có thể không update. Epsilon và target sync theo episode trong khi độ dài episode biến thiên. `gamma=.95` cho horizon discount hiệu dụng khoảng 20 bước; reward sau 100 bước chỉ còn hệ số ~0,0059. Đây là lựa chọn đáng ablate, không tự chứng minh là bug.
9. **P2 — Path và import.** BAT không `cd /d "%~dp0"`; đường dẫn model tương đối theo cwd có thể ghi nhầm chỗ. `sys.stdout.reconfigure` khi import có thể lỗi dưới capture/wrapper; CLI âm thầm bỏ qua tham số không hợp lệ.
10. **Rủi ro tích hợp đã thấy.** Search các Python hiện hành (bỏ archive/evidence) chỉ thấy trainer sử dụng `coverage_model`/onnxruntime, chưa thấy consumer trên Pi. `agv_navigation.py:24` có `twist_centres(... max_w=1.5)`; các caller ở `agv_unified_brain.py:869,915` không override, nên những đường kiểm tra đó từ chối 3,194 rad/s. Một số nhánh operational có bypass riêng. Cần audit tích hợp riêng; không kết luận toàn bộ controller luôn từ chối hoặc luôn an toàn, và không nới/bỏ guard để làm model chạy được.

## Đánh giá 5 đề xuất V2

| Đề xuất | Đánh giá và điều kiện |
|---|---|
| Va chạm -2 đến -5, đứng tại chỗ, không done | Hợp lý cho **action bị chặn trong simulator**. Cần tăng bộ đếm ở mọi nhánh, kiểm tra timeout chung, action mask và recovery. Va chạm thật phải do safety/controller xử lý; không giả định thân xe luôn giữ nguyên pose sau va chạm. |
| Vector tới centroid cụm gần nhất | Chưa đủ: centroid có thể nằm trong tường; khoảng cách Euclid có thể chọn bên kia vách; target có thể nhảy qua lại. Chọn goal free/reachable, BFS/Dijkstra theo đường hợp lệ, cung cấp hướng của đoạn đầu path, khoảng cách và cờ target; dùng hysteresis/điều kiện hủy target. |
| Gradient mỗi 16–32 bước hoặc một lần/episode | Là hyperparameter cần đo sample efficiency. Giảm update không bảo đảm giữ chất lượng. PPO dùng rollout, GAE, minibatch và epoch; không áp dụng lịch DQN máy móc. |
| ONNX opset18, dynamo=False, <5ms | Khả thi về định dạng/mạng nhỏ, nhưng opset không bảo đảm một file hay latency. Kiểm tra graph, parity, rollout, metadata và benchmark Pi. Cảnh báo deprecated legacy exporter không đồng nghĩa export hỏng. |
| 4 action đổi thành waypoint | Hợp lý nếu là planner cao tầng có controller thực hiện option. Phải thống nhất frame, map origin/yaw, heading, thời gian quay/đi, đạt goal, failure và tiến độ. Không tương đương phép dịch một ô tức thời. |

20.000×350=7 triệu transition. Hoàn tất trong 5–8 phút cần ~23.333–14.583 transition/s, chưa tính thay đổi horizon. Sau khi bỏ early termination tổng số transition có thể tăng, dù giảm gradient. Không có profiling thì 5–8 phút chỉ là mong muốn. Đo env step, frontend frontier, tensor conversion, inference, sampling replay và backward riêng; thử 1/2/4 thread vì mạng nhỏ có thể chậm do thread overhead.

## Hướng thiết kế khuyến nghị

Giữ **Double DQN cao tầng + guidance đường đi + safety controller** cho vòng này để ít thay đổi so với mã gốc và dễ kiểm chứng trên CPU. So sánh với BFS-nearest-uncovered và boustrophedon/STC. PPO chỉ đáng chuyển khi có lý do đo được, ví dụ muốn học điều khiển liên tục và chấp nhận chi phí simulator/validation lớn hơn.

Tách hai giai đoạn: known-map point-grid để debug thuật toán; realistic footprint/observed-map để nghiệm thu sim-to-real. Không gọi giai đoạn đầu là đã deploy được. Với point-grid connected, dùng budget cỡ 4×N_reachable làm điểm khởi đầu; DFS traversal trên spanning tree chỉ cần tối đa 2(N−1) cạnh, chứng minh budget không bất khả thi. Đây không phải bảo đảm DQN đạt được. Chuyển sang footprint/variable-duration options thì tính budget theo thời gian và baseline tương ứng.

Unknown khác uncovered: unknown là chưa đo occupancy; uncovered là phần sàn đủ thông tin nhưng chưa được vùng công tác quét. LiDAR nhìn thấy sàn không có nghĩa xe đã phủ sàn. Frontier exploration là biên known-free/unknown; coverage frontier là biên covered/uncovered. Không cho policy/guidance đọc ground-truth map trong chế độ unknown-map; evaluator có thể dùng ground truth để đo kết quả và khả năng tiếp cận.

Cho full physical 32×32 tại 5cm/ô: bản đồ chỉ rộng 1,6×1,6m; patch rộng 0,45m, nhìn từ tâm tới mép chỉ khoảng 0,225m. Trong code robot có radius config 0,20m và margin 0,15m: đây là cấu hình, chưa phải số đo xác nhận; riêng clearance 0,35m đã lớn hơn nửa patch. Cần global planner/costmap đủ rộng để safety, và test bản đồ lớn nhiều phòng thay vì phóng nhỏ cả căn nhà vào 32×32.

## Reward và zíc-zắc

Dùng điểm khởi đầu có thể kiểm chứng, không gọi là tối ưu:

`r = 1.0*new_area - 0.02*overlap - 0.01*duration - 2.0*blocked + 10.0*success + 0.2*(discount*Phi(next)-Phi(current))`

- `new_area`: diện tích mới được footprint công tác thực sự quét, chia đơn vị diện tích cố định; point-grid baseline là số ô mới. Chỉ cộng một lần, không thưởng lại khi đổi goal.
- `overlap`: lượng di chuyển trùng vết theo định nghĩa công bố; không tính quay tại chỗ thành hàng loạt ô đi lại. Trở lại hành lang nối phòng thường là bắt buộc; không dùng phạt quá lớn hay yêu cầu overlap=0.
- `duration`: thời gian option gồm quay/đi, chia đơn vị thời gian cố định. Nếu model point-grid thì bắt đầu bằng chi phí bước và nêu rõ giới hạn.
- `blocked`: đề xuất action bị validator chặn. Action mask áp dụng cả exploration, greedy và Bellman target; collision-penalty có thể ít được kích hoạt nếu mask hoàn hảo.
- `success`: trả một lần khi thực sự đạt tiêu chí. Phân biệt đạt 95% với complete=100% serviceable area.
- `Phi(s)=-clip(d_geodesic(s, remaining_target_set)/Dmax,0,1)`, bằng 0 ở terminal. Goal/coverage change phải nằm trong state dùng tính Phi; dùng cùng hàm cho cả hai đầu transition. Nếu fixed-duration thì discount=gamma; nếu options thời lượng khác nhau thì thống nhất `gamma**duration_units` trong reward shaping và TD target.

Potential-based shaping có lý thuyết bảo toàn policy tối ưu dưới các giả thiết về MDP, discount và terminal handling; không bảo đảm mạng xấp xỉ với partial observation sẽ học được hoặc an toàn. Overlap/time penalties là thay đổi mục tiêu, không được quảng cáo là invariant. Nguồn: [Ng, Harada & Russell 1999](https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf).

Để khuyến khích zíc-zắc, ưu tiên reward diện tích và chi phí thời gian/quay nhỏ, kiểm tra total-variation ablation trên coverage map; nếu phải đảm bảo dạng đường boustrophedon thì dùng decomposition/lane planner hoặc demonstration + imitation. Thưởng “đi thẳng” thuần túy có thể khiến xe chạy vòng hoặc từ chối quay đầu; phạt quay mạnh phá U-turn cần thiết. Không có scalar reward đơn giản bảo đảm boustrophedon trong mọi hình học.

## Mạng tham chiếu

`golden_reference.py` cung cấp CNN fusion, masked greedy, Double DQN target và reward kernel. Đây là khung đối chiếu có kiểm tra số học, chưa phải trainer hay controller hoàn chỉnh.

Nhánh map: Conv(3→8,3×3) → ReLU → Conv(8→16,3×3,stride2) → ReLU → flatten(400) → FC64. Nhánh vector: 8→16→ReLU. Nối 64+16→64→4 Q-values. Tổng 32.644 tham số, 130.576 byte trọng số FP32; artifact ONNX thật phải đo sau export.

Contract gợi ý: 3 kênh `known_free_uncovered`, `inflated_blocked`, `unknown`; 8 scalar `path_dx,path_dy,path_distance_normalized,has_target,sin_yaw,cos_yaw,coverage_fraction,no_progress_fraction`. Các tỷ lệ phải tính được từ thông tin triển khai, không từ oracle simulator. Chọn map-aligned hoặc robot-aligned rồi ghi metadata và dùng thống nhất. Goal identity/path history bị nén nên vẫn có partial observability; nếu còn aliasing thì thử thêm coarse global map hoặc recurrent policy, kèm chi phí ONNX/state.

Bản ablation đúng yêu cầu tối giản `CoverageQNet(channels=2, feature_dim=2)` dùng local map+vector; nó thiếu distance, target validity và heading cho thời gian/quay, nên không mặc định là bản deploy.

## Điều kiện vật lý phải đưa vào prompt

Ở 0,307m/s, một ô 5cm mất khoảng 0,163s; quay 90° ở 3,194rad/s mất khoảng 0,492s lý tưởng. Sai pose, trễ UART/LiDAR, quán tính và wheel slip có thể lớn so với một ô. Controller phải theo feedback đạt heading/pose, không chỉ sleep theo hai con số này. 80 RPM là tốc độ bánh, không phải tần số inference hoặc tốc độ quay thân xe tính RPM.

Safety chạy độc lập với policy: occupancy inflation theo thân đo được, swept-footprint cho quay/đi, LiDAR/TF fresh, timeout, watchdog, STOP khi không có action hợp lệ hoặc model lỗi. Khoảng dừng tối thiểu còn phụ thuộc `v*latency + v²/(2*a_brake)` cộng bất định; phải đo a_brake và latency. Không dùng con số giả để chứng nhận an toàn. Không tự sửa phần cứng/firmware trong phạm vi sửa trainer.

## Đối chiếu nghiên cứu

[Jonnarth, Zhao & Felsberg, ICML 2024](https://proceedings.mlr.press/v235/jonnarth24a.html), cùng [bản toàn văn](https://arxiv.org/html/2306.16978v3), nghiên cứu map egocentric nhiều tỉ lệ, frontier representation, reward total variation và điều khiển liên tục với SAC. Nghiên cứu hỗ trợ việc cung cấp ngữ cảnh rộng hơn và giảm lỗ coverage; không chứng nhận combo 9×9+centroid+DQN hay cam kết 20.000 episode trong vài phút. Các lựa chọn trong báo cáo này là thiết kế thực dụng cho repo, không phải tái lập paper.

“Li 2023” chưa đủ tên bài/DOI để xác định duy nhất. Không gán một công thức hoặc kết luận cho nguồn đó. [Jonnarth et al., Sim-to-Real 2024](https://arxiv.org/abs/2406.04920) cũng đánh giá riêng ảnh hưởng của dynamics và tần suất suy luận; không thể suy ra rằng xuất ONNX xong là đã giải quyết sim-to-real.

## Bước tiếp theo

Dán prompt ngắn dẫn tới `ANTIGRAVITY_PROMPT.md` vào Antigravity. Yêu cầu agent để lại diff, test/evaluation JSON, manifest và trạng thái các gate. Người giám sát kiểm tra artifact thực tế thay vì tin dòng “done”. Chưa có thao tác gửi trực tiếp tới cửa sổ Antigravity hoặc monitor nền trong lượt này.
