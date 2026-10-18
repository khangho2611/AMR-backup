"""Protect the one-shot release gate from training/acceptance data leakage."""

import json
from pathlib import Path

import pytest

from ai_local_planner.scripts import run_fast_gate, solve_and_release_final as solver


def test_release_windows_are_distinct():
    windows = solver.seed_windows(24000000, 25000000, 27000000)
    observed = {seed for section in ('training', 'development')
                for values in windows[section].values() for seed in values}
    certified = {seed for values in windows['final'].values() for seed in values}
    assert len(certified) == 500
    assert not certified.intersection(observed)


def test_fail_closed_on_development_acceptance_overlap():
    with pytest.raises(ValueError, match='overlap'):
        solver.seed_windows(24000000, 25000000, 25000000)


def test_fast_gate_rejects_development_seed_provenance(tmp_path: Path):
    file = tmp_path / 'provenance.json'
    file.write_text(json.dumps({
        'config': {'train_seed': 24000000, 'pilot_seed': 25000000,
                   'episodes': 40, 'replay_episodes': 10,
                   'level2_replay_episodes': 40, 'pilot_episodes': 20},
        'seed_sets': {'development': {'4': [27001000]}}
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='overlap'):
        run_fast_gate.verify_heldout_seeds(file, 27000000, 100)
