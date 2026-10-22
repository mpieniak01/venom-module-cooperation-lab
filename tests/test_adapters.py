from __future__ import annotations

import hashlib
import io
import json
import time
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from venom_module_cooperation_lab.adapters import registry
from venom_module_cooperation_lab.adapters.base import (
    ChatMessage,
    GenerationParameters,
    remaining,
    validate_messages,
)
from venom_module_cooperation_lab.adapters.ollama import NoRedirect, OllamaAdapter
from venom_module_cooperation_lab.adapters.rwkv import RecurrentAdapter
from venom_module_cooperation_lab.adapters.rwkv_process import RwkvError, RwkvParameters
from venom_module_cooperation_lab.errors import LabError


class Lease:
    def __init__(self):
        self.cancelled = False
        self.events = []

    @contextmanager
    def operation(self, *, kind="generation"):
        if self.cancelled:
            raise LabError("lease_cancelled")
        self.events.append("start")
        try:
            yield
        finally:
            self.events.append("end")

    @contextmanager
    def cleanup(self, *, confirm_quiescent):
        self.events.append("cleanup")
        yield
        assert confirm_quiescent()

    def cancel(self):
        self.cancelled = True


def test_registry_is_pure_and_fixed(monkeypatch):
    models = registry.list_model_specs()
    assert len(models) == 3
    assert all(not spec.qualified for spec in models)
    assert "http" not in json.dumps([asdict(model) for model in models])
    assert registry.get_model_spec("rwkv7-g1d-0.4b").digest
    with pytest.raises(LabError, match="model_not_allowed"):
        registry.get_model_spec("http://localhost/model")
    with pytest.raises(LabError, match="runtime_lease_required"):
        registry.create_adapter("rwkv7-g1d-0.4b", None)
    assert isinstance(
        registry.create_adapter("rwkv7-g1d-0.4b", Lease()), RecurrentAdapter
    )
    assert isinstance(
        registry.create_adapter("qwen3-4b-control", Lease()), OllamaAdapter
    )
    with pytest.raises(LabError, match="model_not_allowed"):
        registry.create_adapter("unknown", Lease())
    monkeypatch.setenv("COOPERATION_LAB_RWKV_MODEL_ROOT", "relative")
    with pytest.raises(LabError, match="invalid_model_configuration"):
        registry.create_adapter("rwkv7-g1d-0.4b", Lease())


@pytest.mark.parametrize(
    "kw",
    [
        {"max_new_tokens": 0},
        {"max_new_tokens": True},
        {"seed": -1},
        {"temperature": float("nan")},
        {"top_p": 1.1},
        {"max_context_tokens": 4096},
    ],
)
def test_parameters_reject_bad_values(kw):
    with pytest.raises(LabError, match="invalid_parameters"):
        GenerationParameters(**kw)


def test_messages_and_deadline():
    assert remaining(time.monotonic() + 1000, 2) == 2
    with pytest.raises(LabError, match="generation_timeout"):
        remaining(time.monotonic() - 1)
    with pytest.raises(LabError, match="invalid_message"):
        ChatMessage("tool", "anything")
    with pytest.raises(LabError):
        validate_messages("C", [ChatMessage("user", "x")])
    with pytest.raises(LabError):
        validate_messages("A", [ChatMessage("assistant", "x")])
    with pytest.raises(LabError):
        validate_messages("A", [ChatMessage("user", "x" * 9000)] * 2)


class Process:
    _process = None

    def __init__(self):
        self.calls = []
        self.reason = "stop_sequence"
        self.fail = False

    def load(self, timeout):
        from venom_module_cooperation_lab.adapters.rwkv_process import RwkvError

        if self.fail:
            raise RwkvError("artifact_missing")
        return {"state": "ready"}

    def generate(self, participant, prompt, parameters, timeout):
        from venom_module_cooperation_lab.adapters.rwkv_process import RwkvError

        if self.fail:
            raise RwkvError("generation_failed")
        self.calls.append((participant, prompt))
        return {
            "text": "answer",
            "input_tokens": 3,
            "output_tokens": 1,
            "stop_reason": self.reason,
            "quiescent": True,
            "effective_parameters": {},
        }

    def reset(self, participant):
        self.calls.append((participant, "reset"))
        return {"state": "reset"}

    def cancel(self):
        self.calls.append((None, "cancel"))

    def close(self):
        return True

    def status(self):
        return {"state": "ready", "quiescent": True}


