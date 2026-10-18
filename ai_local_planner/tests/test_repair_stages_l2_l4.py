"""Regression checks for staged single-actor DAgger repair controls."""

import numpy as np
import pytest
import torch

from ai_local_planner.scripts.repair_stages_l2_l4 import (
    _project_conflicting_gradient, asymmetric_actor_loss, choose_level4_rollout,
    level2_approach_weights, level4_recovery_weights, level4_side_distance,
    perturb_student_action,
)


def _observation(distance):
    x = np.zeros((2, 365), np.float32)
    x[:, :360] = (np.asarray(distance, np.float32)[:, None] - .12) / 11.88
    return x


def test_level2_approach_uses_supplied_multiplier_and_disagreement():
    obs = _observation([1.5, 4.])
    target = np.zeros((2, 2), np.float32)
    student = target.copy()
    assert level2_approach_weights(obs, target, student, 6.).tolist() == [6., 1.]
    student[1, 1] = .16
    assert level2_approach_weights(obs, target, student, 6.).tolist() == [6., 6.]


def test_level4_weight_approach_critical_and_disagreement():
    obs = _observation([.3, 1.3])
    labels = np.zeros((2, 2), np.float32)
    student = labels.copy()
    assert level4_recovery_weights(obs, labels, student).tolist() == [6., 5.]
    student[1, 1] = .16
    assert level4_recovery_weights(obs, labels, student).tolist() == [6., 25.]
    far = _observation([3., 4.])
    assert level4_recovery_weights(far, labels, student).tolist() == [1., 5.]
    with pytest.raises(ValueError):
        level4_recovery_weights(obs, labels, None)


def test_level4_front_wide_scan_ignores_single_dropout():
    obs = _observation([4., 4.])
    obs[0, 60] = 0.  # +/-60 degrees inclusive
    assert level4_recovery_weights(obs)[0] == 1.
    obs[0, 0:60] = (.4 - .12) / 11.88
    assert level4_recovery_weights(obs)[0] == 6.


def test_level4_lateral_clearance_prioritized_without_front_obstacle():
    obs = _observation([3., 3.])
    obs[0, 60:121] = (.40 - .12) / 11.88
    assert level4_side_distance(obs)[0] == pytest.approx(.40, abs=1e-4)
    assert level4_recovery_weights(obs, side_weight=6.).tolist() == [6., 1.]
    obs[1, 235] = 0.  # One dropout cannot trigger the 15th percentile.
    assert level4_recovery_weights(obs, side_weight=6.).tolist() == [6., 1.]


def test_asymmetric_speed_loss_only_penalizes_excess_speed():
    labels = torch.tensor([[0., .5], [0., .5], [.8, 0.]])
    student = torch.tensor([[.2, .5], [-.2, .5], [1., 0.]])
    error = asymmetric_actor_loss(student, labels)
    # Only overspeed during a sharp teacher turn receives the extra weight.
    expected = (3.5 * .2**2 + .2**2 + .2**2) / 6
    assert float(error) == pytest.approx(expected)
    error.backward() if error.requires_grad else None


def test_mixed_rollout_switches_policies_and_clamps_commands():
    rng = np.random.default_rng(7)
    student = np.array([1.5, -1.5], np.float32)
    teacher = np.array([-.8, 1.3], np.float32)
    action, chosen = choose_level4_rollout(student, teacher, .4, rng,
                                           teacher_probability=0.)
    assert chosen and np.array_equal(action, np.array([-.8, 1.], np.float32))
    for _ in range(100):
        action, chosen = choose_level4_rollout(student, teacher, 3., rng,
                                              teacher_probability=.5,
                                              perturb_probability=1.)
        assert action.shape == (2,)
        assert np.isfinite(action).all() and (np.abs(action) <= 1.).all()


def test_randomized_angular_perturbation_preserves_linear_and_bounds():
    rng = np.random.default_rng(41)
    original = np.asarray([.2, .4], np.float32)
    perturbed = [perturb_student_action(original, rng, 1.) for _ in range(200)]
    assert all(a[0] == original[0] for a in perturbed)
    assert all(abs(float(a[1]) - float(original[1])) <= .3 / 1.5 + 1e-6
               for a in perturbed)
    assert any(a[1] != original[1] for a in perturbed)
    assert np.array_equal(original, np.asarray([.2, .4], np.float32))


def test_risky_student_rollout_can_collect_failure_states():
    rng = np.random.default_rng(10)
    student = np.asarray([.8, 0.], np.float32)
    teacher = np.asarray([-.8, 1.], np.float32)
    action, teacher_used = choose_level4_rollout(
        student, teacher, .35, rng, teacher_probability=0.,
        perturb_probability=0., risk_override_probability=0.)
    assert not teacher_used
    np.testing.assert_array_equal(action, student)
    with pytest.raises(ValueError, match='risk_override_probability'):
        choose_level4_rollout(student, teacher, .35, rng,
                             risk_override_probability=1.5)


