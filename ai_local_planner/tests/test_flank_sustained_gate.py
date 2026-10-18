"""Targeted flank-gate and SI-unit coupled-loss regression tests."""

import numpy as np
import pytest
import torch

from ai_local_planner.models.actor_critic import (
    DirectionalContextualResidualActorCritic, MeanPolicy,
)
from ai_local_planner.scripts.repair_stages_l2_l4 import (
    _level4_side_clearance_torch, asymmetric_actor_loss, level4_side_distance,
)


def _observations(n, distance_m=4.):
    scan = torch.full((n, 365), (distance_m - .12) / 11.88)
    scan[:, 360:] = 0.
    return scan


def _flank_arc(obs, row, distance_m, start=80, count=5):
    obs[row, start:start + count] = (distance_m - .12) / 11.88


def test_flank_sustained_gate_requires_consecutive_returns_with_clear_front(monkeypatch):
    net = DirectionalContextualResidualActorCritic()
    # Emulate the observed failure: classifier confidence drops to zero as
    # soon as the *front* opens beyond three metres.
    monkeypatch.setattr(net, 'context_probability', lambda x: x[..., 0] * 0.)
    obs = _observations(7, distance_m=4.)
    _flank_arc(obs, 0, .35, start=80)      # Five consecutive left flank rays.
    _flank_arc(obs, 1, .25, start=270)     # Right flank, saturated rescue.
    _flank_arc(obs, 2, .40, start=80)      # Below 0.45 physical trigger.
    _flank_arc(obs, 3, .45, start=80)      # Exactly on threshold, gain zero.
    _flank_arc(obs, 4, .12, start=80, count=1)  # Isolated 5% dropout.
    _flank_arc(obs, 5, .20, start=80, count=4)  # Four rays are unconfirmed.
    # Independent per-ray dropout across the whole scan, including both flanks.
    dropout = torch.rand(360, generator=torch.Generator().manual_seed(713)) < .05
    assert dropout.sum() >= 10
    obs[6, :360][dropout] = 0.
    clearance = net.sustained_flank_clearance_m(obs[:, :360])
    gain = net.effective_context_gain(obs)
    assert clearance.tolist()[:4] == pytest.approx([.35, .25, .40, .45], abs=1e-5)
    assert gain.tolist()[:4] == pytest.approx([.5, 1., .25, 0.], abs=1e-5)
    assert torch.all(gain[4:] == 0.)
    assert torch.all(clearance[4:] > 3.)


def test_flank_gain_applies_to_actor_forward_without_new_weights(monkeypatch):
    net = DirectionalContextualResidualActorCritic().eval()
    original_keys = tuple(net.state_dict())
    clone = DirectionalContextualResidualActorCritic()
    clone.load_state_dict(net.state_dict(), strict=True)
    assert tuple(clone.state_dict()) == original_keys
    monkeypatch.setattr(net, 'context_probability', lambda x: x[..., 0] * 0.)
    with torch.no_grad():
        net.correction[-1].bias.copy_(torch.tensor([0., .8]))
    obs = _observations(2, 4.)
    _flank_arc(obs, 0, .35, start=80)
    with torch.no_grad():
        mean, value = net(obs)
        physical = MeanPolicy(net)(obs)
    assert mean.shape == (2, 2) and value.shape == (2,)
    assert physical.shape == (2, 2)
    assert float(mean[0, 1]) == pytest.approx(.4, abs=1e-5)
    assert float(mean[1, 1]) == pytest.approx(0., abs=1e-6)
    assert 0. <= float(physical[0, 0]) <= .35
    assert abs(float(physical[0, 1])) <= 1.5


