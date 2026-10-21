"""CPU-only worker protocol tests. No checkpoint or GPU is used here."""

from __future__ import annotations

import json
import sys
import threading
import types

import pytest
from adapters_fixtures import MiniTorch

from venom_module_cooperation_lab.adapters import rwkv_worker as worker
from venom_module_cooperation_lab.adapters.rwkv_tokenizer import SafeRwkvTokenizer

torch = MiniTorch()


class Connection:
    def __init__(self, commands=()):
        self.commands = list(commands)
        self.replies = []
        self.closed = False

    def recv_bytes(self, maximum):
        if not self.commands:
            raise EOFError
        return json.dumps(self.commands.pop(0)).encode()

    def send_bytes(self, data):
        self.replies.append(json.loads(data))

    def close(self):
        self.closed = True


class Model:
    def __init__(self, **kwargs):
        self.z = {"head.weight": torch.zeros(8, 8)}
        self.invalid = False
        self.stop = False

    def forward(self, tokens, state):
        state = [torch.zeros(2)] if state is None else state
        state[0] = state[0] + len(tokens)
        logits = torch.zeros(4)
        logits[3 if self.stop else 2] = 100
        if self.invalid:
            logits[0] = float("nan")
        return logits, state


@pytest.fixture
def tokenizer(tmp_path):
    path = tmp_path / "rwkv" / "rwkv_vocab_v20230424.txt"
    path.parent.mkdir()
    path.write_text("1 b'a' 1\n2 b'b' 1\n3 b'\\n\\n' 2\n")
    return SafeRwkvTokenizer(path)


def command(**params):
    return {
        "participant": "A",
        "prompt": "a",
        "parameters": {
            "seed": 1,
            "max_new_tokens": 2,
            "max_context_tokens": 16,
            "temperature": 0,
            "top_p": 0,
            **params,
        },
        "timeout_s": 5,
    }


def states():
    return {participant: {"tokens": 0, "tensors": None} for participant in ("A", "B")}


def test_worker_generation_and_state_isolation(tokenizer):
    private = states()
    result = worker._generate(
        Model(), tokenizer, private, threading.Event(), command(), torch, False
    )
    assert result["text"] == "bb" and result["output_tokens"] == 2
    snapshot = worker._state_snapshot(private)
    assert snapshot["participants"]["A"]["tensor_count"] == 1
    assert snapshot["participants"]["B"]["tensor_count"] == 0
    assert not snapshot["shared_state_storage"]
    worker._generate(
        Model(), tokenizer, private, threading.Event(), command(), torch, False
    )
    assert private["A"]["tokens"] == 6


def test_worker_cancel_budget_deadline_nonfinite_and_eos(tokenizer):
    private = states()
    event = threading.Event()
    event.set()
    assert (
        worker._generate(Model(), tokenizer, private, event, command(), torch, False)[
            "stop_reason"
        ]
        == "cancelled"
    )
    assert (
        worker._generate(
            Model(),
            tokenizer,
            private,
            threading.Event(),
            command(max_context_tokens=1),
            torch,
            False,
        )["error"]
        == "context_budget_exceeded"
    )
    expired = command()
    expired["timeout_s"] = 0
    assert (
        worker._generate(
            Model(), tokenizer, private, threading.Event(), expired, torch, False
        )["stop_reason"]
        == "deadline"
    )
    model = Model()
    model.invalid = True
    assert (
        worker._generate(
            model, tokenizer, private, threading.Event(), command(), torch, False
        )["error"]
        == "nonfinite_logits"
    )

    class Eos(Model):
        def forward(self, tokens, state):
            output, state = super().forward(tokens, state)
            output.zero_()
            output[0] = 100
            return output, state

    assert (
        worker._generate(
            Eos(), tokenizer, private, threading.Event(), command(), torch, False
        )["stop_reason"]
        == "eos"
    )


