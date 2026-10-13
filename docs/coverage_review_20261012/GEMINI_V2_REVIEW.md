# Review độc lập phần Gemini đã làm — 12/10/2026

## Kết luận: CHƯA ĐẠT yêu cầu nghiệm thu

Gemini đã làm được bản point-grid V2 có budget khả thi, BFS guidance và Double DQN. Nhưng vòng quản lý model có lỗi làm candidate chưa đạt được ghi đè thành model chính; kiểm thử chưa bao phủ code thực; chưa hoàn thành các giai đoạn đánh giá và sim-to-real đã giao.

Review theo snapshot trainer SHA256 `f89b7f6f0b9b47eb0378ea2ec440d7fc75992a4700db8e2ac4b1b8bf32fe4fb1`. Toàn bộ hashes và dữ liệu từng episode ở `audit_gemini_v2.json`. Reviewer không sửa trainer, BAT hoặc model. Hash đầu/cuối audit giống nhau.

## Những phần đã đúng

- `max_steps=max(100,4*N_reachable)` đã bỏ trần coverage bất khả thi của V1.
- Reachability flood fill, BFS hướng đoạn đầu đường đi, action mask trong exploration/greedy/TD target được triển khai cho robot điểm trên bản đồ biết trước.
- Replay lưu riêng terminated/truncated; Double DQN target dùng terminated để cắt bootstrap, không dùng truncation.
- Va chạm bị chặn giữ vị trí và vẫn tiêu thụ bước; đã kiểm tra chính lớp `GridCoverageEnvV2` với collision ở bước cuối budget.
- CNN fusion 3 channel/8 scalar được sử dụng; ONNX 132.717 byte, không external initializer, load từ bytes thành công.
- BAT đã `cd /d "%~dp0"` và lấy errorlevel ngay sau Python. Tuy nhiên mã trả về từ Python đang sai nên thông báo BAT vẫn có thể sai.
- Có snapshot backup V1 trong `models/runs/v1_baseline_snapshot/`.

## Findings cần sửa

### P1 — Candidate không đạt chất lượng vẫn ghi đè model chính

`train_coverage_20000.py:640–648` chỉ yêu cầu numerical ONNX PASS rồi ghi đè `models/coverage_model.onnx`. Không kiểm tra smoke/incomplete, số episode hoàn tất, coverage, success rate hoặc bộ test. Manifest smoke có 10 episode, coverage 55,38%, 0/10 đạt 95%, nhưng SHA256 model chính trùng hoàn toàn smoke candidate. Đây là sự cố đã xảy ra, không chỉ khả năng lý thuyết.

`write_bytes` ghi trực tiếp/truncate destination, không phải atomic replacement dù log ghi “ATOMIC PROMOTE”. Chương trình cũng lưu best checkpoint ở dòng 617 nhưng export final checkpoint ở dòng 623–627: nếu cuối run tụt chất lượng thì không xuất checkpoint tốt nhất đã chọn bằng validation.

Sửa: tách export candidate và promotion; smoke/incomplete không promote; chọn best validated checkpoint; chỉ promote sau software quality gates; ghi file tạm cùng filesystem rồi `os.replace`, kèm manifest/hash nhất quán. Không tự rollback V1 thành “model đạt chuẩn”: V1 cũng chưa đạt.

### P1 — Ctrl+C hoặc export FAIL vẫn báo thành công

`train_coverage_20000.py:619–648`: KeyboardInterrupt bị bắt rồi tiếp tục export/promote và return 0. Manifest `episodes` là số yêu cầu, không phải số đã hoàn tất. ONNX status FAIL cũng rơi xuống return 0; BAT vì vậy in thành công.

Đã tái hiện bằng chính `run_trainer` trong thư mục tạm, thay baseline/export bằng stub chỉ để kiểm tra control flow:

| Tình huống | Exit code | Model sentinel bị ghi đè | episodes trong manifest |
|---|---:|---|---:|
| 0 episode + export PASS giả lập | 0 | Có | 0 |
| Interrupt trước transition đầu tiên + export PASS giả lập | 0 | Có | 20.000 |
| Gate export FAIL giả lập | 0 | Không | 0 |

