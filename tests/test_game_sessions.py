"""CPU-only checks for exact replay, native cursors and compute receipts."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from pathlib import Path

import pytest
from test_adapters import Lease, Process
from test_hf_adapters import Model, Tokenizer, Torch, command

from venom_module_cooperation_lab.adapters import hf_worker
from venom_module_cooperation_lab.adapters.base import (
    ChatMessage,
    GenerationParameters,
    GenerationResult,
    validate_messages,
)
from venom_module_cooperation_lab.adapters.hf import HfAdapter, pinned_specs
from venom_module_cooperation_lab.adapters.registry import RWKV_SPEC
from venom_module_cooperation_lab.adapters.rwkv import RecurrentAdapter
from venom_module_cooperation_lab.adapters.rwkv_process import RwkvError, RwkvParameters
from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.sessions import (
    SessionDriver,
    capabilities_for,
)


def rwkv():
    adapter = RecurrentAdapter(RWKV_SPEC, Lease(), Path("/unused"), Path("/unused"))
    adapter._process = Process()
    return adapter, adapter._process


def run(driver, participant="A", observation="event", **params):
    return driver.generate(
        participant,
        observation,
        GenerationParameters(**params),
        time.monotonic() + 5,
    )


def test_replay_resets_before_every_full_history_without_dropping_answers():
    adapter, process = rwkv()
    driver = SessionDriver(adapter, "history_replay", "carry")
    driver.begin_episode()
    run(driver, observation="first")
    driver.begin_episode()
    result = run(driver, observation="second")
    assert process.calls[0] == (None, "reset")
    assert [c for c in process.calls if c[1] == "reset"] == [
        (None, "reset"),
        ("A", "reset"),
        ("A", "reset"),
    ]
    assert process.calls[-1][1] == (
        "User: first\n\nAssistant: answer\n\nUser: second\n\nAssistant:"
    )
    assert result.effective_parameters["memory_kind"] == "text_history"
    assert result.effective_parameters["event_cursor"] == 2
    assert result.effective_parameters["episode_index"] == 2


def test_native_carry_consumes_only_new_suffix_and_isolates_players():
    adapter, process = rwkv()
    driver = SessionDriver(adapter, "native_incremental", "carry")
    driver.begin_episode()
    run(driver, "A", "A-secret")
    run(driver, "B", "B-secret")
    driver.begin_episode()
    result = run(driver, "A", "A-next")
    assert [c for c in process.calls if c[1] == "reset"] == [(None, "reset")]
    assert process.calls[-1] == ("A", "User: A-next\n\nAssistant:")
    assert all(
        "B-secret" not in str(prompt) for who, prompt in process.calls if who == "A"
    )
    assert result.effective_parameters["context_mode"] == "append"
    assert result.effective_parameters["event_cursor"] == 2
    assert result.effective_parameters["memory_kind"] == "native_state"
    assert adapter.state()["history_messages"] == {"A": 4, "B": 2}


@pytest.mark.parametrize("mode", ["history_replay", "native_incremental"])
def test_fresh_resets_every_episode_and_never_replays_previous_game(mode):
    adapter, process = rwkv()
    driver = SessionDriver(adapter, mode, "fresh")
    driver.begin_episode()
    run(driver, observation="old game")
    driver.begin_episode()
    result = run(driver, observation="new game")
    assert [c for c in process.calls if c == (None, "reset")] == [(None, "reset")] * 2
    assert "old game" not in process.calls[-1][1]
    assert result.effective_parameters["event_cursor"] == 1


def test_memory_events_are_exact_and_native_carry_cannot_inject_rebuilt_history():
    adapter, process = rwkv()
    driver = SessionDriver(adapter, "native_incremental", "carry")
    driver.begin_episode({"A": [ChatMessage("system", "public rules")]})
    run(driver)
    assert "System: public rules" in process.calls[-1][1]
    with pytest.raises(LabError, match="unsupported_memory_injection"):
        driver.begin_episode({"A": [ChatMessage("user", "old summary")]})
    driver.begin_episode()
    run(driver, observation="new")
    assert "public rules" not in process.calls[-1][1]
    replay = SessionDriver(adapter, "history_replay", "carry")
    replay.begin_episode()
    run(replay)
    replay.begin_episode({"A": [ChatMessage("user", "permitted note")]})
    run(replay)
    assert "permitted note" in process.calls[-1][1]


@pytest.mark.parametrize(
    "memories", [{"C": []}, {"A": ["not a message"]}, {"A": ()}, []]
)
def test_bad_memory_injection_is_rejected_before_reset(memories):
    adapter, process = rwkv()
    driver = SessionDriver(adapter, "history_replay", "fresh")
    with pytest.raises(LabError, match="invalid_messages"):
        driver.begin_episode(memories)
    assert not process.calls


def test_unsupported_model_and_native_combinations_fail_before_operations():
    specs = [asdict(s) for s in pinned_specs()]
    for spec in specs:
        capabilities = capabilities_for(spec)
        assert capabilities["observation_modes"] == ["history_replay"]
        assert capabilities["snapshot_restore"] is False
        adapter, process = rwkv()
        adapter.spec = next(s for s in pinned_specs() if s.model_id == spec["model_id"])
        with pytest.raises(LabError, match="unsupported_session_configuration"):
            SessionDriver(adapter, "native_incremental", "carry")
        assert not process.calls
    assert capabilities_for({})["reason"] == "unsupported_model_adapter"
    assert not capabilities_for({"architecture": "rwkv7", "runtime": "old"})[
        "observation_modes"
    ] == ["history_replay", "native_incremental"]


@pytest.mark.parametrize(
    "mode,memory,limit",
    [
        ("bad", "fresh", 2048),
        ("history_replay", "bad", 2048),
        ("history_replay", "fresh", True),
        ("history_replay", "fresh", 8193),
    ],
)
def test_bad_driver_configuration(mode, memory, limit):
    adapter, _ = rwkv()
    with pytest.raises(LabError):
        SessionDriver(adapter, mode, memory, limit)


def test_session_requires_begin_and_does_not_hide_context_or_runtime_errors():
    adapter, process = rwkv()
    driver = SessionDriver(adapter, "history_replay", "fresh", max_context_tokens=100)
    with pytest.raises(LabError, match="session_not_started"):
        run(driver)
    driver.begin_episode()
    with pytest.raises(LabError, match="invalid_participant"):
        run(driver, "C")
    with pytest.raises(LabError, match="unsupported_compute_steps"):
        run(driver, num_steps=16)
    original = process.generate

    def checked(participant, prompt, parameters, timeout):
        assert parameters.max_context_tokens == 100
        assert parameters.session_protocol == "game-eval-v2"
        assert parameters.temperature == 0.7 and parameters.top_p == 0.9
        return original(participant, prompt, parameters, timeout)

    process.generate = checked
    run(driver, temperature=0.7, top_p=0.9)
    process.generate = original
    process.fail = True
    with pytest.raises(LabError, match="generation_failed"):
        run(driver)
    with pytest.raises(LabError, match="session_interrupted"):
        driver.begin_episode()
    with pytest.raises(LabError, match="session_interrupted"):
        run(driver)


def test_v2_history_supports_memory_episode_past_legacy_message_limit():
    adapter, _ = rwkv()
    driver = SessionDriver(adapter, "native_incremental", "fresh")
    driver.begin_episode()
    for index in range(64):
        run(driver, observation=f"reveal event {index}")
    assert len(driver._histories["A"]) == 128
    with pytest.raises(LabError, match="invalid_messages"):
        validate_messages("A", [ChatMessage("user", "x")] * 25)
    validate_messages("A", [ChatMessage("user", "x")] * 25, protocol="game-eval-v2")
    driver._histories["A"] = [ChatMessage("user", "x" * 16000)]
    with pytest.raises(LabError, match="context_budget_exceeded"):
        run(driver, observation="y" * 1000)
    assert len(driver._histories["A"][0].content) == 16000


def test_invalid_memory_bound_is_rejected_before_reset():
    adapter, process = rwkv()
    driver = SessionDriver(adapter, "history_replay", "fresh")
    with pytest.raises(LabError, match="context_budget_exceeded"):
        driver.begin_episode({"A": [ChatMessage("user", "x")] * 513})
    assert not process.calls


@pytest.mark.parametrize("reason", ["cancelled", "deadline"])
def test_interruption_prevents_fake_carry(reason):
    adapter, process = rwkv()
    driver = SessionDriver(adapter, "native_incremental", "carry")
    driver.begin_episode()
    process.reason = reason
    result = run(driver)
    assert result.effective_parameters["event_cursor"] == 0
    with pytest.raises(LabError, match="session_interrupted"):
        run(driver)


def test_native_continuity_loss_is_explicit():
    adapter, _ = rwkv()
    driver = SessionDriver(adapter, "native_incremental", "carry")
    driver.begin_episode()
    run(driver)
    # Simulate an external reset which would otherwise silently replay history.
    adapter.reset("A")
    with pytest.raises(LabError, match="native_state_continuity_lost"):
        run(driver)


@pytest.mark.parametrize("parameters", [GenerationParameters, RwkvParameters])
@pytest.mark.parametrize("steps", [0, 7, 128, True, 8.0])
def test_step_contract_rejects_unknown_budgets(parameters, steps):
    with pytest.raises((LabError, RwkvError), match="invalid_parameters"):
        parameters(num_steps=steps)


@pytest.mark.parametrize("steps", [8, 16, 32, 64])
def test_huginn_step_budget_reaches_forward_and_applied_receipt(steps):
    model = Model()
    result = hf_worker.generate(
        model,
        Tokenizer(),
        Torch(),
        {"model_id": "huginn-0125"},
        command(num_steps=steps),
        threading.Event(),
    )
    assert all(call["num_steps"] == steps for call in model.calls)
    assert result["effective_parameters"]["num_steps_requested"] == steps
    assert result["effective_parameters"]["num_steps_applied"] == steps


def test_hrm_default_step_is_not_claimed_as_applied_and_nondefault_is_unsupported():
    result = hf_worker.generate(
        Model(),
        Tokenizer(),
        Torch(),
        {"model_id": "hrm-text-1b"},
        command(),
        threading.Event(),
    )
    assert result["effective_parameters"]["num_steps_applied"] is None
    assert result["effective_parameters"]["num_steps"] is None
    with pytest.raises(RuntimeError, match="unsupported_compute_steps"):
        hf_worker.generate(
            Model(),
            Tokenizer(),
            Torch(),
            {"model_id": "hrm-text-1b"},
            command(num_steps=16),
            threading.Event(),
        )
    with pytest.raises(RuntimeError, match="unsupported_compute_steps"):
        hf_worker.generate(
            Model(),
            Tokenizer(),
            Torch(),
            {"model_id": "huginn-0125"},
            command(num_steps=9),
            threading.Event(),
        )
    assert (
        hf_worker.error_code(RuntimeError("unsupported_compute_steps"))
        == "unsupported_compute_steps"
    )


def test_local_adapters_reject_unsupported_steps_before_using_lease():
    adapter, process = rwkv()
    with pytest.raises(LabError, match="unsupported_compute_steps"):
        adapter.generate(
            "A",
            [ChatMessage("user", "x")],
            GenerationParameters(num_steps=16),
            time.monotonic() + 5,
        )
    assert not process.calls
    hrm = HfAdapter(
        next(s for s in pinned_specs() if s.architecture == "hrm_text"), Lease()
    )
    with pytest.raises(LabError, match="unsupported_compute_steps"):
        hrm.generate(
            "A",
            [ChatMessage("user", "x")],
            GenerationParameters(num_steps=16),
            time.monotonic() + 5,
        )


def test_nonquiescent_result_cannot_continue():
    adapter, _ = rwkv()
    driver = SessionDriver(adapter, "history_replay", "carry")
    driver.begin_episode()
    adapter.generate = lambda *args: GenerationResult(
        "x", 1, 1, None, 0, "eos", {}, False
    )
    run(driver)
    with pytest.raises(LabError, match="session_interrupted"):
        run(driver)


@pytest.mark.parametrize("parameters", [GenerationParameters, RwkvParameters])
def test_unknown_session_protocol_is_not_silently_accepted(parameters):
    with pytest.raises((LabError, RwkvError), match="invalid_parameters"):
        parameters(session_protocol="unknown")


def test_v2_rwkv_sampling_respects_temperature_and_zero_nucleus_without_greedy():
    from adapters_fixtures import MiniTorch, Tensor

    from venom_module_cooperation_lab.adapters import rwkv_worker

    class Scores(Tensor):
        def __truediv__(self, value):
            return Tensor(item / value for item in self.values)

    class Sampling(MiniTorch):
        def __init__(self):
            super().__init__()
            self.multinomial_calls = 0
            self.scores = None

        def softmax(self, tensor, *, dim):
            self.scores = tensor.values
            return super().softmax(tensor, dim=dim)

        def multinomial(self, tensor, count):
            self.multinomial_calls += 1
            return Tensor([1])

    torch = Sampling()
    choice = rwkv_worker._sample_token(
        Scores([4, 2, 1]),
        {},
        {
            "profile": "structured",
            "temperature": 2.0,
            "top_p": 0,
            "session_protocol": "game-eval-v2",
        },
        torch,
    )
    assert choice == 1 and torch.multinomial_calls == 1
    assert torch.scores == [2, 1, 0.5]
    # Qualified legacy top_p=0 remains greedy with exactly the same parameters.
    legacy = rwkv_worker._sample_token(
        Scores([4, 2, 1]),
        {},
        {"profile": "structured", "temperature": 2.0, "top_p": 0},
        torch,
    )
    assert legacy == 0 and torch.multinomial_calls == 1


@pytest.mark.parametrize("top_p", [0, 0.8, 1])
def test_hf_sampling_does_not_silently_force_greedy(top_p):
    from adapters_fixtures import Tensor

    class Scores(Tensor):
        def __truediv__(self, value):
            return Tensor(item / value for item in self.values)

        def float(self):
            return self

    class SampleModel:
        def __call__(self, **kwargs):
            class Logits:
                def __getitem__(self, key):
                    return Scores([0, 10, 9, 8, 0])

            from types import SimpleNamespace

            return SimpleNamespace(logits=Logits(), past_key_values=None)

    class Sampling(Torch):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def multinomial(self, tensor, count):
            self.calls += 1
            return super().multinomial(tensor, count)

    torch = Sampling()
    result = hf_worker.generate(
        SampleModel(),
        Tokenizer(),
        torch,
        {"model_id": "huginn-0125"},
        command(temperature=0.7, top_p=top_p),
        threading.Event(),
    )
    assert torch.calls == 2
    assert result["effective_parameters"]["temperature"] == 0.7
    assert result["effective_parameters"]["top_p"] == top_p


def test_history_capability_tracks_participant_and_fresh_boundary():
    adapter, _ = rwkv()
    driver = SessionDriver(adapter, "history_replay", "fresh")
    driver.begin_episode()
    assert not driver.has_history("A")
    run(driver)
    assert driver.has_history("A") and not driver.has_history("B")
    driver.begin_episode()
    assert not driver.has_history("A")
    with pytest.raises(LabError, match="invalid_participant"):
        driver.has_history("C")


def test_ollama_replay_capabilities_require_provider_and_runtime():
    spec = {"architecture": "gemma4", "provider": "ollama", "runtime": "ollama==0.40.6"}
    caps = capabilities_for(spec)
    assert caps["observation_modes"] == ["history_replay"]
    assert caps["episode_memories"] == ["fresh", "carry"]
    assert caps["compute_steps"] == []
    assert caps["snapshot_restore"] is False
    for changes in ({"provider": "unknown"}, {"runtime": "unknown"}):
        assert (
            capabilities_for({**spec, **changes})["reason"]
            == "unsupported_model_adapter"
        )


def test_context_capability_is_specific_to_verified_ollama_gemma():
    spec = {"provider": "ollama", "runtime": "ollama==0.40.6", "architecture": "gemma4"}
    assert capabilities_for(spec)["max_context_tokens"] == 8192
    assert (
        capabilities_for({**spec, "architecture": "other"})["max_context_tokens"]
        == 2048
    )
    assert capabilities_for({**spec, "provider": "other"})["max_context_tokens"] == 2048
