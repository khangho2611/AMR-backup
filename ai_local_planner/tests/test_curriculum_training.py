"""Protect promotion from silent collision and old-level regressions."""

from collections import deque

from ai_local_planner.scripts.run_train import (can_promote, passes_level_gate,
                                                restore_episode_history)


def report(level: int, success: float, collisions: float = 0.,
           episodes: int = 100, randomized: bool = True) -> dict:
    return dict(level=level, episodes=episodes,
                domain_randomization=randomized,
                success_rate=success, collision_rate=collisions)


def test_level_specific_success_thresholds_are_enforced():
    assert not passes_level_gate(report(1, .90), 1)
    assert not passes_level_gate(report(2, .97), 2)
    assert passes_level_gate(report(1, .99), 1)
    assert passes_level_gate(report(2, .98), 2)
    assert passes_level_gate(report(3, .90), 3)


def test_collisions_and_randomization_block_promotion():
    assert not passes_level_gate(report(3, .95, collisions=.03), 3)
    assert not passes_level_gate(report(3, .99, episodes=99), 3)
    assert not passes_level_gate(report(3, 1., randomized=False), 3)
    assert not passes_level_gate(report(1, 1.), 2)


def test_retention_gate_blocks_candidate_even_if_current_level_passes():
    current = dict(current_passed=True, retention_passed=False)
    assert not can_promote(current)
    assert not can_promote(dict(current_passed=False, retention_passed=True))
    assert can_promote(dict(current_passed=True, retention_passed=True))
    assert can_promote(current, retention_enabled=False)


def test_resume_preserves_per_level_episodes_and_window(tmp_path):
    log = tmp_path / "episodes.csv"
    log.write_text("episode,level,success\n1,1,1\n2,2,0\n3,1,0\n4,2,1\n",
                   encoding="utf-8")
    history = {i: deque(maxlen=2) for i in range(1, 7)}
    assert restore_episode_history(log, history) == 4
    assert list(history[1]) == [1., 0.]
    assert list(history[2]) == [0., 1.]
    assert not history[3]