Các thử này không ghi vào models thật và không phải phép kiểm tra exporter. Sửa bằng status completed/interrupted/failed, số episode thực hoàn tất, checkpoint incomplete, exit 130 khi interrupt và nonzero khi gate fail. CLI phải từ chối số episode/frequency/batch không hợp lệ trước khi làm việc.

### P1 — Test môi trường không kiểm tra trainer thật

`tests/test_coverage_v2.py:31` tự định nghĩa `MockGridEnv`, rồi kiểm tra bản sao đó. File test không import `train_coverage_20000.GridCoverageEnvV2`. Các test Double DQN/reward/network kiểm tra module golden reference, có giá trị cho kernel nhưng không chứng minh đường dữ liệu trainer dùng kernel đúng. Test horizon chỉ tính số học constants.

Lệnh `python -m unittest discover -s tests -p test_coverage_v2.py -v` trả 8/8 PASS. Điều này không đủ để ghi G1 PASS. Sửa bằng fixture map/start cho production env, test trực tiếp production step/reset/obs/mask, replay collector và trainer lifecycle. Giữ kernel unit tests nhưng bổ sung integration tests. Cần test all-false/nonfinite, single-cell, disconnected, terminal/truncation, timeout mọi nhánh, preservation model, CLI/BAT exit codes.

### P1 — Seed không tái lập training; chưa có resume

`run_trainer:478–486` chỉ truyền seed vào environment. Exploration/replay dùng module `random` và trọng số dùng Torch nhưng không seed hai nguồn này. CLI `--seed 42` không bảo đảm khởi tạo mạng hoặc chuỗi training giống nhau.

Checkpoint ở dòng 617/623 chỉ là state_dict mạng. Không có target/optimizer/RNG/replay/counters/config. `--checkpoint` chỉ được sử dụng trong nhánh eval-only; không có --resume. Sửa thành seed đầy đủ và full checkpoint/resume, hoặc công bố warm restart rõ ràng; không gọi weights-only là resumable checkpoint.

### P1 — Chưa có simulator/contract cho robot thật

`GridCoverageEnvV2:113–122,157–189,198–247` vẫn là robot điểm, map hoàn toàn biết trước, mỗi bước dịch một ô, duration=1. Channel thứ ba là covered thay vì unknown; không có observed-map mode, inflation, swept footprint, sensor observation, quay theo feedback hoặc thời lượng option. Heading là hướng action mới nhất, thậm chí đổi ở blocked action.

Điều này chấp nhận được cho baseline known-map nếu gắn nhãn đúng. Chưa đáp ứng nhánh realistic simulator đã yêu cầu và không được tuyên bố là deploy-ready. Metadata ONNX kiểm tra được là `{}` nên consumer cũng chưa có contract xác định channels/actions/frame/mode/normalization. Cần ghi contract và đánh dấu hardware gate BLOCKED khi thiếu số đo/thiết bị.

### P2 — Bộ đánh giá và bàn giao còn thiếu

Trong `models/runs/` chỉ thấy V1 snapshot và smoke_test_run. Manifest chứng minh 10 episode, không có bằng chứng full run 20.000, acceptance_report, test ≥500 seeds tách biệt, geometry diversity, confidence intervals, random-masked/STC baseline, raw-policy vs mask/fallback comparison, profiler hay Pi latency. Training validation chỉ dùng 50 seeds, smoke 10; eval-only dùng 100 seeds bao gồm tập validation, không có test split độc lập được định nghĩa.

Exporter dòng 435–458 chỉ dùng 100 random-normal inputs, không realistic obs hoặc ONNX rollout. Review này đã bổ sung rollout độc lập bên dưới nhưng không thay thế quy trình nghiệm thu của implementation.

### P2 — Loop/no-progress chưa có recovery

`steps_without_new_cell` chỉ thành feature rồi clamp sau 100 bước, không có replan/recovery/no-progress stop có lý do. BFS chọn lại goal mỗi bước, không lưu hysteresis. Budget giúp không chạy vô hạn nhưng model có thể tiêu hết hàng nghìn bước trong loop. Quan sát audit có episode 3.352 bước cuối không tăng coverage.

