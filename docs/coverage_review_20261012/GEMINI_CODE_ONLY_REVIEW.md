# Review code Gemini lần tiếp theo — không kiểm tra training

Kết luận: **chưa thể chấp nhận code**, dù đã sửa nhiều lỗi của lần trước.

Snapshot trainer SHA256: `7f8152fc41a6de14d829fe3c0e17a19c6cc6a2872f45ec7b6d8dbf20a97d07e3`.

Phạm vi: đọc code, chạy 7 unit tests không gọi trainer, kiểm tra exporter bằng mạng tổng hợp chứa NaN và kiểm tra khối promotion trích nguyên AST từ source. Không gọi run_trainer, không optimizer/backprop, không chạy baseline, không đánh giá coverage hoặc model đang lưu. Test regression smoke của Gemini bị loại vì nó thực sự chạy training. Trainer/BAT/model không bị sửa; hash production trước/sau audit giữ nguyên.

## 1. P1 — Model đầu ra NaN vẫn được exporter cho PASS

Vị trí `train_coverage_20000.py:451–465`.

`np.max(abs(pt_out-ort_out))` trả NaN nếu outputs NaN; `max(0.0, float('nan'))` giữ 0.0. Do không kiểm tra isfinite và dùng max_abs_error để quyết định PASS, model hỏng có thể vượt gate.

Đã tái hiện với `CoverageQNet` chưa train, đặt trọng số convolution đầu thành NaN và gọi exporter thật trong thư mục tạm. Kết quả: output toàn NaN, `max_abs_error=0.0`, `status=PASS`. Không liên quan chất lượng học; đây là lỗi kiểm tra số học.

Sửa: từ chối nonfinite parameters, inputs, PyTorch outputs, ONNX outputs và error; kiểm tra np.isfinite trước reduction. Dùng tolerance đã định nghĩa và báo mismatch rõ. Thêm regression test NaN/Inf luôn FAIL/nonzero và không promote.

## 2. P1 — ONNX FAIL vẫn return 0 trong một số nhánh

Vị trí `train_coverage_20000.py:754–764`.

Exit code chỉ đổi sang 1 khi không smoke và best_eval_coverage thấp. Nếu smoke có exporter FAIL, hoặc coverage đủ nhưng exporter FAIL, hàm vẫn trả 0. BAT sẽ in thành công.

Đã thực thi nguyên khối promotion/status trích bằng AST, với atomic_promote là spy, không chạy trainer:

| Trạng thái đầu vào | Kết quả |
|---|---|
| smoke, ONNX FAIL | exit 0, không promote |
| completed, coverage giả lập 99, ONNX FAIL | exit 0, không promote |

Sửa: gate exporter FAIL luôn nonzero, độc lập với smoke/coverage; giữ 130 cho interrupted nếu quy ước ưu tiên đó. Catch exporter exception và ghi manifest FAILED trước khi thoát. Hiện manifest chỉ ghi sau export nên exception có thể làm mất manifest mới và trạng thái interruption.

## 3. P1 — Resume chưa khôi phục đầy đủ và có thể làm hỏng bước bàn giao

Vị trí `train_coverage_20000.py:530–540,666–695,699–752`.

Đã thêm policy/target/optimizer nhưng vẫn thiếu replay, Python/NumPy/Torch/env RNG state, epsilon. Epsilon khởi tạo lại 1.0, môi trường sinh lại từ seed ban đầu; đây không phải tiếp tục đúng trạng thái cũ. Không tìm thấy resume path thì code âm thầm train mới.

Có lỗi cụ thể hơn: resume khôi phục `best_eval_coverage` nhưng không mang `best_checkpoint.pth` sang run_dir mới. Nếu không có điểm mới tốt hơn best cũ, run_dir không có file best. Export dùng policy cuối thay vì best; khi quality_passed đúng, ONNX được thay trước rồi `atomic_promote(best_checkpoint.pth,...)` thất bại FileNotFoundError. Hai model có thể mất đồng bộ. Nếu resume episode đã bằng/vượt episodes yêu cầu, vòng lặp rỗng nhưng status vẫn COMPLETED và completed_episodes=0.

