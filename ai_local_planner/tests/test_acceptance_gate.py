"""Catch false policy-promotion decisions from incomplete evaluation evidence."""

import pytest

from ai_local_planner.scripts import acceptance_gate
from ai_local_planner.scripts.acceptance_gate import assess


def reports(levels=(1, 2, 3)):
    return {level: {
        "checkpoint": "candidate.pth", "level": level, "episodes": 100,
        "domain_randomization": True, "success_rate": 1.,
        "collision_rate": 0., "timeout_rate": 0.,
    } for level in levels}


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


@pytest.mark.parametrize("collision, expected_pass", [(.12, True), (.13, False)])
def test_level4_collision_threshold_boundary(monkeypatch, collision, expected_pass):
    # Isolate the collision threshold: the production .90 success floor and
    # mutually exclusive outcome rates make .12 collision impossible to pass.
    monkeypatch.setitem(acceptance_gate.MIN_SUCCESS, 4, .80)
    data = reports(range(1, 7))
    data[4].update(success_rate=round(1. - collision, 2), collision_rate=collision)

    result = assess(data)

    assert result["levels"]["4"]["maximum_collision_rate"] == .12
    assert result["levels"]["4"]["passed"] is expected_pass
    assert result["simulation_gate_passed"] is expected_pass
    assert all(result["levels"][str(level)]["maximum_collision_rate"] == .02
               for level in (1, 2, 3, 5, 6))


@pytest.mark.parametrize("success, collision, expected_pass", [
    (.90, .10, True),
    (.89, .11, False),
])
def test_level4_still_requires_ninety_percent_success(success, collision, expected_pass):
    data = reports(range(1, 6))
    data[4].update(success_rate=success, collision_rate=collision)

    result = assess(data)

    assert result["levels"]["4"]["minimum_success_rate"] == .90
    assert result["levels"]["4"]["passed"] is expected_pass
