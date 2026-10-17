"""Catch false policy-promotion decisions from incomplete evaluation evidence."""

import pytest

from ai_local_planner.scripts.acceptance_gate import assess


def reports():
    return {level: {
        "checkpoint": "candidate.pth", "level": level, "episodes": 100,
        "domain_randomization": True, "success_rate": 1.,
        "collision_rate": 0., "timeout_rate": 0.,
    } for level in (1, 2, 3)}


def test_gate_requires_all_levels_to_pass():
    result = assess(reports())
    assert result["simulation_gate_passed"]
    data = reports()
    data[1].update(success_rate=.86, timeout_rate=.14)
    assert not assess(data)["simulation_gate_passed"]
    data = reports()
    data[3].update(success_rate=.90, collision_rate=.10)
    assert not assess(data)["simulation_gate_passed"]


def test_gate_rejects_clean_runs_and_mismatched_checkpoint():
    data = reports()
    data[2]["domain_randomization"] = False
    assert not assess(data)["simulation_gate_passed"]
    data = reports()
    data[3]["checkpoint"] = "other.pth"
    with pytest.raises(ValueError, match="same checkpoint"):
        assess(data)


def test_full_six_level_gate_cannot_skip_untrained_scenarios():
    data = reports()
    assert assess(data)['simulation_gate_passed']
    assert not assess(data)['full_six_level_gate']
    data.update({i: {
        "checkpoint": "candidate.pth", "level": i, "episodes": 100,
        "domain_randomization": True, "success_rate": 1.,
        "collision_rate": 0., "timeout_rate": 0.,
    } for i in (4, 5, 6)})
    assert assess(data)['full_six_level_gate']
    assert assess(data)['simulation_gate_passed']
    data[6].update(success_rate=.97, collision_rate=.03)
    assert not assess(data)['simulation_gate_passed']
    data.pop(5)
    with pytest.raises(ValueError, match='all Levels'):
        assess(data)


def test_five_level_approval_checks_every_level():
    data = reports()
    data.update({i: {
        "checkpoint": "candidate.pth", "level": i, "episodes": 100,
        "domain_randomization": True, "success_rate": .90,
        "collision_rate": .02, "timeout_rate": .08,
    } for i in (4, 5)})
    assert assess(data)["simulation_gate_passed"]
    assert not assess(data)["full_six_level_gate"]
    data[5].update(success_rate=.89, collision_rate=.02, timeout_rate=.09)
    assert not assess(data)["simulation_gate_passed"]
