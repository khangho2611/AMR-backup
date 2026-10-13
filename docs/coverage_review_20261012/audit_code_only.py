"""No training, optimizer steps, baseline runs, or policy-quality evaluation.

Checks exporter with synthetic NaN weights and executes the actual promotion
AST block in a temporary namespace. Source and production models are read only.
"""
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import train_coverage_20000 as module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def promotion_case(smoke, status, coverage):
    tree = ast.parse((ROOT/'train_coverage_20000.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='run_trainer')
    start = next(i for i,n in enumerate(fn.body) if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id=='quality_passed' for t in n.targets))
    # Run only promotion/status code, excluding function's return statement.
    block = ast.Module(body=fn.body[start:-1],type_ignores=[])
    calls = []
    with tempfile.TemporaryDirectory(prefix='coverage-code-review-') as tmp:
        ns = dict(args=SimpleNamespace(smoke=smoke,min_coverage=90.),
            manifest={'status':'COMPLETED'},onnx_res={'status':status},
            best_eval_coverage=coverage,exit_code=0,ROOT=Path(tmp),run_dir=Path(tmp)/'run',
            candidate_onnx=Path(tmp)/'candidate.onnx',
            atomic_promote=lambda src,dst: calls.append([str(src),str(dst)]))
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(block,'<actual-promotion-block>','exec'),ns)
        return dict(exit_code=ns['exit_code'],quality_passed=ns['quality_passed'],
                    promotion_calls=len(calls))


def main():
    watched = [ROOT/'train_coverage_20000.py',ROOT/'tests/test_coverage_v2.py',
               ROOT/'models/coverage_model.onnx',ROOT/'models/coverage_model.pth']
    hashes = {str(p.relative_to(ROOT)):digest(p) for p in watched}
    torch.set_num_threads(1)
    net = module.gr.CoverageQNet().eval()
    with torch.no_grad():
        next(net.parameters()).fill_(float('nan'))
        output = net(torch.zeros(1,3,9,9),torch.zeros(1,8))
    assert not torch.isfinite(output).any()
    with tempfile.TemporaryDirectory(prefix='coverage-nan-export-') as tmp:
        with contextlib.redirect_stdout(io.StringIO()):
            result = module.export_and_verify_onnx(net,Path(tmp)/'nan.onnx',Path(tmp))
    assert hashes == {str(p.relative_to(ROOT)):digest(p) for p in watched}
    report = dict(scope='Code only; no training or quality evaluation',sha256=hashes,
        nan_export=dict(status=result['status'],max_abs_error=result['max_abs_error'],
                        model_output_all_nan=bool(torch.isnan(output).all()),
                        file_size=result['file_size_bytes']),
        actual_promotion_block={
            'smoke_export_fail':promotion_case(True,'FAIL',0.),
            'completed_export_fail_high_coverage':promotion_case(False,'FAIL',99.),
            'completed_export_pass_coverage92':promotion_case(False,'PASS',92.)})
    Path(__file__).with_name('audit_code_only.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
