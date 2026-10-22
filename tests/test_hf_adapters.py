from __future__ import annotations

import hashlib
import json
import threading
import time
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from adapters_fixtures import MiniTorch, Tensor
from test_adapters import Lease, Process

from venom_module_cooperation_lab.adapters import hf
from venom_module_cooperation_lab.adapters import hf_worker as worker
from venom_module_cooperation_lab.adapters.base import ChatMessage, GenerationParameters
from venom_module_cooperation_lab.adapters.registry import create_adapter
from venom_module_cooperation_lab.adapters.rwkv_process import RwkvError
from venom_module_cooperation_lab.errors import LabError


def test_pins_and_factory_are_fixed():
    specs = hf.pinned_specs()
    assert {s.model_id for s in specs} == {"hrm-text-1b", "huginn-0125"}
    for spec in specs:
        assert len(spec.digest) == 64
        adapter = create_adapter(spec.model_id, Lease())
        assert adapter.spec == spec
        assert adapter._process.config.root.is_absolute()


def test_manifest_validation_all_paths(tmp_path, monkeypatch):
    p = tmp_path / "weight"
    p.write_bytes(b"abc")
    pins = {
        "fixture": {
            "files": {
                "weight": {"bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
            }
        }
    }
    monkeypatch.setattr(hf, "PINS", pins)
    config = hf.HfConfig("fixture", tmp_path)
    config.validate()
    assert config.payload()["root"] == str(tmp_path)
    pins["fixture"]["files"]["weight"] = {
        "bytes": 3,
        "git_sha1": hashlib.sha1(b"blob 3\0abc", usedforsecurity=False).hexdigest(),
    }
    config.validate()
    p.write_bytes(b"bad")
    with pytest.raises(RwkvError, match="artifact_hash_mismatch"):
        config.validate()
    p.write_bytes(b"ab")
    with pytest.raises(RwkvError, match="artifact_hash_mismatch"):
        config.validate()
    p.unlink()
    with pytest.raises(RwkvError, match="artifact_missing"):
        config.validate()
    with pytest.raises(RwkvError, match="invalid_model_configuration"):
        hf.HfConfig("unknown", Path("relative")).validate()


def test_hf_adapter_lease_and_replay(monkeypatch):
    adapter = hf.HfAdapter(hf.pinned_specs()[0], Lease())
    process = adapter._process = Process()

    def generate(participant, prompt, parameters, timeout):
        process.calls.append((participant, json.loads(prompt)))
        return {
            "text": "answer",
            "raw_text": " answer",
            "input_tokens": 4,
            "output_tokens": 1,
            "ttft_s": 0.1,
            "generation_s": 0.2,
            "stop_reason": "eos",
            "effective_parameters": {"context_mode": "replay"},
            "quiescent": True,
        }

    monkeypatch.setattr(process, "generate", generate)
    result = adapter.generate(
        "A",
        [ChatMessage("user", "question")],
        GenerationParameters(),
        time.monotonic() + 5,
    )
    assert result.raw_text == " answer" and result.text == "answer"
    assert adapter.state()["history_messages"] == {"A": 2, "B": 0}

    def fail(*args):
        raise RwkvError("generation_timeout")

    monkeypatch.setattr(process, "generate", fail)
    with pytest.raises(LabError, match="generation_timeout"):
        adapter.generate(
            "B",
            [ChatMessage("user", "q")],
            GenerationParameters(),
            time.monotonic() + 5,
        )


class Torch(MiniTorch):
    long = "long"
    bfloat16 = "bf16"

    def tensor(self, values, **kwargs):
        return values

    def ones_like(self, values):
        return "prefix"

    def zeros_like(self, values):
        return "causal"

    def inference_mode(self):
        return nullcontext()


class Tokenizer:
    eos_token_id = 0

    def encode(self, text, **kwargs):
        return {"A1": [1, 2], "B2": [3, 2]}.get(text, [4, 4])

    def decode(self, tokens, **kwargs):
        return "".join({1: "A", 2: "1", 3: "B"}.get(t, "?") for t in tokens)

    def apply_chat_template(self, messages, **kwargs):
        return "native"


class Model:
    def __init__(self, eos=False, bad=False):
        self.calls = []
        self.eos = eos
        self.bad = bad

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        tensor = Tensor([0, 10, 9, 8, 0])
        if self.eos:
            tensor = Tensor([100, 0, 0, 0, 0])
        if self.bad:
            tensor = Tensor([float("nan")] * 5)

        class Logits:
            def __getitem__(self, key):
                return tensor

        return SimpleNamespace(logits=Logits(), past_key_values="cache")


def command(**kw):
    return {
        "prompt": json.dumps([{"role": "user", "content": "question"}]),
        "parameters": {
            **asdict(GenerationParameters(max_new_tokens=2, temperature=0)),
            **kw,
        },
        "timeout_s": 5,
    }


@pytest.mark.parametrize("mid", ["hrm-text-1b", "huginn-0125"])
def test_native_prompt_and_generation(mid):
    model = Model()
    tokenizer = Tokenizer()
    torch = Torch()
    r = worker.generate(
        model, tokenizer, torch, {"model_id": mid}, command(), threading.Event()
    )
    assert (
        r["text"] == "AA" and r["output_tokens"] == 2 and r["stop_reason"] == "length"
    )
    assert r["effective_parameters"]["context_mode"] == "replay"
    if mid == "hrm-text-1b":
        assert model.calls[0]["token_type_ids"] == "prefix"
        assert model.calls[1]["token_type_ids"] == "causal"
        assert model.calls[1]["past_key_values"] == "cache"
        assert (
            "synth"
            not in worker.prompt_text(
                mid, [{"role": "user", "content": "q"}], tokenizer, True
            )[0]
        )
        assert worker.prompt_text(mid, [], tokenizer, False)[1] == "synth,cot"
    else:
        assert model.calls[0]["num_steps"] == 8 and not model.calls[0]["use_cache"]
        assert worker.prompt_text(mid, [], tokenizer, False) == (
            "native",
            "native_chat",
        )


def test_constraints_eos_cancellation_and_context():
    t = Tokenizer()
    torch = Torch()
    cfg = {"model_id": "hrm-text-1b"}
    r = worker.generate(
        Model(), t, torch, cfg, command(allowed_outputs=("B2",)), threading.Event()
    )
    assert r["text"] == "B1" and r["stop_reason"] == "allowed_output"
    assert (
        worker.generate(Model(eos=True), t, torch, cfg, command(), threading.Event())[
            "stop_reason"
        ]
        == "eos"
    )
    event = threading.Event()
    event.set()
    assert (
        worker.generate(Model(), t, torch, cfg, command(), event)["stop_reason"]
        == "cancelled"
    )
    with pytest.raises(RuntimeError, match="context_budget_exceeded"):
        worker.generate(
            Model(), t, torch, cfg, command(max_context_tokens=1), threading.Event()
        )
    with pytest.raises(RuntimeError, match="nonfinite_logits"):
        worker.generate(Model(bad=True), t, torch, cfg, command(), threading.Event())


@pytest.mark.parametrize(
    "code",
    [
        "cuda_unavailable",
        "context_budget_exceeded",
        "unsupported_command",
        "insufficient_gpu_memory",
    ],
)
def test_error_codes(code):
    assert worker.error_code(RuntimeError(code)) == code


def test_unknown_error_is_sanitized():
    assert worker.error_code(ValueError("private path")) == "hf_worker_failed"

    class OutOfMemoryError(Exception):
        pass

    assert worker.error_code(OutOfMemoryError()) == "out_of_memory"


def test_huginn_loader_adapts_only_pinned_class(monkeypatch):
    calls = []

    class Factory:
        _tied_weights_keys = ["lm_head.weight"]

        @classmethod
        def from_pretrained(cls, root, **kwargs):
            calls.append((root, kwargs, cls._tied_weights_keys))
            return SimpleNamespace(
                to=lambda device: SimpleNamespace(eval=lambda: "model")
            )

    torch = SimpleNamespace(
        __version__="2.13.0+cu130",
        bfloat16="bf16",
        cuda=SimpleNamespace(
            is_available=lambda: True,
            mem_get_info=lambda: (12 * 1024**3, 0),
            reset_peak_memory_stats=lambda: None,
            synchronize=lambda: None,
        ),
    )
    transformers = SimpleNamespace(
        __version__="5.17.0",
        AutoModelForCausalLM=None,
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **k: "tokenizer"),
    )
    dynamic = SimpleNamespace(get_class_from_dynamic_module=lambda *a, **k: Factory)
    monkeypatch.setattr(
        worker.importlib,
        "import_module",
        lambda name: {
            "torch": torch,
            "transformers": transformers,
            "transformers.dynamic_module_utils": dynamic,
        }[name],
    )
    assert worker.load_models({"model_id": "huginn-0125", "root": "/pinned"})[:2] == (
        "model",
        "tokenizer",
    )
    assert calls[0][2] == {"lm_head.weight": "transformer.wte.weight"}
    assert calls[0][1]["local_files_only"] is True


def test_hrm_game_prompt_uses_actual_observation_without_foreign_examples():
    messages = [
        {
            "role": "user",
            "content": (
                '{"instruction":"Reply cards=I,J","observation":{"last_reveal":[]}}'
            ),
        }
    ]
    text, condition = worker.prompt_text(
        "hrm-text-1b", messages, Tokenizer(), True, "game-eval-v2"
    )
    assert condition == "direct-game-v2"
    assert messages[0]["content"] in text
    assert "Paris" not in text and "2 + 2" not in text and "Examples" not in text
    legacy, condition = worker.prompt_text("hrm-text-1b", messages, Tokenizer(), True)
    assert condition == "direct" and "Paris" in legacy
