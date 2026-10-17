import numpy as np
import pytest
import torch

from ai_local_planner.models.actor_critic import (ActorCritic, MeanPolicy,
                                                  migrate_legacy_state_dict)
from ai_local_planner.trainers.ppo_agent import PPOAgent
from ai_local_planner.trainers.rollout_buffer import RolloutBuffer
from ai_local_planner.configs.settings import load_config


def test_actor_critic_shapes_gradients_and_log_prob():
    torch.manual_seed(0)
    model = ActorCritic()
    obs = torch.rand(7, 365)
    action, logp, values = model.sample(obs)
    assert action.shape == (7, 2)
    assert logp.shape == values.shape == (7,)
    assert torch.isfinite(action).all() and (action.abs() <= 1).all()
    check_logp, entropy, check_values = model.evaluate(obs, action)
    assert torch.allclose(logp, check_logp, atol=1e-4)
    assert torch.allclose(values, check_values, atol=1e-6)
    (check_logp.mean() + check_values.mean() + entropy.mean()).backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())


def test_mean_policy_physical_velocity_bounds():
    policy = MeanPolicy(ActorCritic()).eval()
    with torch.no_grad():
        output = policy(torch.rand(11, 365))
    assert output.shape == (11, 2)
    assert bool(((output[:, 0] >= 0) & (output[:, 0] <= .35)).all())
    assert bool((output[:, 1].abs() <= 1.5).all())


def test_new_lidar_resolution_and_exact_legacy_migration(tmp_path):
    new = ActorCritic()
    assert new.lidar_net[6].kernel_size == (3,)
    assert new.lidar_net[8].in_features == 32 * 30
    assert new.fusion[2].out_features == 128
    old = ActorCritic(legacy=True)
    with torch.no_grad():
        old.actor.weight.normal_(0., .1)
        old.actor.bias.copy_(torch.tensor([.4, -.3]))
    upgraded = ActorCritic()
    upgraded.load_state_dict(migrate_legacy_state_dict(old.state_dict()))
    samples = torch.rand(8, 365)
    with torch.no_grad():
        old_action, old_value = old(samples)
        new_action, new_value = upgraded(samples)
    assert torch.allclose(new_action, old_action, atol=1e-6)
    assert torch.allclose(new_value, old_value, atol=1e-6)
    checkpoint = tmp_path / "legacy.pth"
    torch.save({"model": old.state_dict(), "steps": 10, "level": 2}, checkpoint)
    agent = PPOAgent(load_config()["ppo"], device="cpu")
    state = agent.load(checkpoint)
    assert state["migrated_from_legacy"] is True
    with torch.no_grad():
        migrated_action, _ = agent.network(samples)
    assert torch.allclose(migrated_action, old_action, atol=1e-6)


def test_teacher_targets_are_cached_per_rehearsal_level():
    class Expert:
        def __init__(self, action):
            self.action = np.asarray(action, dtype=np.float32)

        def act(self, obs):
            return self.action, 0., 0.

    p = load_config()["ppo"]
    agent = PPOAgent(p, device="cpu")
    agent.reference_experts = [Expert((-.8, .5)), Expert((.8, -.5))]
    agent.reference_coef = 10.
    obs = np.random.default_rng(4).random(365, dtype=np.float32)
    a1 = agent.reference_action(obs, 1)
    a2 = agent.reference_action(obs, 2)
    assert np.allclose(a1, [-.8, .5])
    assert np.allclose(a2, [.8, -.5])
    with pytest.raises(ValueError, match="No reference teacher"):
        agent.reference_action(obs, 3)
    buffer = RolloutBuffer()
    for index, target in enumerate([a1, a2] * 8):
        action, value, logp = agent.act(obs)
        buffer.add(obs, action, logp, .2, value, value,
                   terminated=(index == 15), truncated=False,
                   reference_action=target)
    targets = buffer.reference_tensor(torch.device("cpu"))
    assert torch.allclose(targets[0], torch.tensor([-.8, .5]))
    assert torch.allclose(targets[1], torch.tensor([.8, -.5]))
    metrics = agent.update(buffer, epochs=1, batch_size=8)
    assert np.isfinite(metrics["reference_action_mse"])
    assert not buffer.reference_actions


def test_gae_bootstraps_time_limit_but_not_terminal():
    buffer = RolloutBuffer()
    obs = np.zeros(365, np.float32)
    action = np.zeros(2, np.float32)
    buffer.add(obs, action, 0., 1., 2., 3., terminated=False, truncated=True)
    *_, advantages, returns = buffer.tensors(.9, .95, torch.device("cpu"))
    assert advantages.item() == pytest.approx(1. + .9 * 3. - 2.)
    assert returns.item() == pytest.approx(1. + .9 * 3.)
    buffer.clear()
    buffer.add(obs, action, 0., 1., 2., 3., terminated=True, truncated=False)
    *_, advantages, returns = buffer.tensors(.9, .95, torch.device("cpu"))
    assert advantages.item() == pytest.approx(-1.)
    assert returns.item() == pytest.approx(1.)


def test_rollout_can_reuse_subsequent_value_without_second_forward():
    buffer = RolloutBuffer()
    buffer.add(np.zeros(365, np.float32), np.zeros(2, np.float32),
               0., 1., 2., 0., False, False)
    buffer.finish_last(3.)
    *_, advantage, target = buffer.tensors(.9, .95, torch.device("cpu"))
    assert advantage.item() == pytest.approx(1.7)
    assert target.item() == pytest.approx(3.7)


def test_ppo_update_and_checkpoint_round_trip(tmp_path):
    p = load_config()["ppo"]
    agent = PPOAgent(p, device="cpu")
    buffer = RolloutBuffer()
    rng = np.random.default_rng(3)
    for i in range(16):
        obs = rng.random(365, dtype=np.float32)
        act, value, logp = agent.act(obs)
        buffer.add(obs, act, logp, .4, value, value, terminated=(i == 15), truncated=False)
    outcome = agent.update(buffer, epochs=2, batch_size=8)
    assert not buffer.data
    assert all(np.isfinite(value) for value in outcome.values())
    saved = tmp_path / "checkpoint.pth"
    agent.save(saved, 16, 1)
    other = PPOAgent(p, device="cpu")
    info = other.load(saved)
    assert info["steps"] == 16
    assert all(torch.equal(a, b) for a, b in zip(agent.network.parameters(),
                                                   other.network.parameters()))