Sửa: validate resume path/range/config; mang theo best policy và metrics gắn cùng checkpoint; kiểm tra toàn bộ nguồn trước promotion. Khôi phục đầy đủ state hoặc gắn nhãn warm restart, không tuyên bố full resume. Atomic từng file chưa phải transaction cho cả bộ artifacts.

## 4. P2 — Regression test smoke dùng sentinel không liên quan destination

Vị trí `tests/test_coverage_v2.py:128–159`.

Test tạo `tmp/protected_model.onnx`, nhưng code production ghi `ROOT/models/coverage_model.onnx`. Test không patch ROOT và không kiểm tra đường dẫn destination thật, nên sentinel không đổi kể cả production code ghi đè model chính. Ngoài ra test chạy 2 episode thật và exporter thật, không phải unit test nhỏ cô lập.

Sửa: patch ROOT vào temp sandbox, đặt sentinel tại `sandbox/models/coverage_model.onnx` và .pth, stub environment/evaluator/exporter để kiểm tra control flow mà không train. Kiểm tra hashes, promotion-call count, manifest và exit code cho smoke, interruption, export fail và success. Các production env tests đã được thay thế đúng hướng; 7 test không training chạy PASS trong review này.

## 5. P2 — Điều kiện chọn model bị hạ so với spec

Vị trí `train_coverage_20000.py:741–745,787`.

Default threshold hiện là 90%, trong khi prompt gốc yêu cầu mean≥95% và ≥95% episode đạt coverage≥95%. Code chỉ dùng best mean, bỏ qua success rate. Đây là kiểm tra logic gate, không phải đánh giá training.

AST case coverage giả lập 92%, export PASS, completed, non-smoke đã cho quality_passed=True và gọi promotion hai lần. Sửa threshold và success-rate condition đúng contract, metric phải thuộc cùng selected checkpoint. Việc cấu hình threshold thấp cho thử nghiệm không được âm thầm coi là acceptance production.

## Điểm đã sửa đúng và giới hạn còn lại

- Có seed Python/NumPy/Torch cho run mới.
- Có validation episodes/train_freq/batch_size dương; còn thiếu target_sync_freq>0 (hiện có thể modulo zero), buffer_size hợp lệ, threads>0, lr finite dương và threshold hữu hạn trong [0,100].
- Có production environment tests thay cho MockGridEnv.
- Có atomic replace cho từng file; smoke/interrupted bị chặn promotion trong nhánh điều kiện bình thường.
- Có requested/completed episodes và trạng thái interrupted.
- Có lựa chọn best checkpoint trong run mới, nhưng resume chưa xử lý best đúng như finding 3.
- Có metadata mode known_map_point_grid_baseline. Tuy nhiên channel 1 ghi `inflated_blocked` trong khi observation vẫn chỉ `(patch == OBSTACLE)`, chưa có inflation; cần ghi đúng raw_obstacle cho mode này.
- Nhánh Q không hữu hạn vẫn fallback random action tại dòng 586; cần chuyển thành lỗi/STOP rõ, tránh che model hỏng.

## Bằng chứng và cách tái hiện

`python docs/coverage_review_20261012/audit_code_only.py`

Kết quả: `audit_code_only.json`. Script chỉ dùng model tổng hợp chưa train, temp files và khối promotion tách riêng; không chạy learning hoặc đánh giá policy.

## Prompt gửi Gemini

```text
Đọc docs/coverage_review_20261012/GEMINI_CODE_ONLY_REVIEW.md và audit_code_only.json.
Sửa lỗi CODE, chưa chạy training:
1. NaN/Inf phải fail exporter; thêm regression tests.
2. ONNX FAIL luôn trả nonzero và lưu manifest; interrupted giữ trạng thái đúng.
3. Resume phải xử lý missing path, RNG/replay/epsilon và best checkpoint liên tục;
   ngăn ONNX bị thay rồi mới phát hiện thiếu best_checkpoint.pth.
4. Regression tests phải patch ROOT và bảo vệ đúng destination model; dùng stub,
   không dùng smoke training để test control flow.
5. Khôi phục acceptance gate đúng spec, đủ mean và success rate trên selected checkpoint.
6. Validate toàn bộ numeric CLI, sửa metadata raw/inflated và nonfinite Q handling.
Bàn giao diff và unit-test results; không chạy train hoặc đánh giá chất lượng model ở lượt này.
```