Ngoài ra epsilon vẫn giảm theo episode ở dòng 589, chưa theo global steps như spec; fallback khi Q nonfinite ở dòng 537 lại chọn action ngẫu nhiên thay vì STOP/failure. Cần kiểm tra finite loss/Q và xử lý lỗi nhất quán.

## Đánh giá ONNX độc lập

Chạy `python docs/coverage_review_20261012/audit_gemini_v2.py`. Dùng model thật từ `models/coverage_model.onnx`, production environment, epsilon=0, mask đúng. Không train thêm hoặc chỉnh reward/budget.

| Tập seed | Mean coverage | Số đạt ≥95% | Timeout |
|---|---:|---:|---:|
| 10000–10009, cùng validation smoke | 55,3835% | 0/10 | 10/10 |
| 20000–20019, bổ sung cho audit | 46,7547% | 0/20 | 20/20 |
| BFS cùng 20000–20019 | 100% | — | — |

BFS trung bình 899,35 bước. PyTorch/ONNX sampled parity max abs error 1,526e-5. Numerical export có vẻ đúng trong các mẫu được kiểm tra; hành vi coverage chưa đạt. Vì chỉ mới train 10 episode, không suy ra rằng thuật toán không thể học tốt sau này. Kết quả chứng minh việc promote candidate hiện tại là sai gate.

Các audit seeds bổ sung chưa nằm trong validation được code khai báo; không có seed manifest train đầy đủ để tuyên bố geometry tuyệt đối chưa từng thấy.

## Gate status

| Gate | Trạng thái |
|---|---|
| G1 correctness offline | PARTIAL: kernels pass, production tests thiếu |
| G2 smoke/export/lifecycle | FAIL: promotion, interruption, exit-code và checkpoint lỗi |
| G3 pilot/evaluation | PARTIAL: BFS + một phần validation; model hiện tại không đạt chất lượng |
| G4 full 20.000 + test acceptance | NOT_RUN / chưa có bằng chứng trên đĩa |
| G5 deployment/Pi | NOT_RUN; simulator/contract còn thiếu |

## Prompt phản hồi để gửi Gemini

```text
Codex đã review code của bạn và kết luận CHƯA ĐẠT.
Đọc docs/coverage_review_20261012/GEMINI_V2_REVIEW.md và audit_gemini_v2.json.

Sửa theo thứ tự:
1. Ngăn smoke, interrupted, zero-episode hoặc quality-failed candidate ghi đè model chính.
   Dùng best validated checkpoint và atomic replacement thật; chưa được promote bản hiện tại.
2. Ctrl+C lưu incomplete checkpoint, trả 130; export/gate fail trả nonzero.
   Ghi requested/completed episodes riêng và validate CLI số dương trước khi chạy.
3. Thay tests trên MockGridEnv bằng tests trực tiếp production env và trainer lifecycle.
   Bổ sung regression tests tái hiện ba lỗi audit đã chỉ ra.
4. Seed Python/NumPy/Torch đầy đủ; bổ sung full checkpoint/resume, không chỉ weights.
5. Gắn nhãn known-map point-grid hiện tại; thực hiện observed-map/footprint theo prompt gốc,
   ghi ONNX metadata contract, không gọi bản này deploy-ready.
6. Thêm no-progress handling, finite checks, đánh giá checkpoint tốt nhất, ONNX rollout,
   test split và báo cáo các gate đúng trạng thái.
7. Sau khi G1/G2 sửa và kiểm thử thật sự qua mới tiếp tục pilot/full train 20.000.
   Bàn giao acceptance_report.md, metrics/manifest/hash và lệnh tái hiện.

Hiện model chính là smoke 10-episode: audit 20 seed bổ sung chỉ đạt 46,75%, 0/20 đạt 95%,
trong khi BFS cùng seeds đạt 100%. Không sửa evaluator hoặc hạ gate để làm kết quả pass.
Giữ nguyên evidence của Codex; không sửa ROS/firmware, bypass safety hoặc chạy xe thật.
```