def test_narrow_symmetric_corridor_does_not_trigger_unilateral_rescue(monkeypatch):
    """L3 has ~0.35 m on BOTH sides; L4 flank rescue must stay suppressed."""
    net = DirectionalContextualResidualActorCritic()
    monkeypatch.setattr(net, 'context_probability', lambda x: x[..., 0] * 0.)
    obs = _observations(3, distance_m=4.)
    obs[0, 65:116] = (.35 - .12) / 11.88
    obs[0, 245:296] = (.35 - .12) / 11.88
    obs[1, 65:116] = (.35 - .12) / 11.88
    obs[1, 245:296] = (.40 - .12) / 11.88
    obs[2, 65:116] = (.25 - .12) / 11.88
    obs[2, 245:296] = (.80 - .12) / 11.88
    gains = net.effective_context_gain(obs)
    assert gains.tolist() == pytest.approx([0., 0., 1.], abs=1e-5)


def test_approaching_corner_does_not_activate_flank_exit_gate(monkeypatch):
    net = DirectionalContextualResidualActorCritic()
    monkeypatch.setattr(net, 'context_probability', lambda x: x[..., 0] * 0.)
    obs = _observations(2, distance_m=4.)
    _flank_arc(obs, 0, .25)
    _flank_arc(obs, 1, .25)
    obs[0, :16] = (.7 - .12) / 11.88
    obs[0, 345:360] = (.7 - .12) / 11.88
    gain = net.effective_context_gain(obs)
    assert gain.tolist() == pytest.approx([0., 1.], abs=1e-5)


def test_coupled_loss_uses_physical_omega_threshold_and_side_distance():
    # Teacher 0.3 normalized = 0.45 rad/s, which is > 0.4 rad/s.
    teacher = torch.tensor([[.4, .3], [.4, .3]])
    student = torch.tensor([[.8, .1], [.8, .1]], requires_grad=True)
    sides = torch.tensor([.39, .40])
    active = asymmetric_actor_loss(student, teacher, clearance_m=sides)
    baseline = asymmetric_actor_loss(student, teacher, clearance_m=sides,
                                     coupled_penalty=0.)
    # v difference = (0.8 - 0.4) * (0.35/2) = 0.07 m/s.
    # Missing yaw = (0.3 - 0.1) * 1.5 = 0.30 rad/s.
    expected_increment = 1.5 * .07 * .30 / 2
    assert float(active - baseline) == pytest.approx(expected_increment, abs=1e-6)
    active.backward()
    assert torch.isfinite(student.grad).all()
    assert student.grad[0, 0] > student.grad[1, 0]
    assert student.grad[0, 1] < student.grad[1, 1]


@pytest.mark.parametrize('student,teacher', [
    ((.8, .1), (.4, .25)),   # Teacher only 0.375 rad/s.
    ((.3, .1), (.4, .7)),    # No student overspeed.
    ((.8, .8), (.4, .7)),    # Same-direction oversteer is not understeer.
])
def test_coupled_penalty_requires_all_danger_conditions(student, teacher):
    pred = torch.tensor([student])
    labels = torch.tensor([teacher])
    active = asymmetric_actor_loss(pred, labels, clearance_m=torch.tensor([.39]))
    baseline = asymmetric_actor_loss(pred, labels, clearance_m=torch.tensor([.39]),
                                     coupled_penalty=0.)
    torch.testing.assert_close(active, baseline)


def test_coupled_loss_detects_wrong_way_turn_for_negative_teacher_omega():
    teacher = torch.tensor([[.2, -.6]])
    predicted = torch.tensor([[.6, .3]], requires_grad=True)
    loss = asymmetric_actor_loss(predicted, teacher,
                                 clearance_m=torch.tensor([.35]))
    base = asymmetric_actor_loss(predicted, teacher,
                                 clearance_m=torch.tensor([.35]), coupled_penalty=0.)
    assert loss > base
    loss.backward()
    assert torch.isfinite(predicted.grad).all()
    assert predicted.grad[0, 1] > 0.


def test_level4_training_clearance_matches_dropout_robust_numpy_statistic():
    obs = _observations(2)
    obs[0, 80:115] = (.38 - .12) / 11.88
    obs[1, 280] = 0.  # Isolated dropout must not activate the 0.40 m gate.
    actual = _level4_side_clearance_torch(obs)
    expected = level4_side_distance(obs.numpy())
    np.testing.assert_allclose(actual.detach().numpy(), expected, atol=1e-5)
    assert actual[0] < .40 and actual[1] > 3.