def test_worker_sampling_stop_and_sync(tokenizer, monkeypatch):
    monkeypatch.setattr(torch.cuda, "synchronize", lambda: None)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda: 123)
    model = Model()
    model.stop = True
    result = worker._generate(
        model,
        tokenizer,
        states(),
        threading.Event(),
        command(temperature=1, top_p=0.9),
        torch,
        True,
    )
    assert result["stop_reason"] == "stop_sequence" and result["peak_vram_bytes"] == 123


def install_fake_model(monkeypatch):
    module = types.ModuleType("rwkv.model")
    module.RWKV = Model
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "rwkv", types.ModuleType("rwkv"))
    monkeypatch.setitem(sys.modules, "rwkv.model", module)
    monkeypatch.setattr(sys, "path", list(sys.path))


def test_worker_loop_load_reset_state_generation_and_close(
    tokenizer, tmp_path, monkeypatch
):
    install_fake_model(monkeypatch)
    connection = Connection(
        [
            {"command": "generate", "request_id": 1, **command()},
            {"command": "state", "request_id": 2},
            {"command": "reset", "participant": "A", "request_id": 3},
            {"command": "reset", "request_id": 4},
            {"command": "unknown", "request_id": 5},
            {"command": "close"},
        ]
    )
    worker._run_worker(
        connection,
        threading.Event(),
        {
            "strategy": "cpu fp32",
            "model_path": "/unused.pth",
            "runtime_root": str(tmp_path),
        },
    )
    assert connection.replies[0]["state"] == "ready"
    assert connection.replies[1]["text"] == "bb"
    assert connection.replies[2]["participants"]["A"]["tokens"] == 3
    assert connection.replies[-1]["error"] == "unsupported_command"


def test_worker_loop_cuda_unavailable_and_eof(tokenizer, tmp_path, monkeypatch):
    install_fake_model(monkeypatch)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    connection = Connection()
    worker._run_worker(
        connection,
        threading.Event(),
        {
            "strategy": "cuda fp16",
            "model_path": "/unused.pth",
            "runtime_root": str(tmp_path),
        },
    )
    assert connection.replies == [{"error": "cuda_unavailable"}]
    connection = Connection()
    worker._run_worker(
        connection,
        threading.Event(),
        {
            "strategy": "cpu fp32",
            "model_path": "/unused.pth",
            "runtime_root": str(tmp_path),
        },
    )
    assert connection.replies[0]["state"] == "ready"


def test_worker_loop_error_is_sanitized(tokenizer, tmp_path, monkeypatch):
    install_fake_model(monkeypatch)

    class OutOfMemoryError(Exception):
        pass

    def fail(*args):
        raise OutOfMemoryError("private path and prompt")

    monkeypatch.setattr(worker, "_generate", fail)
    connection = Connection([{"command": "generate", "request_id": 1}])
    worker._run_worker(
        connection,
        threading.Event(),
        {
            "strategy": "cpu fp32",
            "model_path": "/unused.pth",
            "runtime_root": str(tmp_path),
        },
    )
    assert connection.replies[-1] == {"error": "out_of_memory", "request_id": 1}


def test_parent_death_guard_and_initialization_error(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(worker.sys, "platform", "other")
    worker.worker_main(connection, threading.Event(), {}, 5)
    assert connection.replies == [{"error": "unsupported_parent_lifecycle"}]
    monkeypatch.setattr(worker.sys, "platform", "linux")
    monkeypatch.setattr(
        worker.ctypes, "CDLL", lambda name: types.SimpleNamespace(prctl=lambda *args: 0)
    )
    monkeypatch.setattr(worker.os, "getppid", lambda: 5)

    def fail(*args):
        raise RuntimeError("private path")

    monkeypatch.setattr(worker, "_run_worker", fail)
    connection = Connection()
    worker.worker_main(connection, threading.Event(), {}, 5)
    assert connection.replies == [{"error": "worker_initialization_failed"}]
    assert connection.closed
    connection = Connection()
    worker.worker_main(connection, threading.Event(), {}, 6)
    assert not connection.replies
