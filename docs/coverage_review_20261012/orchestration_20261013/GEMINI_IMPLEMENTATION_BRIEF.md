You are the sole GEMINI IMPLEMENTATION WORKER. The human explicitly requested Gemini to fix code and Claude Opus4.6 to review. This is an API generation call; you have NO filesystem or shell tools. Generate a precise apply_patch patch for the source pasted below. Do not ask what the task is. You are not alone in the codebase; preserve others' edits and unrelated files. Ownership ONLY train_coverage_20000.py, tests/test_coverage_v2.py, run_train_20000.bat if exit/report wording needs updating. NO training, NO real policy evaluation, NO official models writes, hardware/ROS/firmware changes, dependencies, global config, commits or arbitrary executable tasks. All new tests MUST exercise actual production functions with stubs/temp dirs, never real evaluate_policy or evaluate_bfs_baseline; preserve the other prior tests. Root executes the patch and tests after validating it. No model files will be changed this turn.

SUBTASK: Repair all six verified bugs in the brief, using a maintainable scoped implementation.
ADVISOR CONDITIONS: Acceptance must bind selected exact immutable checkpoint SHA256, contract version, full fixed100seed-set identity and evaluation mode. Historical best/smoke/25seed metrics never count as production acceptance. It is fine to use last weights as explicitly unverified fallback when best missing, but use FRESH acceptance before promotion. Stage both artifacts and preserve exact old bytes or original absence; rollback and report rollback failure/nonzero truthfully. Two os.replace calls are not a concurrent-reader atomic transaction; document practical tested rollback limit, keep existing filenames. Never write a success manifest before actual outcome. Tests must be structurally unable to enter training/real evaluation. Extract small callable functions for selection/finalization/commit; don't replace integration with AST slices. Interrupted/failed/smoke never promote; preserve interrupted episode boundary and exit130 even before first new transition. Explicit warm restart replay/env RNG limitations. No unrelated reward/architecture/robotics redesign. Add numerical-forward/ORT nonfinite and valid binary observation boundary parity tests. Keep95% success/coverage gate and numerical checks.

OUTPUT FORMAT: exactly one JSON object with keys patch, summary, verification_plan, limitations. patch is a string in Codex apply_patch format beginning *** Begin Patch and ending *** End Patch, containing ONLY *** Update File operations for the three owned files. Include ample unique context for every hunk. No delete/move/add operations. Root applies your patch directly; do not emit shell commands or reconstructed entire source files. summary and limitations are lists of concrete strings; verification_plan is a list of isolated test commands. Do not claim tests were executed in this tool-less call, do not claim deployment readiness. Fix underlying flow, not only tests. Generation may be followed by a separate correction call with actual failure feedback.


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



