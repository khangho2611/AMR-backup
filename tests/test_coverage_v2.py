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
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import torch

from train_coverage_20000 import (
    GridCoverageEnvV2,
    atomic_promote,
    build_onnx_metadata,
    commit_artifact_pair,
    export_and_verify_onnx,
    finalize_candidate_artifacts,
    fresh_accept_candidate,
    parse_args,
    run_trainer,
    select_candidate_checkpoint,
    sha256_file,
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

    def test_production_env_rejects_steps_after_terminal_until_reset(self):
        env = GridCoverageEnvV2(size=8, seed=7)
        env.grid.fill(env.OBSTACLE)
        env.ry, env.rx = 1, 1
        env.grid[1, 1] = env.COVERED
        env.grid[1, 2] = env.UNCOVERED
        env.reachable_cells = {(1, 1), (1, 2)}
        env.total_reachable = 2
        env.covered_count = 1
        env.steps = 0
        env.max_steps = 8
        env.steps_without_new_cell = 0
        env.last_action_idx = 3
        env._episode_done = False
        env._get_obs()

        _, reward, terminated, truncated, _ = env.step(3)
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertGreater(reward, 0.0)
        with self.assertRaises(RuntimeError):
            env.step(3)

        env.reset(seed=7)
        self.assertFalse(env._episode_done)
        env.step(0)

    def test_production_env_rejects_steps_after_truncation(self):
        env = GridCoverageEnvV2(seed=8)
        env.ry, env.rx = 1, 1
        env.grid[0, 1] = env.OBSTACLE
        env.steps = env.max_steps - 1
        env._episode_done = False

        _, _, terminated, truncated, _ = env.step(0)
        self.assertFalse(terminated)
        self.assertTrue(truncated)
        with self.assertRaises(RuntimeError):
            env.step(0)

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

    def test_finite_weights_with_nonfinite_forward_output_fail_export(self):
        net = gr.CoverageQNet(channels=3, feature_dim=8).eval()
        self.assertTrue(all(torch.isfinite(p).all() for p in net.parameters()))

        def nonfinite_forward(local_map, features):
            return torch.full((local_map.shape[0], 4), float("nan"))

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(net, "forward", side_effect=nonfinite_forward):
                result = export_and_verify_onnx(net, Path(tmpdir) / "nan_forward.onnx", Path(tmpdir))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("Output model", result["reason"])

    def test_nonfinite_onnxruntime_output_fails_export(self):
        import onnxruntime as ort

        net = gr.CoverageQNet(channels=3, feature_dim=8).eval()
        with tempfile.TemporaryDirectory() as tmpdir:
            onnx_path = Path(tmpdir) / "nan_ort.onnx"
            with mock.patch.object(
                ort.InferenceSession,
                "run",
                return_value=[np.full((1, 4), np.inf, dtype=np.float32)],
            ):
                result = export_and_verify_onnx(net, onnx_path, Path(tmpdir))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("NaN/Inf", result["reason"])

    def test_valid_model_passes_representative_export_contract(self):
        net = gr.CoverageQNet(channels=3, feature_dim=8).eval()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_and_verify_onnx(net, Path(tmpdir) / "valid.onnx", Path(tmpdir))
        self.assertEqual(result["status"], "PASS")

    def test_missing_best_selects_last_as_unverified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            last_checkpoint = run_dir / "coverage_model.pth"
            last_checkpoint.write_bytes(b"LAST_WEIGHTS")
            selected = select_candidate_checkpoint(run_dir, last_checkpoint)
            self.assertEqual(selected["source"], "last_unverified")
            self.assertTrue(selected["unverified"])
            self.assertEqual(selected["sha256"], sha256_file(last_checkpoint))
            self.assertFalse((run_dir / "best_checkpoint.pth").exists())
            metadata = build_onnx_metadata("test-run", selected)
            self.assertEqual(metadata["selected_checkpoint_sha256"], selected["sha256"])
            self.assertNotIn("best_eval_coverage", metadata)
            self.assertNotIn("best_success_rate", metadata)

    def test_fresh_acceptance_binds_hash_model_and_fixed_seeds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint = Path(tmpdir) / "candidate.pth"
            checkpoint.write_bytes(b"SELECTED_WEIGHTS")
            evaluator = mock.Mock(return_value={"mean_coverage": 96.0, "success_rate_pct": 97.0})
            model = object()
            result = fresh_accept_candidate(
                model, checkpoint, sha256_file(checkpoint), evaluator,
                GridCoverageEnvV2, "cpu",
            )
            self.assertTrue(result["passed"])
            evaluator.assert_called_once_with(
                model, GridCoverageEnvV2,
                eval_seeds=tuple(range(10000, 10100)), device="cpu",
            )

            evaluator.reset_mock()
            wrong_hash = fresh_accept_candidate(
                model, checkpoint, "wrong", evaluator, GridCoverageEnvV2, "cpu"
            )
            wrong_seeds = fresh_accept_candidate(
                model, checkpoint, sha256_file(checkpoint), evaluator,
                GridCoverageEnvV2, "cpu", seeds=tuple(range(50)),
            )
            self.assertFalse(wrong_hash["passed"])
            self.assertFalse(wrong_seeds["passed"])
            evaluator.assert_not_called()

    def test_pair_commit_second_replace_failure_restores_old_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_onnx = root / "candidate.onnx"
            candidate_pth = root / "candidate.pth"
            dest_onnx = root / "coverage_model.onnx"
            dest_pth = root / "coverage_model.pth"
            candidate_onnx.write_bytes(b"NEW_ONNX")
            candidate_pth.write_bytes(b"NEW_PTH")
            dest_onnx.write_bytes(b"OLD_ONNX")
            dest_pth.write_bytes(b"OLD_PTH")
            real_replace = os.replace
            calls = 0

            def fail_second_replace(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected second replace failure")
                return real_replace(source, destination)

            result = commit_artifact_pair(
                candidate_onnx, candidate_pth, dest_onnx, dest_pth,
                replace_fn=fail_second_replace,
            )
            self.assertFalse(result["promoted"])
            self.assertEqual(dest_onnx.read_bytes(), b"OLD_ONNX")
            self.assertEqual(dest_pth.read_bytes(), b"OLD_PTH")

    def test_pair_commit_restores_absence_and_reports_rollback_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_onnx = root / "candidate.onnx"
            candidate_pth = root / "candidate.pth"
            dest_onnx = root / "coverage_model.onnx"
            dest_pth = root / "coverage_model.pth"
            candidate_onnx.write_bytes(b"NEW_ONNX")
            candidate_pth.write_bytes(b"NEW_PTH")
            real_replace = os.replace
            calls = 0

            def fail_second_replace(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected second replace failure")
                return real_replace(source, destination)

            result = commit_artifact_pair(
                candidate_onnx, candidate_pth, dest_onnx, dest_pth,
                replace_fn=fail_second_replace,
            )
            self.assertFalse(result["promoted"])
            self.assertFalse(dest_onnx.exists())
            self.assertFalse(dest_pth.exists())

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_onnx = root / "candidate.onnx"
            candidate_pth = root / "candidate.pth"
            dest_onnx = root / "coverage_model.onnx"
            dest_pth = root / "coverage_model.pth"
            candidate_onnx.write_bytes(b"NEW_ONNX")
            candidate_pth.write_bytes(b"NEW_PTH")
            dest_onnx.write_bytes(b"OLD_ONNX")
            dest_pth.write_bytes(b"OLD_PTH")
            real_replace = os.replace
            calls = 0

            def fail_commit_and_rollback(source, destination):
                nonlocal calls
                calls += 1
                if calls in (2, 3):
                    raise OSError(f"injected failure {calls}")
                return real_replace(source, destination)

            result = commit_artifact_pair(
                candidate_onnx, candidate_pth, dest_onnx, dest_pth,
                replace_fn=fail_commit_and_rollback,
            )
            self.assertTrue(result["rollback_errors"])
            self.assertTrue(list(root.glob(".coverage_model.onnx.*.backup")))

    def test_pair_commit_success_returns_matching_hashes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_onnx = root / "candidate.onnx"
            candidate_pth = root / "candidate.pth"
            dest_onnx = root / "coverage_model.onnx"
            dest_pth = root / "coverage_model.pth"
            candidate_onnx.write_bytes(b"NEW_ONNX")
            candidate_pth.write_bytes(b"NEW_PTH")
            result = commit_artifact_pair(candidate_onnx, candidate_pth, dest_onnx, dest_pth)
            self.assertTrue(result["promoted"])
            self.assertEqual(result["onnx_sha256"], sha256_file(dest_onnx))
            self.assertEqual(result["pth_sha256"], sha256_file(dest_pth))

    def test_finalizer_uses_fresh_selected_acceptance_not_historical_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "run"
            models_dir = root / "models"
            run_dir.mkdir()
            models_dir.mkdir()
            checkpoint = run_dir / "best_checkpoint.pth"
            checkpoint.write_bytes(b"SELECTED_WEIGHTS")
            candidate = {
                "path": checkpoint,
                "source": "best_checkpoint",
                "unverified": False,
                "sha256": sha256_file(checkpoint),
            }
            manifest = {
                "status": "COMPLETED",
                "best_eval_coverage": 99.0,
                "best_success_rate": 99.0,
            }
            args = SimpleNamespace(smoke=False, min_coverage=95.0, min_success_rate=95.0)

            def exporter(model, path, out_dir, metadata=None):
                path.write_bytes(b"CANDIDATE_ONNX")
                return {"status": "PASS", "sha256": sha256_file(path)}

            evaluator = mock.Mock(return_value={"mean_coverage": 90.0, "success_rate_pct": 80.0})
            commit = mock.Mock()
            code, _ = finalize_candidate_artifacts(
                manifest, args, run_dir, candidate, object(), "cpu", models_dir, {},
                exporter_fn=exporter, evaluator_fn=evaluator, commit_fn=commit,
            )
            self.assertEqual(code, 1)
            self.assertFalse(manifest["promoted"])
            commit.assert_not_called()
            self.assertFalse((models_dir / "coverage_model.onnx").exists())

    def test_finalizer_success_records_provenance_after_commit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "run"
            models_dir = root / "models"
            run_dir.mkdir()
            models_dir.mkdir()
            checkpoint = run_dir / "coverage_model.pth"
            checkpoint.write_bytes(b"SELECTED_WEIGHTS")
            candidate = {
                "path": checkpoint,
                "source": "last_unverified",
                "unverified": True,
                "sha256": sha256_file(checkpoint),
            }
            manifest = {"status": "COMPLETED"}
            args = SimpleNamespace(smoke=False, min_coverage=95.0, min_success_rate=95.0)

            def exporter(model, path, out_dir, metadata=None):
                path.write_bytes(b"CANDIDATE_ONNX")
                return {"status": "PASS", "sha256": sha256_file(path)}

            evaluator = mock.Mock(return_value={"mean_coverage": 96.0, "success_rate_pct": 97.0})
            code, _ = finalize_candidate_artifacts(
                manifest, args, run_dir, candidate, object(), "cpu", models_dir, {},
                exporter_fn=exporter, evaluator_fn=evaluator,
            )
            self.assertEqual(code, 0)
            self.assertTrue(manifest["promoted"])
            self.assertEqual(manifest["acceptance"]["checkpoint_sha256"], candidate["sha256"])
            self.assertEqual(
                manifest["artifact_hashes"]["pth"],
                sha256_file(models_dir / "coverage_model.pth"),
            )

    def test_finalizer_interrupted_returns_130_without_acceptance_or_commit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "run"
            run_dir.mkdir()
            checkpoint = run_dir / "incomplete_checkpoint.pth"
            checkpoint.write_bytes(b"EPISODE_37")
            candidate = {
                "path": checkpoint,
                "source": "last_unverified",
                "unverified": True,
                "sha256": sha256_file(checkpoint),
            }
            manifest = {"status": "INTERRUPTED", "completed_episodes": 37}
            args = SimpleNamespace(smoke=False, min_coverage=95.0, min_success_rate=95.0)
            exporter = mock.Mock(return_value={"status": "PASS"})
            evaluator = mock.Mock()
            commit = mock.Mock()
            code, _ = finalize_candidate_artifacts(
                manifest, args, run_dir, candidate, object(), "cpu", root / "models", {},
                exporter_fn=exporter, evaluator_fn=evaluator, commit_fn=commit,
            )
            self.assertEqual(code, 130)
            self.assertEqual(manifest["completed_episodes"], 37)
            evaluator.assert_not_called()
            commit.assert_not_called()

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