def test_recurrent_contexts_append_replay_and_cleanup():
    lease = Lease()
    adapter = RecurrentAdapter(
        registry.RWKV_SPEC, lease, Path("/unused"), Path("/unused")
    )
    process = adapter._process = Process()
    assert adapter.load(time.monotonic() + 2)["state"] == "ready"
    first = [ChatMessage("user", "start")]
    result = adapter.generate("A", first, GenerationParameters(), time.monotonic() + 2)
    assert result.effective_parameters["context_mode"] == "replay"
    continuation = [
        *first,
        ChatMessage("assistant", "answer"),
        ChatMessage("user", "continue"),
    ]
    assert (
        adapter.generate(
            "A", continuation, GenerationParameters(), time.monotonic() + 2
        ).effective_parameters["context_mode"]
        == "append"
    )
    assert process.calls[-1][1].startswith("User: continue")
    adapter.generate("B", first, GenerationParameters(), time.monotonic() + 2)
    assert adapter.state()["history_messages"] == {"A": 4, "B": 2}
    adapter.generate("A", first, GenerationParameters(), time.monotonic() + 2)
    assert ("A", "reset") in process.calls
    process.reason = "cancelled"
    adapter.generate(
        "A", [ChatMessage("user", "new")], GenerationParameters(), time.monotonic() + 2
    )
    adapter.reset("A")
    adapter.reset()
    assert adapter.state()["history_messages"] == {"A": 0, "B": 0}
    with pytest.raises(LabError):
        adapter.reset("C")
    process.fail = True
    with pytest.raises(LabError, match="artifact_missing"):
        adapter.load(time.monotonic() + 2)
    with pytest.raises(LabError, match="generation_failed"):
        adapter.generate("A", first, GenerationParameters(), time.monotonic() + 2)
    adapter.cancel()
    assert lease.cancelled and adapter.close()
    assert adapter.is_quiescent()


def configured_ollama():
    spec = replace(
        registry.OLLAMA_SPEC, template_hash=hashlib.sha256(b"template").hexdigest()
    )
    lease = Lease()
    adapter = OllamaAdapter(spec, lease)
    values = {
        "/api/version": {"version": "0.40.6"},
        "/api/ps": {"models": []},
        "/api/tags": {"models": [{"name": "qwen3:4b", "digest": spec.digest}]},
        "/api/show": {"template": "template"},
    }
    adapter._json = lambda path, payload, timeout: values[path]
    return adapter, lease, values


def test_ollama_load_identity_and_template():
    adapter, _, values = configured_ollama()
    assert adapter.load(time.monotonic() + 3)["metadata_verified"]
    values["/api/tags"] = {"models": []}
    with pytest.raises(LabError, match="artifact_missing"):
        adapter.load(time.monotonic() + 3)
    values["/api/tags"] = {"models": [{"name": "qwen3:4b", "digest": "other"}]}
    with pytest.raises(LabError, match="model_identity_changed"):
        adapter.load(time.monotonic() + 3)
    values["/api/tags"]["models"][0]["digest"] = adapter.spec.digest
    values["/api/show"] = {"template": "changed"}
    with pytest.raises(LabError, match="model_template_changed"):
        adapter.load(time.monotonic() + 3)


def stream(adapter, items, cancel=False):
    class Response(io.BytesIO):
        def readline(self, size=-1):
            if cancel:
                adapter.cancel()
            return super().readline(size)

    response = Response(b"".join(json.dumps(item).encode() + b"\n" for item in items))
    adapter._open = lambda path, payload, timeout: response
    return response


def test_ollama_generation_usage_isolation_reset():
    adapter, _, _ = configured_ollama()
    adapter.load(time.monotonic() + 3)
    stream(
        adapter,
        [
            {"message": {"content": "hello"}},
            {"done": True, "prompt_eval_count": 12, "eval_count": 1},
        ],
    )
    result = adapter.generate(
        "A",
        [ChatMessage("user", "hello")],
        GenerationParameters(),
        time.monotonic() + 3,
    )
    assert result.text == "hello" and result.input_tokens == 12 and result.quiescent
    assert adapter.state()["history_messages"] == {"A": 2, "B": 0}
    assert result.effective_parameters["think"] is False
    adapter.reset("A")
    adapter.reset()
    with pytest.raises(LabError):
        adapter.reset("C")
    adapter._busy = True
    with pytest.raises(LabError, match="runtime_busy"):
        adapter.reset()
    adapter._busy = False
    assert adapter.close()


def test_ollama_cancel_drains_terminal_before_close():
    adapter, lease, _ = configured_ollama()
    adapter.load(time.monotonic() + 3)
    response = stream(
        adapter, [{"message": {"content": "ignored"}}, {"done": True}], cancel=True
    )
    result = adapter.generate(
        "B",
        [ChatMessage("user", "hello")],
        GenerationParameters(),
        time.monotonic() + 3,
    )
    assert result.stop_reason == "cancelled" and response.closed
    assert adapter.state()["history_messages"]["B"] == 0
    assert lease.cancelled and adapter.close()


@pytest.mark.parametrize(
    "items,code",
    [
        ([], "runtime_not_quiescent"),
        ([{"error": "private"}], "generation_failed"),
        ([{"message": {"content": 5}}], "malformed_model_output"),
        ([{"done": True, "eval_count": -1}], "malformed_model_usage"),
    ],
)
def test_ollama_failure_does_not_fake_quiescence(items, code):
    adapter, _, _ = configured_ollama()
    adapter.load(time.monotonic() + 3)
    stream(adapter, items)
    with pytest.raises(LabError, match=code):
        adapter.generate(
            "A",
            [ChatMessage("user", "hello")],
            GenerationParameters(),
            time.monotonic() + 3,
        )
    if code != "malformed_model_usage":
        assert not adapter.is_quiescent()
        with pytest.raises(LabError, match="runtime_not_quiescent"):
            adapter.close()