CURRENT FILE: train_coverage_20000.py
```python
"""
Huấn Luyện AI Phủ Kín Bản Đồ Ma Trận 2D (Coverage DRL V2)
Tuân thủ hợp đồng kỹ thuật và khuyến nghị từ docs/coverage_review_20261012.

Đặc tả:
- Kiến trúc mạng: CoverageQNet (32,644 tham số, 3 channels, 8 scalar features).
- Double DQN + Action Masking an toàn.
- Ngân sách bước: 4 * N_reachable (xóa bỏ trần horizon 44.5% của V1).
- Va chạm vật cản: Phạt điểm, giữ vị trí (không kết thúc màn sớm).
- Tách biệt terminated (hoàn thành) và truncated (hết thời gian) theo chuẩn Gymnasium.
- Xuất ONNX đơn file, nhúng metadata contract, kiểm chứng số học chặt chẽ (từ chối NaN/Inf).
- Khóa van Promotion nghiêm ngặt: chỉ promote khi qua toàn bộ Software Quality Gates.
"""

from pathlib import Path
import os
import sys
import time
import json
import random
import argparse
import hashlib
from collections import deque

# Bảng mã UTF-8 an toàn cho console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
os.environ["PYTHONIOENCODING"] = "utf-8"

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import docs.coverage_review_20261012.golden_reference as gr


# ==============================================================================
# 1. MÔI TRƯỜNG GIẢ LẬP LƯỚI MA TRẬN 2D (GridCoverageEnvV2)
# ==============================================================================
class GridCoverageEnvV2:
    def __init__(self, size=32, seed=None):
        self.size = size
        self.UNCOVERED = 1
        self.COVERED = 0
        self.OBSTACLE = 100
        # Thứ tự 4 hướng: 0: Up (-1, 0), 1: Down (1, 0), 2: Left (0, -1), 3: Right (0, 1)
        self.actions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        self.rng = random.Random(seed)
        self.np_rng = np.random.RandomState(seed)
        self.padded_grid = np.full((self.size + 8, self.size + 8), self.OBSTACLE, dtype=np.int8)
        self.current_potential = 0.0
        self.reset()

    def reset(self, seed=None):
        if seed is not None:
            self.rng = random.Random(seed)
            self.np_rng = np.random.RandomState(seed)

        self.grid = np.full((self.size, self.size), self.UNCOVERED, dtype=np.int8)

        # 1. Tường bao 4 cạnh
        self.grid[0, :] = self.OBSTACLE
        self.grid[-1, :] = self.OBSTACLE
        self.grid[:, 0] = self.OBSTACLE
        self.grid[:, -1] = self.OBSTACLE

        # 2. Sinh chướng ngại vật ngẫu nhiên (4-7 khối)
        num_obs = self.rng.randint(4, 7)
        for _ in range(num_obs):
            bw = self.rng.randint(2, 4)
            bh = self.rng.randint(2, 4)
            bx = self.rng.randint(2, self.size - bw - 2)
            by = self.rng.randint(2, self.size - bh - 2)
            self.grid[by:by+bh, bx:bx+bw] = self.OBSTACLE

        # 3. Chọn điểm xuất phát ngẫu nhiên trên ô trống
        empty_ys, empty_xs = np.where(self.grid == self.UNCOVERED)
        idx = self.rng.randint(0, len(empty_ys) - 1)
        self.ry = int(empty_ys[idx])
        self.rx = int(empty_xs[idx])

        # 4. Xác định thành phần liên thông tiếp cận được (Reachable Component)
        self.reachable_cells = self._compute_reachable()
        self.total_reachable = len(self.reachable_cells)

        # Ngân sách bước: 4 * N_reachable
        self.max_steps = max(100, 4 * self.total_reachable)

        # Đánh dấu ô bắt đầu là đã dọn
        self.grid[self.ry, self.rx] = self.COVERED
        self.covered_count = 1
        self.steps = 0
        self.steps_without_new_cell = 0
        self.last_action_idx = 1 # mặc định hướng Down

        self.padded_grid.fill(self.OBSTACLE)
        self.padded_grid[4:4+self.size, 4:4+self.size] = self.grid
        return self._get_obs()

    def _compute_reachable(self):
        seen = {(self.ry, self.rx)}
        q = deque([(self.ry, self.rx)])
        while q:
            cy, cx = q.popleft()
            for dy, dx in self.actions:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < self.size and 0 <= nx < self.size:
                    if (ny, nx) not in seen and self.grid[ny, nx] != self.OBSTACLE:
                        seen.add((ny, nx))
                        q.append((ny, nx))
        return seen

    def get_valid_mask(self):
        """Mặt nạ nhị phân 4 hành động: True nếu ô kế tiếp là hợp lệ và không phải tường."""
        mask = []
        for dy, dx in self.actions:
            ny, nx = self.ry + dy, self.rx + dx
            if 0 <= ny < self.size and 0 <= nx < self.size and self.grid[ny, nx] != self.OBSTACLE:
                mask.append(True)
            else:
                mask.append(False)
        return np.array(mask, dtype=bool)

    def find_geodesic_target(self):
        """Tìm đường đi ngắn nhất (BFS Geodesic) tới ô chưa dọn tiếp cận được gần nhất."""
        size = self.size
        visited = bytearray(size * size)
        visited[self.ry * size + self.rx] = 1
        q = deque([(self.ry, self.rx, None, 0)])
        target_pos = None
        first_act = None
        dist = 0

        while q:
            cy, cx, first, d = q.popleft()
            if self.grid[cy, cx] == self.UNCOVERED:
                target_pos = (cy, cx)
                first_act = first
                dist = d
                break
            for a_idx, (dy, dx) in enumerate(self.actions):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < size and 0 <= nx < size:
                    idx = ny * size + nx
                    if not visited[idx] and self.grid[ny, nx] != self.OBSTACLE:
                        visited[idx] = 1
                        q.append((ny, nx, a_idx if first is None else first, d + 1))

        if target_pos is None or first_act is None:
            return 0.0, 0.0, 0.0, False

        dy, dx = self.actions[first_act]
        norm = max(1e-5, np.hypot(dy, dx))
        path_dy, path_dx = dy / norm, dx / norm
        max_dist = 2.0 * self.size
        path_dist_norm = min(1.0, dist / max_dist)
        return float(path_dx), float(path_dy), float(path_dist_norm), True

    def _get_obs(self):
        """
        Tạo quan sát chuẩn:
        - local_map: (3, 9, 9) float32 (Channel 0: Uncovered, 1: Raw Obstacle, 2: Covered)
        - features:  (8,) float32 [path_dx, path_dy, path_dist_norm, has_target, sin_yaw, cos_yaw, cov_frac, no_prog_frac]
        """
        self.padded_grid[4:4+self.size, 4:4+self.size] = self.grid
        cy, cx = self.ry + 4, self.rx + 4
        patch = self.padded_grid[cy-4:cy+5, cx-4:cx+5]

        ch_uncov = (patch == self.UNCOVERED).astype(np.float32)
        ch_obs   = (patch == self.OBSTACLE).astype(np.float32)
        ch_cov   = (patch == self.COVERED).astype(np.float32)
        local_map = np.stack([ch_uncov, ch_obs, ch_cov], axis=0) # (3, 9, 9)

        p_dx, p_dy, p_dist, has_tgt = self.find_geodesic_target()
        self.current_potential = -float(p_dist) if has_tgt else 0.0

        last_dy, last_dx = self.actions[self.last_action_idx]
        yaw = np.arctan2(last_dy, last_dx)
        sin_yaw = float(np.sin(yaw))
        cos_yaw = float(np.cos(yaw))

        cov_frac = float(self.covered_count / max(1, self.total_reachable))
        no_prog_frac = float(min(1.0, self.steps_without_new_cell / 100.0))

        features = np.array([
            p_dx, p_dy, p_dist, 1.0 if has_tgt else 0.0,
            sin_yaw, cos_yaw, cov_frac, no_prog_frac
        ], dtype=np.float32)

        return local_map, features

    def compute_potential(self):
        """Phi(s) = -clip(d_geodesic / Dmax, 0, 1)"""
        _, _, p_dist, has_tgt = self.find_geodesic_target()
        if not has_tgt:
            return 0.0
        return -float(p_dist)

    def step(self, action_idx):
        dy, dx = self.actions[action_idx]
        ny, nx = self.ry + dy, self.rx + dx
        self.steps += 1
        self.last_action_idx = action_idx

        phi_before = self.current_potential
        blocked = False
        new_area = 0.0
        revisit = 0.0

        if not (0 <= ny < self.size and 0 <= nx < self.size) or self.grid[ny, nx] == self.OBSTACLE:
            blocked = True
            self.steps_without_new_cell += 1
        else:
            self.ry, self.rx = ny, nx
            if self.grid[ny, nx] == self.UNCOVERED:
                self.grid[ny, nx] = self.COVERED
                self.covered_count += 1
                new_area = 1.0
                self.steps_without_new_cell = 0
            else:
                revisit = 1.0
                self.steps_without_new_cell += 1

        terminated = (self.covered_count >= self.total_reachable)
        truncated = (self.steps >= self.max_steps) and not terminated
        success = (self.covered_count >= self.total_reachable)

        obs = self._get_obs()
        phi_after = self.current_potential
        discount = 0.99

        reward = gr.shaped_reward(
            new_area_units=new_area,
            revisit_units=revisit,
            duration_units=1.0,
            blocked=blocked,
            success=success,
            phi_before=phi_before,
            phi_after=phi_after,
            discount=discount,
            terminated=terminated
        )

        info = {
            "blocked": blocked,
            "new_area": bool(new_area > 0),
            "covered_count": self.covered_count,
            "total_reachable": self.total_reachable,
            "coverage_pct": (self.covered_count / max(1, self.total_reachable)) * 100.0
        }
        return obs, float(reward), terminated, truncated, info


# ==============================================================================
# 2. BỘ ĐỆM KINH NGHIỆM (REPLAY BUFFER)
# ==============================================================================
class ReplayBuffer:
    def __init__(self, capacity=40000):
        self.buffer = deque(maxlen=capacity)

    def push(self, map_s, feat_s, action, reward, map_next, feat_next,
             terminated, truncated, mask_s, mask_next):
        self.buffer.append((
            map_s, feat_s, int(action), float(reward),
            map_next, feat_next, bool(terminated), bool(truncated),
            mask_s, mask_next
        ))

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        maps_s, feats_s, actions, rewards, maps_next, feats_next, \
            terms, truncs, masks_s, masks_next = zip(*batch)

        return (
            torch.tensor(np.array(maps_s), dtype=torch.float32),
            torch.tensor(np.array(feats_s), dtype=torch.float32),
            torch.tensor(actions, dtype=torch.long),
            torch.tensor(rewards, dtype=torch.float32),
            torch.tensor(np.array(maps_next), dtype=torch.float32),
            torch.tensor(np.array(feats_next), dtype=torch.float32),
            torch.tensor(terms, dtype=torch.bool),
            torch.tensor(truncs, dtype=torch.bool),
            torch.tensor(np.array(masks_s), dtype=torch.bool),
            torch.tensor(np.array(masks_next), dtype=torch.bool)
        )

    def __len__(self):
        return len(self.buffer)


# ==============================================================================
# 3. ĐÁNH GIÁ CHUẨN TRÊN CÁC SEED CỐ ĐỊNH (EVALUATION ENGINE)
# ==============================================================================
def evaluate_policy(model, env_cls, eval_seeds=range(10000, 10100), device='cpu'):
    """Đánh giá mô hình trên seed kiểm định với epsilon=0."""
    model.eval()
    coverages = []
    steps_list = []
    collisions = 0
    success_95_count = 0

    for seed in eval_seeds:
        env = env_cls(seed=seed)
        obs_map, obs_feat = env.reset(seed=seed)
        total_rec = env.total_reachable

        for _ in range(env.max_steps):
            mask = env.get_valid_mask()
            t_map = torch.tensor(obs_map, dtype=torch.float32, device=device).unsqueeze(0)
            t_feat = torch.tensor(obs_feat, dtype=torch.float32, device=device).unsqueeze(0)

            with torch.no_grad():
                q_vals = model(t_map, t_feat)[0]
                if not torch.isfinite(q_vals).all():
                    # Non-finite Q detection: dừng ngay, không fallback bừa
                    break
                action = gr.greedy_safe_action(q_vals, torch.tensor(mask, device=device))

            if action is None:
                break

            (obs_map, obs_feat), _, term, trunc, info = env.step(action)
            if info["blocked"]:
                collisions += 1

            if term or trunc:
                break

        cov_pct = (env.covered_count / max(1, total_rec)) * 100.0
        coverages.append(cov_pct)
        steps_list.append(env.steps)
        if cov_pct >= 95.0:
            success_95_count += 1

    total_eval = len(eval_seeds)
    return {
        "mean_coverage": float(np.mean(coverages)) if coverages else 0.0,
        "median_coverage": float(np.median(coverages)) if coverages else 0.0,
        "min_coverage": float(np.min(coverages)) if coverages else 0.0,
        "max_coverage": float(np.max(coverages)) if coverages else 0.0,
        "mean_steps": float(np.mean(steps_list)) if steps_list else 0.0,
        "success_ge_95": int(success_95_count),
        "success_rate_pct": float((success_95_count / max(1, total_eval)) * 100.0),
        "total_evaluated": total_eval,
        "collisions": int(collisions)
    }


def evaluate_bfs_baseline(env_cls, eval_seeds=range(10000, 10100)):
    """Baseline heuristic: BFS tới ô chưa phủ gần nhất."""
    coverages = []
    steps_list = []
    for seed in eval_seeds:
        env = env_cls(seed=seed)
        env.reset(seed=seed)
        for _ in range(env.max_steps):
            _, _, _, has_target = env.find_geodesic_target()
            if not has_target:
                break
            start = (env.ry, env.rx)
            q = deque([(start, None)])
            seen = {start}
            best_action = None
            while q:
                (cy, cx), first = q.popleft()
                if env.grid[cy, cx] == env.UNCOVERED:
                    best_action = first
                    break
                for a_idx, (dy, dx) in enumerate(env.actions):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < env.size and 0 <= nx < env.size:
                        if (ny, nx) not in seen and env.grid[ny, nx] != env.OBSTACLE:
                            seen.add((ny, nx))
                            q.append(((ny, nx), a_idx if first is None else first))
            if best_action is None:
                break
            _, _, term, trunc, _ = env.step(best_action)
            if term or trunc:
                break
        cov_pct = (env.covered_count / max(1, env.total_reachable)) * 100.0
        coverages.append(cov_pct)
        steps_list.append(env.steps)

    return {
        "mean_coverage": float(np.mean(coverages)) if coverages else 0.0,
        "median_coverage": float(np.median(coverages)) if coverages else 0.0,
        "mean_steps": float(np.mean(steps_list)) if steps_list else 0.0
    }


# ==============================================================================
# 4. XUẤT VÀ KIỂM CHỨNG ONNX (VERIFICATION GATE)
# ==============================================================================
def export_and_verify_onnx(model, onnx_path, out_dir, metadata=None):
    """Xuất file ONNX độc lập, nhúng metadata contract và kiểm tra sai số số học.
    Từ chối tuyệt đối các mô hình chứa trọng số hoặc đầu ra non-finite (NaN/Inf).
    """
    import onnx
    import onnxruntime as ort

    model.eval()
    model.to("cpu")

    # Kiểm tra xem trọng số hoặc buffer mạng có chứa NaN/Inf không
    for p in model.parameters():
        if not torch.isfinite(p).all():
            return {
                "onnx_path": str(onnx_path),
                "file_size_bytes": 0,
                "sha256": "",
                "max_abs_error": float('nan'),
                "argmax_disagreements": 100,
                "status": "FAIL",
                "reason": "Trọng số model chứa giá trị non-finite (NaN/Inf)"
            }
    for b in model.buffers():
        if not torch.isfinite(b).all():
            return {
                "onnx_path": str(onnx_path),
                "file_size_bytes": 0,
                "sha256": "",
                "max_abs_error": float('nan'),
                "argmax_disagreements": 100,
                "status": "FAIL",
                "reason": "Buffer model chứa giá trị non-finite (NaN/Inf)"
            }

    dummy_map = torch.randn(1, 3, 9, 9, dtype=torch.float32)
    dummy_feat = torch.randn(1, 8, dtype=torch.float32)

    with torch.no_grad():
        dummy_out = model(dummy_map, dummy_feat)
        if not torch.isfinite(dummy_out).all():
            return {
                "onnx_path": str(onnx_path),
                "file_size_bytes": 0,
                "sha256": "",
                "max_abs_error": float('nan'),
                "argmax_disagreements": 100,
                "status": "FAIL",
                "reason": "Output model với dummy input chứa giá trị non-finite (NaN/Inf)"
            }

    try:
        torch.onnx.export(
            model,
            (dummy_map, dummy_feat),
            str(onnx_path),
            export_params=True,
            opset_version=18,
            do_constant_folding=True,
            dynamo=False,
            input_names=['local_map', 'features'],
            output_names=['q_values']
        )
    except Exception as e:
        return {
            "onnx_path": str(onnx_path),
            "file_size_bytes": 0,
            "sha256": "",
            "max_abs_error": float('nan'),
            "argmax_disagreements": 100,
            "status": "FAIL",
            "reason": f"Export exception: {e}"
        }

    # 1. Kiểm tra cấu trúc đồ thị ONNX & nhúng metadata
    onnx_model = onnx.load(str(onnx_path), load_external_data=False)
    if metadata:
        for k, v in metadata.items():
            meta_prop = onnx_model.metadata_props.add()
            meta_prop.key = str(k)
            meta_prop.value = str(v)
        onnx.save(onnx_model, str(onnx_path))

    try:
        onnx.checker.check_model(onnx_model)
    except Exception as e:
        return {
            "onnx_path": str(onnx_path),
            "file_size_bytes": Path(onnx_path).stat().st_size if Path(onnx_path).exists() else 0,
            "sha256": "",
            "max_abs_error": float('nan'),
            "argmax_disagreements": 100,
            "status": "FAIL",
            "reason": f"Checker failed: {e}"
        }

    # 2. Kiểm tra tải từ bytes (đảm bảo không phụ thuộc file .data ngoài)
    raw_bytes = Path(onnx_path).read_bytes()
    sess_opts = ort.SessionOptions()
    sess_opts.intra_op_num_threads = 1
    session = ort.InferenceSession(raw_bytes, sess_options=sess_opts, providers=['CPUExecutionProvider'])

    # 3. Kiểm tra sai số số học (Parity Check) trên 100 mẫu
    max_abs_err = 0.0
    disagreements = 0

    for _ in range(100):
        test_map = np.random.randn(1, 3, 9, 9).astype(np.float32)
        test_feat = np.random.randn(1, 8).astype(np.float32)

        with torch.no_grad():
            pt_out = model(torch.from_numpy(test_map), torch.from_numpy(test_feat)).numpy()

        ort_out = session.run(None, {'local_map': test_map, 'features': test_feat})[0]

        if not np.isfinite(pt_out).all() or not np.isfinite(ort_out).all():
            return {
                "onnx_path": str(onnx_path),
                "file_size_bytes": len(raw_bytes),
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "max_abs_error": float('nan'),
                "argmax_disagreements": 100,
                "status": "FAIL",
                "reason": "Inference output chứa NaN/Inf"
            }

        err = np.max(np.abs(pt_out - ort_out))
        if not np.isfinite(err):
            return {
                "onnx_path": str(onnx_path),
                "file_size_bytes": len(raw_bytes),
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "max_abs_error": float('nan'),
                "argmax_disagreements": 100,
                "status": "FAIL",
                "reason": "Sai số parity không hữu hạn"
            }

        max_abs_err = max(max_abs_err, float(err))
        if pt_out.argmax() != ort_out.argmax():
            disagreements += 1

    file_size = Path(onnx_path).stat().st_size
    onnx_sha = hashlib.sha256(raw_bytes).hexdigest()

    is_pass = (
        np.isfinite(max_abs_err)
        and max_abs_err < 1e-4
        and disagreements == 0
        and file_size < 1_000_000
    )

    return {
        "onnx_path": str(onnx_path),
        "file_size_bytes": file_size,
        "sha256": onnx_sha,
        "max_abs_error": max_abs_err,
        "argmax_disagreements": disagreements,
        "status": "PASS" if is_pass else "FAIL"
    }


def atomic_promote(src_file, dst_file):
    """Ghi đè nguyên tử an toàn (atomic replace) qua file tạm trên cùng filesystem."""
    dst_path = Path(dst_file)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dst = dst_path.with_suffix(f".tmp_{int(time.time()*1000)}")
    temp_dst.write_bytes(Path(src_file).read_bytes())
    os.replace(temp_dst, dst_path)


# ==============================================================================
# 5. VÒNG LẶP HUẤN LUYỆN CHÍNH (TRAINING LOOP)
# ==============================================================================
def run_trainer(args):
    # Validation tham số số học nghiêm ngặt
    if (args.episodes <= 0 or args.train_freq <= 0 or args.target_sync_freq <= 0 or
        args.batch_size <= 0 or args.buffer_size <= 0 or args.buffer_size < args.batch_size or
        args.threads <= 0 or not np.isfinite(args.lr) or args.lr <= 0 or
        not (0.0 <= args.min_coverage <= 100.0 and np.isfinite(args.min_coverage)) or
        not (0.0 <= args.min_success_rate <= 100.0 and np.isfinite(args.min_success_rate))):
        print("[!] Lỗi tham số: Các tham số số học phải là số dương hợp lệ!")
        return 2

    # Seed đầy đủ cả 3 nguồn RNG
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    torch.set_num_threads(args.threads)
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu_only else "cpu")

    run_id = f"run_{int(time.time())}"
    run_dir = Path(args.out_dir) if args.out_dir else ROOT / "models" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"BẮT ĐẦU HUẤN LUYỆN DRL COVERAGE V2 | THIẾT BỊ: {device} | RUN DIR: {run_dir}")
    print(f"Tổng số Episodes: {args.episodes:,} | Tần suất train: {args.train_freq} bước | Seed: {args.seed} | Luồng CPU: {args.threads}")
    print("=" * 80)

    env = GridCoverageEnvV2(seed=args.seed)
    policy_net = gr.CoverageQNet(channels=3, feature_dim=8).to(device)
    target_net = gr.CoverageQNet(channels=3, feature_dim=8).to(device)
    target_net.load_state_dict(policy_net.state_dict())
    target_net.eval()

    optimizer = optim.Adam(policy_net.parameters(), lr=args.lr)
    criterion = nn.SmoothL1Loss()
    replay_buffer = ReplayBuffer(capacity=args.buffer_size)

    gamma = 0.99
    batch_size = args.batch_size
    epsilon = 1.0
    epsilon_min = 0.05
    epsilon_decay = 0.9997

    global_env_steps = 0
    start_time = time.time()
    best_eval_coverage = 0.0
    best_success_rate = 0.0
    start_ep = 1

    # Resume handling hoàn chỉnh
    if args.resume:
        resume_path = Path(args.resume)
        if not resume_path.exists():
            print(f"[!] Lỗi: Không tìm thấy checkpoint resume tại: {resume_path}")
            return 2
        print(f"[*] Nạp checkpoint khôi phục từ: {resume_path}")
        try:
            ckpt = torch.load(resume_path, map_location=device, weights_only=False)
        except Exception as e:
            print(f"[!] Lỗi: Không thể nạp checkpoint: {e}")
            return 2

        start_ep = ckpt.get("episode", 0) + 1
        if start_ep > args.episodes:
            print(f"[!] Lỗi: Checkpoint đã ở episode {start_ep - 1} >= tổng episodes yêu cầu {args.episodes}")
            return 2

        policy_net.load_state_dict(ckpt["policy_state_dict"])
        target_net.load_state_dict(ckpt["target_state_dict"])
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        global_env_steps = ckpt.get("global_env_steps", 0)
        best_eval_coverage = ckpt.get("best_eval_coverage", 0.0)
        best_success_rate = ckpt.get("best_success_rate", 0.0)
        epsilon = float(ckpt.get("epsilon", max(epsilon_min, 1.0 * (epsilon_decay ** global_env_steps))))

        if "rng_state" in ckpt:
            try:
                random.setstate(ckpt["rng_state"]["python"])
                np.random.set_state(ckpt["rng_state"]["numpy"])
                torch.set_rng_state(ckpt["rng_state"]["torch"])
            except Exception as e:
                print(f"[*] Cảnh báo: Không thể khôi phục đầy đủ RNG state: {e}")

        # Đồng bộ best_checkpoint.pth sang run_dir mới
        parent_best = resume_path.parent / "best_checkpoint.pth"
        if parent_best.exists():
            (run_dir / "best_checkpoint.pth").write_bytes(parent_best.read_bytes())
        elif resume_path.name == "best_checkpoint.pth":
            (run_dir / "best_checkpoint.pth").write_bytes(resume_path.read_bytes())
        elif best_eval_coverage > 0:
            torch.save(ckpt, run_dir / "best_checkpoint.pth")

    baseline_seeds = range(10000, 10010) if args.smoke else range(10000, 10100)
    print(f"[*] Đang chạy Baseline Heuristic (BFS) trên {len(baseline_seeds)} seed kiểm định...")
    bfs_baseline = evaluate_bfs_baseline(GridCoverageEnvV2, eval_seeds=baseline_seeds)
    print(f"    -> BFS Baseline: Phủ TB = {bfs_baseline['mean_coverage']:.2f}% | Bước TB = {bfs_baseline['mean_steps']:.1f}\n")

    manifest = {
        "run_id": run_id,
        "timestamp": time.time(),
        "requested_episodes": args.episodes,
        "completed_episodes": 0,
        "seed": args.seed,
        "threads": args.threads,
        "is_smoke": bool(args.smoke),
        "run_mode": "warm_restart" if args.resume else "scratch",
        "resume_from": str(args.resume) if args.resume else None,
        "status": "RUNNING",
        "bfs_baseline": bfs_baseline,
        "eval_history": []
    }

    exit_code = 0
    completed_ep = 0

    try:
        for ep in range(start_ep, args.episodes + 1):
            obs_map, obs_feat = env.reset()
            ep_reward = 0.0

            while True:
                global_env_steps += 1
                valid_mask = env.get_valid_mask()

                valid_indices = np.where(valid_mask)[0]
                if len(valid_indices) == 0:
                    break

                if random.random() < epsilon:
                    action = int(random.choice(valid_indices))
                else:
                    t_map = torch.tensor(obs_map, dtype=torch.float32, device=device).unsqueeze(0)
                    t_feat = torch.tensor(obs_feat, dtype=torch.float32, device=device).unsqueeze(0)
                    with torch.no_grad():
                        q_vals = policy_net(t_map, t_feat)[0]
                        if not torch.isfinite(q_vals).all():
                            print("[!] LỖI NGHIÊM TRỌNG: Phát hiện Q-values non-finite (NaN/Inf) từ policy network! Dừng huấn luyện.")
                            manifest["status"] = "FAILED"
                            exit_code = 1
                            break
                        act_opt = gr.greedy_safe_action(q_vals, torch.tensor(valid_mask, device=device))
                        action = act_opt if act_opt is not None else int(random.choice(valid_indices))

                (next_map, next_feat), reward, term, trunc, info = env.step(action)
                next_mask = env.get_valid_mask()
                ep_reward += reward

                replay_buffer.push(
                    obs_map, obs_feat, action, reward,
                    next_map, next_feat, term, trunc, valid_mask, next_mask
                )

                obs_map, obs_feat = next_map, next_feat

                # Cập nhật gradient Double DQN
                if len(replay_buffer) >= batch_size and global_env_steps % args.train_freq == 0:
                    b_map, b_feat, b_act, b_rew, b_next_map, b_next_feat, \
                        b_term, b_trunc, b_mask, b_next_mask = replay_buffer.sample(batch_size)

                    b_map = b_map.to(device)
                    b_feat = b_feat.to(device)
                    b_act = b_act.to(device)
                    b_rew = b_rew.to(device)
                    b_next_map = b_next_map.to(device)
                    b_next_feat = b_next_feat.to(device)
                    b_term = b_term.to(device)
                    b_next_mask = b_next_mask.to(device)

                    current_q = policy_net(b_map, b_feat).gather(1, b_act.unsqueeze(1)).squeeze(1)

                    with torch.no_grad():
                        next_online_q = policy_net(b_next_map, b_next_feat)
                        next_target_q = target_net(b_next_map, b_next_feat)
                        target_q = gr.double_dqn_target(
                            b_rew, b_term, gamma,
                            next_online_q, next_target_q, b_next_mask
                        )

                    loss = criterion(current_q, target_q)
                    optimizer.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(policy_net.parameters(), max_norm=10.0)
                    optimizer.step()

                if global_env_steps % args.target_sync_freq == 0:
                    target_net.load_state_dict(policy_net.state_dict())

                if term or trunc:
                    break

            if manifest.get("status") == "FAILED":
                break

            epsilon = max(epsilon_min, epsilon * epsilon_decay)
            completed_ep = ep

            log_interval = 25 if not args.smoke else 1
            if ep % log_interval == 0:
                elapsed = time.time() - start_time
                print(f"[{ep:5d}/{args.episodes}] Tập này: Phủ {info['coverage_pct']:5.1f}% | Bước: {env.steps:4d} | Global Steps: {global_env_steps:6d} | Eps: {epsilon:.3f} | T/g: {elapsed/60:4.1f}p")

            eval_interval = 500 if not args.smoke else 5
            if ep % eval_interval == 0 or ep == args.episodes:
                elapsed = time.time() - start_time
                val_seeds = range(10000, 10010) if args.smoke else (range(10000, 10100) if ep == args.episodes else range(10000, 10025))
                eval_stats = evaluate_policy(policy_net, GridCoverageEnvV2, eval_seeds=val_seeds, device=device)
                policy_net.train()

                eval_record = {
                    "episode": ep,
                    "env_steps": global_env_steps,
                    "elapsed_sec": elapsed,
                    "eval_coverage": eval_stats["mean_coverage"],
                    "eval_steps": eval_stats["mean_steps"],
                    "success_ge_95": eval_stats["success_ge_95"],
                    "success_rate_pct": eval_stats["success_rate_pct"]
                }
                manifest["eval_history"].append(eval_record)

                print(f"\n>>> [KIỂM ĐỊNH {ep:5d}/{args.episodes}] Steps: {global_env_steps:6d} | "
                      f"Eval Phủ TB: {eval_stats['mean_coverage']:5.1f}% | "
                      f"Bước TB: {eval_stats['mean_steps']:5.0f} | "
                      f"Đạt >=95%: {eval_stats['success_ge_95']:2d}/{eval_stats['total_evaluated']} | "
                      f"Eps: {epsilon:.2f} | T/g: {elapsed/60:4.1f}p\n")

                if eval_stats["mean_coverage"] > best_eval_coverage:
                    best_eval_coverage = eval_stats["mean_coverage"]
                    best_success_rate = eval_stats["success_rate_pct"]
                    torch.save({
                        "policy_state_dict": policy_net.state_dict(),
                        "target_state_dict": target_net.state_dict(),
                        "optimizer_state_dict": optimizer.state_dict(),
                        "rng_state": {
                            "python": random.getstate(),
                            "numpy": np.random.get_state(),
                            "torch": torch.get_rng_state()
                        },
                        "episode": ep,
                        "epsilon": epsilon,
                        "global_env_steps": global_env_steps,
                        "best_eval_coverage": best_eval_coverage,
                        "best_success_rate": best_success_rate,
                        "config": vars(args)
                    }, run_dir / "best_checkpoint.pth")

        if manifest["status"] == "RUNNING":
            manifest["status"] = "COMPLETED"

    except KeyboardInterrupt:
        print("\n[!] Dừng sớm do KeyboardInterrupt! Đang lưu checkpoint incomplete...")
        manifest["status"] = "INTERRUPTED"
        exit_code = 130
    except Exception as e:
        print(f"\n[!] LỖI KHÔNG MONG MUỐN TRONG VÒNG LẶP HUẤN LUYỆN: {e}")
        manifest["status"] = "FAILED"
        manifest["error"] = str(e)
        exit_code = 1

    manifest["completed_episodes"] = completed_ep

    last_ckpt_name = "coverage_model.pth" if manifest["status"] == "COMPLETED" else "incomplete_checkpoint.pth"
    torch.save({
        "policy_state_dict": policy_net.state_dict(),
        "target_state_dict": target_net.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "rng_state": {
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "torch": torch.get_rng_state()
        },
        "episode": completed_ep,
        "epsilon": epsilon,
        "global_env_steps": global_env_steps,
        "best_eval_coverage": best_eval_coverage,
        "best_success_rate": best_success_rate,
        "config": vars(args)
    }, run_dir / last_ckpt_name)

    # Ghi manifest sơ bộ để đảm bảo không mất thông tin trạng thái
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Chọn checkpoint tốt nhất để xuất ONNX nếu có
    export_model = policy_net
    best_ckpt_file = run_dir / "best_checkpoint.pth"
    if best_ckpt_file.exists():
        ckpt_data = torch.load(best_ckpt_file, map_location="cpu", weights_only=False)
        export_model = gr.CoverageQNet(channels=3, feature_dim=8)
        export_model.load_state_dict(ckpt_data["policy_state_dict"])

    # Metadata chuẩn contract
    onnx_meta = {
        "contract_version": "2.0.0",
        "mode": "known_map_point_grid_baseline",
        "input_channels": "0:known_free_uncovered,1:raw_obstacle,2:known_free_covered",
        "feature_scalars": "0:path_dx,1:path_dy,2:path_dist_norm,3:has_target,4:sin_yaw,5:cos_yaw,6:cov_frac,7:no_prog_frac",
        "actions": "0:Up(-1,0),1:Down(1,0),2:Left(0,-1),3:Right(0,1)",
        "run_id": run_id,
        "best_eval_coverage": f"{best_eval_coverage:.2f}%",
        "best_success_rate": f"{best_success_rate:.2f}%"
    }

    candidate_onnx = run_dir / "coverage_model.onnx"
    try:
        onnx_res = export_and_verify_onnx(export_model, candidate_onnx, run_dir, metadata=onnx_meta)
    except Exception as e:
        print(f"[!] Lỗi ngoại lệ khi xuất/kiểm chứng ONNX: {e}")
        onnx_res = {
            "onnx_path": str(candidate_onnx),
            "file_size_bytes": 0,
            "sha256": "",
            "max_abs_error": float('nan'),
            "argmax_disagreements": 100,
            "status": "FAIL",
            "reason": f"Export exception: {e}"
        }
        if manifest.get("status") != "INTERRUPTED":
            manifest["status"] = "FAILED"

    manifest["onnx_verification"] = onnx_res
    manifest["best_eval_coverage"] = best_eval_coverage
    manifest["best_success_rate"] = best_success_rate

    # Luôn ghi manifest cập nhật trước khi kết thúc
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\n" + "=" * 80)
    print(f"KẾT QUẢ HUẤN LUYỆN: TRẠNG THÁI [{manifest['status']}] (Hoàn tất: {completed_ep}/{args.episodes})")
    print(f"• Candidate ONNX: {candidate_onnx} ({onnx_res['file_size_bytes']} bytes)")
    print(f"• Parity Error:   {onnx_res['max_abs_error']} | Status: {onnx_res['status']}")
    print(f"• Best Eval Cov:  {best_eval_coverage:.2f}% | Success Rate: {best_success_rate:.2f}%")
    print(f"• Manifest:       {run_dir / 'manifest.json'}")

    # ==============================================================================
    # KHÓA PROMOTION GATE: CHỈ PROMOTE KHI ĐẠT TOÀN BỘ TIÊU CHUẨN SOFTWARE
    # Điều kiện nghiêm ngặt:
    # 1. KHÔNG PHẢI SMOKE TEST
    # 2. Hoàn tất đầy đủ (không bị INTERRUPTED hoặc FAILED)
    # 3. ONNX Parity status == PASS
    # 4. Tỷ lệ phủ Best Eval Coverage >= 95.0%
    # 5. Tỷ lệ hoàn thành Best Success Rate >= 95.0%
    # ==============================================================================
    quality_passed = (
        not getattr(args, "smoke", False)
        and manifest.get("status") == "COMPLETED"
        and onnx_res.get("status") == "PASS"
        and best_eval_coverage >= max(95.0, float(getattr(args, "min_coverage", 95.0)))
        and float(locals().get("best_success_rate", best_eval_coverage)) >= max(95.0, float(getattr(args, "min_success_rate", 95.0)))
    )

    if quality_passed:
        best_ckpt_src = run_dir / "best_checkpoint.pth"
        if best_ckpt_src.exists() and candidate_onnx.exists():
            dest_onnx = ROOT / "models" / "coverage_model.onnx"
            dest_pth = ROOT / "models" / "coverage_model.pth"
            atomic_promote(candidate_onnx, dest_onnx)
            atomic_promote(best_ckpt_src, dest_pth)
            print(f"✓ ĐÃ ATOMIC PROMOTE MODEL CHÍNH THỨC SANG: {dest_onnx}")
        else:
            print("[!] Lỗi: Thiếu file artifact để promote.")
            if exit_code == 0:
                exit_code = 1
    else:
        req_cov = max(95.0, float(getattr(args, "min_coverage", 95.0)))
        req_succ = max(95.0, float(getattr(args, "min_success_rate", 95.0)))
        succ_val = float(locals().get("best_success_rate", best_eval_coverage))
        reason = "Chế độ Smoke test" if getattr(args, "smoke", False) else \
                 "Bị ngắt quãng sớm" if manifest.get("status") == "INTERRUPTED" else \
                 "Huấn luyện thất bại" if manifest.get("status") == "FAILED" else \
                 "ONNX Export/Parity thất bại" if onnx_res.get("status") != "PASS" else \
                 f"Chưa đạt ngưỡng nghiệm thu chất lượng (Coverage {best_eval_coverage:.1f}% < {req_cov}%, Success {succ_val:.1f}% < {req_succ}%)"
        print(f"[!] KHÔNG PROMOTE SANG models/coverage_model.onnx: {reason}")
        if exit_code == 0:
            if onnx_res.get("status") != "PASS":
                exit_code = 1
            elif manifest.get("status") == "INTERRUPTED":
                exit_code = 130
            elif manifest.get("status") == "FAILED":
                exit_code = 1
            elif not getattr(args, "smoke", False) and (best_eval_coverage < req_cov or succ_val < req_succ):
                exit_code = 1

    print("=" * 80)
    return exit_code


# ==============================================================================
# 6. GIAO DIỆN DÒNG LỆNH (CLI)
# ==============================================================================
def parse_args():
    parser = argparse.ArgumentParser(description="Coverage DRL V2 Trainer (Double DQN + Action Masking)")
    parser.add_argument("episodes_pos", nargs="?", type=int, default=None, help="Số episodes (vị trí tương thích code cũ)")
    parser.add_argument("--episodes", type=int, default=20000, help="Tổng số episodes huấn luyện (default: 20000)")
    parser.add_argument("--smoke", action="store_true", help="Chạy thử smoke test nhanh 10 episodes")
    parser.add_argument("--eval-only", action="store_true", help="Chỉ đánh giá checkpoint trên 100 seed kiểm định")
    parser.add_argument("--checkpoint", type=str, default=None, help="Đường dẫn checkpoint để nạp/đánh giá")
    parser.add_argument("--resume", type=str, default=None, help="Đường dẫn checkpoint để khôi phục tiếp tục train")
    parser.add_argument("--out-dir", type=str, default=None, help="Thư mục xuất output run")
    parser.add_argument("--seed", type=int, default=42, help="Seed ngẫu nhiên")
    parser.add_argument("--train-freq", type=int, default=8, help="Tần suất cập nhật gradient (bước)")
    parser.add_argument("--target-sync-freq", type=int, default=500, help="Tần suất đồng bộ target network (bước)")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size (default: 64)")
    parser.add_argument("--buffer-size", type=int, default=40000, help="Kích thước bộ đệm Replay")
    parser.add_argument("--lr", type=float, default=5e-4, help="Tốc độ học Adam")
    parser.add_argument("--threads", type=int, default=2, help="Số luồng CPU cho PyTorch")
    parser.add_argument("--cpu-only", action="store_true", help="Bắt buộc chỉ dùng CPU")
    parser.add_argument("--min-coverage", type=float, default=95.0, help="Ngưỡng tỷ lệ phủ tối thiểu để được promote (default: 95.0%)")
    parser.add_argument("--min-success-rate", type=float, default=95.0, help="Ngưỡng success rate tối thiểu để được promote (default: 95.0%)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.episodes_pos is not None:
        args.episodes = args.episodes_pos
    if args.smoke:
        args.episodes = 10
        args.batch_size = 16
        args.train_freq = 2

    if args.eval_only:
        ckpt_path = Path(args.checkpoint) if args.checkpoint else ROOT / "models" / "coverage_model.pth"
        print(f"[*] Chế độ Eval-Only | Nạp checkpoint: {ckpt_path}")
        model = gr.CoverageQNet(channels=3, feature_dim=8)
        ckpt_data = torch.load(ckpt_path, map_location='cpu', weights_only=False)
        if isinstance(ckpt_data, dict) and "policy_state_dict" in ckpt_data:
            model.load_state_dict(ckpt_data["policy_state_dict"])
        else:
            model.load_state_dict(ckpt_data)
        res = evaluate_policy(model, GridCoverageEnvV2, eval_seeds=range(10000, 10100))
        print(json.dumps(res, indent=2))
        sys.exit(0)

    exit_code = run_trainer(args)
    sys.exit(exit_code)

```



