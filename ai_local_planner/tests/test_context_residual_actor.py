"""Compatibility and isolation tests for experimental single actor adapter."""

import numpy as np
import pytest
import torch
from pathlib import Path

from ai_local_planner.configs.settings import load_config
from ai_local_planner.models.actor_critic import (ActorCritic,
                                                  ContextualResidualActorCritic,
                                                  ConservativeContextualResidualActorCritic,
                                                  DirectionalContextualResidualActorCritic,
                                                  upgrade_contextual_to_directional,
                                                  MeanPolicy)
from ai_local_planner.trainers.ppo_agent import PPOAgent
from ai_local_planner.scripts.train_context_residual import update_residual, prepare_replay


def test_residual_initialization_preserves_original_actor_exactly():
    torch.manual_seed(4)
    old = ActorCritic()
    expanded = ContextualResidualActorCritic()
    expanded.load_state_dict(old.state_dict(), strict=False)
    x = torch.rand(5, 365)
    with torch.no_grad():
        original_action = MeanPolicy(old)(x)
        new_action = MeanPolicy(expanded)(x)
    torch.testing.assert_close(original_action, new_action, rtol=0, atol=0)
    assert new_action.shape == (5, 2)


def test_context_gate_is_bounded_and_suppressed_for_low_p4():
    policy = ContextualResidualActorCritic()
    class FixedClassifier(torch.nn.Module):
        def forward(self, obs):
            p = torch.tensor([0.001, .05, .9])
            logit = torch.log(p / (1 - p))
            logits = torch.full((len(p), 6), -100., dtype=obs.dtype)
            logits[:, 0] = 0.
            logits[:, 3] = logit
            return logits

    policy.context_scene = FixedClassifier()
    gain = policy.context_probability(torch.rand(3, 365)).detach().numpy()
    assert gain[0] < .001
    assert gain[1] == pytest.approx(.5, abs=.01)
    assert gain[2] > .99


def test_frozen_context_updates_only_correction():
    policy = ContextualResidualActorCritic()
    policy.freeze_pretrained()
    parameters = dict(policy.named_parameters())
    assert all(parameter.requires_grad == name.startswith('correction.')
               for name, parameter in parameters.items())
    x = torch.rand(2, 365)
    torch.tanh(policy(x)[0]).sum().backward()
    assert parameters['correction.4.bias'].grad is not None
    assert parameters['actor.bias'].grad is None


def test_checkpoint_roundtrip_auto_detects_context_architecture(tmp_path):
    cfg = load_config()['ppo']
    student = PPOAgent(cfg, 'cpu')
    student.network = ContextualResidualActorCritic()
    student.optimizer = torch.optim.Adam(student.network.parameters(), lr=cfg['learning_rate'])
    with torch.no_grad():
        student.network.correction[-1].bias.copy_(torch.tensor([.25, -.2]))
    path = tmp_path / 'contextual.pth'
    student.save(path, 0, 5, independently_gated=False)
    restored = PPOAgent(cfg, 'cpu')
    checkpoint = restored.load(path)
    assert checkpoint['architecture'] == 'lidar30_context_residual'
    assert isinstance(restored.network, ContextualResidualActorCritic)
    sample = np.random.default_rng(24).uniform(0, 1, 365).astype(np.float32)
    original, _, _ = student.act(sample, deterministic=True)
    copied, _, _ = restored.act(sample, deterministic=True)
    np.testing.assert_allclose(original, copied, rtol=0, atol=0)


def test_conservative_context_gate_zero_for_old_scenes_and_roundtrip(tmp_path):
    class FixedClassifier(torch.nn.Module):
        def forward(self, obs):
            logits = torch.full((len(obs), 6), -100., dtype=obs.dtype)
            logits[:, 0] = 0.
            logits[:, 3] = torch.log(torch.tensor(.004 / .996))
            return logits

    model = ConservativeContextualResidualActorCritic()
    model.context_scene = FixedClassifier()
    gain = model.context_probability(torch.rand(4, 365))
    assert torch.count_nonzero(gain) == 0
    cfg = load_config()['ppo']
    student = PPOAgent(cfg, 'cpu')
    student.network = ConservativeContextualResidualActorCritic()
    student.optimizer = torch.optim.Adam(student.network.parameters(), lr=cfg['learning_rate'])
    path = tmp_path / 'context_conservative.pth'
    student.save(path, 0, 5, independently_gated=False)
    loaded = PPOAgent(cfg, 'cpu')
    loaded.load(path)
    assert type(loaded.network) is ConservativeContextualResidualActorCritic