def test_flank_rescue_uses_teacher_when_front_is_clear_but_side_is_close():
    rng = np.random.default_rng(512)
    student = np.array([.8, 0.], dtype=np.float32)
    teacher = np.array([-.8, .9], dtype=np.float32)
    actual, rescued = choose_level4_rollout(
        student, teacher, 3.0, rng, teacher_probability=0.,
        risk_override_probability=1., side_distance=.32, flank_rescue=True)
    assert rescued
    np.testing.assert_array_equal(actual, teacher)
    # Explicitly allow unsafe student recovery states to be visited in DAgger.
    actual, rescued = choose_level4_rollout(
        student, teacher, 3.0, rng, teacher_probability=0.,
        risk_override_probability=0., side_distance=.32, flank_rescue=True,
        perturb_probability=0.)
    assert not rescued
    np.testing.assert_array_equal(actual, student)
    actual, rescued = choose_level4_rollout(
        student, teacher, 3.0, rng, teacher_probability=0.,
        risk_override_probability=0., side_distance=.75, flank_rescue=True,
        perturb_probability=0.)
    assert not rescued
    np.testing.assert_array_equal(actual, student)


def test_asymmetric_loss_turn_and_flank_penalties():
    prediction = torch.tensor([[.6, .2], [.6, .2]], requires_grad=True)
    teacher = torch.tensor([[0., .9], [0., .9]])
    ordinary = asymmetric_actor_loss(prediction, teacher)
    safety = asymmetric_actor_loss(prediction, teacher, turn_multiplier=2.5,
                                   clearance_m=torch.tensor([.3, 2.]))
    assert safety > ordinary
    safety.backward()
    assert prediction.grad is not None
    assert torch.isfinite(prediction.grad).all()
    with pytest.raises(ValueError, match='clearance'):
        asymmetric_actor_loss(prediction, teacher,
                              clearance_m=torch.tensor([.3]))


def test_joint_loss_teacher_relative_overspeed_and_flank_steering():
    labels = torch.tensor([[.5, .8], [.5, .8]])
    prediction = torch.tensor([[.8, .1], [.8, .1]], requires_grad=True)
    protected = asymmetric_actor_loss(prediction, labels,
                                     clearance_m=torch.tensor([.49, .50]))
    # velocity weights 3.5 in both rows, angular weights 5 (risk) and 3.
    expected = ((.3**2 * 3.5 + .7**2 * 5.) +
                (.3**2 * 3.5 + .7**2 * 3.)) / 4
    assert float(protected.detach()) == pytest.approx(expected, abs=1e-6)
    protected.backward()
    assert torch.isfinite(prediction.grad).all()
    assert prediction.grad[0, 1] < prediction.grad[1, 1]
    assert prediction.grad[0, 0] == pytest.approx(prediction.grad[1, 0])


def test_joint_loss_no_fixed_creep_threshold_and_no_penalty_for_teacher_speed():
    # The old loss would punish a fast command even when it equals the expert.
    teacher = torch.tensor([[.7, .75]])
    prediction = teacher.clone().requires_grad_()
    protected = asymmetric_actor_loss(prediction, teacher,
                                     clearance_m=torch.tensor([.20]))
    assert float(protected) == pytest.approx(0.)
    protected.backward()
    torch.testing.assert_close(prediction.grad, torch.zeros_like(prediction))
    with pytest.raises(ValueError, match='clearance'):
        asymmetric_actor_loss(prediction, teacher,
                              clearance_m=torch.tensor([.2, .3]))


def test_joint_loss_safe_steering_penalizes_understeer_only():
    teacher = torch.tensor([[.4, -.8], [.4, -.8]])
    predicted = torch.tensor([[.3, -.4], [.3, -.8]])
    output = asymmetric_actor_loss(predicted, teacher,
                                  clearance_m=torch.tensor([.3, .3]))
    # A slower-than-teacher speed has no overspeed penalty.
    expected = ((.1**2 + .4**2 * 5.) + (.1**2 + 0.)) / 4
    assert float(output) == pytest.approx(expected, abs=1e-6)


def test_perturbation_disabled():
    action = np.asarray([-.4, .9], np.float32)
    assert np.array_equal(perturb_student_action(action, np.random.default_rng(1), 0.),
                          action)


def test_observation_contract_rejects_wrong_size():
    with pytest.raises(ValueError, match="365"):
        level4_recovery_weights(np.zeros((3, 360), np.float32))


def test_gradient_surgery_preserves_nonconflicting_old_direction():
    old = [torch.tensor([1., 0.]), torch.tensor([0., 2.])]
    new = [torch.tensor([-3., 4.]), torch.tensor([0., -1.])]
    projected, changed = _project_conflicting_gradient(old, new)
    assert changed
    assert sum(float((a * b).sum()) for a, b in zip(old, projected)) >= -1e-6
    partial, changed = _project_conflicting_gradient(old, new, relaxation=.5)
    assert changed
    assert 0 > sum(float((a * b).sum()) for a, b in zip(old, partial)) > -5.001
    parallel = [torch.tensor([2., 0.]), torch.tensor([0., 3.])]
    kept, changed = _project_conflicting_gradient(old, parallel)
    assert not changed
    assert all(torch.equal(a, b) for a, b in zip(parallel, kept))