def test_ollama_rejects_context_and_redirect():
    adapter, _, _ = configured_ollama()
    with pytest.raises(LabError, match="invalid_state"):
        adapter.generate(
            "A",
            [ChatMessage("user", "hi")],
            GenerationParameters(),
            time.monotonic() + 2,
        )
    adapter.load(time.monotonic() + 2)
    with pytest.raises(LabError, match="context_budget_exceeded"):
        adapter.generate(
            "A",
            [ChatMessage("user", "x" * 2000)],
            GenerationParameters(),
            time.monotonic() + 2,
        )
    with pytest.raises(LabError, match="runtime_redirect_rejected"):
        NoRedirect().redirect_request(
            None, None, 302, "redirect", {}, "http://elsewhere/"
        )


def test_ollama_wire_is_fixed_local_and_bounded():
    from types import SimpleNamespace

    adapter = OllamaAdapter(registry.OLLAMA_SPEC, Lease())
    seen = []

    def open_request(request, *, timeout):
        seen.append(
            (request.full_url, json.loads(request.data) if request.data else None)
        )
        return io.BytesIO(b'{"ok":true}')

    adapter._opener = SimpleNamespace(open=open_request)
    assert adapter._json("/api/show", {"model": "qwen3:4b"}, 1) == {"ok": True}
    assert seen == [("http://127.0.0.1:11434/api/show", {"model": "qwen3:4b"})]
    adapter._opener = SimpleNamespace(
        open=lambda *args, **kw: io.BytesIO(b"x" * 262145)
    )
    with pytest.raises(LabError, match="runtime_response_too_large"):
        adapter._json("/api/show", None, 1)


def test_ollama_broken_wire_and_metadata_are_sanitized():
    adapter, _, _ = configured_ollama()
    adapter.load(time.monotonic() + 3)
    adapter._open = lambda *args: io.BytesIO(b"private broken message\n")
    with pytest.raises(LabError, match="runtime_transport_failed"):
        adapter.generate(
            "A",
            [ChatMessage("user", "hello")],
            GenerationParameters(),
            time.monotonic() + 3,
        )
    assert not adapter.is_quiescent()

    def fail(*args):
        raise ValueError("private runtime configuration")

    adapter._json = fail
    with pytest.raises(LabError, match="runtime_unavailable"):
        adapter.load(time.monotonic() + 3)


def test_ollama_close_refuses_unconfirmed_model_unload(monkeypatch):
    from venom_module_cooperation_lab.adapters import ollama

    adapter, _, values = configured_ollama()
    adapter._request_sent = True
    values["/api/ps"] = {"models": [{"name": "qwen3:4b"}]}
    ticks = iter((0, 0, 3))
    monkeypatch.setattr(ollama.time, "monotonic", lambda: next(ticks))
    with pytest.raises(LabError, match="runtime_not_quiescent"):
        adapter.close()
    assert not adapter.is_quiescent()


def test_rwkv_29_identity_and_factory():
    spec = registry.get_model_spec("rwkv7-g1k-2.9b")
    adapter = registry.create_adapter(spec.model_id, Lease())
    assert isinstance(adapter, RecurrentAdapter)
    assert adapter._process.config.model_sha256 == spec.digest
    assert adapter._process.config.model_path.name == spec.artifact
    assert spec.digest != registry.RWKV_SPEC.digest
    assert spec.tokenizer_hash == registry.RWKV_SPEC.tokenizer_hash


@pytest.mark.parametrize(
    "reason,prefix", [("eos", "\n\n"), ("stop_sequence", ""), ("length", "\n\n")]
)
def test_recurrent_append_preserves_exact_round_boundary(reason, prefix):
    adapter = RecurrentAdapter(
        registry.RWKV_SPEC, Lease(), Path("/unused"), Path("/unused")
    )
    process = adapter._process = Process()
    process.reason = reason
    first = [ChatMessage("user", "start")]
    adapter.generate("A", first, GenerationParameters(), time.monotonic() + 5)
    adapter.generate(
        "A",
        [*first, ChatMessage("assistant", "answer"), ChatMessage("user", "next")],
        GenerationParameters(),
        time.monotonic() + 5,
    )
    assert process.calls[-1][1] == prefix + "User: next\n\nAssistant:"
    adapter.reset("A")
    assert adapter._round_ended["A"] is False


@pytest.mark.parametrize("parameters", [GenerationParameters, RwkvParameters])
def test_unknown_generation_profile_is_rejected(parameters):
    with pytest.raises((LabError, RwkvError), match="invalid_parameters"):
        parameters(profile="unknown")