def test_context_calibration_updates_classifier_but_keeps_actor_backbone_frozen():
    torch.manual_seed(43)
    agent = PPOAgent(load_config()['ppo'], 'cpu')
    agent.network = ConservativeContextualResidualActorCritic()
    agent.network.freeze_pretrained()
    for parameter in agent.network.context_scene.parameters():
        parameter.requires_grad_(True)
    observations = np.random.default_rng(43).uniform(0, 1, (16, 365)).astype(np.float32)
    demonstrations = (observations, np.zeros((16, 2), np.float32),
                      np.ones(16, np.float32))
    replay = {level: (torch.tensor(observations), torch.zeros((16, 2)))
              for level in (1, 2, 3, 5)}
    before_actor = agent.network.actor.weight.detach().clone()
    before_context = agent.network.context_scene.head[-1].weight.detach().clone()
    summary = update_residual(agent, demonstrations, replay, .0001, 3, 8,
                              np.random.default_rng(44), train_context=True)
    assert summary['context_finetuned'] is True
    torch.testing.assert_close(before_actor, agent.network.actor.weight)
    assert not torch.equal(before_context, agent.network.context_scene.head[-1].weight)


def test_directional_clearances_preserve_near_flank_geometry():
    scan = torch.full((2, 360), .9)
    scan[0, 85] = .02
    scan[1, 275] = .03
    pool = DirectionalContextualResidualActorCritic.directional_clearances(scan)
    assert pool.shape == (2, 6)
    assert pool[0, 3].item() == pytest.approx(.02)
    assert pool[1, 4].item() == pytest.approx(.03)
    assert pool[0, 5].item() == pytest.approx(.02)
    assert torch.all(pool[:, 0] == .9)
    assert DirectionalContextualResidualActorCritic().correction[0].in_features == 283


def test_upgrade_preserves_trained_conservative_policy_and_autoload(tmp_path):
    baseline_path = Path('ai_local_planner/checkpoints/single_actor_conservative_dagger_20261018/retention_candidate.pth')
    if not baseline_path.exists():
        pytest.skip('Retained experimental checkpoint is unavailable')
    source = PPOAgent(load_config()['ppo'], 'cpu')
    source.initialize_from(baseline_path)
    assert isinstance(source.network, ConservativeContextualResidualActorCritic)
    upgraded = DirectionalContextualResidualActorCritic()
    upgraded.load_state_dict(upgrade_contextual_to_directional(source.network.state_dict()))
    rng = np.random.default_rng(1751)
    observations = torch.from_numpy(rng.random((8, 365)).astype(np.float32))
    source.network.eval()
    upgraded.eval()
    with torch.no_grad():
        before = MeanPolicy(source.network)(observations)
        after = MeanPolicy(upgraded)(observations)
    torch.testing.assert_close(before, after, rtol=0, atol=1e-6)
    cfg = load_config()['ppo']
    student = PPOAgent(cfg, 'cpu')
    student.network = upgraded
    student.optimizer = torch.optim.Adam(upgraded.parameters(), lr=cfg['learning_rate'])
    checkpoint = tmp_path / 'directional.pth'
    student.save(checkpoint, 0, 5)
    restored = PPOAgent(cfg, 'cpu')
    metadata = restored.load(checkpoint)
    assert metadata['architecture'] == 'lidar30_context_directional'
    assert type(restored.network) is DirectionalContextualResidualActorCritic
    with torch.no_grad():
        copied = MeanPolicy(restored.network)(observations)
    torch.testing.assert_close(after, copied, rtol=0, atol=0)


def test_level2_rehearsal_uses_specialist_labels_on_student_states(monkeypatch):
    observed = []
    class Expert:
        pass
    old_expert, level2_expert, student = Expert(), Expert(), Expert()

    def collect(expert, actor, level, seeds, max_steps, rng, stage):
        assert actor is student
        observed.append((level, expert, len(seeds)))
        states = np.full((2, 365), level, dtype=np.float32)
        expert_action = (0.2 if expert is level2_expert else 0.9)
        labels = np.full((2, 2), expert_action, dtype=np.float32)
        return states, labels, None, None, {'level': level}

    monkeypatch.setattr('ai_local_planner.scripts.train_context_residual.collect_dagger', collect)
    replay = prepare_replay(student, old_expert, 2, 100, 20,
                            level2_teacher=level2_expert, level2_episodes=5)
    assert observed == [(1, old_expert, 2), (2, level2_expert, 5),
                        (3, old_expert, 2), (5, old_expert, 2)]
    assert torch.all(replay[2][1] == torch.tensor(.2, dtype=torch.float32))
    assert torch.all(replay[3][1] == torch.tensor(.9, dtype=torch.float32))
