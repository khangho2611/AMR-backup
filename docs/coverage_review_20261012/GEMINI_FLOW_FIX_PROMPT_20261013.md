# Gemini: sua dung luong code - khong chay training

Snapshot trainer: ae235055f71df68f8586aa557c0ed4d92c02a799e070ef0e13e68bf275db41bb.
Codex da chay 10 tests: PASS. Loi NaN/Inf, exit code, sentinel, gate 95%,
raw_obstacle metadata da sua. Khong lam lai cac muc da dung.
Chi sua code va tests co lap. KHONG train, KHONG danh gia chat luong model,
KHONG thay models/coverage_model.onnx hay .pth trong luot nay.

## Loi con lai

1. trainer:663 thay LAST checkpoint thanh BEST neu thieu file best, nhung
   giu best metrics lich su. Weights va metrics khong thuoc cung model.
   Khong duoc promote LAST weights bang BEST metrics. Thieu best artifact
   thi candidate UNVERIFIED; can acceptance moi, dung evaluator stub o tests.

2. trainer:778/799/859/921: best duoc chon tren 25 validation seeds nhung
   khong duoc acceptance lai tren tap day du; final evaluation chi danh gia
   final policy. Acceptance phai danh gia DUNG selected checkpoint, metrics
   gan weights hash va seed-set identity. Smoke/validation khong la acceptance.

3. trainer:930/931: ONNX thay truoc PTH. Inject OSError lan replace thu hai
   se de lai NEW_ONNX + OLD_PTH. Stage va kiem tra ca bo; can version pointer
   atomic hoac rollback co test, giu giao dien duong dan da thong nhat.
   Atomic tung file khong phai transaction ca bo. Manifest phai ghi loi commit.

4. trainer:687/844: resume episode K, interrupt truoc khi hoan tat episode
   K+1 se ghi completed_ep=0. Khoi tao completed_ep=start_ep-1; giu boundary
   khi interrupted/failed truoc transition dau tien. Warm restart phai cong
   bo replay/env RNG chua khoi phuc, khong goi la full continuation.

5. trainer:204/229/246: step sau terminal van tra success bonus moi lan.
   Trainer hien tai break dung nhung env API sai contract success-once.
   Them lifecycle guard: chi reset moi cho phep bat dau episode tiep theo.

6. trainer:505/506: parity chi dung random-normal. Bo sung tests voi binary
   map/scalars hop le, all-covered/blocked/no-target va nonfinite forward/ORT.
   Day la kiem tra hop dong suy luan, khong phai evaluation coverage.

## Luong bat buoc

VALIDATE -> LOAD_CHECKPOINT_OR_WARM_RESTART -> RUN_STATUS
-> SAVE_INCOMPLETE_OR_COMPLETED -> SELECT_CANDIDATE
-> EXPORT_CANDIDATE -> VERIFY_FORMAT_FINITE_AND_CONTRACT
-> ACCEPT_SELECTED_CANDIDATE -> STAGE_ARTIFACT_SET
-> COMMIT_ARTIFACT_SET -> RECORD_FINAL_MANIFEST_AND_EXIT.

- Moi metric acceptance gan checkpoint SHA256, contract version va seed-set.
- Interrupted/failed/smoke khong promote; interrupt exit130, loi khac nonzero.
- Manifest cuoi co promoted true/false, ly do, hashes va commit_error; khong
  ghi success truoc khi commit thuc su thanh cong.
- Tach finalization thanh ham co interface ro de test truc tiep; khong tiep
  tuc cat AST ben trong run_trainer de thay cho integration tests.
- Khong nhoi them tinh nang dieu khien xe, ROS, firmware hay bypass safety.

## Tests bat buoc: stub + temp sandbox, khong learning/evaluation that

- LAST weights + BEST metrics + missing best file: khong duoc promote.
- Interim validation PASS, selected acceptance FAIL: destination giu nguyen.
- Smoke checkpoint warm restart: metrics cu khong la acceptance moi.
- Inject loi lan replace thu hai: ca hai destination rollback ve bo cu,
  manifest FAILED, exit nonzero; stage failure truoc commit cung giu bo cu.
- Resume episode37, interrupt truoc transition dau: checkpoint van episode37.
- Step sau terminated/truncated bi tu choi; success bonus chi mot lan.
- Finite weights nhung forward/ORT NaN/Inf: exporter FAIL, khong promote.
- Acceptance stub PASS: ONNX va selected PTH cung checkpoint/provenance,
  manifest promoted chinh xac sau commit.
- Giu 10 tests hien tai PASS. Bao exact command, exit code, diff va invariant
  PASS/FAIL. Khong train hay evaluate_policy/evaluate_bfs_baseline that.

Neu code tren dia da thay doi, doi chieu lai snapshot va lines truoc khi sua.
Ban giao de Codex review doc lap; khong tu ket luan deployment-ready.
