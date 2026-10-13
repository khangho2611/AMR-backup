"""Independent V2 audit. Production sources/models are read only.

Lifecycle tests patch only expensive baseline/export and redirect ROOT to a
temporary sandbox; these are control-flow reproductions, not export tests.
Real ONNX rollouts use actual saved model and actual production environment.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import contextlib
import io
import time

import numpy as np
import onnx
import onnxruntime as ort
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import train_coverage_20000 as t


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lifecycle_case(episodes, interrupt=False, export_status='PASS'):
    with tempfile.TemporaryDirectory(prefix='coverage-review-') as tmp:
        sandbox = Path(tmp)
        (sandbox / 'models').mkdir()
        destination = sandbox / 'models/coverage_model.onnx'
        destination.write_bytes(b'ACCEPTED_SENTINEL')
        args = SimpleNamespace(threads=1, cpu_only=True, out_dir=str(sandbox / 'run'),
            episodes=episodes, train_freq=8, seed=42, lr=.0005,
            buffer_size=100, batch_size=64, target_sync_freq=500, smoke=False)
        def fake_export(model, path, out_dir):
            Path(path).write_bytes(b'UNQUALIFIED_CANDIDATE')
            return dict(status=export_status, file_size_bytes=20, max_abs_error=0.)
        baseline = dict(mean_coverage=100., mean_steps=900.)
        with contextlib.redirect_stdout(io.StringIO()), \
                patch.object(t, 'ROOT', sandbox), \
                patch.object(t, 'evaluate_bfs_baseline', return_value=baseline), \
                patch.object(t, 'export_and_verify_onnx', side_effect=fake_export):
            if interrupt:
                with patch.object(t.GridCoverageEnvV2, 'step', side_effect=KeyboardInterrupt):
                    exit_code = t.run_trainer(args)
            else:
                exit_code = t.run_trainer(args)
        manifest = json.loads((sandbox / 'run/manifest.json').read_text())
        return dict(exit_code=exit_code, accepted_model_overwritten=
                    destination.read_bytes() != b'ACCEPTED_SENTINEL',
                    manifest_episodes=manifest['episodes'],
                    eval_history=manifest['eval_history'])


def main():
    watched = [ROOT/'train_coverage_20000.py', ROOT/'run_train_20000.bat',
               ROOT/'tests/test_coverage_v2.py', ROOT/'models/coverage_model.onnx',
               ROOT/'models/coverage_model.pth']
    before = {str(p.relative_to(ROOT)): sha(p) for p in watched}
    lifecycle = {
        'zero_episodes_pass_export': lifecycle_case(0),
        'interrupt_before_first_transition': lifecycle_case(20000, interrupt=True),
        'failed_export_gate': lifecycle_case(0, export_status='FAIL'),
    }
    torch.set_num_threads(1)
    model_path = ROOT/'models/coverage_model.onnx'
    graph = onnx.load(str(model_path), load_external_data=False)
    onnx.checker.check_model(graph)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(model_path.read_bytes(), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    net = t.gr.CoverageQNet().eval()
    net.load_state_dict(torch.load(ROOT/'models/coverage_model.pth', weights_only=True, map_location='cpu'))
    # Actual production environment: blocked action still must consume time.
    env = t.GridCoverageEnvV2(seed=42)
    env.grid[:] = 100
    env.grid[1, 1:4] = 1
    env.grid[1, 1] = 0
    env.ry, env.rx = 1, 1
    env.reachable_cells = env._compute_reachable()
    env.total_reachable = 3
    env.covered_count = 1
    env.steps = 0
    env.max_steps = 1
    _, reward, term, trunc, info = env.step(0)
    assert info['blocked'] and not term and trunc and env.covered_count == 1
    lifecycle['real_env_blocked_at_budget'] = dict(terminated=term,truncated=trunc,reward=reward)
    rows = []
    errors = []
    started = time.perf_counter()
    # Include 10 validation seeds from the smoke manifest and 20 additional seeds.
    for seed in list(range(10000, 10010)) + list(range(20000, 20020)):
        env = t.GridCoverageEnvV2(seed=seed)
        obs_map, obs_feat = env.reset(seed=seed)
        blocked = 0
        actions = []
        while env.steps < env.max_steps:
            mask = env.get_valid_mask()
            if not mask.any():
                break
            data = {'local_map':obs_map[None], 'features':obs_feat[None]}
            q = session.run(None, data)[0][0]
            if env.steps % 100 == 0:
                with torch.inference_mode():
                    pt = net(torch.from_numpy(data['local_map']),torch.from_numpy(data['features'])).numpy()[0]
                errors.append(float(np.max(np.abs(q-pt))))
            action = int(np.where(mask,q,-np.inf).argmax())
            actions.append(action)
            (obs_map,obs_feat), _, term, trunc, info = env.step(action)
            blocked += int(info['blocked'])
            if term or trunc:
                break
        rows.append(dict(seed=seed,coverage_pct=100*env.covered_count/env.total_reachable,
            steps=env.steps, budget=env.max_steps, blocked=blocked,
            no_progress_steps=env.steps_without_new_cell,
            last_12_actions=actions[-12:]))
    baseline = t.evaluate_bfs_baseline(t.GridCoverageEnvV2, eval_seeds=range(20000,20020))
    def summary(selected):
        return dict(mean_coverage=float(np.mean([r['coverage_pct'] for r in selected])),
                    success_ge95=sum(r['coverage_pct'] >= 95 for r in selected),
                    count=len(selected),timeouts=sum(r['steps']==r['budget'] for r in selected),
                    max_no_progress=max(r['no_progress_steps'] for r in selected))
    after = {str(p.relative_to(ROOT)): sha(p) for p in watched}
    assert before == after, 'Files changed during audit; review must be repeated on new snapshot'
    result = dict(sha256=before, lifecycle_reproductions=lifecycle,
        onnx_bytes=model_path.stat().st_size, onnx_metadata={p.key:p.value for p in graph.metadata_props},
        external_initializers=[v.name for v in graph.graph.initializer if v.data_location==onnx.TensorProto.EXTERNAL],
        root_equals_smoke_model=sha(model_path)==sha(ROOT/'models/runs/smoke_test_run/coverage_model.onnx'),
        onnx_rollout_original_10=summary(rows[:10]),onnx_rollout_additional_20=summary(rows[10:]),
        additional_seeds_bfs_baseline=baseline, sampled_pt_onnx_max_abs_error=max(errors),
        elapsed_seconds=time.perf_counter()-started, episodes=rows)
    Path(__file__).with_name('audit_gemini_v2.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='episodes'},indent=2))


if __name__=='__main__':
    main()