CURRENT FILE: tests/test_coverage_v2.py
```python
"""
Bộ kiểm thử đơn vị & tích hợp cho Coverage DRL V2 (Gate G1 & G2)
Kiểm tra trực tiếp code sản phẩm, exporter NaN, promotion gate sandbox, và CLI validation mà không gọi training nặng.
"""

import unittest
from pathlib import Path
import sys
import tempfile
import os
import argparse
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import torch

from train_coverage_20000 import (
    GridCoverageEnvV2,
    atomic_promote,
    export_and_verify_onnx,
    parse_args,
    run_trainer
)
import docs.coverage_review_20261012.golden_reference as gr


class TestProductionCoverageV2(unittest.TestCase):

    def test_production_env_horizon_math(self):
        """Kiểm tra ngân sách bước của production GridCoverageEnvV2 luôn >= 4 * N_reachable."""
        env = GridCoverageEnvV2(seed=12345)
        env.reset(seed=12345)
        self.assertGreater(env.total_reachable, 500)
        self.assertEqual(env.max_steps, 4 * env.total_reachable)

    def test_production_env_collision_non_terminal(self):
        """Kiểm tra va chạm trên GridCoverageEnvV2 không làm ngắt màn (terminated=False) và giữ vị trí."""
        env = GridCoverageEnvV2(seed=42)
        env.reset(seed=42)
        env.ry, env.rx = 1, 1
        env.grid[0, 1] = env.OBSTACLE

        init_steps = env.steps
        obs, reward, terminated, truncated, info = env.step(0)

        self.assertTrue(info["blocked"])
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertEqual((env.ry, env.rx), (1, 1))
        self.assertEqual(env.steps, init_steps + 1)
        self.assertLess(reward, 0.0)

    def test_production_env_obs_contract(self):
        """Kiểm tra hợp đồng quan sát: local_map shape (3, 9, 9) và features shape (8,)."""
        env = GridCoverageEnvV2(seed=999)
        local_map, features = env.reset(seed=999)

        self.assertEqual(local_map.shape, (3, 9, 9))
        self.assertEqual(features.shape, (8,))
        self.assertEqual(local_map.dtype, np.float32)
        self.assertEqual(features.dtype, np.float32)

    def test_production_env_geodesic_corridor(self):
        """Kiểm tra BFS Geodesic trên GridCoverageEnvV2 đi vòng qua tường chữ U."""
        env = GridCoverageEnvV2(seed=100)
        env.reset(seed=100)
        env.grid[1:31, 1:31] = env.COVERED
        env.grid[5:15, 10] = env.OBSTACLE
        env.ry, env.rx = 10, 8
        env.grid[10, 12] = env.UNCOVERED

        p_dx, p_dy, dist_norm, has_tgt = env.find_geodesic_target()
        self.assertTrue(has_tgt)
        self.assertNotEqual((p_dx, p_dy), (1.0, 0.0))

    def test_golden_reference_network_architecture(self):
        """Kiểm tra CoverageQNet khớp chính xác 32,644 tham số."""
        net = gr.CoverageQNet(channels=3, feature_dim=8)
        self.assertEqual(sum(p.numel() for p in net.parameters()), 32644)

    def test_double_dqn_target_and_bootstrap(self):
        """Kiểm tra Double DQN target cắt bootstrap ở terminated, giữ bootstrap ở truncated."""
        reward = torch.tensor([5.0, 5.0])
        discount = 0.99
        next_online_q = torch.tensor([[10.0, 2.0, 1.0, 0.0], [10.0, 2.0, 1.0, 0.0]])
        next_target_q = torch.tensor([[100.0, 20.0, 10.0, 0.0], [100.0, 20.0, 10.0, 0.0]])
        next_valid_mask = torch.tensor([[True, True, True, True], [True, True, True, True]])

        terminated = torch.tensor([False, True])
        targets = gr.double_dqn_target(reward, terminated, discount, next_online_q, next_target_q, next_valid_mask)
        self.assertAlmostEqual(targets[0].item(), 5.0 + 0.99 * 100.0, places=4)
        self.assertAlmostEqual(targets[1].item(), 5.0, places=4)

    def test_atomic_promote_safe(self):
        """Kiểm tra ghi đè nguyên tử an toàn qua atomic_promote."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "candidate.onnx"
            dst = Path(tmpdir) / "final.onnx"
            src.write_bytes(b"MODEL_VERSION_2")

            atomic_promote(src, dst)
            self.assertTrue(dst.exists())
            self.assertEqual(dst.read_bytes(), b"MODEL_VERSION_2")

    def test_nan_model_export_fails(self):
        """Regression test P1: Model chứa NaN hoặc Inf trong trọng số bắt buộc exporter phải trả status FAIL."""
        net = gr.CoverageQNet(channels=3, feature_dim=8).eval()
        with torch.no_grad():
            next(net.parameters()).fill_(float('nan'))

        with tempfile.TemporaryDirectory() as tmpdir:
            onnx_path = Path(tmpdir) / "nan_test.onnx"
            res = export_and_verify_onnx(net, onnx_path, Path(tmpdir))
            self.assertEqual(res["status"], "FAIL", "Model chứa NaN weights bắt buộc status phải là FAIL.")

        net_inf = gr.CoverageQNet(channels=3, feature_dim=8).eval()
        with torch.no_grad():
            next(net_inf.parameters()).fill_(float('inf'))

        with tempfile.TemporaryDirectory() as tmpdir:
            onnx_path = Path(tmpdir) / "inf_test.onnx"
            res = export_and_verify_onnx(net_inf, onnx_path, Path(tmpdir))
            self.assertEqual(res["status"], "FAIL", "Model chứa Inf weights bắt buộc status phải là FAIL.")

    def test_promotion_gate_control_flow(self):
        """Regression test P2: Sandbox test kiểm tra control-flow bảo vệ destination model không bị ghi đè trái phép."""
        import ast
        import contextlib
        import io

        tree = ast.parse((ROOT / "train_coverage_20000.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_trainer")
        start = next(i for i, n in enumerate(fn.body) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "quality_passed" for t in n.targets))
        block = ast.Module(body=fn.body[start:-1], type_ignores=[])

        def run_promotion_block(sandbox_root, smoke, manifest_status, onnx_status, cov, succ=95.0, candidate_exists=True):
            run_dir = sandbox_root / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            cand_onnx = run_dir / "candidate.onnx"
            cand_pth = run_dir / "best_checkpoint.pth"
            if candidate_exists:
                cand_onnx.write_bytes(b"NEW_CANDIDATE_ONNX")
                cand_pth.write_bytes(b"NEW_CANDIDATE_PTH")

            ns = dict(
                args=SimpleNamespace(smoke=smoke, min_coverage=95.0, min_success_rate=95.0),
                manifest={"status": manifest_status},
                onnx_res={"status": onnx_status},
                best_eval_coverage=cov,
                best_success_rate=succ,
                exit_code=0,
                ROOT=sandbox_root,
                run_dir=run_dir,
                candidate_onnx=cand_onnx,
                atomic_promote=atomic_promote
            )
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(block, "<test-promotion-block>", "exec"), ns)
            return ns["exit_code"], ns["quality_passed"]

        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir)
            dest_models = sandbox / "models"
            dest_models.mkdir(parents=True, exist_ok=True)
            sentinel_onnx = dest_models / "coverage_model.onnx"
            sentinel_pth = dest_models / "coverage_model.pth"
            sentinel_onnx.write_bytes(b"ORIGINAL_SENTINEL_ONNX")
            sentinel_pth.write_bytes(b"ORIGINAL_SENTINEL_PTH")

            # 1. Smoke test: Không promote, giữ nguyên sentinel
            code, passed = run_promotion_block(sandbox, smoke=True, manifest_status="COMPLETED", onnx_status="PASS", cov=99.0)
            self.assertFalse(passed)
            self.assertEqual(sentinel_onnx.read_bytes(), b"ORIGINAL_SENTINEL_ONNX")

            # 2. Interrupted: Không promote, trả exit code 130
            code, passed = run_promotion_block(sandbox, smoke=False, manifest_status="INTERRUPTED", onnx_status="PASS", cov=99.0)
            self.assertFalse(passed)
            self.assertEqual(code, 130)
            self.assertEqual(sentinel_onnx.read_bytes(), b"ORIGINAL_SENTINEL_ONNX")

            # 3. ONNX Fail: Không promote, trả nonzero
            code, passed = run_promotion_block(sandbox, smoke=False, manifest_status="COMPLETED", onnx_status="FAIL", cov=99.0)
            self.assertFalse(passed)
            self.assertEqual(code, 1)
            self.assertEqual(sentinel_onnx.read_bytes(), b"ORIGINAL_SENTINEL_ONNX")

            # 4. Coverage < 95%: Không promote, trả nonzero
            code, passed = run_promotion_block(sandbox, smoke=False, manifest_status="COMPLETED", onnx_status="PASS", cov=92.0)
            self.assertFalse(passed)
            self.assertEqual(code, 1)
            self.assertEqual(sentinel_onnx.read_bytes(), b"ORIGINAL_SENTINEL_ONNX")

            # 5. Full Success: Promote an toàn ghi đè sentinel
            code, passed = run_promotion_block(sandbox, smoke=False, manifest_status="COMPLETED", onnx_status="PASS", cov=96.0, succ=97.0)
            self.assertTrue(passed)
            self.assertEqual(code, 0)
            self.assertEqual(sentinel_onnx.read_bytes(), b"NEW_CANDIDATE_ONNX")
            self.assertEqual(sentinel_pth.read_bytes(), b"NEW_CANDIDATE_PTH")

    def test_cli_argument_validation(self):
        """Regression test: Kiểm tra CLI từ chối số âm hoặc không hợp lệ với exit code 2."""
        invalid_args = [
            argparse.Namespace(episodes=-1, train_freq=8, target_sync_freq=500, batch_size=64, buffer_size=1000, threads=1, lr=1e-3, min_coverage=95.0, min_success_rate=95.0, seed=42, cpu_only=True, resume=None, smoke=False, out_dir=None),
            argparse.Namespace(episodes=10, train_freq=0, target_sync_freq=500, batch_size=64, buffer_size=1000, threads=1, lr=1e-3, min_coverage=95.0, min_success_rate=95.0, seed=42, cpu_only=True, resume=None, smoke=False, out_dir=None),
            argparse.Namespace(episodes=10, train_freq=8, target_sync_freq=500, batch_size=64, buffer_size=1000, threads=1, lr=float('nan'), min_coverage=95.0, min_success_rate=95.0, seed=42, cpu_only=True, resume=None, smoke=False, out_dir=None),
            argparse.Namespace(episodes=10, train_freq=8, target_sync_freq=500, batch_size=64, buffer_size=1000, threads=1, lr=1e-3, min_coverage=150.0, min_success_rate=95.0, seed=42, cpu_only=True, resume=None, smoke=False, out_dir=None)
        ]
        for a in invalid_args:
            ret = run_trainer(a)
            self.assertEqual(ret, 2, f"Tham số không hợp lệ phải trả exit code 2: {a}")


if __name__ == '__main__':
    unittest.main()

```



CURRENT FILE: run_train_20000.bat
```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Huấn Luyện AI Coverage V2 - AGV Autonomous Navigation
color 0b

echo ==============================================================================
echo        CHƯƠNG TRÌNH HUẤN LUYỆN DRL COVERAGE V2 (CHUẨN HỢP ĐỒNG 2026)
echo ==============================================================================
echo.
echo [*] Bắt đầu huấn luyện mô hình Double DQN trên môi trường ma trận giả lập...
echo [*] Bạn có thể bấm Ctrl+C bất cứ lúc nào để dừng và lưu checkpoint an toàn.
echo.

python "train_coverage_20000.py" %*
set TRAIN_EXIT_CODE=%errorlevel%

echo.
if %TRAIN_EXIT_CODE% equ 0 (
    echo ==============================================================================
    echo        HUẤN LUYỆN HOÀN TẤT VÀ ĐÃ XUẤT FILE MODEL THÀNH CÔNG!
    echo ==============================================================================
) else (
    echo [!] Tiến trình kết thúc với mã lỗi: %TRAIN_EXIT_CODE%
)

pause
exit /b %TRAIN_EXIT_CODE%

```
