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
